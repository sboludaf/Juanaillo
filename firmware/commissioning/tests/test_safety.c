#include "juanillo_safety.h"

#include <assert.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static JuanilloConfig test_config(bool motion_enabled)
{
    JuanilloConfig config = {motion_enabled, motion_enabled, 200, 400, 250, 50};
    return config;
}

static uint8_t feed(JuanilloSafety *safety, uint8_t frame_id, const uint8_t *payload, size_t length, uint32_t now_ms)
{
    uint8_t packet[69];
    size_t packet_length = JuanilloSafety_Packet(frame_id, payload, length, packet, sizeof(packet));
    assert(packet_length != 0);
    uint8_t events = 0;
    for (size_t offset = 0; offset < packet_length; ++offset) {
        events |= JuanilloSafety_Feed(safety, packet[offset], now_ms);
    }
    return events;
}

static void zero(JuanilloSafety *safety, uint32_t now_ms)
{
    const uint8_t payload[6] = {0};
    assert(feed(safety, 0x50, payload, sizeof(payload), now_ms) == JUANILLO_EVENT_STOP);
}

static void arm(JuanilloSafety *safety, uint32_t now_ms)
{
    const uint8_t token[4] = {'A', 'R', 'M', '!'};
    feed(safety, 0x61, token, sizeof(token), now_ms);
}

static void positive_velocity(JuanilloSafety *safety, uint32_t now_ms)
{
    const uint8_t payload[6] = {0, 100, 0, 0, 0, 200};
    feed(safety, 0x50, payload, sizeof(payload), now_ms);
}

static void test_locked_never_arms(void)
{
    JuanilloConfig config = test_config(false);
    JuanilloSafety safety;
    JuanilloSafety_Init(&safety, &config, 10);
    JuanilloSafety_Ready(&safety, 20);
    for (uint32_t attempt = 0; attempt < 100; ++attempt) {
        zero(&safety, 30 + attempt);
        arm(&safety, 31 + attempt);
        positive_velocity(&safety, 32 + attempt);
        assert(safety.state == JUANILLO_DISARMED);
        assert(safety.linear_mm_s == 0 && safety.angular_mrad_s == 0);
    }
    uint8_t status[16];
    JuanilloSafety_Status(&safety, 150, status);
    assert(status[0] == 1 && status[1] == 0 && status[2] == 0 && status[3] == 1);
}

static void test_ready_and_zero_required(void)
{
    JuanilloConfig config = test_config(true);
    JuanilloSafety safety;
    JuanilloSafety_Init(&safety, &config, 0);
    zero(&safety, 1);
    arm(&safety, 2);
    assert(safety.state == JUANILLO_DISARMED && !safety.has_recent_zero);
    JuanilloSafety_Ready(&safety, 3);
    arm(&safety, 4);
    assert(safety.state == JUANILLO_DISARMED);
    zero(&safety, 5);
    arm(&safety, 6);
    assert(safety.state == JUANILLO_ARMED);
    positive_velocity(&safety, 7);
    assert(safety.linear_mm_s == 100 && safety.angular_mrad_s == 200);
}

static void test_stop_disarms_immediately(void)
{
    JuanilloConfig config = test_config(true);
    JuanilloSafety safety;
    JuanilloSafety_Init(&safety, &config, 0);
    JuanilloSafety_Ready(&safety, 0);
    zero(&safety, 1);
    arm(&safety, 2);
    positive_velocity(&safety, 3);
    zero(&safety, 4);
    assert(safety.state == JUANILLO_DISARMED);
    assert(safety.linear_mm_s == 0 && safety.angular_mrad_s == 0);
    positive_velocity(&safety, 5);
    assert(safety.state == JUANILLO_DISARMED && safety.linear_mm_s == 0);
    arm(&safety, 6);
    assert(safety.state == JUANILLO_DISARMED);
}

static void test_timeout_and_wrap(void)
{
    JuanilloConfig config = test_config(true);
    JuanilloSafety safety;
    uint32_t start = UINT32_MAX - 100u;
    JuanilloSafety_Init(&safety, &config, start);
    JuanilloSafety_Ready(&safety, start);
    zero(&safety, start + 1u);
    arm(&safety, start + 2u);
    positive_velocity(&safety, start + 3u);
    JuanilloSafety_Tick(&safety, start + 252u);
    assert(safety.state == JUANILLO_ARMED);
    JuanilloSafety_Tick(&safety, start + 253u);
    assert(safety.state == JUANILLO_DISARMED && safety.reason == JUANILLO_REASON_TIMEOUT);
    assert(safety.linear_mm_s == 0);
    positive_velocity(&safety, start + 254u);
    assert(safety.state == JUANILLO_DISARMED);
    zero(&safety, start + 300u);
    arm(&safety, start + 301u);
    assert(safety.state == JUANILLO_ARMED);
    positive_velocity(&safety, start + 600u);
    assert(safety.state == JUANILLO_DISARMED);
}

static void test_queries_do_not_refresh_and_fault_answers(void)
{
    JuanilloConfig config = test_config(true);
    JuanilloSafety safety;
    JuanilloSafety_Init(&safety, &config, 0);
    JuanilloSafety_Ready(&safety, 0);
    zero(&safety, 1);
    arm(&safety, 2);
    positive_velocity(&safety, 3);
    assert(feed(&safety, 0x60, NULL, 0, 200) == JUANILLO_EVENT_STATUS);
    assert(feed(&safety, 0x63, NULL, 0, 240) == JUANILLO_EVENT_ENCODERS);
    assert(safety.velocity_ms == 3);
    JuanilloSafety_Tick(&safety, 253);
    assert(safety.state == JUANILLO_DISARMED);
    JuanilloSafety_Fault(&safety, JUANILLO_REASON_RX_FAULT);
    assert(feed(&safety, 0x60, NULL, 0, 260) == JUANILLO_EVENT_STATUS);
    zero(&safety, 270);
    arm(&safety, 271);
    assert(safety.state == JUANILLO_FAULT);
    uint8_t status[16];
    JuanilloSafety_Status(&safety, 300, status);
    assert(status[2] == 2 && status[3] == 2);
    assert(status[12] == 0 && status[13] == JUANILLO_REASON_RX_FAULT);
    assert(status[14] == 0 && status[15] == 0);
}

static void test_bad_range_lateral_and_token(void)
{
    JuanilloConfig config = test_config(true);
    JuanilloSafety safety;
    JuanilloSafety_Init(&safety, &config, 0);
    JuanilloSafety_Ready(&safety, 0);
    zero(&safety, 1);
    const uint8_t bad_token[4] = {'A', 'R', 'M', '?'};
    feed(&safety, 0x61, bad_token, 4, 2);
    assert(safety.state == JUANILLO_DISARMED);
    arm(&safety, 3);
    const uint8_t lateral[6] = {0, 0, 0, 1, 0, 0};
    feed(&safety, 0x50, lateral, 6, 4);
    assert(safety.state == JUANILLO_DISARMED && safety.reason == JUANILLO_REASON_RANGE);
    assert(safety.velocity_ms == 1);
    zero(&safety, 5);
    arm(&safety, 6);
    const uint8_t excessive[6] = {0x80, 0, 0, 0, 0, 0};
    feed(&safety, 0x50, excessive, 6, 7);
    assert(safety.state == JUANILLO_DISARMED && safety.linear_mm_s == 0);
}

static void test_parser_fragmentation_and_malformed(void)
{
    JuanilloConfig config = test_config(true);
    JuanilloSafety safety;
    JuanilloSafety_Init(&safety, &config, 0);
    JuanilloSafety_Ready(&safety, 0);
    uint8_t frame[69];
    uint8_t payload[6] = {0};
    size_t length = JuanilloSafety_Packet(0x50, payload, 6, frame, sizeof(frame));
    assert(length == 11 && frame[10] == 0x5A);
    for (size_t offset = 0; offset < 5; ++offset) {
        JuanilloSafety_Feed(&safety, frame[offset], 1);
    }
    for (size_t offset = 5; offset < length; ++offset) {
        JuanilloSafety_Feed(&safety, frame[offset], 2);
    }
    assert(safety.has_velocity && safety.velocity_ms == 2);
    frame[length - 1] ^= 1;
    for (size_t offset = 0; offset < length; ++offset) {
        JuanilloSafety_Feed(&safety, frame[offset], 3);
    }
    assert(safety.velocity_ms == 2);
    for (size_t offset = 0; offset < 4; ++offset) {
        JuanilloSafety_Feed(&safety, frame[offset], 4);
    }
    JuanilloSafety_Tick(&safety, 54);
    assert(safety.frame_used == 0);
    for (size_t offset = 4; offset < length; ++offset) {
        JuanilloSafety_Feed(&safety, frame[offset], 55);
    }
    assert(safety.velocity_ms == 2);
    uint8_t short_payload = 0;
    feed(&safety, 0x50, &short_payload, 1, 56);
    assert(safety.velocity_ms == 2);
    for (uint32_t frame_length = 0; frame_length <= UINT8_MAX; ++frame_length) {
        JuanilloSafety_Tick(&safety, 100 + frame_length * 100);
        JuanilloSafety_Feed(&safety, 0xAA, 100 + frame_length * 100);
        JuanilloSafety_Feed(&safety, 0x55, 100 + frame_length * 100);
        JuanilloSafety_Feed(&safety, (uint8_t)frame_length, 100 + frame_length * 100);
        for (uint32_t offset = 0; offset < 260; ++offset) {
            JuanilloSafety_Feed(&safety, 0, 100 + frame_length * 100);
            assert(safety.frame_used < JUANILLO_MAX_FRAME);
        }
    }
}

static void test_random_stream_and_profile_fault(void)
{
    struct {
        uint32_t before;
        JuanilloSafety safety;
        uint32_t after;
    } guarded;
    JuanilloConfig config = test_config(false);
    guarded.before = 0x12345678;
    guarded.after = 0xABCDEF01;
    JuanilloSafety_Init(&guarded.safety, &config, 0);
    JuanilloSafety_Ready(&guarded.safety, 0);
    uint32_t random_value = 7;
    for (uint32_t offset = 0; offset < 300000; ++offset) {
        random_value = random_value * 1664525u + 1013904223u;
        JuanilloSafety_Feed(&guarded.safety, (uint8_t)(random_value >> 16), offset);
        assert(guarded.safety.state != JUANILLO_ARMED);
    }
    assert(guarded.before == 0x12345678 && guarded.after == 0xABCDEF01);
    config.motion_enabled = true;
    JuanilloSafety_Init(&guarded.safety, &config, 0);
    JuanilloSafety_Ready(&guarded.safety, 0);
    zero(&guarded.safety, 1);
    arm(&guarded.safety, 2);
    assert(guarded.safety.state == JUANILLO_FAULT && !guarded.safety.ready);
}

static void test_pid_saturation_reset_and_invalid(void)
{
    JuanilloPid pid = {0};
    int16_t output = 0;
    for (unsigned iteration = 0; iteration < 10000; ++iteration) {
        assert(JuanilloPid_Step(&pid, 10, 0, 0.02f, 100, 50, 10, 400, &output));
        assert(output <= 400 && output >= -400);
        assert(pid.integral == 0);
    }
    JuanilloPid_Reset(&pid);
    assert(JuanilloPid_Step(&pid, 0, 0, 0.02f, 100, 50, 10, 400, &output));
    assert(output == 0 && pid.integral == 0 && pid.previous_error == 0);
    assert(JuanilloPid_Step(&pid, -10, 0, 0.02f, 100, 50, 10, 400, &output));
    assert(output == -400);
    assert(!JuanilloPid_Step(&pid, NAN, 0, 0.02f, 100, 50, 10, 400, &output));
    assert(output == 0 && !pid.has_previous);
    assert(!JuanilloPid_Step(&pid, 1, 0, 0, 100, 50, 10, 400, &output));
    assert(output == 0);
}

int main(void)
{
    test_locked_never_arms();
    test_ready_and_zero_required();
    test_stop_disarms_immediately();
    test_timeout_and_wrap();
    test_queries_do_not_refresh_and_fault_answers();
    test_bad_range_lateral_and_token();
    test_parser_fragmentation_and_malformed();
    test_random_stream_and_profile_fault();
    test_pid_saturation_reset_and_invalid();
    puts("PASS: 9 native safety/parser/PID groups, malformed lengths, 300000-byte fuzz, no hardware");
    return 0;
}
