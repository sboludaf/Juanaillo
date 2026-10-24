#ifndef H60_PULSE_H
#define H60_PULSE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PULSE_MARKER "H60_FORWARD3S_SINGLE_SHOT_V1"
#define PULSE_CHANNEL_MASK 15u
#define PULSE_REVERSED_MASK 10u
#define PULSE_PROFILE 4u
#define PULSE_LEASE_MS 100u
#define PULSE_PREPARE_LIMIT_MS 300u
#define PULSE_ENVELOPE_MS 3005u
#define PULSE_QUIET_MS 1000u
#define PULSE_WAKE_MIN_MS 3u
#define PULSE_PWM_MS 3000u
#define PULSE_DUTY_PERMILLE 100u
#define PULSE_PWM_HZ 5000u

enum { P_IDLE, P_READY, P_WAKE, P_RUNNING, P_DONE, P_FAULT };
enum { R_BOOT, R_STOP, R_PREPARED, R_FIRED, R_FINISHED, R_LEASE,
       R_FRAME, R_NONCE, R_SEQUENCE, R_MOVING, R_LATE, R_HARDWARE, R_RNG };
enum { E_NONE=0, E_OFF=1, E_WAKE=2, E_PWM=4, E_REPLY=16, E_ENCODERS=32, E_CAPS=64 };
typedef struct {
    uint8_t state, reason, reply_id;
    bool consumed, stop_seen;
    uint64_t nonce;
    uint32_t prepared_ms, heartbeat_ms, fire_ms, stop_ms, quiet_since_ms;
    uint32_t frame_ms;
    uint16_t counters[4];
    uint8_t frame[13], used, length;
} Pulse;

void pulse_init(Pulse *p, uint64_t nonce, uint32_t now);
uint8_t pulse_observe(Pulse *p, const uint16_t counts[4], uint32_t now);
uint8_t pulse_fault(Pulse *p, uint8_t reason);
uint8_t pulse_tick(Pulse *p, uint32_t now, bool hardware_finished);
uint8_t pulse_feed(Pulse *p, uint8_t byte, uint32_t now);
void pulse_status(const Pulse *p, uint32_t now, bool all_low, uint8_t out[36]);
size_t pulse_packet(uint8_t id, const uint8_t *payload, size_t length, uint8_t out[64]);
void pulse_caps(uint8_t out[48]);
#endif
