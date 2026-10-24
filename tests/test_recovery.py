import contextlib
import importlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import h60_common as common
import h60_recovery as recovery
from fake_rom import FakeSerial, flash_image, hex_image, identity


class RecoveryTests(unittest.TestCase):
    def test_read_only_rom_and_signature(self):
        fake = FakeSerial()
        rom = common.Rom(fake)
        rom.connect()
        self.assertEqual(common.identity_key(rom.identify()), common.identity_key(identity()))
        self.assertEqual(rom.read_memory(common.FLASH_BASE + 100, 10), flash_image()[100:110])
        for command in (0x21, 0x31, 0x44, 0x73, 0x92):
            with self.assertRaises(common.H60Error):
                rom.command(command)
        with self.assertRaises(common.H60Error):
            rom.read_memory(0x1FFFC000, 16)

    def test_backup_two_full_reads_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "backup"
            fake = FakeSerial()
            result = recovery.recover("backup", "/dev/ttyFAKE", out, factory=fake.factory,
                                      hupcl=lambda _: None, sleep=lambda _: None, entry="inverted-both")
            self.assertEqual(result["status"], "verified")
            metadata, data, _ = common.load_baseline(out)
            self.assertEqual(metadata["read_count"], 2)
            self.assertEqual(data, flash_image())
            self.assertTrue(fake.closed)
            self.assertTrue(set(fake.commands) <= {0, 2, 0x11})
            self.assertEqual(fake.commands.count(0x11), 4097)  # Signature + two full reads.
            path = out / "flash-read-2.bin"
            altered = bytearray(path.read_bytes()); altered[99] ^= 1; path.write_bytes(altered)
            with self.assertRaises(common.H60Error):
                common.load_baseline(out)

    def test_default_cli_does_not_open_or_create_output(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(recovery, "recover") as recover:
            output = Path(tmp) / "not-created"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(recovery.main(["backup", "--port", "/dev/ttyFAKE", "--out-dir", str(output)]), 0)
            recover.assert_not_called()
            self.assertFalse(output.exists())

    def test_hupcl_failure_prevents_sync_and_closes(self):
        fake = FakeSerial()
        def fail(_):
            raise common.H60Error("HUPCL failure")
        with self.assertRaises(common.H60Error), common.open_link("/dev/ttyFAKE", 115200,
                                                                  factory=fake.factory, hupcl=fail):
            self.fail("Must not yield after HUPCL failure")
        self.assertTrue(fake.closed)
        self.assertEqual(fake.commands, [])

    def test_bin_hex_vectors_checksum_overlap_and_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = bytearray(64); struct.pack_into("<II", data, 0, 0x20020000, common.FLASH_BASE + 9)
            binary, hexf = root / "image.bin", root / "image.hex"
            binary.write_bytes(data); hexf.write_bytes(hex_image(data))
            self.assertEqual(common.inspect_image(binary)[1], common.inspect_image(hexf)[1])
            hexf.write_bytes(hex_image(data).replace(b":00000001FF", b":00000001FE"))
            with self.assertRaises(common.H60Error):
                common.inspect_image(hexf)
            bad = bytearray(data); struct.pack_into("<I", bad, 4, common.FLASH_BASE + 0x1001)
            binary.write_bytes(bad)
            with self.assertRaises(common.H60Error):
                common.inspect_image(binary)
            lines = hex_image(data).splitlines(); hexf.write_bytes(b"\n".join(lines[:2] + lines[1:]) + b"\n")
            with self.assertRaises(common.H60Error):
                common.inspect_image(hexf)


if __name__ == "__main__":
    unittest.main()
