#ifndef JUANILLO_CLOCK_VALIDATION_H
#define JUANILLO_CLOCK_VALIDATION_H

#include <stdbool.h>
#include <stdint.h>

bool JUANILLO_ClockRegistersValid(uint32_t control, uint32_t configuration, uint32_t pll_configuration, uint32_t core_frequency);

#endif
