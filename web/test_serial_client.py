import struct
import unittest
from unittest.mock import Mock

from web.serial_client import (CAPS_BYTES, DeviceError, INFO, MOVE, STOP, ManualClient,
                               SerialTransport, STATUS_FORMAT, StaleHold, frame)


class Wire:
    def __init__(self):
        self.buffer, self.commands, self.state, self.nonce = bytearray(), [], 0, 12345
        self.direction, self.bad_checksum, self.closed = 0, False, False

    def write(self, data):
        self.commands.append(bytes(data))
        command = data[3]
        if command == INFO:
            payload = CAPS_BYTES
        else:
            if command == MOVE:
                assert len(data) == 14
                nonce, direction = struct.unpack(">Qb", data[4:-1])
                assert nonce == 12345 and direction in (-1, 1)
                self.state, self.direction = 2, direction
            elif command == STOP:
                self.state, self.direction = 0, 0
            active = self.state in (1, 2)
            payload = struct.pack(STATUS_FORMAT, 1, 5, self.state, 7 if active else 9,
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
