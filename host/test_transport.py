import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock

from transport import DebugTransport, HostError, RawJournal, disable_hupcl, valid_port

FAKE_PORT = "COM3" if sys.platform == "win32" else "/dev/fake-debug"


class FakeSerial:
    def __init__(self, **options):
        self.options = options
        self.dtr = None
        self.rts = None
        self.open_snapshot = None
        self.port = None
        self.closed = 0
        self.writes = []
        self.buffer = bytearray()
        self.short_write = False

    def open(self):
        self.open_snapshot = (self.port, self.dtr, self.rts)

    def close(self):
        self.closed += 1

    def flush(self):
        pass

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data) - 1 if self.short_write else len(data)

    def read(self, count):
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "run"
        self.journal = RawJournal(self.path)
        self.addCleanup(self.journal.close)
        self.serial = None

    def factory(self, **options):
        self.serial = FakeSerial(**options)
        return self.serial

    def open_fake(self):
        return DebugTransport.open(FAKE_PORT, self.journal, factory=self.factory,
                                   hupcl_setter=lambda _: None)

    def test_application_open_has_no_reset_pulse(self):
        transport = self.open_fake()
        self.assertEqual(self.serial.open_snapshot, (FAKE_PORT, True, False))
        self.assertEqual(self.serial.options["baudrate"], 230400)
        self.assertEqual(self.serial.options["parity"], "N")
        transport.close()
        self.assertEqual((self.serial.dtr, self.serial.rts), (True, False))
        self.assertEqual(self.serial.closed, 1)
        transport.close()
        self.assertEqual(self.serial.closed, 1)

    def test_raw_transcript_preserves_bytes(self):
        transport = self.open_fake()
        transport.write(b"\xaa\x55\x00\xff")
        self.serial.buffer.extend(b"\x00\x79\xff")
        self.assertEqual(transport.read(3), b"\x00\x79\xff")
        transport.close()
        events = [json.loads(line) for line in (self.path / "raw.jsonl").read_text().splitlines()]
        raw = [event for event in events if event["event"] == "raw"]
        self.assertEqual([(event["direction"], event["hex"]) for event in raw],
                         [("tx-requested", "aa5500ff"), ("rx", "0079ff")])

    def test_short_write_is_not_retried(self):
        transport = self.open_fake()
        self.serial.short_write = True
        with self.assertRaisesRegex(HostError, "no se reintenta"):
            transport.write(b"abc")
        self.assertEqual(self.serial.writes, [b"abc"])
        transport.close()

    def test_log_failure_prevents_transmission(self):
        transport = self.open_fake()
        with mock.patch.object(self.journal, "raw", side_effect=OSError("disk")), \
                self.assertRaises(OSError):
            transport.write(b"abc")
        self.assertEqual(self.serial.writes, [])
        transport.close()

    def test_hupcl_failure_closes_without_transmission(self):
        def fail(_):
            raise HostError("HUPCL")
        with self.assertRaisesRegex(HostError, "HUPCL"):
            DebugTransport.open(FAKE_PORT, self.journal, factory=self.factory,
                                hupcl_setter=fail)
        self.assertEqual(self.serial.writes, [])
        self.assertEqual(self.serial.closed, 1)

    def test_journal_never_overwrites_directory_or_report(self):
        with self.assertRaises(FileExistsError):
            RawJournal(self.path)
        self.journal.report({"status": "offline"})
        with self.assertRaises(FileExistsError):
            self.journal.report({"status": "changed"})
        self.assertEqual(json.loads((self.path / "result.json").read_text()), {"status": "offline"})

    def test_windows_accepts_com_ports_without_posix_termios(self):
        with mock.patch("transport.sys.platform", "win32"):
            self.assertTrue(valid_port("COM3"))
            self.assertTrue(valid_port(r"\\.\COM12"))
            self.assertFalse(valid_port("relative-port"))
            self.assertFalse(valid_port("/dev/ttyUSB0"))
            self.assertFalse(disable_hupcl(mock.Mock()))
            transport = DebugTransport.open("COM3", self.journal, factory=self.factory)
            self.assertNotIn("exclusive", self.serial.options)
            self.assertEqual(self.serial.open_snapshot, ("COM3", True, False))
            transport.close()

    def test_posix_rejects_relative_device_paths(self):
        with mock.patch("transport.sys.platform", "linux"):
            self.assertTrue(valid_port("/dev/fake-debug"))
            self.assertFalse(valid_port("ttyUSB0"))


if __name__ == "__main__":
    unittest.main()
