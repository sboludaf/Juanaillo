#include "pulse.h"
#include <string.h>

static void be16(uint8_t *p, uint16_t x) { p[0]=(uint8_t)(x>>8); p[1]=(uint8_t)x; }
static void be32(uint8_t *p, uint32_t x) { for(unsigned i=0;i<4;i++) p[i]=(uint8_t)(x>>(24-8*i)); }
static void be64(uint8_t *p, uint64_t x) { for(unsigned i=0;i<8;i++) p[i]=(uint8_t)(x>>(56-8*i)); }
static uint64_t read64(const uint8_t *p) { uint64_t x=0; for(unsigned i=0;i<8;i++) x=(x<<8)|p[i]; return x; }

void pulse_init(Pulse *p, uint64_t nonce, uint32_t now)
{
    memset(p,0,sizeof(*p)); p->nonce=nonce; p->quiet_since_ms=now;
    if(!nonce) { p->state=P_FAULT; p->reason=R_RNG; }
}
uint8_t pulse_observe(Pulse *p,const uint16_t counts[4],uint32_t now)
{
    bool moved=false,other_moved=false;
    for(unsigned i=0;i<4;i++) {
        if(counts[i]!=p->counters[i]) {
            p->quiet_since_ms=now; moved=true;
            if(!(PULSE_CHANNEL_MASK&(1u<<i))) other_moved=true;
        }
        p->counters[i]=counts[i];
    }
    if((moved && p->state==P_READY) ||
       (other_moved && (p->state==P_WAKE || p->state==P_RUNNING)))
        return pulse_fault(p,R_MOVING);
    return E_NONE;
}
uint8_t pulse_fault(Pulse *p,uint8_t reason)
{
    if(p->state!=P_FAULT) p->reason=reason;
    p->state=P_FAULT; return E_OFF;
}
uint8_t pulse_tick(Pulse *p,uint32_t now,bool hardware_finished)
{
    if(p->used && (uint32_t)(now-p->frame_ms)>=30u) {
        p->used=0; p->length=0; return pulse_fault(p,R_FRAME);
    }
    if(p->state==P_READY && ((uint32_t)(now-p->prepared_ms)>=PULSE_PREPARE_LIMIT_MS ||
                            (uint32_t)(now-p->heartbeat_ms)>=PULSE_LEASE_MS))
        return pulse_fault(p,R_LEASE);
    if(p->state==P_WAKE || p->state==P_RUNNING) {
        if((uint32_t)(now-p->heartbeat_ms)>=PULSE_LEASE_MS) return pulse_fault(p,R_LEASE);
        if((uint32_t)(now-p->fire_ms)>=PULSE_ENVELOPE_MS ||
           (p->state==P_RUNNING && hardware_finished)) {
            p->state=P_DONE; p->reason=R_FINISHED; return E_OFF;
        }
        /* Cuatro ticks desde un FIRE entre ticks equivalen a 3..4 ms reales.
           El hardware comprueba además el tiempo DWT antes de activar CEN. */
        if(p->state==P_WAKE && (uint32_t)(now-p->fire_ms)>=4u) {
            if((uint32_t)(now-p->fire_ms)>4u) return pulse_fault(p,R_LATE);
            p->state=P_RUNNING; return E_PWM;
        }
    }
    return E_NONE;
}
static uint8_t stop(Pulse *p,uint32_t now)
{
    p->stop_seen=true; p->stop_ms=now;
    if(p->state!=P_FAULT) { p->state=p->consumed?P_DONE:P_IDLE; p->reason=R_STOP; }
    return E_OFF|E_REPLY;
}
static uint8_t command(Pulse *p,uint8_t id,const uint8_t *data,size_t size,uint32_t now)
{
    p->reply_id=id;
    uint8_t expired=pulse_tick(p,now,false);
    if(id==0x70 && size==0) return expired|E_REPLY;
    if(id==0x76 && size==0) return expired|E_REPLY|E_CAPS;
    if(id==0x63 && size==0) return expired|E_REPLY|E_ENCODERS;
    if((id==0x74 || id==0x62) && size==0) return stop(p,now);
    if(id==0x50 && size==6 && !memcmp(data,"\0\0\0\0\0\0",6)) return stop(p,now);
    if((id!=0x71 && id!=0x73 && id!=0x75) || size!=8)
        return pulse_fault(p,R_FRAME)|E_REPLY;
    if(read64(data)!=p->nonce || !p->nonce) return pulse_fault(p,R_NONCE)|E_REPLY;
    if(p->state==P_FAULT) return expired|E_REPLY;
    /* HB válido mantiene el lease durante el único disparo ya consumido.
       pulse_tick se ejecuta ANTES: un lease caducado jamás se resucita. */
    if(id==0x75) {
        if(p->state==P_READY || p->state==P_WAKE || p->state==P_RUNNING) {
            p->heartbeat_ms=now; return E_REPLY;
        }
        if(p->consumed) return expired|E_REPLY;
        return pulse_fault(p,R_SEQUENCE)|E_REPLY;
    }
    if(p->consumed) return expired|E_REPLY;
    if(id==0x71) {
        if(p->state==P_READY) return E_REPLY; /* Duplicado no renueva ningún plazo. */
        if(p->state!=P_IDLE || !p->stop_seen || (uint32_t)(now-p->stop_ms)>500u)
            return pulse_fault(p,R_SEQUENCE)|E_REPLY;
        if((uint32_t)(now-p->quiet_since_ms)<PULSE_QUIET_MS)
            return pulse_fault(p,R_MOVING)|E_REPLY;
        p->state=P_READY; p->reason=R_PREPARED;
        p->prepared_ms=now; p->heartbeat_ms=now; return E_REPLY;
    }
    if(p->state!=P_READY) return pulse_fault(p,R_SEQUENCE)|E_REPLY;
    if((uint32_t)(now-p->quiet_since_ms)<PULSE_QUIET_MS)
        return pulse_fault(p,R_MOVING)|E_REPLY;
    /* El disparo se consume ANTES de cualquier GPIO. Nunca se limpia sin reset. */
    p->consumed=true; p->fire_ms=now; p->heartbeat_ms=now;
    p->state=P_WAKE; p->reason=R_FIRED; return E_WAKE|E_REPLY;
}
uint8_t pulse_feed(Pulse *p,uint8_t byte,uint32_t now)
{
    uint8_t event=pulse_tick(p,now,false);
    if(p->used==0) {
        if(byte!=0xAA) return event|pulse_fault(p,R_FRAME);
        p->frame_ms=now; p->frame[p->used++]=byte; return event;
    }
    if(p->used==1 && byte!=0x55) { p->used=0; return event|pulse_fault(p,R_FRAME); }
    if(p->used>=sizeof(p->frame)) { p->used=0; return event|pulse_fault(p,R_FRAME); }
    p->frame[p->used++]=byte;
    if(p->used==3) {
        p->length=byte;
        if(byte<5 || byte>sizeof(p->frame)) { p->used=0; return event|pulse_fault(p,R_FRAME); }
    }
    if(p->used>=3 && p->used==p->length) {
        uint8_t checksum=0;
        for(unsigned i=0;i<p->length-1u;i++) checksum=(uint8_t)(checksum+p->frame[i]);
        uint8_t length=p->length; p->used=0; p->length=0;
        if(checksum!=byte) return event|pulse_fault(p,R_FRAME);
        return event|command(p,p->frame[3],p->frame+4,length-5u,now);
    }
    return event;
}
void pulse_status(const Pulse *p,uint32_t now,bool all_low,uint8_t out[36])
{
    out[0]=1; out[1]=PULSE_PROFILE; out[2]=p->state;
    out[3]=(uint8_t)(1u|(p->consumed?2u:0u)|
        ((p->state==P_WAKE || p->state==P_RUNNING)?4u:0u)|(all_low?8u:0u));
    be32(out+4,now);
    uint32_t age=now-p->heartbeat_ms;
    be32(out+8,(p->state==P_READY || p->state==P_WAKE || p->state==P_RUNNING) && age<PULSE_LEASE_MS?PULSE_LEASE_MS-age:0);
    be64(out+12,p->nonce);
    for(unsigned i=0;i<4;i++) be16(out+20+2*i,p->counters[i]);
    be32(out+28,p->consumed?1u:0u); be32(out+32,p->reason);
}
void pulse_caps(uint8_t out[48])
{
    out[0]=1; out[1]=PULSE_PROFILE; out[2]=PULSE_CHANNEL_MASK; out[3]=PULSE_REVERSED_MASK;
    be16(out+4,PULSE_DUTY_PERMILLE); be16(out+6,PULSE_PWM_HZ);
    be16(out+8,PULSE_WAKE_MIN_MS); be16(out+10,PULSE_PWM_MS);
    be32(out+12,PULSE_ENVELOPE_MS*1000u); be32(out+16,PULSE_LEASE_MS);
    memcpy(out+20,PULSE_MARKER,28);
}
size_t pulse_packet(uint8_t id,const uint8_t *payload,size_t length,uint8_t out[64])
{
    if(length>59) return 0;
    out[0]=0xAA;out[1]=0x55;out[2]=(uint8_t)(length+5);out[3]=id;
    if(length)memcpy(out+4,payload,length);
    uint8_t sum=0; for(size_t i=0;i<length+4;i++)sum=(uint8_t)(sum+out[i]);
    out[length+4]=sum; return length+5;
}
