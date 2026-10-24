#ifndef AX_KINEMATICS_H
#define AX_KINEMATICS_H

#include <stdbool.h>
#include <stdint.h>

void AX_ROBOT_ReadCounters(uint16_t counters[4]);
void AX_ROBOT_ResetMeasurements(void);
bool AX_ROBOT_Measure(float delta_seconds);
bool AX_ROBOT_GetMeasured(float *linear_m_s, float *angular_rad_s);
void AX_ROBOT_Stop(void);
bool AX_ROBOT_Control(int16_t linear_mm_s, int16_t angular_mrad_s, float delta_seconds);

#endif
