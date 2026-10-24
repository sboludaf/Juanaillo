#include "hold.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const uint64_t nonce=UINT64_C(0x123456789abcdef0);
/* Millisecond-aligned hardware origin for the existing state-machine tests.
   The explicit phase-sweep tests below pass their own real GPIO origin. */
static uint8_t tick(Hold *p,uint32_t now,bool finished)
{
    uint8_t event=hold_tick(p,now,finished);
    if(!(event&E_OFF))event|=hold_qualify_wake(p,(now-p->wake_ms)*168000u,168000u);
    return event;
}

static void session(uint8_t out[9],int direction)
{
    for(unsigned i=0;i<8;i++)out[i]=(uint8_t)(nonce>>(56u-8u*i));
    out[8]=(uint8_t)direction;
}
static uint8_t send(Hold *p,uint8_t id,const uint8_t *data,size_t size,uint32_t now)
{
    uint8_t packet[64],event=0;size_t length=hold_packet(id,data,size,packet);
    for(size_t i=0;i<length;i++)event|=hold_feed(p,packet[i],now);
    return event;
}
static uint8_t move(Hold *p,int direction,uint32_t now)
{
    uint8_t data[9];session(data,direction);return send(p,0x77,data,9,now);
}
static uint8_t stop(Hold *p,uint32_t now) { return send(p,0x74,NULL,0,now); }
static uint32_t read32(const uint8_t *p)
{
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static void boot_and_caps(void)
{
    Hold p;hold_init(&p,nonce,0);assert(p.state==H_IDLE && p.direction==0);
    assert(tick(&p,600000,false)==E_NONE && p.burst_count==0);
    uint8_t caps[48],status[44];hold_caps(caps);hold_status(&p,123,true,status);
    const uint8_t prefix[]={1,6,15,10,0,100,0x13,0x88,0,4,0x27,0x10,0,0x98,0x96,0x80,0,0,0,150};
    assert(!memcmp(caps,prefix,20));assert(!memcmp(caps+20,HOLD_MARKER,28));
    assert(status[1]==6 && status[2]==H_IDLE && status[3]==9);
    assert(read32(status+28)==0 && read32(status+36)==0 && read32(status+40)==0);
    hold_init(&p,0,0);assert(p.state==H_FAULT && p.reason==R_RNG);
    assert(move(&p,1,1)&E_OFF);assert(p.state==H_FAULT);
}
static void hold_release_and_new_press(void)
{
    Hold p;hold_init(&p,nonce,0);
    assert(move(&p,1,10)&E_WAKE);assert(p.state==H_WAKE && p.direction==1 && p.burst_count==1);
    assert(tick(&p,13,false)==0);assert(tick(&p,14,false)==E_PWM);
    assert(p.state==H_RUNNING);
    for(uint32_t now=16;now<400;now++) {
        assert(!(tick(&p,now,false)&E_OFF));
        if(now%50u==0)assert(!(move(&p,1,now)&(E_WAKE|E_PWM|E_OFF)));
    }
    assert(p.burst_ms==10 && p.burst_count==1);
    assert(stop(&p,400)&E_OFF);assert(p.state==H_IDLE && p.direction==0);
    assert(move(&p,-1,500)&E_WAKE);assert(p.burst_count==2 && p.burst_ms==500);
    assert(tick(&p,505,false)==E_PWM);
    assert(stop(&p,510)&E_OFF);assert(p.state==H_IDLE);
}
static void lease_expiry_cannot_revive(void)
{
    Hold p;hold_init(&p,nonce,0);move(&p,1,0);tick(&p,5,false);
    assert(!(move(&p,1,149)&E_OFF));assert(p.heartbeat_ms==149);
    assert(move(&p,1,299)&E_OFF);assert(p.state==H_FAULT && p.reason==R_LEASE);
    uint32_t count=p.burst_count;stop(&p,300);move(&p,-1,301);
    assert(p.state==H_FAULT && p.burst_count==count && p.direction==0);
}
static void reversal_wakes_without_extending_burst(void)
{
    Hold p;hold_init(&p,nonce,0);move(&p,1,0);tick(&p,5,false);
    assert(move(&p,-1,50)&E_WAKE);assert(p.state==H_WAKE && p.direction==-1);
    assert(p.burst_ms==0 && p.burst_count==1 && p.wake_ms==50);
    assert(tick(&p,53,false)==0);assert(tick(&p,54,false)==E_PWM);
    assert(move(&p,1,75)&E_WAKE);assert(p.burst_ms==0 && p.burst_count==1);
    assert(stop(&p,80)&E_OFF);assert(p.state==H_IDLE);
    /* STOP at the exact wake transition keeps E_OFF dominant. */
    move(&p,1,100);assert(stop(&p,105)&E_OFF);assert(p.state==H_IDLE);
    /* Last byte of reversal coincides with old wake-to-PWM transition. */
    move(&p,1,200);uint8_t data[9],packet[64];session(data,-1);
    size_t n=hold_packet(0x77,data,9,packet);
    for(size_t i=0;i<n-1;i++)hold_feed(&p,packet[i],204);
    uint8_t event=hold_feed(&p,packet[n-1],205);
    assert((event&E_WAKE) && !(event&E_PWM) && p.state==H_WAKE && p.wake_ms==205);
}
static void absolute_limit_needs_release(void)
{
    Hold p;hold_init(&p,nonce,0);move(&p,1,0);
    const int directions[]={1,-1,2,-2};
    for(uint32_t now=1;now<=10000;now++) {
        uint8_t event=tick(&p,now,false);
        if(now<10000) {
            assert(!(event&E_OFF));
            if(now%50u==0)move(&p,directions[(now/50u)%4u],now);
            if(now==9999u)move(&p,p.direction==2?-2:2,now);
        } else assert(event&E_OFF);
    }
    assert(p.state==H_LIMIT && p.reason==R_LIMIT && p.burst_ms==0);
    for(unsigned i=0;i<4;i++) {
        assert(!(move(&p,directions[i],10001)&(E_WAKE|E_PWM)));
        assert(p.state==H_LIMIT && p.burst_count==1 && p.direction==0);
    }
    stop(&p,10002);assert(move(&p,-1,10003)&E_WAKE);assert(p.burst_count==2);
    assert(tick(&p,10004,true)&E_OFF);assert(p.state==H_LIMIT);
}
static void nonce_direction_and_frames(void)
{
    Hold p;uint8_t data[9];session(data,1);
    hold_init(&p,nonce+1,0);assert(send(&p,0x77,data,9,0)&E_OFF);assert(p.reason==R_NONCE);
    hold_init(&p,nonce,0);assert(move(&p,0,0)&E_OFF);assert(p.reason==R_DIRECTION);
    hold_init(&p,nonce,0);assert(send(&p,0x73,data,8,0)&E_OFF);assert(p.reason==R_FRAME);
    hold_init(&p,nonce,0);hold_feed(&p,0xAA,1);
    assert(tick(&p,31,false)&E_OFF);assert(p.reason==R_FRAME);
    hold_init(&p,nonce,0);uint8_t packet[64];size_t n=hold_packet(0x77,data,9,packet);packet[n-1]^=1;
    for(size_t i=0;i<n;i++)hold_feed(&p,packet[i],0);
    assert(p.state==H_FAULT && p.reason==R_FRAME && !p.burst_count);
    hold_init(&p,nonce,0);move(&p,1,0);assert(tick(&p,7,false)&E_OFF);assert(p.reason==R_LATE);
}
static void status_counts_wrap_and_directions(void)
{
    Hold p;uint8_t status[44];hold_init(&p,nonce,UINT32_MAX-20u);
    uint16_t counts[]={1,65535,3,4};hold_observe(&p,counts);move(&p,-1,UINT32_MAX-10u);
    tick(&p,UINT32_MAX-5u,false);hold_status(&p,0,false,status);
    assert(status[2]==H_RUNNING && status[3]==7 && read32(status+36)==UINT32_MAX);
    assert(read32(status+8)==139 && read32(status+40)==9989);
    assert(status[20]==0 && status[21]==1 && status[22]==255 && status[23]==255);
    assert(!(move(&p,-1,100)&E_OFF));assert(tick(&p,250,false)&E_OFF);
    const bool forward[]={false,true,false,true};
    for(unsigned channel=0;channel<4;channel++) {
        assert(hold_reverse_channel(1,channel)==forward[channel]);
        assert(hold_reverse_channel(-1,channel)!=forward[channel]);
    }
}
static void four_commands_and_pwm_mapping(void)
{
    const int8_t directions[]={1,-1,2,-2};
    const int8_t raw[4][4]={{1,-1,1,-1},{-1,1,-1,1},{1,1,1,1},{-1,-1,-1,-1}};
    /* Compare values below are the actual values consumed by TIM1 CH1/2 A,
       TIM1 CH3/4 B, TIM9 CH1/2 C and TIM12 CH1/2 D in main.c. */
    for(unsigned command=0;command<4;command++) {
        Hold p;hold_init(&p,nonce,0);assert(hold_direction_valid(directions[command]));
        assert(move(&p,directions[command],0)&E_WAKE);assert(tick(&p,5,false)==E_PWM);
        for(unsigned channel=0;channel<4;channel++) {
            HoldCompare pwm=hold_channel_compare(directions[command],channel);
            assert(hold_reverse_channel(directions[command],channel)==(raw[command][channel]<0));
            assert(pwm.in1_ticks==(raw[command][channel]>0?4200:3780));
            assert(pwm.in2_ticks==(raw[command][channel]>0?3780:4200));
            assert((int)pwm.in1_ticks-(int)pwm.in2_ticks==420*raw[command][channel]);
        }
        Hold stale;hold_init(&stale,nonce+1,0);
        assert(move(&stale,directions[command],0)&E_OFF);
        assert(stale.state==H_FAULT && stale.reason==R_NONCE && !stale.burst_count);
    }
    const int8_t invalid[]={0,3,-3,127,-128};
    for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
        Hold p;hold_init(&p,nonce,0);assert(!hold_direction_valid(invalid[i]));
        assert(move(&p,invalid[i],0)&E_OFF);assert(p.state==H_FAULT && p.reason==R_DIRECTION);
        HoldCompare pwm=hold_channel_compare(invalid[i],0);assert(!pwm.in1_ticks && !pwm.in2_ticks);
    }
    HoldCompare invalid_channel=hold_channel_compare(1,4);assert(!invalid_channel.in1_ticks && !invalid_channel.in2_ticks);
}
static void every_transition_keeps_limits(void)
{
    const int8_t directions[]={1,-1,2,-2};
    for(unsigned a=0;a<4;a++)for(unsigned b=0;b<4;b++) {
        Hold p;hold_init(&p,nonce,0);move(&p,directions[a],0);tick(&p,5,false);
        uint8_t event=move(&p,directions[b],10);
        assert(p.heartbeat_ms==10 && p.burst_ms==0 && p.burst_count==1);
        if(a==b) {
            assert(!(event&(E_WAKE|E_OFF|E_PWM)));assert(p.state==H_RUNNING && p.wake_ms==0);
        } else {
            assert((event&E_WAKE) && !(event&E_PWM));assert(p.state==H_WAKE && p.wake_ms==10);
            assert(tick(&p,13,false)==0);assert(tick(&p,14,false)==E_PWM);
        }
        assert(p.direction==directions[b]);assert(stop(&p,20)&E_OFF);assert(p.state==H_IDLE);
        assert(move(&p,directions[a],21)&E_WAKE);assert(p.burst_count==2);
        /* The same16 transitions are checked while the first wake is pending. */
        hold_init(&p,nonce,0);move(&p,directions[a],0);event=move(&p,directions[b],2);
        assert(p.burst_ms==0 && p.burst_count==1 && p.heartbeat_ms==2);
        if(a==b) {
            assert(!(event&(E_WAKE|E_OFF|E_PWM)));assert(p.wake_ms==0);
            assert(tick(&p,5,false)==E_PWM);
        } else {
            assert((event&E_WAKE) && !(event&E_PWM));assert(p.wake_ms==2);
            assert(tick(&p,5,false)==0);assert(tick(&p,6,false)==E_PWM);
        }
        /* A late refresh of any command faults; changing direction cannot revive it. */
        assert(move(&p,directions[a],152)&E_OFF);assert(p.state==H_FAULT && p.reason==R_LEASE);
        stop(&p,153);move(&p,directions[b],154);assert(p.state==H_FAULT);
    }
}
static void real_wake_phase_and_configuration_sweep(void)
{
    const uint32_t cycles_per_ms=168000u,cycles_per_us=168u;
    const uint32_t critical_cost_us[]={0,1,20,80};
    const uint32_t config_cost_us[]={0,1,3,20,250,999,1000};
    for(uint32_t phase=0;phase<1000;phase++) {
        for(unsigned critical=0;critical<sizeof(critical_cost_us)/sizeof(critical_cost_us[0]);critical++) {
            Hold p;hold_init(&p,nonce,0);move(&p,1,0);
            /* MOVE belongs to integer tick0. GPIO11 may start after the tick1
               edge because E_WAKE runs with interrupts masked. */
            uint32_t origin_us=phase+critical_cost_us[critical];
            uint32_t elapsed_us=0;bool qualified=false;
            for(uint32_t edge_us=1000;edge_us<=7000;edge_us+=1000) {
                uint32_t serviced_us=edge_us;
                if(serviced_us<origin_us+20u)serviced_us=origin_us+20u;
                assert(hold_tick(&p,edge_us/1000u,false)==E_NONE);
                assert(p.state==H_WAKE); /* Integer parser time alone never enables PWM. */
                elapsed_us=serviced_us-origin_us;
                /* Exercise unsigned DWT wrap as well as every SysTick phase. */
                uint32_t origin_cycles=UINT32_MAX-1234u;
                uint32_t now_cycles=origin_cycles+elapsed_us*cycles_per_us;
                uint8_t event=hold_qualify_wake(&p,now_cycles-origin_cycles,cycles_per_ms);
                if(elapsed_us<4000u) {
                    assert(event==E_NONE && p.state==H_WAKE);
                } else {
                    assert(event==E_PWM && p.state==H_RUNNING);
                    assert(elapsed_us<=4999u);qualified=true;break;
                }
            }
            assert(qualified && p.burst_ms==0 && p.burst_count==1);
            for(unsigned cost=0;cost<sizeof(config_cost_us)/sizeof(config_cost_us[0]);cost++) {
                uint32_t elapsed_cycles=(elapsed_us+config_cost_us[cost])*cycles_per_us;
                assert(hold_wake_phase(elapsed_cycles,cycles_per_ms)==W_READY);
            }
            /* At the actual6ms deadline there is no extra configuration margin. */
            assert(hold_wake_phase(6000u*cycles_per_us,cycles_per_ms)==W_READY);
            assert(hold_wake_phase(6000u*cycles_per_us+1u,cycles_per_ms)==W_EXPIRED);
        }
    }
    assert(hold_wake_phase(4000u*cycles_per_us-1u,cycles_per_ms)==W_WAIT);
    assert(hold_wake_phase(4000u*cycles_per_us,cycles_per_ms)==W_READY);
    assert(hold_wake_phase(4999u*cycles_per_us,cycles_per_ms)==W_READY);
    assert(hold_wake_phase(5002u*cycles_per_us,cycles_per_ms)==W_READY);
    assert(hold_wake_phase(0,0)==W_EXPIRED);
    assert(hold_wake_phase(0,UINT32_MAX)==W_EXPIRED);
    Hold late;hold_init(&late,nonce,0);move(&late,1,0);
    assert(hold_qualify_wake(&late,6000u*cycles_per_us+1u,cycles_per_ms)&E_OFF);
    assert(late.state==H_FAULT && late.reason==R_LATE && late.direction==0);
}
static void parser_stop_and_reversal_do_not_qualify_old_wake(void)
{
    Hold p;hold_init(&p,nonce,0);move(&p,1,0);
    assert(hold_tick(&p,5,false)==E_NONE && p.state==H_WAKE);
    assert(!(send(&p,0x70,NULL,0,5)&E_PWM) && p.state==H_WAKE);
    assert(!(move(&p,1,6)&E_PWM) && p.state==H_WAKE && p.wake_ms==0);
    assert(hold_qualify_wake(&p,3991u*168u,168000u)==E_NONE && p.state==H_WAKE);
    assert(hold_qualify_wake(&p,4000u*168u,168000u)==E_PWM);
    uint8_t pending=E_PWM;
    pending|=stop(&p,7);
    assert(pending&E_OFF);assert(p.state==H_IDLE && p.direction==0);
    assert(hold_qualify_wake(&p,4000u*168u,168000u)==E_NONE);
    move(&p,1,10);assert(hold_qualify_wake(&p,4000u*168u,168000u)==E_PWM);
    assert(move(&p,2,14)&E_WAKE);assert(p.state==H_WAKE && p.wake_ms==14);
    assert(hold_qualify_wake(&p,0,168000u)==E_NONE && p.state==H_WAKE);
    assert(p.burst_ms==10 && p.burst_count==2);
    /* Lease and burst stop before a physical qualifier may issue PWM. */
    assert(hold_tick(&p,164,false)&E_OFF);assert(p.state==H_FAULT);
    assert(hold_qualify_wake(&p,4000u*168u,168000u)==E_NONE);
    hold_init(&p,nonce,0);move(&p,1,0);
    p.heartbeat_ms=9999;p.wake_ms=9999; /* Valid lease, old absolute burst. */
    assert(hold_tick(&p,10000,false)&E_OFF);assert(p.state==H_LIMIT);
    assert(hold_qualify_wake(&p,4000u*168u,168000u)==E_NONE);
}
int main(void)
{
    boot_and_caps();hold_release_and_new_press();lease_expiry_cannot_revive();
    reversal_wakes_without_extending_burst();absolute_limit_needs_release();
    nonce_direction_and_frames();status_counts_wrap_and_directions();
    four_commands_and_pwm_mapping();every_transition_keeps_limits();
    real_wake_phase_and_configuration_sweep();parser_stop_and_reversal_do_not_qualify_old_wake();
    puts("PASS: manual-turn11 native groups:1000 tick phases/configuration bounds, real wake4..6ms,32 transitions, lease,STOP,LIMIT,nonce. No hardware.");
    return 0;
}
