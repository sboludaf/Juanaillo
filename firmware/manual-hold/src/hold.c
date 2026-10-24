#include "hold.h"
#include <string.h>

static void be16(uint8_t *p,uint16_t value) { p[0]=(uint8_t)(value>>8);p[1]=(uint8_t)value; }
static void be32(uint8_t *p,uint32_t value) { for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(value>>(24u-8u*i)); }
static void be64(uint8_t *p,uint64_t value) { for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(value>>(56u-8u*i)); }
static uint64_t read64(const uint8_t *p) { uint64_t value=0;for(unsigned i=0;i<8;i++)value=(value<<8)|p[i];return value; }
static bool active(const Hold *p) { return p->state==H_WAKE || p->state==H_RUNNING; }
bool hold_reverse_channel(int8_t direction,unsigned channel)
{
    if(channel>=4)return false;
    return (direction<0)!=((HOLD_REVERSED_MASK&(1u<<channel))!=0);
}

void hold_init(Hold *p,uint64_t nonce,uint32_t now)
{
    memset(p,0,sizeof(*p));p->nonce=nonce;p->heartbeat_ms=now;
    if(!nonce) { p->state=H_FAULT;p->reason=R_RNG; }
}
void hold_observe(Hold *p,const uint16_t counts[4])
{
    memcpy(p->counters,counts,sizeof(p->counters));
}
uint8_t hold_fault(Hold *p,uint8_t reason)
{
    if(p->state!=H_FAULT)p->reason=reason;
    p->state=H_FAULT;p->direction=0;return E_OFF;
}
uint8_t hold_tick(Hold *p,uint32_t now,bool burst_finished)
{
    if(p->used && (uint32_t)(now-p->frame_ms)>=30u) {
        p->used=0;p->length=0;return hold_fault(p,R_FRAME);
    }
    if(active(p)) {
        if((uint32_t)(now-p->heartbeat_ms)>=HOLD_LEASE_MS)return hold_fault(p,R_LEASE);
        if((uint32_t)(now-p->burst_ms)>=HOLD_BURST_MS || burst_finished) {
            p->state=H_LIMIT;p->reason=R_LIMIT;p->direction=0;return E_OFF;
        }
        /* Five integer ticks after a between-ticks request mean 4..5 ms real.
           The hardware also checks the DWT elapsed time before starting PWM. */
        if(p->state==H_WAKE && (uint32_t)(now-p->wake_ms)>=HOLD_WAKE_MS+1u) {
            if((uint32_t)(now-p->wake_ms)>HOLD_WAKE_MS+1u)return hold_fault(p,R_LATE);
            p->state=H_RUNNING;return E_PWM;
        }
    }
    return E_NONE;
}
static uint8_t stop(Hold *p)
{
    if(p->state!=H_FAULT) { p->state=H_IDLE;p->reason=R_STOP;p->direction=0; }
    return E_OFF|E_REPLY;
}
static uint8_t command(Hold *p,uint8_t id,const uint8_t *data,size_t size,uint32_t now)
{
    p->reply_id=id;
    uint8_t event=hold_tick(p,now,false);
    if(id==0x70 && size==0)return event|E_REPLY;
    if(id==0x76 && size==0)return event|E_REPLY|E_CAPS;
    if(id==0x63 && size==0)return event|E_REPLY|E_ENCODERS;
    if((id==0x74 || id==0x62) && size==0)return stop(p);
    if(id==0x50 && size==6 && !memcmp(data,"\0\0\0\0\0\0",6))return stop(p);
    if(id!=0x77 || size!=9)return hold_fault(p,R_FRAME)|E_REPLY;
    if(read64(data)!=p->nonce || !p->nonce)return hold_fault(p,R_NONCE)|E_REPLY;
    if(data[8]!=1u && data[8]!=255u)return hold_fault(p,R_DIRECTION)|E_REPLY;
    if(p->state==H_FAULT || p->state==H_LIMIT)return event|E_REPLY;
    int8_t direction=data[8]==1u?1:-1;
    p->heartbeat_ms=now;
    if(p->state==H_IDLE) {
        p->burst_ms=now;p->burst_count++;
    } else if(p->direction==direction) {
        return event|E_REPLY; /* Refresh lease; never extend wake/burst. */
    }
    p->direction=direction;p->state=H_WAKE;p->reason=R_MOVE;p->wake_ms=now;
    return E_WAKE|E_REPLY; /* The hardware first stops all bridges, then wakes11. */
}
uint8_t hold_feed(Hold *p,uint8_t byte,uint32_t now)
{
    uint8_t event=hold_tick(p,now,false);
    if(p->used==0) {
        if(byte!=0xAA)return event|hold_fault(p,R_FRAME);
        p->frame_ms=now;p->frame[p->used++]=byte;return event;
    }
    if(p->used==1 && byte!=0x55) { p->used=0;return event|hold_fault(p,R_FRAME); }
    if(p->used>=sizeof(p->frame)) { p->used=0;return event|hold_fault(p,R_FRAME); }
    p->frame[p->used++]=byte;
    if(p->used==3) {
        p->length=byte;
        if(byte<5 || byte>sizeof(p->frame)) { p->used=0;return event|hold_fault(p,R_FRAME); }
    }
    if(p->used>=3 && p->used==p->length) {
        uint8_t sum=0;
        for(unsigned i=0;i<p->length-1u;i++)sum=(uint8_t)(sum+p->frame[i]);
        uint8_t length=p->length;p->used=0;p->length=0;
        if(sum!=byte)return event|hold_fault(p,R_FRAME);
        uint8_t next=command(p,p->frame[3],p->frame+4,length-5u,now);
        /* A reversal at the previous wake deadline must start a NEW wake;
           never also apply the old direction's delayed E_PWM event. */
        if(next&E_WAKE)event=(uint8_t)(event&~E_PWM);
        return event|next;
    }
    return event;
}
void hold_status(const Hold *p,uint32_t now,bool all_low,uint8_t out[44])
{
    bool running=active(p);
    out[0]=1;out[1]=HOLD_PROFILE;out[2]=p->state;
    out[3]=(uint8_t)(1u|(running?6u:0u)|(all_low?8u:0u));
    be32(out+4,now);
    uint32_t age=now-p->heartbeat_ms;
    be32(out+8,running && age<HOLD_LEASE_MS?HOLD_LEASE_MS-age:0);
    be64(out+12,p->nonce);
    for(unsigned i=0;i<4;i++)be16(out+20+2u*i,p->counters[i]);
    be32(out+28,p->burst_count);be32(out+32,p->reason);
    be32(out+36,(uint32_t)(int32_t)p->direction);
    age=now-p->burst_ms;
    be32(out+40,running && age<HOLD_BURST_MS?HOLD_BURST_MS-age:0);
}
void hold_caps(uint8_t out[48])
{
    out[0]=1;out[1]=HOLD_PROFILE;out[2]=HOLD_CHANNEL_MASK;out[3]=HOLD_REVERSED_MASK;
    be16(out+4,HOLD_DUTY_PERMILLE);be16(out+6,HOLD_PWM_HZ);
    be16(out+8,HOLD_WAKE_MS);be16(out+10,HOLD_BURST_MS);
    be32(out+12,HOLD_BURST_MS*1000u);be32(out+16,HOLD_LEASE_MS);
    memcpy(out+20,HOLD_MARKER,28);
}
size_t hold_packet(uint8_t id,const uint8_t *payload,size_t size,uint8_t out[64])
{
    if(size>59)return 0;
    out[0]=0xAA;out[1]=0x55;out[2]=(uint8_t)(size+5);out[3]=id;
    if(size)memcpy(out+4,payload,size);
    uint8_t sum=0;for(size_t i=0;i<size+4;i++)sum=(uint8_t)(sum+out[i]);
    out[size+4]=sum;return size+5;
}
