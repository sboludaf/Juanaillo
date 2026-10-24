import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import import_vendor as vendor


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = b"original vendor file\n"
        self.entry = {"member": "Package/Driver/encoder.c", "output": "Driver/encoder.c",
                      "archive": "Package.zip", "pristine_sha256": vendor.sha(self.data),
                      "output_sha256": vendor.sha(self.data)}

    def tearDown(self):
        self.tmp.cleanup()

    def direct_zip(self, data=None):
        path = self.root / "source.zip"
        with zipfile.ZipFile(path, "w") as packed:
            packed.writestr(self.entry["member"], self.data if data is None else data)
        return path

    def test_direct_zip_and_idempotent_import(self):
        source = self.direct_zip()
        out = self.root / "vendor"
        vendor.import_files([self.entry], [source], out)
        vendor.import_files([self.entry], [source], out)
        self.assertEqual((out / self.entry["output"]).read_bytes(), self.data)

    def test_nested_zip_has_archive_and_file_checksums(self):
        inner = self.direct_zip().read_bytes()
        self.entry["archive_sha256"] = vendor.sha(inner)
        outer = self.root / "outer.zip"
        with zipfile.ZipFile(outer, "w") as packed:
            packed.writestr("Code/Package.zip", inner)
        self.assertEqual(vendor.locate_in_zip(outer, [self.entry])[self.entry["output"]], self.data)
        self.entry["archive_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            vendor.locate_in_zip(outer, [self.entry])

    def test_extracted_directory(self):
        source = self.root / "extracted"
        file = source / self.entry["member"]
        file.parent.mkdir(parents=True)
        file.write_bytes(self.data)
        self.assertEqual(vendor.locate_in_directory(source, [self.entry])[self.entry["output"]], self.data)

    def test_tampered_or_missing_input_never_creates_destination(self):
        out = self.root / "vendor"
        with self.assertRaises(ValueError):
            vendor.import_files([self.entry], [self.direct_zip(b"tampered")], out)
        self.assertFalse(out.exists())
        missing = dict(self.entry, member="Package/missing.c")
        with self.assertRaises(ValueError):
            vendor.import_files([missing], [self.direct_zip()], out)
        self.assertFalse(out.exists())

    def test_different_existing_output_and_symlink_are_rejected(self):
        out = self.root / "vendor"
        target = out / self.entry["output"]
        target.parent.mkdir(parents=True)
        target.write_bytes(b"local modification")
        with self.assertRaises(ValueError):
            vendor.import_files([self.entry], [self.direct_zip()], out)
        self.assertEqual(target.read_bytes(), b"local modification")
        target.unlink()
        target.symlink_to(self.direct_zip())
        with self.assertRaises(ValueError):
            vendor.verify([self.entry], out)

    def test_startup_transform_is_exact_and_no_path_escape(self):
        raw = b"Default_Handler:\r\n  b  Infinite_Loop\r\n"
        expected = b"Default_Handler:\n  b.w JUANILLO_FatalStop\n\n"
        entry = dict(self.entry, transform="startup-fatal-stop-v1",
                     pristine_sha256=vendor.sha(raw), output_sha256=vendor.sha(expected))
        self.assertEqual(vendor.transformed(entry, raw), expected)
        for unsafe in ("../outside.c", "/outside.c"):
            with self.assertRaises(ValueError):
                vendor.destination_path(self.root, unsafe)


if __name__ == "__main__":
    unittest.main()
