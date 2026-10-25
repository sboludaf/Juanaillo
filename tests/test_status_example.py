import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from web.serial_client import CAPS_BYTES, EXPECTED, INFO, MARKER, STATUS, STATUS_FORMAT, DeviceError, frame


SPEC = importlib.util.spec_from_file_location("status_example", Path(__file__).resolve().parents[1] / "examples/h60_status.py")
EXAMPLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXAMPLE)


def make_manifest(root, *, profile=6):
    build = root / "build"
    build.mkdir()
    source = root / "main.c"
    source.write_text("/* synthetic example-test fixture */")
    binary = bytearray(64)
    struct.pack_into("<II", binary, 0, 0x20020000, 0x08000009)
    binary[8:8 + len(MARKER) + 1] = MARKER + b"\0"
    files = {"manual.bin": bytes(binary), "manual.hex": b"fixture hex",
             "manual.elf": b"fixture elf", "manual.map": b"fixture map"}
    for name, data in files.items():
        (build / name).write_bytes(data)
    manifest = {
        **EXPECTED, "profile": profile, "image_bytes": len(binary),
        "payload_sha256": hashlib.sha256(binary).hexdigest(),
        "sources": {"main.c": hashlib.sha256(source.read_bytes()).hexdigest()},
        "artifacts": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    path = build / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


class StatusWire:
    def __init__(self, *, caps=CAPS_BYTES, failed_read=False):
        self.caps, self.failed_read = caps, failed_read
        self.buffer, self.commands, self.closed = bytearray(), [], False

    def write(self, packet):
        command = packet[3]
        self.commands.append(command)
        if command == INFO:
            payload = self.caps
        elif command == STATUS:
            payload = struct.pack(STATUS_FORMAT, 1, 6, 0, 9, 100, 0, 12345,
                                  12, 34, 65535, 78, 0, 1, 0, 0)
        else:
            raise AssertionError("A status example sent a control command")
        self.buffer.extend(frame(command, payload))

    def read(self, length):
        if self.failed_read:
            raise DeviceError("Synthetic response timeout")
        raw = bytes(self.buffer[:length])
        del self.buffer[:length]
        return raw

    def close(self):
        self.closed = True


class SerialStatusExampleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest, self.digest = make_manifest(self.root)

    def test_default_is_offline_without_open_or_created_output(self):
        before = set(self.root.rglob("*"))
        def forbidden(*_):
            self.fail("An offline plan opened serial")
        result = EXAMPLE.serial_status(port="/dev/ttyFAKE", manifest=self.manifest, opener=forbidden)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["serial_opened"])
        self.assertEqual(result["manifest_sha256"], self.digest)
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_execute_requires_reviewed_hash_before_open(self):
        calls = []
        with self.assertRaises(EXAMPLE.StatusError):
            EXAMPLE.serial_status(port="/dev/ttyFAKE", manifest=self.manifest, execute=True,
                                  opener=lambda *_: calls.append("open"))
        self.assertEqual(calls, [])

    def test_incompatible_or_changed_manifest_rejected_before_open(self):
        calls = []
        value = json.loads(self.manifest.read_text())
        value["profile"] = 5
        self.manifest.write_text(json.dumps(value))
        for digest in (self.digest, hashlib.sha256(self.manifest.read_bytes()).hexdigest()):
            with self.subTest(digest=digest), self.assertRaises(EXAMPLE.StatusError):
                EXAMPLE.serial_status(port="/dev/ttyFAKE", manifest=self.manifest,
                                      manifest_sha256=digest, execute=True,
                                      opener=lambda *_: calls.append("open"))
        self.assertEqual(calls, [])

    def test_real_contract_sends_only_info_status_and_closes(self):
        wire = StatusWire()
        calls = []
        def opened(port, journal):
            calls.append(port)
            journal.event("serial_tx", hex="synthetic-private-frame")
            return wire
        result = EXAMPLE.serial_status(port="/dev/ttyFAKE", manifest=self.manifest,
                                      manifest_sha256=self.digest, execute=True, opener=opened)
        self.assertEqual(calls, ["/dev/ttyFAKE"])
        self.assertEqual(wire.commands, [INFO, STATUS])
        self.assertTrue(wire.closed)
        self.assertEqual(result["status"]["encoders"], [12, 34, 65535, 78])
        self.assertTrue(result["status"]["all_low"])
        self.assertNotIn("nonce", json.dumps(result))
        self.assertNotIn("private-frame", json.dumps(result))

    def test_incompatible_firmware_closes_without_status_or_control(self):
        wire = StatusWire(caps=bytes(48))
        with self.assertRaises(EXAMPLE.StatusError):
            EXAMPLE.serial_status(port="/dev/ttyFAKE", manifest=self.manifest,
                                  manifest_sha256=self.digest, execute=True, opener=lambda *_: wire)
        self.assertEqual(wire.commands, [INFO])
        self.assertTrue(wire.closed)

    def test_failed_exchange_closes_once_and_does_not_retry(self):
        wire = StatusWire(failed_read=True)
        with self.assertRaises(EXAMPLE.StatusError):
            EXAMPLE.serial_status(port="/dev/ttyFAKE", manifest=self.manifest,
                                  manifest_sha256=self.digest, execute=True, opener=lambda *_: wire)
        self.assertEqual(wire.commands, [INFO])
        self.assertTrue(wire.closed)

    def test_busy_port_is_not_retried(self):
        calls = []
        def busy(*_):
            calls.append("open")
            raise OSError("Synthetic exclusive port lock")
        with self.assertRaises(EXAMPLE.StatusError):
            EXAMPLE.serial_status(port="/dev/ttyFAKE", manifest=self.manifest,
                                  manifest_sha256=self.digest, execute=True, opener=busy)
        self.assertEqual(calls, ["open"])


class HttpStatusExampleTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.redirect = False
        self.payload = {"type": "status", "state": "error", "connected": False,
                        "moving": False, "encoders": [1, 2, 3, 4],
                        "nonce": "synthetic-private-value", "token": "synthetic-private-value"}
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.requests.append((self.command, self.path))
                if outer.redirect:
                    self.send_response(302)
                    self.send_header("Location", "/unexpected-target")
                    self.end_headers()
                    return
                raw = json.dumps(outer.payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def test_http_is_only_read_get_and_preserves_disconnected_state(self):
        result = EXAMPLE.http_status(self.url)
        self.assertEqual(self.requests, [("GET", "/api/status")])
        self.assertTrue(result["ok"])
        self.assertFalse(result["serial_opened"])
        self.assertFalse(result["control_claimed"])
        self.assertFalse(result["status"]["connected"])
        self.assertNotIn("nonce", json.dumps(result))
        self.assertNotIn("token", json.dumps(result))

    def test_redirect_not_followed(self):
        self.redirect = True
        with self.assertRaises(EXAMPLE.StatusError):
            EXAMPLE.http_status(self.url)
        self.assertEqual(self.requests, [("GET", "/api/status")])

    def test_bad_url_is_rejected_without_request(self):
        for url in ("https://example.invalid:8765", self.url + "/ws",
                    self.url + "#not-an-access-key", "http://localhost:8765/?q=1"):
            with self.subTest(url=url), self.assertRaises(EXAMPLE.StatusError):
                EXAMPLE.http_status(url)
        self.assertEqual(self.requests, [])

    def test_unexpected_response_rejected(self):
        self.payload = {"not_status": True}
        with self.assertRaises(EXAMPLE.StatusError):
            EXAMPLE.http_status(self.url)


if __name__ == "__main__":
    unittest.main()
