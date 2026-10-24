#include "ax_kinematics.h"
#include "ax_speed.h"
#include "juanillo_safety.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>

static uint16_t counters[4];
static int16_t outputs[4];

uint16_t AX_ENCODER_A_GetCounter(void) { return counters[0]; }
uint16_t AX_ENCODER_B_GetCounter(void) { return counters[1]; }
uint16_t AX_ENCODER_C_GetCounter(void) { return counters[2]; }
uint16_t AX_ENCODER_D_GetCounter(void) { return counters[3]; }
void AX_MOTOR_A_SetSpeed(int16_t output) { outputs[0] = output; }
void AX_MOTOR_B_SetSpeed(int16_t output) { outputs[1] = output; }
void AX_MOTOR_C_SetSpeed(int16_t output) { outputs[2] = output; }
void AX_MOTOR_D_SetSpeed(int16_t output) { outputs[3] = output; }

static void assert_stopped(void)
{
    for (unsigned wheel = 0; wheel < 4; ++wheel) {
        assert(outputs[wheel] == 0);
    }
}

int main(void)
{
    AX_ROBOT_Stop();
    AX_ROBOT_ResetMeasurements();
    assert_stopped();
    assert(AX_ROBOT_Control(100, 0, 0.02f));
    assert(outputs[0] > 0 && outputs[0] < 100);
    for (unsigned iteration = 0; iteration < 200; ++iteration) {
        assert(AX_ROBOT_Control(100, 0, 0.02f));
        for (unsigned wheel = 0; wheel < 4; ++wheel) {
            assert(outputs[wheel] <= 100 && outputs[wheel] >= -100);
        }
    }
    assert(AX_ROBOT_Control(0, 0, 0.02f));
    assert_stopped();
    assert(AX_ROBOT_Control(100, 0, 0.02f));
    assert(outputs[0] > 0 && outputs[0] < 100);
    AX_ROBOT_Stop();
    assert_stopped();
    assert(!AX_ROBOT_Control(100, 0, 0.1f));
    assert_stopped();
    assert(!AX_ROBOT_Control(201, 0, 0.02f));
    assert_stopped();
    assert(!AX_ROBOT_Control(100, 0, NAN));
    assert_stopped();

    counters[0] = 65530;
    counters[1] = 65530;
    counters[2] = 65530;
    counters[3] = 65530;
    AX_ROBOT_Stop();
    AX_ROBOT_ResetMeasurements();
    for (unsigned wheel = 0; wheel < 4; ++wheel) {
        counters[wheel] = 2;
    }
    assert(AX_ROBOT_Control(100, 0, 0.02f));
    float measured_linear = 0;
    float measured_angular = 0;
    assert(AX_ROBOT_GetMeasured(&measured_linear, &measured_angular));
    assert(measured_linear > 0.081f && measured_linear < 0.083f);
    assert(measured_angular == 0);
    assert(measured_linear != 0.100f);
    for (unsigned wheel = 0; wheel < 4; ++wheel) {
        assert(outputs[wheel] <= 100 && outputs[wheel] >= -100);
    }
    AX_ROBOT_Stop();
    assert_stopped();

    JuanilloConfig config = {true, true, 200, 400, 250, 50};
    JuanilloSafety safety;
    JuanilloSafety_Init(&safety, &config, 0);
    JuanilloSafety_Ready(&safety, 0);
    safety.state = JUANILLO_ARMED;
    safety.has_velocity = true;
    safety.velocity_ms = 1;
    safety.linear_mm_s = 100;
    assert(AX_ROBOT_Control(safety.linear_mm_s, safety.angular_mrad_s, 0.02f));
    JuanilloSafety_Tick(&safety, 251);
    assert(safety.state == JUANILLO_DISARMED);
    AX_ROBOT_Stop();
    assert_stopped();
    puts("PASS: hardware-stub controller, same-call STOP/timeout/reset, PWM bounds, encoder wrap; synthetic profile only");
    return 0;
}
