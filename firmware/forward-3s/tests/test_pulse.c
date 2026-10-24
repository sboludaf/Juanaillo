#include "pulse.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const uint64_t NONCE=UINT64_C(0x123456789abcdef0);
static uint8_t send(Pulse *p,uint8_t id,const uint8_t *data,size_t n,uint32_t now)
{
    uint8_t raw[64],event=0;size_t length=pulse_packet(id,data,n,raw);
    for(size_t i=0;i<length;i++)event|=pulse_feed(p,raw[i],now);
    return event;
}
static uint8_t token(Pulse *p,uint8_t id,uint32_t now)
{
    uint8_t data[8];for(unsigned i=0;i<8;i++)data[i]=(uint8_t)(p->nonce>>(56-8*i));
    return send(p,id,data,8,now);
}
static void ready(Pulse *p,uint32_t now)
{
    pulse_init(p,NONCE,now-1100);assert(send(p,0x74,0,0,now)&E_OFF);
    assert(token(p,0x71,now)&E_REPLY);assert(p->state==P_READY);
}
static void normal_and_duplicate(void)
{
    Pulse p;ready(&p,1100);assert(token(&p,0x73,1101)&E_WAKE);assert(p.consumed);
    assert(token(&p,0x73,1102)==E_REPLY);assert(p.state==P_WAKE);
    assert(pulse_tick(&p,1104,false)==E_NONE);
    assert(pulse_tick(&p,1105,false)==E_PWM);assert(p.state==P_RUNNING);
    for(uint32_t now=1120;now<=4080;now+=20) {
        assert(!(token(&p,0x75,now)&(E_WAKE|E_PWM)));
        assert(p.state==P_RUNNING&&p.consumed);
    }
    assert(pulse_tick(&p,4105,true)==E_OFF);assert(p.state==P_DONE);
    for(unsigned i=0;i<10;i++) {
        assert(!(token(&p,0x73,4106+i)&(E_WAKE|E_PWM)));
        assert(!(token(&p,0x71,4106+i)&(E_WAKE|E_PWM)));
    }
    send(&p,0x74,0,0,4120);assert(p.state==P_DONE && p.consumed);
}
static void time_bounds(void)
{
    Pulse p;ready(&p,1100);assert(pulse_tick(&p,1200,false)&E_OFF);assert(p.state==P_FAULT);
    ready(&p,1100);token(&p,0x75,1190);token(&p,0x75,1280);token(&p,0x75,1370);
    assert(pulse_tick(&p,1400,false)&E_OFF);assert(p.state==P_FAULT);
    ready(&p,1100);token(&p,0x73,1101);assert(pulse_tick(&p,1106,false)&E_OFF);assert(p.state==P_FAULT);
    ready(&p,1100);token(&p,0x73,1101);pulse_tick(&p,1105,false);
    for(uint32_t now=1120;now<=4080;now+=20)token(&p,0x75,now);
    assert(pulse_tick(&p,4106,false)&E_OFF);assert(p.state==P_DONE);
}
static void no_stop_no_motion(void)
{
    Pulse p;pulse_init(&p,NONCE,0);token(&p,0x71,1100);assert(p.state==P_FAULT && !p.consumed);
    ready(&p,1100);uint16_t values[4]={1,0,0,0};assert(pulse_observe(&p,values,1101)&E_OFF);
    assert(!(token(&p,0x73,1102)&E_WAKE));assert(!p.consumed);
    ready(&p,1100);token(&p,0x73,1101);values[1]=1;
    assert(pulse_observe(&p,values,1102)==E_NONE);assert(p.state==P_WAKE);
}
static void nonce_and_reset(void)
{
    Pulse p;ready(&p,1100);uint8_t wrong[8]={0};send(&p,0x73,wrong,8,1101);
    assert(p.state==P_FAULT&&!p.consumed);
    pulse_init(&p,NONCE+1,0);send(&p,0x74,0,0,1100);
    uint8_t old[8];for(unsigned i=0;i<8;i++)old[i]=(uint8_t)(NONCE>>(56-8*i));
    send(&p,0x71,old,8,1100);assert(p.state==P_FAULT&&!p.consumed);
    pulse_init(&p,0,0);assert(p.state==P_FAULT && p.reason==R_RNG);
}
static void malformed_and_stop(void)
{
    Pulse p;ready(&p,1100);token(&p,0x73,1101);
    assert(send(&p,0x74,0,0,1105)&E_OFF);assert(p.state==P_DONE);
    /* Tick y STOP coincidentes pueden combinar E_PWM|E_OFF; OFF debe dominar. */
    ready(&p,1100);token(&p,0x73,1101);
    uint8_t ev=send(&p,0x74,0,0,1105);assert(ev&E_OFF);assert(p.state==P_DONE);
    ready(&p,1100);token(&p,0x73,1101);assert(pulse_feed(&p,0xAA,1102)==0);
    assert(pulse_tick(&p,1132,false)&E_OFF);assert(p.state==P_FAULT);
    ready(&p,1100);uint8_t bad[]={0xAA,0x55,5,0x73,0};
    for(unsigned i=0;i<sizeof(bad);i++)pulse_feed(&p,bad[i],1101);
    assert(p.state==P_FAULT&&!p.consumed);
    ready(&p,1100);send(&p,0x61,(const uint8_t*)"ARM!",4,1101);assert(p.state==P_FAULT);
}
static void info_and_flags(void)
{
    Pulse p;ready(&p,1100);uint8_t status[36],caps[48];pulse_status(&p,1100,true,status);
    assert(status[0]==1&&status[1]==4&&status[2]==P_READY&&status[3]==9);
    pulse_caps(caps);assert(caps[0]==1&&caps[1]==4&&caps[2]==15&&caps[3]==10);
    assert(caps[4]==0&&caps[5]==100&&caps[8]==0&&caps[9]==3);
    assert(((unsigned)caps[10]<<8|caps[11])==3000u);
    assert(((uint32_t)caps[12]<<24|(uint32_t)caps[13]<<16|(uint32_t)caps[14]<<8|caps[15])==3005000u);
    assert(!memcmp(caps+20,PULSE_MARKER,28));
    token(&p,0x73,1101);pulse_status(&p,1101,false,status);assert(status[3]==7&&status[31]==1);
    send(&p,0x74,0,0,1102);pulse_status(&p,1102,true,status);assert(status[3]==11);
}
static void duplicate_prepare_and_expiry(void)
{
    Pulse p;ready(&p,1100);uint32_t prepared=p.prepared_ms,heartbeat=p.heartbeat_ms;
    token(&p,0x71,1199);assert(p.prepared_ms==prepared&&p.heartbeat_ms==heartbeat);
    token(&p,0x75,1200);assert(p.state==P_FAULT);assert(!(token(&p,0x73,1200)&E_WAKE));
    ready(&p,UINT32_MAX-50);token(&p,0x73,UINT32_MAX-49);
    pulse_tick(&p,UINT32_MAX-45,false);assert(p.state==P_RUNNING);
    uint32_t fire=UINT32_MAX-49;
    for(uint32_t age=20;age<3005;age+=20)token(&p,0x75,fire+age);
    assert(pulse_tick(&p,fire+3005,false)&E_OFF);assert(p.state==P_DONE);
}
static void all_encoders_selected(void)
{
    Pulse p;ready(&p,1100);token(&p,0x73,1101);pulse_tick(&p,1105,false);
    uint16_t values[4]={1,2,3,4};
    assert(pulse_observe(&p,values,1106)==E_NONE);assert(p.state==P_RUNNING);
    assert(send(&p,0x74,0,0,1107)&E_OFF);assert(p.state==P_DONE);
    assert(!(token(&p,0x73,1108)&(E_WAKE|E_PWM)));
}
static void active_heartbeat_and_stop(void)
{
    Pulse p;ready(&p,1100);token(&p,0x73,1101);pulse_tick(&p,1105,false);
    token(&p,0x75,1150);assert(p.state==P_RUNNING&&p.heartbeat_ms==1150);
    assert(pulse_tick(&p,1249,false)==E_NONE);
    assert(token(&p,0x75,1250)&E_OFF);assert(p.state==P_FAULT&&p.heartbeat_ms==1150);
    assert(!(token(&p,0x75,1251)&(E_WAKE|E_PWM)));assert(p.state==P_FAULT);
    ready(&p,1100);token(&p,0x73,1101);pulse_tick(&p,1105,false);
    token(&p,0x75,1120);send(&p,0x74,0,0,1121);assert(p.state==P_DONE);
    token(&p,0x75,1122);assert(p.state==P_DONE&&p.heartbeat_ms==1120);
    assert(!(token(&p,0x73,1123)&(E_WAKE|E_PWM)));
}
int main(void)
{
    normal_and_duplicate();time_bounds();no_stop_no_motion();nonce_and_reset();
    malformed_and_stop();info_and_flags();duplicate_prepare_and_expiry();all_encoders_selected();active_heartbeat_and_stop();
    puts("PASS: 9 grupos nativos; 3s/HB activo y caducado/STOP/one-shot/nonce/flags/direcciones. Sin hardware.");
}
