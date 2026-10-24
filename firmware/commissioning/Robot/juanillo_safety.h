#ifndef JUANILLO_SAFETY_H
#define JUANILLO_SAFETY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define JUANILLO_MAX_FRAME 11u
#define JUANILLO_STATUS_LENGTH 16u
#define JUANILLO_EVENT_STATUS 1u
#define JUANILLO_EVENT_ENCODERS 2u
#define JUANILLO_EVENT_STOP 4u

typedef enum {
    JUANILLO_DISARMED = 0,
    JUANILLO_ARMED = 1,
    JUANILLO_FAULT = 2
} JuanilloState;

typedef enum {
    JUANILLO_REASON_BOOT = 1,
    JUANILLO_REASON_READY = 2,
    JUANILLO_REASON_STOP = 3,
    JUANILLO_REASON_DISARM = 4,
    JUANILLO_REASON_TIMEOUT = 5,
    JUANILLO_REASON_LOCKED = 6,
    JUANILLO_REASON_NOT_READY = 7,
    JUANILLO_REASON_NO_RECENT_ZERO = 8,
    JUANILLO_REASON_NOT_ARMED = 9,
    JUANILLO_REASON_RANGE = 10,
    JUANILLO_REASON_RX_FAULT = 11,
    JUANILLO_REASON_CONTROL_FAULT = 12,
    JUANILLO_REASON_PROFILE = 13,
    JUANILLO_REASON_ARMED = 14,
    JUANILLO_REASON_IMU = 15,
    JUANILLO_REASON_BATTERY = 16
} JuanilloReason;

typedef struct {
    bool motion_enabled;
    bool calibrated;
    int16_t max_linear_mm_s;
    int16_t max_angular_mrad_s;
    uint32_t command_timeout_ms;
    uint32_t frame_timeout_ms;
} JuanilloConfig;

typedef struct {
    JuanilloConfig config;
    JuanilloState state;
    JuanilloReason reason;
    bool ready;
    bool has_velocity;
    bool has_recent_zero;
    uint32_t boot_ms;
    uint32_t velocity_ms;
    int16_t linear_mm_s;
    int16_t angular_mrad_s;
    uint8_t frame[JUANILLO_MAX_FRAME];
    uint8_t frame_used;
    uint8_t frame_length;
    uint32_t frame_ms;
    uint32_t rejected_frames;
} JuanilloSafety;

typedef struct {
    float integral;
    float previous_error;
    bool has_previous;
} JuanilloPid;

typedef struct {
    int16_t acceleration[3];
    int16_t gyroscope[3];
    float measured_linear_m_s;
    float measured_angular_rad_s;
    uint16_t battery_centivolts;
    bool imu_valid;
    bool velocity_valid;
    bool battery_valid;
} JuanilloTelemetry;

void JuanilloSafety_Init(JuanilloSafety *safety, const JuanilloConfig *config, uint32_t now_ms);
void JuanilloSafety_Ready(JuanilloSafety *safety, uint32_t now_ms);
void JuanilloSafety_Fault(JuanilloSafety *safety, JuanilloReason reason);
uint8_t JuanilloSafety_Feed(JuanilloSafety *safety, uint8_t value, uint32_t arrival_ms);
void JuanilloSafety_Tick(JuanilloSafety *safety, uint32_t now_ms);
bool JuanilloSafety_DriveProfile(const JuanilloSafety *safety);
void JuanilloSafety_Status(const JuanilloSafety *safety, uint32_t now_ms, uint8_t status[JUANILLO_STATUS_LENGTH]);
size_t JuanilloSafety_Packet(uint8_t frame_id, const uint8_t *payload, size_t payload_length, uint8_t *output, size_t capacity);
void JuanilloPid_Reset(JuanilloPid *pid);
bool JuanilloPid_Step(JuanilloPid *pid, float target, float measured, float delta_seconds, float proportional, float integral, float derivative, int16_t limit, int16_t *output);
bool JuanilloTelemetry_Encode(const JuanilloTelemetry *telemetry, uint8_t payload[20]);

#endif
