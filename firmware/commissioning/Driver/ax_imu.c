#include "ax_imu.h"

#include <limits.h>
#include <string.h>

static bool config_matches(AX_IMU_Device *device)
{
    uint8_t identity = 0;
    uint8_t control[7] = {0};
    return device->bus.read(device->bus.context, 0x00, &identity, 1) && identity == 0x05 &&
           device->bus.read(device->bus.context, 0x02, control, sizeof(control)) &&
           control[0] == 0x40 && control[1] == 0x14 && control[2] == 0x54 &&
           control[4] == 0x77 && control[6] == 0x83;
}

static bool wait_status(AX_IMU_Device *device, uint8_t mask, bool high)
{
    uint32_t started = device->bus.now_us(device->bus.context);
    for (unsigned attempt = 0; attempt < 64; ++attempt) {
        uint8_t status = 0;
        if (!device->bus.read(device->bus.context, 0x2D, &status, 1) ||
            (uint32_t)(device->bus.now_us(device->bus.context) - started) >= 5000u) {
            return false;
        }
        if (((status & mask) != 0) == high) {
            return true;
        }
        if (!device->bus.delay_us(device->bus.context, 100)) {
            return false;
        }
    }
    return false;
}

bool AX_IMU_InitWithBus(AX_IMU_Device *device, const AX_IMU_Bus *bus)
{
    memset(device, 0, sizeof(*device));
    if (bus == NULL || bus->read == NULL || bus->write == NULL || bus->delay_us == NULL || bus->now_us == NULL) {
        return false;
    }
    device->bus = *bus;
    uint8_t identity = 0;
    if (!bus->read(bus->context, 0x00, &identity, 1) || identity != 0x05 ||
        !bus->write(bus->context, 0x60, 0xB0) || !bus->delay_us(bus->context, 150000)) {
        return false;
    }
    static const uint8_t registers[][2] = {
        {0x08, 0x00}, {0x02, 0x40}, {0x03, 0x14},
        {0x04, 0x54}, {0x06, 0x77}
    };
    for (unsigned offset = 0; offset < sizeof(registers) / sizeof(registers[0]); ++offset) {
        if (!bus->write(bus->context, registers[offset][0], registers[offset][1])) {
            return false;
        }
    }
    if (!wait_status(device, 0x80, false) ||
        !bus->write(bus->context, 0x0B, 0x01) || !bus->write(bus->context, 0x0A, 0x12) ||
        !wait_status(device, 0x80, true) || !bus->write(bus->context, 0x0A, 0x00) ||
        !wait_status(device, 0x80, false) || !bus->write(bus->context, 0x08, 0x83) ||
        !bus->delay_us(bus->context, 3000) || !config_matches(device)) {
        return false;
    }
    device->initialized = true;
    return true;
}

static uint32_t read_u24(const uint8_t input[3])
{
    return (uint32_t)input[0] | ((uint32_t)input[1] << 8) | ((uint32_t)input[2] << 16);
}

static int16_t read_i16(const uint8_t input[2])
{
    uint16_t value = (uint16_t)input[0] | ((uint16_t)input[1] << 8);
    return value <= INT16_MAX ? (int16_t)value : (int16_t)((int32_t)value - 65536);
}

bool AX_IMU_ReadWithBus(AX_IMU_Device *device, AX_IMU_Sample *sample)
{
    sample->valid = false;
    if (!device->initialized || !config_matches(device)) {
        device->initialized = false;
        return false;
    }
    uint8_t status = 0;
    uint8_t values[17];
    if (!device->bus.read(device->bus.context, 0x2D, &status, 1) || (status & 0x01) == 0 ||
        !wait_status(device, 0x02, true) ||
        !device->bus.read(device->bus.context, 0x30, values, sizeof(values))) {
        device->initialized = false;
        return false;
    }
    uint32_t timestamp = read_u24(values);
    if (device->has_timestamp && timestamp == device->timestamp) {
        device->initialized = false;
        return false;
    }
    for (unsigned axis = 0; axis < 3; ++axis) {
        sample->acceleration[axis] = read_i16(values + 5 + axis * 2);
        sample->gyroscope[axis] = read_i16(values + 11 + axis * 2);
    }
    sample->valid = true;
    device->timestamp = timestamp;
    device->has_timestamp = true;
    return true;
}

#ifndef JUANILLO_NATIVE_TEST
#include "stm32f4xx.h"
#include "juanillo_profile.h"

static AX_IMU_Device hardware_device;
static uint32_t transaction_start;
static uint32_t last_clock_cycles;
static uint64_t elapsed_clock_cycles;

static uint32_t bus_now_us(void *context)
{
    (void)context;
    uint32_t cycles = DWT->CYCCNT;
    elapsed_clock_cycles += (uint32_t)(cycles - last_clock_cycles);
    last_clock_cycles = cycles;
    return (uint32_t)(elapsed_clock_cycles / (SystemCoreClock / 1000000u));
}

static bool delay_cycles(uint32_t microseconds)
{
    uint32_t cycles = (SystemCoreClock / 1000000u) * microseconds;
    uint32_t start = DWT->CYCCNT;
    uint32_t guard = cycles * 4u + 100u;
    while ((uint32_t)(DWT->CYCCNT - start) < cycles && guard != 0) {
        --guard;
    }
    return (uint32_t)(DWT->CYCCNT - start) >= cycles;
}

static bool delay_bus(void *context, uint32_t microseconds)
{
    (void)context;
    return microseconds <= 150000u && delay_cycles(microseconds);
}

static bool transaction_ok(void)
{
    return (uint32_t)(DWT->CYCCNT - transaction_start) < (SystemCoreClock / 1000u) * 6u;
}

static void set_sda(bool high)
{
    if (high) {
        GPIO_SetBits(GPIOB, GPIO_Pin_7);
    } else {
        GPIO_ResetBits(GPIOB, GPIO_Pin_7);
    }
}

static void lower_scl(void)
{
    GPIO_ResetBits(GPIOB, GPIO_Pin_6);
}

static bool raise_scl(void)
{
    GPIO_SetBits(GPIOB, GPIO_Pin_6);
    uint32_t start = DWT->CYCCNT;
    for (uint32_t attempts = 0; attempts < 20000u; ++attempts) {
        if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_6) != Bit_RESET) {
            return transaction_ok() && delay_cycles(2);
        }
        if ((uint32_t)(DWT->CYCCNT - start) > (SystemCoreClock / 1000000u) * 100u) {
            return false;
        }
    }
    return false;
}

static bool start_bus(void)
{
    set_sda(true);
    if (!raise_scl() || GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_7) == Bit_RESET) {
        return false;
    }
    set_sda(false);
    bool success = delay_cycles(2);
    lower_scl();
    return success;
}

static bool stop_bus(void)
{
    lower_scl();
    set_sda(false);
    if (!delay_cycles(2) || !raise_scl()) {
        set_sda(true);
        return false;
    }
    set_sda(true);
    return delay_cycles(2) && transaction_ok();
}

static bool write_byte(uint8_t value)
{
    for (unsigned bit_index = 0; bit_index < 8; ++bit_index) {
        set_sda((value & 0x80u) != 0);
        value = (uint8_t)(value << 1);
        if (!delay_cycles(2) || !raise_scl()) {
            return false;
        }
        lower_scl();
    }
    set_sda(true);
    if (!delay_cycles(2) || !raise_scl()) {
        return false;
    }
    bool acknowledged = GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_7) == Bit_RESET;
    lower_scl();
    return acknowledged && transaction_ok();
}

static bool read_byte(uint8_t *value, bool acknowledge)
{
    uint8_t received = 0;
    set_sda(true);
    for (unsigned bit_index = 0; bit_index < 8; ++bit_index) {
        if (!delay_cycles(2) || !raise_scl()) {
            return false;
        }
        received = (uint8_t)(received << 1);
        if (GPIO_ReadInputDataBit(GPIOB, GPIO_Pin_7) != Bit_RESET) {
            received |= 1u;
        }
        lower_scl();
    }
    set_sda(!acknowledge);
    if (!delay_cycles(2) || !raise_scl()) {
        return false;
    }
    lower_scl();
    set_sda(true);
    *value = received;
    return transaction_ok();
}

static bool read_register(void *context, uint8_t reg, uint8_t *data, size_t length)
{
    (void)context;
    if (length == 0 || length > 17) {
        return false;
    }
    transaction_start = DWT->CYCCNT;
    bool success = start_bus() && write_byte((uint8_t)(JUANILLO_QMI_ADDRESS << 1)) &&
                   write_byte(reg) && start_bus() && write_byte((uint8_t)((JUANILLO_QMI_ADDRESS << 1) | 1u));
    for (size_t offset = 0; success && offset < length; ++offset) {
        success = read_byte(data + offset, offset + 1 < length);
    }
    bool stopped = stop_bus();
    return success && stopped;
}

static bool write_register(void *context, uint8_t reg, uint8_t value)
{
    (void)context;
    transaction_start = DWT->CYCCNT;
    bool success = start_bus() && write_byte((uint8_t)(JUANILLO_QMI_ADDRESS << 1)) && write_byte(reg) && write_byte(value);
    bool stopped = stop_bus();
    return success && stopped;
}

bool AX_IMU_InitChecked(void)
{
    GPIO_InitTypeDef gpio;
    if (SystemCoreClock < 1000000u) {
        return false;
    }
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    if (!delay_cycles(2)) {
        return false;
    }
    RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOB, ENABLE);
    GPIO_SetBits(GPIOB, GPIO_Pin_6 | GPIO_Pin_7);
    GPIO_StructInit(&gpio);
    gpio.GPIO_Pin = GPIO_Pin_6 | GPIO_Pin_7;
    gpio.GPIO_Mode = GPIO_Mode_OUT;
    gpio.GPIO_OType = GPIO_OType_OD;
    gpio.GPIO_Speed = GPIO_Speed_50MHz;
    gpio.GPIO_PuPd = GPIO_PuPd_UP;
    GPIO_Init(GPIOB, &gpio);
    last_clock_cycles = DWT->CYCCNT;
    elapsed_clock_cycles = 0;
    AX_IMU_Bus bus = {NULL, read_register, write_register, delay_bus, bus_now_us};
    return AX_IMU_InitWithBus(&hardware_device, &bus);
}

bool AX_IMU_ReadChecked(AX_IMU_Sample *sample)
{
    return AX_IMU_ReadWithBus(&hardware_device, sample);
}
#endif
