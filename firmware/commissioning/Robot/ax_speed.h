#ifndef AX_SPEED_H
#define AX_SPEED_H

#include <stdbool.h>
#include <stdint.h>

void AX_SPEED_Reset(void);
bool AX_SPEED_Wheel(unsigned wheel, float target, float measured, float delta_seconds, int16_t *output);

#endif
