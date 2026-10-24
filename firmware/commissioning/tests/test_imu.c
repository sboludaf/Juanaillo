#include "ax_imu.h"
#include "juanillo_safety.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t registers[256];
    unsigned operations;
    unsigned fail_at;
    uint32_t microseconds;
    bool deny_lock;
    bool stall_command;
} FakeBus;

static bool operation_ok(FakeBus *bus)
{
    ++bus->operations;
    bus->microseconds += 50;
    return bus->fail_at == 0 || bus->operations != bus->fail_at;
}

static bool fake_read(void *context, uint8_t reg, uint8_t *data, size_t length)
{
    FakeBus *bus = context;
    if (!operation_ok(bus) || (size_t)reg + length > sizeof(bus->registers)) {
        return false;
    }
    if (reg == 0x2D && (bus->registers[0x08] & 0x80) != 0 && (bus->registers[0x2D] & 1) != 0 && !bus->deny_lock) {
        bus->registers[0x2D] |= 2;
    }
    memcpy(data, bus->registers + reg, length);
    if (reg == 0x30 && length == 17) {
        bus->registers[0x2D] &= (uint8_t)~3u;
    }
    return true;
}

static bool fake_write(void *context, uint8_t reg, uint8_t value)
{
    FakeBus *bus = context;
    if (!operation_ok(bus)) {
        return false;
    }
    if (reg == 0x60) {
        memset(bus->registers, 0, sizeof(bus->registers));
        bus->registers[0] = 0x05;
    }
    bus->registers[reg] = value;
    if (reg == 0x0A && value == 0x12 && !bus->stall_command) {
        bus->registers[0x2D] |= 0x80;
    } else if (reg == 0x0A && value == 0) {
        bus->registers[0x2D] &= (uint8_t)~0x80u;
    }
    return true;
}

static bool fake_delay(void *context, uint32_t microseconds)
{
    FakeBus *bus = context;
    assert(microseconds <= 150000u);
    bus->microseconds += microseconds;
    return operation_ok(bus);
}

static uint32_t fake_now(void *context)
{
    FakeBus *bus = context;
    return bus->microseconds;
}

static AX_IMU_Bus make_bus(FakeBus *bus)
{
    AX_IMU_Bus api = {bus, fake_read, fake_write, fake_delay, fake_now};
    return api;
}

static void put_sample(FakeBus *bus)
{
    bus->registers[0x30] = 1;
    bus->registers[0x2D] |= 1;
    const uint8_t values[12] = {0x64, 0, 0xC8, 0, 0, 0x20, 0xFF, 0xFF, 2, 0, 3, 0};
    memcpy(bus->registers + 0x35, values, sizeof(values));
}

static void test_ack_identity_and_config(void)
{
    FakeBus bus = {0};
    bus.registers[0] = 0x05;
    AX_IMU_Bus api = make_bus(&bus);
    AX_IMU_Device device;
    assert(AX_IMU_InitWithBus(&device, &api));
    assert(bus.registers[0x02] == 0x40 && bus.registers[0x08] == 0x83);
    assert(bus.registers[0x0B] == 1 && bus.registers[0x0A] == 0);
    assert(bus.registers[0x03] == 0x14 && bus.registers[0x04] == 0x54);
    assert((bus.registers[0x03] & 0x80) == 0 && (bus.registers[0x04] & 0x80) == 0);
    unsigned init_operations = bus.operations;
    for (unsigned failure = 1; failure <= init_operations; ++failure) {
        memset(&bus, 0, sizeof(bus));
        bus.registers[0] = 0x05;
        bus.fail_at = failure;
        assert(!AX_IMU_InitWithBus(&device, &api));
        assert(!device.initialized);
    }
    memset(&bus, 0, sizeof(bus));
    bus.registers[0] = 0x68;
    assert(!AX_IMU_InitWithBus(&device, &api));
    memset(&bus, 0, sizeof(bus));
    bus.registers[0] = 0x05;
    bus.stall_command = true;
    uint32_t started = bus.microseconds;
    assert(!AX_IMU_InitWithBus(&device, &api));
    assert(bus.microseconds - started < 170000u);
}

static void test_read_failure_stale_and_tearing(void)
{
    FakeBus bus = {0};
    bus.registers[0] = 0x05;
    AX_IMU_Bus api = make_bus(&bus);
    AX_IMU_Device device;
    AX_IMU_Sample sample;
    assert(AX_IMU_InitWithBus(&device, &api));
    put_sample(&bus);
    assert(AX_IMU_ReadWithBus(&device, &sample));
    assert(sample.valid && sample.acceleration[0] == 100 && sample.acceleration[2] == 8192);
    assert(sample.gyroscope[0] == -1 && sample.gyroscope[2] == 3);
    assert(!AX_IMU_ReadWithBus(&device, &sample));
    assert(!sample.valid && !device.initialized);

    assert(AX_IMU_InitWithBus(&device, &api));
    put_sample(&bus);
    bus.deny_lock = true;
    uint32_t started = bus.microseconds;
    assert(!AX_IMU_ReadWithBus(&device, &sample));
    assert(!sample.valid && bus.microseconds - started < 7000u);
    bus.deny_lock = false;

    assert(AX_IMU_InitWithBus(&device, &api));
    put_sample(&bus);
    bus.registers[0x03] |= 0x80;
    assert(!AX_IMU_ReadWithBus(&device, &sample));
    assert(!sample.valid);

    for (unsigned failed_read = 1; failed_read <= 5; ++failed_read) {
        bus.fail_at = 0;
        assert(AX_IMU_InitWithBus(&device, &api));
        put_sample(&bus);
        bus.fail_at = bus.operations + failed_read;
        assert(!AX_IMU_ReadWithBus(&device, &sample));
        assert(!sample.valid && !device.initialized);
    }
}

static void test_no_fake_telemetry(void)
{
    JuanilloTelemetry telemetry = {0};
    uint8_t payload[20];
    memset(payload, 0xA5, sizeof(payload));
    assert(!JuanilloTelemetry_Encode(&telemetry, payload));
    assert(payload[0] == 0xA5);
    telemetry.imu_valid = true;
    telemetry.velocity_valid = true;
    telemetry.battery_valid = true;
    telemetry.battery_centivolts = 1234;
    telemetry.acceleration[2] = 8192;
    telemetry.gyroscope[2] = -100;
    telemetry.measured_linear_m_s = 0.012f;
    telemetry.measured_angular_rad_s = -0.200f;
    assert(JuanilloTelemetry_Encode(&telemetry, payload));
    assert(payload[4] == 0x20 && payload[5] == 0);
    assert(payload[12] == 0 && payload[13] == 12);
    assert(payload[14] == 0 && payload[15] == 0);
    assert(payload[16] == 0xFF && payload[17] == 0x38);
    assert(payload[18] == 0x04 && payload[19] == 0xD2);
    telemetry.imu_valid = false;
    assert(!JuanilloTelemetry_Encode(&telemetry, payload));
    telemetry.imu_valid = true;
    telemetry.measured_linear_m_s = NAN;
    assert(!JuanilloTelemetry_Encode(&telemetry, payload));

    FakeBus bus = {0};
    bus.registers[0] = 0x05;
    AX_IMU_Bus api = make_bus(&bus);
    AX_IMU_Device device;
    AX_IMU_Sample sample;
    assert(AX_IMU_InitWithBus(&device, &api));
    bus.fail_at = bus.operations + 1;
    telemetry.measured_linear_m_s = 0;
    telemetry.imu_valid = AX_IMU_ReadWithBus(&device, &sample) && sample.valid;
    assert(!JuanilloTelemetry_Encode(&telemetry, payload));
}

int main(void)
{
    test_ack_identity_and_config();
    test_read_failure_stale_and_tearing();
    test_no_fake_telemetry();
    puts("PASS: IMU fake-bus failures, LE/readback/self-test off, bounded CMD12/SyncSample lock, stale rejection, no fabricated telemetry");
    return 0;
}
