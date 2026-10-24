#ifndef H60_MANUAL_HOLD_H
#define H60_MANUAL_HOLD_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HOLD_MARKER "H60_MANUAL_TURN_CONTROL_V1__"
#define HOLD_PROFILE 6u
#define HOLD_CHANNEL_MASK 15u
#define HOLD_REVERSED_MASK 10u
#define HOLD_LEASE_MS 150u
#define HOLD_BURST_MS 10000u
#define HOLD_WAKE_MS 4u
#define HOLD_DUTY_PERMILLE 100u
#define HOLD_PWM_HZ 5000u
#define HOLD_TIMER_TICKS 4200u
#define HOLD_DRIVE_TICKS (HOLD_TIMER_TICKS*HOLD_DUTY_PERMILLE/1000u)

enum { H_IDLE, H_WAKE, H_RUNNING, H_LIMIT, H_FAULT };
enum { R_BOOT=0, R_STOP=1, R_MOVE=3, R_LIMIT=4, R_LEASE=5,
       R_FRAME=6, R_NONCE=7, R_DIRECTION=8, R_LATE=10,
       R_HARDWARE=11, R_RNG=12 };
enum { E_NONE=0, E_OFF=1, E_WAKE=2, E_PWM=4, E_REPLY=16,
       E_ENCODERS=32, E_CAPS=64 };
typedef struct {
    uint8_t state, reason, reply_id;
    int8_t direction;
    uint64_t nonce;
    uint32_t heartbeat_ms, burst_ms, wake_ms, burst_count;
    uint32_t frame_ms;
    uint16_t counters[4];
    uint8_t frame[14], used, length;
} Hold;
typedef struct { uint16_t in1_ticks, in2_ticks; } HoldCompare;

void hold_init(Hold *state, uint64_t nonce, uint32_t now);
void hold_observe(Hold *state, const uint16_t counts[4]);
uint8_t hold_fault(Hold *state, uint8_t reason);
uint8_t hold_tick(Hold *state, uint32_t now, bool burst_finished);
uint8_t hold_feed(Hold *state, uint8_t byte, uint32_t now);
void hold_status(const Hold *state, uint32_t now, bool all_low, uint8_t out[44]);
void hold_caps(uint8_t out[48]);
bool hold_reverse_channel(int8_t direction, unsigned channel);
bool hold_direction_valid(int8_t direction);
HoldCompare hold_channel_compare(int8_t direction, unsigned channel);
size_t hold_packet(uint8_t id, const uint8_t *payload, size_t length, uint8_t out[64]);
#endif
