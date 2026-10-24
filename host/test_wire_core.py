"""Exercise the real C protocol/state core through a simulated serial bridge."""
import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import pulse_client as pulse
from test_pulse_client import Clock

BRIDGE = r'''
#include "pulse.h"
#include <stdlib.h>
#include <string.h>
typedef struct {
    Pulse pulse;
    uint16_t encoders[4];
    bool moved;
    unsigned fire_events;
    uint32_t last_ms;
} Bridge;
void *bridge_new(uint64_t nonce) {
    Bridge *b=calloc(1,sizeof(*b));
    if(!b) return NULL;
    for(unsigned i=0;i<4;i++) b->encoders[i]=(uint16_t)(1000u*(i+1u));
    pulse_init(&b->pulse,nonce,0);
    pulse_observe(&b->pulse,b->encoders,0);
    return b;
}
void bridge_free(void *opaque) { free(opaque); }
unsigned bridge_fires(void *opaque) { return ((Bridge*)opaque)->fire_events; }
size_t bridge_exchange(void *opaque,const uint8_t *input,size_t size,uint32_t now,uint8_t *out) {
    Bridge *b=opaque;
    /* Simulate the independent 1ms SysTick, not just host polling instants. */
    while(b->last_ms<now) {
        ++b->last_ms;
        bool active=b->pulse.state==P_WAKE || b->pulse.state==P_RUNNING;
        uint32_t elapsed=b->last_ms-b->pulse.fire_ms;
        bool finished=active && elapsed>=3004u;
        if(active) {
            uint32_t motion=elapsed>4u?elapsed-4u:0u;
            if(motion>3000u) motion=3000u;
            b->encoders[0]=(uint16_t)(1000u-motion);
            b->encoders[1]=(uint16_t)(2000u+motion*6u/5u);
            b->encoders[2]=(uint16_t)(3000u-motion*7u/5u);
            b->encoders[3]=(uint16_t)(4000u+motion*8u/5u);
        }
        pulse_observe(&b->pulse,b->encoders,b->last_ms);
        pulse_tick(&b->pulse,b->last_ms,finished);
    }
    uint8_t events=0;
    for(size_t i=0;i<size;i++) {
        uint8_t next=pulse_feed(&b->pulse,input[i],now);
        if(next&E_WAKE) b->fire_events++;
        events|=next;
    }
    if(!(events&E_REPLY)) return 0;
    uint8_t payload[64]; size_t length;
    if(events&E_CAPS) { pulse_caps(payload); length=48; }
    else if(events&E_ENCODERS) {
        for(unsigned i=0;i<4;i++) { payload[2*i]=(uint8_t)(b->pulse.counters[i]>>8); payload[2*i+1]=(uint8_t)b->pulse.counters[i]; }
        length=8;
    } else {
        bool low=b->pulse.state!=P_WAKE && b->pulse.state!=P_RUNNING;
        pulse_status(&b->pulse,now,low,payload); length=36;
    }
    return pulse_packet(b->pulse.reply_id,payload,length,out);
}
'''


class CoreSerial:
    def __init__(self, library, clock):
        self.lib = library
        self.clock = clock
        self.handle = library.bridge_new(0x1122334455667788)
        assert self.handle
        self.buffer = bytearray()
        self.commands = []

    def close(self):
        if self.handle:
            self.lib.bridge_free(self.handle)
            self.handle = None

    def write(self, data):
        self.commands.append(data[3])
        source = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        target = (ctypes.c_ubyte * 64)()
        count = self.lib.bridge_exchange(self.handle, source, len(data),
                                         int(self.clock() * 1000), target)
        self.buffer.extend(bytes(target[:count]))
        return len(data)

    def read(self, count):
        self.clock.sleep(.001)
        data = bytes(self.buffer[:count])
        del self.buffer[:count]
        return data


class RealCoreContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform == "win32":
            raise unittest.SkipTest("Puente C nativo validado en Linux; pendiente en Windows.")
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(__file__).resolve().parents[1] / "firmware" / "forward-3s"
        bridge_path = Path(cls.temporary.name) / "bridge.c"
        bridge_path.write_text(BRIDGE)
        shared_path = Path(cls.temporary.name) / "bridge.so"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        "-I" + str(root / "include"), str(root / "src/pulse.c"), str(bridge_path),
                        "-o", str(shared_path)], check=True, capture_output=True, text=True)
        cls.lib = ctypes.CDLL(str(shared_path))
        cls.lib.bridge_new.argtypes = [ctypes.c_uint64]
        cls.lib.bridge_new.restype = ctypes.c_void_p
        cls.lib.bridge_free.argtypes = [ctypes.c_void_p]
        cls.lib.bridge_fires.argtypes = [ctypes.c_void_p]
        cls.lib.bridge_fires.restype = ctypes.c_uint
        cls.lib.bridge_exchange.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                           ctypes.c_uint32, ctypes.c_void_p]
        cls.lib.bridge_exchange.restype = ctypes.c_size_t

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.clock = Clock()
        self.serial = CoreSerial(self.lib, self.clock)
        self.addCleanup(self.serial.close)
        self.client = pulse.Client(self.serial, mock.Mock(), clock=self.clock)

    def test_host_sequence_matches_real_core_wire_and_done(self):
        result = pulse.run_pulse(self.client, sleep=self.clock.sleep)
        self.assertEqual(result["final_status"]["state"], pulse.DONE)
        self.assertEqual(result["final_status"]["flags"], 11)
        self.assertEqual(result["status"], "forward-verified")
        self.assertEqual(result["analysis"]["signed_delta"], [-3000, 3600, -4200, 4800])
        self.assertTrue(result["analysis"]["all_forward"])
        self.assertGreaterEqual(self.serial.commands.count(pulse.LEASE), 100)
        self.assertEqual(self.lib.bridge_fires(self.serial.handle), 1)

    def test_core_fault_before_prepare_never_fires(self):
        self.client.identify()
        self.client.stop()
        with self.assertRaisesRegex(pulse.HostError, "FAULT"):
            self.client.prepare()  # less than one second of quiet, rejected by real C
        self.assertEqual(self.lib.bridge_fires(self.serial.handle), 0)
        with self.assertRaises(pulse.HostError):
            self.client.fire_once()
        self.assertEqual(self.lib.bridge_fires(self.serial.handle), 0)

    def test_real_core_active_lease_expires_and_cannot_be_revived(self):
        self.client.identify()
        self.clock.sleep(1.1)
        self.client.stop()
        self.client.prepare()
        self.client.lease()
        self.client.fire_once()
        self.clock.sleep(.15)
        with self.assertRaisesRegex(pulse.HostError, "FAULT"):
            self.client.status()
        with self.assertRaises(pulse.HostError):
            self.client.lease()
        self.assertEqual(self.lib.bridge_fires(self.serial.handle), 1)
        with self.assertRaises(pulse.HostError):
            self.client.fire_once()
        self.assertEqual(self.lib.bridge_fires(self.serial.handle), 1)


if __name__ == "__main__":
    unittest.main()
