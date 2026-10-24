#include "juanillo_safety.h"

#include <limits.h>
#include <math.h>
#include <string.h>

static void write_u16(uint8_t *output, uint16_t value)
{
    output[0] = (uint8_t)(value >> 8);
    output[1] = (uint8_t)value;
}

static void write_u32(uint8_t *output, uint32_t value)
{
    output[0] = (uint8_t)(value >> 24);
    output[1] = (uint8_t)(value >> 16);
    output[2] = (uint8_t)(value >> 8);
    output[3] = (uint8_t)value;
}

static int16_t read_i16(const uint8_t *input)
{
    uint16_t value = ((uint16_t)input[0] << 8) | input[1];
    return value <= INT16_MAX ? (int16_t)value : (int16_t)((int32_t)value - 65536);
}

static void clear_parser(JuanilloSafety *safety)
{
    safety->frame_used = 0;
    safety->frame_length = 0;
}

static void disarm(JuanilloSafety *safety, JuanilloReason reason, bool keep_zero)
{
    if (safety->state != JUANILLO_FAULT) {
        safety->state = JUANILLO_DISARMED;
        safety->reason = reason;
    }
    safety->linear_mm_s = 0;
    safety->angular_mrad_s = 0;
    if (!keep_zero) {
        safety->has_recent_zero = false;
    }
}

bool JuanilloSafety_DriveProfile(const JuanilloSafety *safety)
{
    return safety->config.motion_enabled && safety->config.calibrated &&
           safety->config.max_linear_mm_s > 0 && safety->config.max_angular_mrad_s > 0;
}

void JuanilloSafety_Init(JuanilloSafety *safety, const JuanilloConfig *config, uint32_t now_ms)
{
    memset(safety, 0, sizeof(*safety));
    safety->config = *config;
    safety->boot_ms = now_ms;
    safety->reason = JUANILLO_REASON_BOOT;
    if (config->command_timeout_ms == 0 || config->command_timeout_ms > INT32_MAX ||
        config->frame_timeout_ms == 0 || config->frame_timeout_ms > INT32_MAX ||
        (config->motion_enabled && !JuanilloSafety_DriveProfile(safety))) {
        JuanilloSafety_Fault(safety, JUANILLO_REASON_PROFILE);
    }
}

void JuanilloSafety_Ready(JuanilloSafety *safety, uint32_t now_ms)
{
    clear_parser(safety);
    safety->ready = safety->state != JUANILLO_FAULT;
    safety->has_velocity = false;
    safety->velocity_ms = now_ms;
    disarm(safety, JUANILLO_REASON_READY, false);
}

void JuanilloSafety_Fault(JuanilloSafety *safety, JuanilloReason reason)
{
    safety->state = JUANILLO_FAULT;
    safety->reason = reason;
    safety->linear_mm_s = 0;
    safety->angular_mrad_s = 0;
    safety->has_recent_zero = false;
}

void JuanilloSafety_Tick(JuanilloSafety *safety, uint32_t now_ms)
{
    if (safety->frame_used != 0 && (uint32_t)(now_ms - safety->frame_ms) >= safety->config.frame_timeout_ms) {
        clear_parser(safety);
    }
    if (safety->has_velocity && (uint32_t)(now_ms - safety->velocity_ms) >= safety->config.command_timeout_ms) {
        safety->has_recent_zero = false;
        if (safety->state == JUANILLO_ARMED) {
            disarm(safety, JUANILLO_REASON_TIMEOUT, false);
        }
    }
}

static uint8_t apply_frame(JuanilloSafety *safety, uint32_t arrival_ms)
{
    JuanilloSafety_Tick(safety, arrival_ms);
    uint8_t frame_id = safety->frame[3];
    const uint8_t *payload = &safety->frame[4];
    if (frame_id == 0x60) {
        return JUANILLO_EVENT_STATUS;
    }
    if (frame_id == 0x63) {
        return JUANILLO_EVENT_ENCODERS;
    }
    if (frame_id == 0x62) {
        disarm(safety, JUANILLO_REASON_DISARM, false);
        return JUANILLO_EVENT_STOP;
    }
    if (frame_id == 0x61) {
        if (memcmp(payload, "ARM!", 4) != 0 || safety->state == JUANILLO_FAULT) {
            return 0;
        }
        if (!safety->ready) {
            disarm(safety, JUANILLO_REASON_NOT_READY, false);
        } else if (!JuanilloSafety_DriveProfile(safety)) {
            disarm(safety, JUANILLO_REASON_LOCKED, false);
        } else if (!safety->has_recent_zero || !safety->has_velocity ||
                   (uint32_t)(arrival_ms - safety->velocity_ms) >= safety->config.command_timeout_ms) {
            disarm(safety, JUANILLO_REASON_NO_RECENT_ZERO, false);
        } else {
            safety->state = JUANILLO_ARMED;
            safety->reason = JUANILLO_REASON_ARMED;
            safety->has_recent_zero = false;
        }
        return 0;
    }
    if (frame_id == 0x50) {
        int16_t linear = read_i16(payload);
        int16_t lateral = read_i16(payload + 2);
        int16_t angular = read_i16(payload + 4);
        bool zero = linear == 0 && lateral == 0 && angular == 0;
        if (safety->state == JUANILLO_FAULT) {
            return JUANILLO_EVENT_STOP;
        }
        if (!safety->ready) {
            disarm(safety, JUANILLO_REASON_NOT_READY, false);
            return JUANILLO_EVENT_STOP;
        }
        if (zero) {
            safety->has_velocity = true;
            safety->velocity_ms = arrival_ms;
            safety->has_recent_zero = true;
            disarm(safety, JUANILLO_REASON_STOP, true);
            return JUANILLO_EVENT_STOP;
        }
        if (!JuanilloSafety_DriveProfile(safety)) {
            disarm(safety, JUANILLO_REASON_LOCKED, false);
        } else if (lateral != 0 || linear > safety->config.max_linear_mm_s ||
                   linear < -safety->config.max_linear_mm_s || angular > safety->config.max_angular_mrad_s ||
                   angular < -safety->config.max_angular_mrad_s) {
            disarm(safety, JUANILLO_REASON_RANGE, false);
        } else if (safety->state != JUANILLO_ARMED) {
            disarm(safety, JUANILLO_REASON_NOT_ARMED, false);
        } else {
            safety->has_velocity = true;
            safety->has_recent_zero = false;
            safety->velocity_ms = arrival_ms;
            safety->linear_mm_s = linear;
            safety->angular_mrad_s = angular;
            return 0;
        }
        return JUANILLO_EVENT_STOP;
    }
    return 0;
}

static uint8_t expected_length(uint8_t frame_id)
{
    if (frame_id == 0x50) {
        return 11;
    }
    if (frame_id == 0x61) {
        return 9;
    }
    if (frame_id == 0x60 || frame_id == 0x62 || frame_id == 0x63) {
        return 5;
    }
    return 0;
}

uint8_t JuanilloSafety_Feed(JuanilloSafety *safety, uint8_t value, uint32_t arrival_ms)
{
    if (safety->frame_used != 0 && (uint32_t)(arrival_ms - safety->frame_ms) >= safety->config.frame_timeout_ms) {
        clear_parser(safety);
    }
    safety->frame_ms = arrival_ms;
    if (safety->frame_used == 0) {
        if (value == 0xAA) {
            safety->frame[0] = value;
            safety->frame_used = 1;
        }
        return 0;
    }
    if (safety->frame_used == 1) {
        if (value == 0x55) {
            safety->frame[1] = value;
            safety->frame_used = 2;
        } else if (value != 0xAA) {
            clear_parser(safety);
        }
        return 0;
    }
    if (safety->frame_used == 2) {
        if (value != 5 && value != 9 && value != 11) {
            ++safety->rejected_frames;
            clear_parser(safety);
            return 0;
        }
        safety->frame_length = value;
    }
    safety->frame[safety->frame_used++] = value;
    if (safety->frame_used == 4 && expected_length(value) != safety->frame_length) {
        ++safety->rejected_frames;
        clear_parser(safety);
        return 0;
    }
    if (safety->frame_used == safety->frame_length) {
        uint8_t checksum = 0;
        for (uint8_t offset = 0; offset + 1 < safety->frame_length; ++offset) {
            checksum = (uint8_t)(checksum + safety->frame[offset]);
        }
        uint8_t events = 0;
        if (checksum == value) {
            events = apply_frame(safety, arrival_ms);
        } else {
            ++safety->rejected_frames;
        }
        clear_parser(safety);
        return events;
    }
    return 0;
}

void JuanilloSafety_Status(const JuanilloSafety *safety, uint32_t now_ms, uint8_t status[JUANILLO_STATUS_LENGTH])
{
    memset(status, 0, JUANILLO_STATUS_LENGTH);
    status[0] = 1;
    status[1] = JuanilloSafety_DriveProfile(safety) ? 1 : 0;
    status[2] = (uint8_t)safety->state;
    status[3] = (safety->config.motion_enabled ? 0 : 1) | (JuanilloSafety_DriveProfile(safety) ? 2 : 0);
    write_u32(status + 4, now_ms - safety->boot_ms);
    write_u32(status + 8, safety->has_velocity ? now_ms - safety->velocity_ms : UINT32_MAX);
    write_u16(status + 12, (uint16_t)safety->reason);
}

size_t JuanilloSafety_Packet(uint8_t frame_id, const uint8_t *payload, size_t payload_length, uint8_t *output, size_t capacity)
{
    if (payload_length > 64 || capacity < payload_length + 5 || (payload_length != 0 && payload == NULL)) {
        return 0;
    }
    output[0] = 0xAA;
    output[1] = 0x55;
    output[2] = (uint8_t)(payload_length + 5);
    output[3] = frame_id;
    if (payload_length != 0) {
        memcpy(output + 4, payload, payload_length);
    }
    uint8_t checksum = 0;
    for (size_t offset = 0; offset < payload_length + 4; ++offset) {
        checksum = (uint8_t)(checksum + output[offset]);
    }
    output[payload_length + 4] = checksum;
    return payload_length + 5;
}

void JuanilloPid_Reset(JuanilloPid *pid)
{
    memset(pid, 0, sizeof(*pid));
}

bool JuanilloPid_Step(JuanilloPid *pid, float target, float measured, float delta_seconds, float proportional, float integral, float derivative, int16_t limit, int16_t *output)
{
    *output = 0;
    if (!isfinite(target) || !isfinite(measured) || !isfinite(delta_seconds) || delta_seconds <= 0 ||
        !isfinite(proportional) || !isfinite(integral) || !isfinite(derivative) ||
        proportional < 0 || integral < 0 || derivative < 0 || limit <= 0 ||
        !isfinite(pid->integral) || !isfinite(pid->previous_error)) {
        JuanilloPid_Reset(pid);
        return false;
    }
    float error = target - measured;
    float rate = pid->has_previous ? (error - pid->previous_error) / delta_seconds : 0;
    float candidate_integral = pid->integral + integral * error * delta_seconds;
    float demand = proportional * error + candidate_integral + derivative * rate;
    if (!isfinite(demand)) {
        JuanilloPid_Reset(pid);
        return false;
    }
    if ((demand > limit && error > 0) || (demand < -limit && error < 0)) {
        demand = proportional * error + pid->integral + derivative * rate;
    } else {
        pid->integral = candidate_integral;
    }
    if (pid->integral > limit) {
        pid->integral = limit;
    } else if (pid->integral < -limit) {
        pid->integral = -limit;
    }
    pid->previous_error = error;
    pid->has_previous = true;
    if (demand > limit) {
        demand = limit;
    } else if (demand < -limit) {
        demand = -limit;
    }
    *output = (int16_t)demand;
    return true;
}

bool JuanilloTelemetry_Encode(const JuanilloTelemetry *telemetry, uint8_t payload[20])
{
    if (!telemetry->imu_valid || !telemetry->velocity_valid || !telemetry->battery_valid ||
        !isfinite(telemetry->measured_linear_m_s) || !isfinite(telemetry->measured_angular_rad_s) ||
        telemetry->measured_linear_m_s > 32.767f || telemetry->measured_linear_m_s < -32.768f ||
        telemetry->measured_angular_rad_s > 32.767f || telemetry->measured_angular_rad_s < -32.768f ||
        telemetry->battery_centivolts == 0) {
        return false;
    }
    for (unsigned axis = 0; axis < 3; ++axis) {
        write_u16(payload + axis * 2, (uint16_t)telemetry->acceleration[axis]);
        write_u16(payload + 6 + axis * 2, (uint16_t)telemetry->gyroscope[axis]);
    }
    write_u16(payload + 12, (uint16_t)(int16_t)(telemetry->measured_linear_m_s * 1000.0f));
    write_u16(payload + 14, 0);
    write_u16(payload + 16, (uint16_t)(int16_t)(telemetry->measured_angular_rad_s * 1000.0f));
    write_u16(payload + 18, telemetry->battery_centivolts);
    return true;
}
