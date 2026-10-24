import struct
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from web.serial_client import (CAPS_BYTES, EXPECTED, MARKER, PROFILE, DeviceError, INFO, MOVE, STOP,
                               ManualClient, SerialTransport, STATUS_FORMAT, StaleHold, frame,
                               sha256, verify_manifest)


class Wire:
    def __init__(self, *, caps=CAPS_BYTES, profile=PROFILE):
        self.buffer, self.commands, self.state, self.nonce = bytearray(), [], 0, 12345
        self.direction, self.bad_checksum, self.closed = 0, False, False
        self.caps, self.profile = caps, profile

    def write(self, data):
        self.commands.append(bytes(data))
        command = data[3]
        if command == INFO:
            payload = self.caps
        else:
            if command == MOVE:
                assert len(data) == 14
                nonce, direction = struct.unpack(">Qb", data[4:-1])
                assert nonce == 12345 and direction in (1, -1, 2, -2)
                self.state, self.direction = 2, direction
            elif command == STOP:
                self.state, self.direction = 0, 0
            active = self.state in (1, 2)
            payload = struct.pack(STATUS_FORMAT, 1, self.profile, self.state, 7 if active else 9,
                                  100, 150 if active else 0, self.nonce, 0, 0, 0, 0,
                                  1, 3 if active else 1, self.direction, 9000 if active else 0)
        result = bytearray(frame(command, payload))
        if self.bad_checksum:
            result[-1] ^= 1
        self.buffer.extend(result)

    def read(self, count):
        result = bytes(self.buffer[:count]); del self.buffer[:count]
        return result

    def close(self):
        self.closed = True


class SerialClientTests(unittest.TestCase):
    def test_turn_contract_caps_and_signed_wire_directions(self):
        self.assertEqual(len(MARKER), 28)
        self.assertEqual(len(CAPS_BYTES), 48)
        self.assertEqual(struct.unpack(">BBBBHHHHII", CAPS_BYTES[:20]),
                         (1, 6, 15, 10, 100, 5000, 4, 10000, 10000000, 150))
        wire = Wire(); client = ManualClient(wire); client.identify()
        for direction in (2, -2):
            self.assertEqual(client.move(direction)["direction_value"], direction)
            self.assertEqual(struct.unpack(">Qb", wire.commands[-1][4:-1]), (12345, direction))
            self.assertEqual(len(wire.commands[-1]), 14)
        self.assertTrue(client.stop()["all_low"])

    def test_profile5_caps_never_receive_move_or_turn(self):
        old_caps = struct.pack(">BBBBHHHHII", 1, 5, 15, 10, 100, 5000, 4, 10000, 10000000, 150) + b"H60_MANUAL_HOLD_CONTROL_V1__"
        wire = Wire(caps=old_caps, profile=5); client = ManualClient(wire)
        with self.assertRaisesRegex(DeviceError, "perfil 6"):
            client.identify()
        for direction in (1, -1, 2, -2):
            with self.assertRaises(DeviceError):
                client.move(direction)
        self.assertEqual([packet[3] for packet in wire.commands], [INFO])
        self.assertFalse(client.verified)

    def test_profile5_status_even_after_new_caps_locks_session(self):
        wire = Wire(profile=5); client = ManualClient(wire)
        with self.assertRaisesRegex(DeviceError, "perfil 6"):
            client.identify()
        with self.assertRaises(DeviceError):
            client.move(-2)
        self.assertNotIn(MOVE, [packet[3] for packet in wire.commands])
        self.assertTrue(client.failed)

    def test_unsupported_direction_bounds_rejected_before_tx(self):
        wire = Wire(); client = ManualClient(wire); client.identify()
        before = len(wire.commands)
        for direction in (0, 3, -3, 128, -129, True, 1.0, None):
            with self.subTest(direction=direction), self.assertRaises(DeviceError):
                client.move(direction)
        self.assertEqual(len(wire.commands), before)

    def test_profile6_manifest_vectors_and_profile5_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); build = root / "build"; build.mkdir()
            source = root / "main.c"; source.write_text("/* synthetic manifest fixture */")
            binary = bytearray(64)
            struct.pack_into("<II", binary, 0, 0x20020000, 0x08000009)
            binary[8:8 + len(MARKER) + 1] = MARKER + b"\0"
            for name, data in {"manual.bin": bytes(binary), "manual.hex": b"synthetic hex",
                               "manual.elf": b"synthetic elf", "manual.map": b"synthetic map"}.items():
                (build / name).write_bytes(data)
            manifest = {**EXPECTED, "image_bytes": len(binary), "payload_sha256": sha256(binary),
                        "sources": {"main.c": sha256(source.read_bytes())},
                        "artifacts": {p.name: sha256(p.read_bytes()) for p in build.iterdir()}}
            path = build / "manifest.json"
            path.write_text(json.dumps(manifest))
            self.assertEqual(verify_manifest(path, sha256(path.read_bytes()))["profile"], 6)
            self.assertEqual(manifest["left_raw_directions"], [1, 1, 1, 1])
            self.assertEqual(manifest["right_raw_directions"], [-1, -1, -1, -1])
            manifest["profile"] = 5; path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(DeviceError, "perfil 6"):
                verify_manifest(path, sha256(path.read_bytes()))

    def test_profile_and_move14_status44_contract(self):
        wire = Wire(); client = ManualClient(wire)
        self.assertEqual(client.identify()["state"], "idle")
        self.assertEqual(client.move(1)["direction_value"], 1)
        self.assertEqual(client.move(-1)["direction_value"], -1)
        self.assertTrue(client.stop()["all_low"])
        self.assertEqual([p[3] for p in wire.commands], [0x76, 0x70, 0x77, 0x77, 0x74])

    def test_cancelled_hold_sends_no_move(self):
        wire = Wire(); client = ManualClient(wire); client.identify()
        before = len(wire.commands)
        with self.assertRaises(StaleHold):
            client.move(1, permit=lambda: False)
        self.assertEqual(len(wire.commands), before)

    def test_checksum_failure_locks_session_without_replay_but_allows_stop(self):
        wire = Wire(); client = ManualClient(wire); client.identify(); wire.bad_checksum = True
        with self.assertRaises(DeviceError):
            client.move(1)
        sent = len(wire.commands)
        with self.assertRaises(DeviceError):
            client.move(1)
        self.assertEqual(len(wire.commands), sent)
        wire.bad_checksum = False; client.stop()
        self.assertEqual(wire.commands[-1][3], STOP)

    def test_nonce_reset_is_detected(self):
        wire = Wire(); client = ManualClient(wire); client.identify(); wire.nonce += 1
        with self.assertRaises(DeviceError):
            client.status()
        with self.assertRaises(DeviceError):
            client.move(1)

    def test_open_waits350_once_before_any_tx_without_requested_reset(self):
        events = []
        serial = Mock()
        serial.open.side_effect = lambda: events.append("open")
        def hupcl(_):
            events.append("hupcl")
        def settle(seconds):
            self.assertEqual(seconds, .350)
            serial.write.assert_not_called()
            self.assertEqual(events, ["open", "hupcl"])
            self.assertIs(serial.dtr, True)
            self.assertIs(serial.rts, False)
            events.append("settle")
        transport = SerialTransport.open("/dev/ttyFAKE", Mock(), factory=lambda **_: serial,
                                         hupcl=hupcl, sleep=settle)
        self.assertEqual(events, ["open", "hupcl", "settle"])
        serial.write.assert_not_called()
        serial.open.assert_called_once()
        transport.close(); serial.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
