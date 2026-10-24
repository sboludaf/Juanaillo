#include <assert.h>
#include <stdio.h>
#include "clock_validation.h"

int main(void)
{
    const uint32_t control = 0x03030000u;
    const uint32_t configuration = 0x0000940au;
    const uint32_t pll = 0x07405408u;
    const uint32_t frequency = 168000000u;
    assert(JUANILLO_ClockRegistersValid(control, configuration, pll, frequency));
    assert(!JUANILLO_ClockRegistersValid(control & ~(1u << 17), configuration, pll, frequency));
    assert(!JUANILLO_ClockRegistersValid(control & ~(1u << 25), configuration, pll, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration & ~3u, pll, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration & ~12u, pll, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration | 0x80u, pll, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration ^ 0x400u, pll, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration ^ 0x2000u, pll, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration, pll ^ 1u, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration, pll ^ 0x40u, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration, pll ^ 0x10000u, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration, pll ^ 0x01000000u, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration, pll & ~0x00400000u, frequency));
    assert(!JUANILLO_ClockRegistersValid(control, configuration, pll, 16000000u));
    assert(JUANILLO_ClockRegistersValid(control | 0x80u, configuration | 0x80000000u, pll, frequency));
    puts("clock register validation: 15 assertions passed");
    return 0;
}
