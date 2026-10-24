#include "ax_kinematics.h"
#include "ax_encoder.h"
#include "ax_motor.h"
#include "ax_speed.h"
#include "juanillo_profile.h"

#include <math.h>

static uint16_t previous_counts[4];
static float ramp_linear;
static float ramp_angular;
#if JUANILLO_MOTION_ENABLED
static float measured_wheel[4];
static bool measured_valid;
static const uint32_t counts_per_turn[4] = {JUANILLO_ENCODER_COUNTS_A, JUANILLO_ENCODER_COUNTS_B, JUANILLO_ENCODER_COUNTS_C, JUANILLO_ENCODER_COUNTS_D};
static const int8_t encoder_sign[4] = {JUANILLO_ENCODER_SIGN_A, JUANILLO_ENCODER_SIGN_B, JUANILLO_ENCODER_SIGN_C, JUANILLO_ENCODER_SIGN_D};
static const uint8_t wheel_side[4] = {JUANILLO_WHEEL_SIDE_A, JUANILLO_WHEEL_SIDE_B, JUANILLO_WHEEL_SIDE_C, JUANILLO_WHEEL_SIDE_D};
#endif

void AX_ROBOT_ReadCounters(uint16_t counters[4])
{
    counters[0] = AX_ENCODER_A_GetCounter();
    counters[1] = AX_ENCODER_B_GetCounter();
    counters[2] = AX_ENCODER_C_GetCounter();
    counters[3] = AX_ENCODER_D_GetCounter();
}

void AX_ROBOT_Stop(void)
{
    AX_MOTOR_A_SetSpeed(0);
    AX_MOTOR_B_SetSpeed(0);
    AX_MOTOR_C_SetSpeed(0);
    AX_MOTOR_D_SetSpeed(0);
    AX_SPEED_Reset();
    ramp_linear = 0;
    ramp_angular = 0;
}

void AX_ROBOT_ResetMeasurements(void)
{
    AX_ROBOT_ReadCounters(previous_counts);
#if JUANILLO_MOTION_ENABLED
    measured_valid = false;
#endif
}

bool AX_ROBOT_Measure(float delta_seconds)
{
#if JUANILLO_MOTION_ENABLED
    uint16_t counters[4];
    measured_valid = false;
    if (!isfinite(delta_seconds) || delta_seconds <= 0 || delta_seconds > 0.04f) {
        return false;
    }
    AX_ROBOT_ReadCounters(counters);
    for (unsigned wheel = 0; wheel < 4; ++wheel) {
        uint16_t unsigned_delta = (uint16_t)(counters[wheel] - previous_counts[wheel]);
        int32_t signed_delta = unsigned_delta <= 32767 ? (int32_t)unsigned_delta : (int32_t)unsigned_delta - 65536;
        previous_counts[wheel] = counters[wheel];
        measured_wheel[wheel] = (float)signed_delta * (float)encoder_sign[wheel] * 3.14159265358979323846f *
                                ((float)JUANILLO_WHEEL_DIAMETER_MM / 1000.0f) /
                                ((float)counts_per_turn[wheel] * delta_seconds);
        if (!isfinite(measured_wheel[wheel])) {
            return false;
        }
    }
    measured_valid = true;
    return true;
#else
    (void)delta_seconds;
    return false;
#endif
}

bool AX_ROBOT_GetMeasured(float *linear_m_s, float *angular_rad_s)
{
#if JUANILLO_MOTION_ENABLED
    if (!measured_valid) {
        return false;
    }
    float left = 0;
    float right = 0;
    for (unsigned wheel = 0; wheel < 4; ++wheel) {
        if (wheel_side[wheel] == 1) {
            left += measured_wheel[wheel] / 2.0f;
        } else {
            right += measured_wheel[wheel] / 2.0f;
        }
    }
    *linear_m_s = (left + right) / 2.0f;
    *angular_rad_s = (right - left) / ((float)JUANILLO_EFFECTIVE_TRACK_MM / 1000.0f);
    return isfinite(*linear_m_s) && isfinite(*angular_rad_s);
#else
    (void)linear_m_s;
    (void)angular_rad_s;
    return false;
#endif
}

#if JUANILLO_MOTION_ENABLED
static float ramp_to(float current, float target, float max_step)
{
    float change = target - current;
    if (change > max_step) {
        change = max_step;
    } else if (change < -max_step) {
        change = -max_step;
    }
    return current + change;
}
#endif

bool AX_ROBOT_Control(int16_t linear_mm_s, int16_t angular_mrad_s, float delta_seconds)
{
#if JUANILLO_MOTION_ENABLED
    static const int8_t motor_sign[4] = {JUANILLO_MOTOR_SIGN_A, JUANILLO_MOTOR_SIGN_B, JUANILLO_MOTOR_SIGN_C, JUANILLO_MOTOR_SIGN_D};
    int16_t outputs[4];
    if (!isfinite(delta_seconds) || delta_seconds <= 0 || delta_seconds > 0.04f ||
        linear_mm_s > JUANILLO_MAX_LINEAR_MM_S || linear_mm_s < -JUANILLO_MAX_LINEAR_MM_S ||
        angular_mrad_s > JUANILLO_MAX_ANGULAR_MRAD_S || angular_mrad_s < -JUANILLO_MAX_ANGULAR_MRAD_S) {
        AX_ROBOT_Stop();
        return false;
    }
    if (!AX_ROBOT_Measure(delta_seconds)) {
        AX_ROBOT_Stop();
        return false;
    }
    if (linear_mm_s == 0 && angular_mrad_s == 0) {
        AX_ROBOT_Stop();
        return true;
    }
    ramp_linear = ramp_to(ramp_linear, (float)linear_mm_s / 1000.0f,
                           (float)JUANILLO_MAX_LINEAR_ACCEL_MM_S2 * delta_seconds / 1000.0f);
    ramp_angular = ramp_to(ramp_angular, (float)angular_mrad_s / 1000.0f,
                            (float)JUANILLO_MAX_ANGULAR_ACCEL_MRAD_S2 * delta_seconds / 1000.0f);
    for (unsigned wheel = 0; wheel < 4; ++wheel) {
        float turn = ramp_angular * ((float)JUANILLO_EFFECTIVE_TRACK_MM / 2000.0f);
        float target = ramp_linear + (wheel_side[wheel] == 1 ? -turn : turn);
        int16_t output = 0;
        if (!AX_SPEED_Wheel(wheel, target, measured_wheel[wheel], delta_seconds, &output)) {
            AX_ROBOT_Stop();
            return false;
        }
        outputs[wheel] = (int16_t)(output * motor_sign[wheel]);
    }
    AX_MOTOR_A_SetSpeed(outputs[0]);
    AX_MOTOR_B_SetSpeed(outputs[1]);
    AX_MOTOR_C_SetSpeed(outputs[2]);
    AX_MOTOR_D_SetSpeed(outputs[3]);
    return true;
#else
    (void)linear_mm_s;
    (void)angular_mrad_s;
    (void)delta_seconds;
    AX_ROBOT_Stop();
    return false;
#endif
}
