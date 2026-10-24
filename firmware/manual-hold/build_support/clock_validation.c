#include "clock_validation.h"

bool JUANILLO_ClockRegistersValid(uint32_t control, uint32_t configuration, uint32_t pll_configuration, uint32_t core_frequency)
{
    const uint32_t required_ready = (1u << 17) | (1u << 25);
    const uint32_t configuration_mask = 0x0000fcffu;
    const uint32_t required_configuration = 0x0000940au;
    const uint32_t pll_mask = 0x0f437fffu;
    const uint32_t required_pll = 0x07405408u;
    return (control & required_ready) == required_ready &&
           (configuration & configuration_mask) == required_configuration &&
           (pll_configuration & pll_mask) == required_pll &&
           core_frequency == 168000000u;
}
