#include "ax_speed.h"
#include "juanillo_profile.h"
#include "juanillo_safety.h"

static JuanilloPid wheel_pid[4];

void AX_SPEED_Reset(void)
{
    for (unsigned wheel = 0; wheel < 4; ++wheel) {
        JuanilloPid_Reset(&wheel_pid[wheel]);
    }
}

bool AX_SPEED_Wheel(unsigned wheel, float target, float measured, float delta_seconds, int16_t *output)
{
    if (wheel >= 4) {
        *output = 0;
        return false;
    }
#if JUANILLO_MOTION_ENABLED
    return JuanilloPid_Step(&wheel_pid[wheel], target, measured, delta_seconds,
                            JUANILLO_KP, JUANILLO_KI, JUANILLO_KD,
                            JUANILLO_MAX_PWM, output);
#else
    (void)target;
    (void)measured;
    (void)delta_seconds;
    JuanilloPid_Reset(&wheel_pid[wheel]);
    *output = 0;
    return false;
#endif
}
