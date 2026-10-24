import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import h60_boot as boot
import h60_common as common
import h60_flash as flash
import h60_recovery as recovery
from fake_rom import FakeSerial, flash_image, hex_image, identity


class FlashTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build = self.root / "firmware" / "example" / "build"
        self.build.mkdir(parents=True)
        source = self.build.parent / "main.c"
        source.write_text("/* synthetic test fixture, never loaded on hardware */\n")
        self.payload = bytearray((n * 17 + 3) % 256 for n in range(600))
        struct.pack_into("<II", self.payload, 0, 0x20020000, common.FLASH_BASE + 9)
        marker = b"LAB_SYNTHETIC_TEST_V1\0"
        self.payload[20:20 + len(marker)] = marker
        self.payload = bytes(self.payload)
        self.binary = self.build / "test.bin"
        self.binary.write_bytes(self.payload)
        (self.build / "test.hex").write_bytes(hex_image(self.payload))
        (self.build / "test.elf").write_bytes(b"synthetic ELF placeholder")
        (self.build / "test.map").write_bytes(b"synthetic map placeholder")
        manifest = {"target": "STM32F407VE", "marker": marker[:-1].decode(),
                    "image_bytes": len(self.payload), "payload_sha256": common.sha256(self.payload),
                    "sources": {"main.c": common.sha256(source.read_bytes())},
                    "artifacts": {p.name: common.sha256(p.read_bytes()) for p in self.build.iterdir()}}
        self.manifest = self.build / "manifest.json"
        common.write_json_new(self.manifest, manifest)
        self.original = flash_image()
        self.baseline = self.root / "baseline"
        self.baseline.mkdir()
        reads = []
        for n in (1, 2):
            name = f"read-{n}.bin"
            (self.baseline / name).write_bytes(self.original)
            reads.append({"filename": name, "length": common.FLASH_BYTES,
                          "sha256": common.sha256(self.original)})
        common.write_json_new(self.baseline / "baseline.json",
                              {"schema": "h60.lab-baseline.v1", "status": "verified", "identity": identity(),
                               "source_kind": "two-rom-reads", "read_count": 2, "reads": reads})
        self.plan = self.root / "plan.json"
        self.summary = flash.create_plan(self.binary, self.manifest, self.baseline, self.plan,
                                         "/dev/ttyFAKE", entry="inverted-both")
        self.prepared = flash.prepare(self.plan, self.summary["plan_sha256"])

    def apply(self, fake):
        self.out = self.root / "flash-run"
        return flash.apply(self.prepared, self.out, factory=fake.factory,
                           hupcl=lambda _: None, sleep=lambda _: None)

    def test_complete_flash_scope_and_preserved_tail(self):
        fake = FakeSerial(self.original)
        result = self.apply(fake)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(bytes(fake.flash), self.prepared.expected)
        self.assertEqual(bytes(fake.flash[16384:]), self.original[16384:])
        self.assertEqual(fake.writes, [(common.FLASH_BASE, 256), (common.FLASH_BASE + 256, 256),
                                      (common.FLASH_BASE + 512, 88)])
        self.assertEqual(len(fake.erase_packets), 1)
        self.assertTrue(set(fake.commands) <= {0, 2, 0x11, 0x31, 0x44})
        self.assertTrue(fake.closed)
        self.assertEqual((self.out / "readback.bin").stat().st_size, common.FLASH_BYTES)

    def test_wrong_identity_and_changed_full_flash_never_erase(self):
        for name in ("wrong-uid", "changed-flash"):
            fake = FakeSerial(self.original, wrong_uid=name == "wrong-uid")
            if name == "changed-flash":
                fake.flash[-100] ^= 1
            with self.subTest(name=name), self.assertRaises(common.H60Error):
                flash.apply(self.prepared, self.root / name, factory=fake.factory,
                            hupcl=lambda _: None, sleep=lambda _: None)
            self.assertEqual(fake.erase_packets, [])
            self.assertEqual(fake.writes, [])
            self.assertTrue(fake.closed)

    def test_tail_readback_corruption_rejects_result(self):
        fake = FakeSerial(self.original, corrupt_tail=True)
        with self.assertRaises(common.H60Error):
            self.apply(fake)
        self.assertEqual(common.read_json(self.out / "result.json")["status"], "failed")
        self.assertEqual(len(fake.erase_packets), 1)
        self.assertTrue(fake.closed)

    def test_nack_and_timeout_attempts_are_sticky(self):
        journal = common.Journal(self.root / "writer-events.jsonl")
        self.addCleanup(journal.close)
        fake = FakeSerial(self.original, erase_nack=True)
        writer = flash.SectorZeroWriter(fake, self.payload, journal)
        writer.connect()
        for _ in range(2):
            with self.assertRaises(common.H60Error):
                writer.erase_zero()
        self.assertEqual(fake.commands.count(0x44), 1)
        fake = FakeSerial(self.original)
        writer = flash.SectorZeroWriter(fake, self.payload, journal)
        writer.connect(); writer.erase_zero()
        with patch.object(writer, "ack", side_effect=common.H60Error("injected timeout")):
            with self.assertRaises(common.H60Error):
                writer.write_image()
        with self.assertRaises(common.H60Error):
            writer.write_image()
        self.assertEqual(fake.commands.count(0x31), 1)

    def test_plan_tampering_input_tampering_and_scope_are_rejected(self):
        with self.assertRaises(common.H60Error):
            flash.prepare(self.plan, "0" * 64)
        plan = common.read_json(self.plan); plan["erase_sectors"] = [0, 1]
        altered = self.root / "bad-plan.json"; common.write_json_new(altered, plan)
        with self.assertRaises(common.H60Error):
            flash.prepare(altered, common.sha256(altered.read_bytes()))
        self.binary.write_bytes(self.payload + b"\0\0\0\0")
        with self.assertRaises(common.H60Error):
            flash.prepare(self.plan, self.summary["plan_sha256"])

    def test_apply_default_dry_run_never_opens_or_creates(self):
        output = self.root / "dry-run-output"
        with patch.object(flash, "apply") as execute, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(flash.main(["apply", "--plan", str(self.plan), "--plan-sha256",
                                         self.summary["plan_sha256"], "--out-dir", str(output)]), 0)
        execute.assert_not_called()
        self.assertFalse(output.exists())

    def test_one_verified_readback_can_be_reused_without_claiming_two_reads(self):
        fake = FakeSerial(self.original); self.apply(fake)
        prior_command_count = len(fake.commands)
        derived = self.root / "derived-baseline"
        result = recovery.import_readback(self.out / "result.json", derived)
        metadata, image, _ = common.load_baseline(derived)
        self.assertEqual(result["read_count"], 1)
        self.assertEqual(metadata["source_kind"], "verified-flash-readback")
        self.assertEqual(image, self.prepared.expected)
        self.assertEqual(len(fake.commands), prior_command_count)
        source = common.read_json(derived / "source-result.json"); source["status"] = "failed"
        (derived / "source-result.json").write_text(json.dumps(source))
        with self.assertRaises(common.H60Error):
            common.load_baseline(derived)

    def test_boot_has_durable_intent_no_uart_bytes_and_no_automatic_repeat(self):
        fake = FakeSerial(self.original); self.apply(fake)
        report = self.out / "result.json"
        path, record = boot.prepare(report, common.sha256(report.read_bytes()))
        self.assertFalse(path.exists())
        boot_serial = FakeSerial(self.original)
        def factory(**options):
            self.assertTrue(path.exists())
            self.assertEqual(common.read_json(path)["tx_bytes"], 0)
            return boot_serial.factory(**options)
        result = boot.boot("/dev/ttyFAKE", path, record, factory=factory,
                           hupcl=lambda _: None, sleep=lambda _: None)
        self.assertTrue(result["reset_sequence_completed"])
        self.assertEqual(boot_serial.all_writes, [])
        self.assertTrue(boot_serial.closed)
        with self.assertRaises(common.H60Error):
            boot.prepare(report, common.sha256(report.read_bytes()))

    def test_existing_flash_outdir_and_hupcl_failure_prevent_rom_transactions(self):
        output = self.root / "already-present"; output.mkdir()
        fake = FakeSerial(self.original)
        with self.assertRaises(FileExistsError):
            flash.apply(self.prepared, output, factory=fake.factory, hupcl=lambda _: None)
        self.assertEqual(fake.all_writes, [])
        def fail(_):
            raise common.H60Error("injected HUPCL error")
        with self.assertRaises(common.H60Error):
            flash.apply(self.prepared, self.root / "hupcl-error", factory=fake.factory, hupcl=fail)
        self.assertEqual(fake.all_writes, [])
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()
