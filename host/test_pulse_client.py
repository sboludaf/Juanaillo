import contextlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import sys
from unittest import mock

import pulse_client as pulse
from transport import HostError

FAKE_PORT = "COM3" if sys.platform == "win32" else "/dev/fake-debug"


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, amount):
        self.value += amount


class FakeDevice:
    def __init__(self, clock, **options):
        self.clock = clock
        self.options = options
        self.buffer = bytearray()
        self.commands = []
        self.packets = []
        self.state = pulse.IDLE
        self.reason = 0
        self.flags_override = None
        self.profile = pulse.PROFILE
        self.nonce = 0x1122334455667788
        self.pulse_count = 0
        self.lease_deadline = 0
        self.prepare_deadline = 0
        self.last_stop = -100
        self.fired_at = None
        self.encoders = [1000, 2000, 3000, 4000]
        self.rates = [-1000, 1200, -1400, 1600]
        self.motion_totals = [0, 0, 0, 0]
        self.active_lease_delay = 0
        self.silence_active_lease = False
        self.never_done = False
        self.closed = 0
        self.open_snapshot = None
        self.dtr = None
        self.rts = None
        self.port = None
        self.caps = pulse.CAPS_BYTES
        self.silent_command = None
        self.bad_checksum_command = None
        self.closed = 0

    def open(self):
        self.open_snapshot = (self.port, self.dtr, self.rts)

    def close(self):
        self.closed += 1

    def flush(self):
        pass

    def advance_state(self):
        now = self.clock()
        if self.state in (pulse.READY, pulse.WAKE, pulse.PULSE) and (
                now >= self.lease_deadline or (self.state == pulse.READY and now >= self.prepare_deadline)):
            self.state, self.reason = pulse.FAULT, 6
        if self.state in (pulse.WAKE, pulse.PULSE):
            elapsed = min(3.0, max(0.0, now - self.fired_at - .003))
            totals = [int(rate * elapsed) for rate in self.rates]
            self.encoders = [(value + total - previous) & 65535
                             for value, total, previous in zip(self.encoders, totals, self.motion_totals)]
            self.motion_totals = totals
            if now >= self.fired_at + 3.003 and not self.never_done:
                self.state, self.reason = pulse.DONE, 4
            elif now >= self.fired_at + .003:
                self.state = pulse.PULSE

    def status_payload(self):
        self.advance_state()
        flags = pulse.CAPABLE
        flags |= pulse.CONSUMED if self.pulse_count else 0
        flags |= pulse.OUTPUT_REQUESTED if self.state in (pulse.WAKE, pulse.PULSE) else pulse.ALL_LOW
        if self.flags_override is not None:
            flags = self.flags_override
        lease = max(0, min(100, int((self.lease_deadline - self.clock()) * 1000)))
        if self.state not in (pulse.READY, pulse.WAKE, pulse.PULSE):
            lease = 0
        return struct.pack(pulse.STATUS_FORMAT, pulse.VERSION, self.profile, self.state, flags,
                           int(self.clock() * 1000), lease, self.nonce, *self.encoders,
                           self.pulse_count, self.reason)

    def write(self, data):
        data = bytes(data)
        assert data[:2] == b"\xaa\x55" and data[2] == len(data)
        assert sum(data[:-1]) & 255 == data[-1]
        command = data[3]
        payload = data[4:-1]
        self.commands.append(command)
        self.packets.append(data)
        if command == pulse.LEASE and self.pulse_count:
            self.clock.sleep(self.active_lease_delay)
        self.advance_state()
        now = self.clock()
        if command in (pulse.PREPARE, pulse.FIRE, pulse.LEASE):
            if payload != struct.pack(">Q", self.nonce):
                self.state, self.reason = pulse.FAULT, 5
        if command == pulse.INFO:
            assert payload == b""
            response = self.caps
        elif command == pulse.STATUS:
            assert payload == b""
            response = self.status_payload()
        elif command == pulse.ENCODERS:
            assert payload == b""
            response = struct.pack(">4H", *self.encoders)
        elif command == pulse.STOP:
            assert payload == b""
            self.last_stop = now
            if self.state != pulse.FAULT:
                self.state = pulse.DONE if self.pulse_count else pulse.IDLE
                self.reason = 1
            response = self.status_payload()
        elif command == pulse.PREPARE:
            if self.state == pulse.IDLE:
                if now < 1 or now - self.last_stop > .5:
                    self.state, self.reason = pulse.FAULT, 7
                else:
                    self.state, self.reason = pulse.READY, 2
                    self.lease_deadline = now + .1
                    self.prepare_deadline = now + .3
            response = self.status_payload()
        elif command == pulse.LEASE:
            if self.state in (pulse.READY, pulse.WAKE, pulse.PULSE):
                self.lease_deadline = now + .1
            response = self.status_payload()
        elif command == pulse.FIRE:
            if self.state == pulse.READY and not self.pulse_count:
                self.pulse_count = 1  # consumed before the response/hardware wake
                self.fired_at = now
                self.lease_deadline = now + .1
                self.state, self.reason = pulse.WAKE, 3
            response = self.status_payload()
        else:
            raise AssertionError(f"Forbidden command {command:#x}")
        if command != self.silent_command and not (
                command == pulse.LEASE and self.pulse_count and self.silence_active_lease):
            reply = pulse.frame(command, response)
            if command == self.bad_checksum_command:
                reply = reply[:-1] + bytes((reply[-1] ^ 1,))
            self.buffer.extend(reply)
        return len(data)

    def read(self, count):
        self.clock.sleep(.001)
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.device = FakeDevice(self.clock)
        self.journal = mock.Mock()
        self.client = pulse.Client(self.device, self.journal, clock=self.clock)

    def prepare_client(self):
        self.client.identify()
        self.clock.sleep(1.1)
        self.client.stop()
        self.client.prepare()
        self.client.lease()

    def assert_no_fire(self):
        self.assertNotIn(pulse.FIRE, self.device.commands)

    def test_end_to_end_fixed_single_pulse(self):
        result = pulse.run_pulse(self.client, sleep=self.clock.sleep)
        self.assertEqual(result["status"], "forward-verified")
        self.assertEqual(self.device.commands.count(pulse.FIRE), 1)
        self.assertEqual(self.device.pulse_count, 1)
        self.assertEqual(result["final_status"]["state"], pulse.DONE)
        self.assertEqual(result["final_status"]["flags"], 11)
        self.assertEqual(result["analysis"]["signed_delta"], [-3000, 3600, -4200, 4800])
        self.assertEqual(result["analysis"]["normalized_forward_delta"], [3000, 3600, 4200, 4800])
        self.assertTrue(result["analysis"]["all_forward"])
        self.assertGreaterEqual(self.device.commands.count(pulse.LEASE), 100)
        self.assertGreaterEqual(self.clock() - self.device.fired_at, 3.0)
        self.assertGreater(result["encoder_samples_tracked"], 100)
        self.assertFalse(result["analysis"]["new_visual_confirmations_required"])
        self.assertEqual(result["analysis"]["prior_visual_reference"], {"A_motor_sign": 1})
        self.assertFalse(result["analysis"]["profile_written"])
        for packet in self.device.packets:
            command = packet[3]
            if command in (pulse.PREPARE, pulse.FIRE, pulse.LEASE):
                self.assertEqual(packet[4:-1], struct.pack(">Q", self.device.nonce))
        self.assertFalse(set(self.device.commands) & {0x50, 0x51, 0x52, 0x53})

    def test_every_caps_field_and_marker_mismatch_prevents_fire(self):
        for offset in (0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20):
            with self.subTest(offset=offset):
                device = FakeDevice(self.clock)
                changed = bytearray(pulse.CAPS_BYTES)
                changed[offset] ^= 1
                device.caps = bytes(changed)
                client = pulse.Client(device, self.journal, clock=self.clock)
                with self.assertRaisesRegex(HostError, "Descriptor"):
                    client.identify()
                self.assertNotIn(pulse.FIRE, device.commands)
                self.assertTrue(client.failed)

    def test_previous_pulse_firmwares_rejected_before_prepare_or_fire(self):
        for profile, channel, polarity, duty, marker in (
                (2, 0, 1, 50, b"H60_PULSE_A_SINGLE_SHOT_V1"),
                (2, 0, 1, 100, b"H60_PULSE_A_SINGLE_SHOT_V2"),
                (2, 1, 1, 100, b"H60_PULSE_B_SINGLE_SHOT_V2"),
                (3, 15, 1, 100, b"H60_PULSE_ALL_SINGLE_SHOT_V1")):
            with self.subTest(marker=marker):
                self.setUp()
                self.device.caps = struct.pack(pulse.CAPS_FORMAT, 1, profile, channel, polarity, duty, 5000, 3, 45, 50000, 100) + marker
                with self.assertRaises(HostError):
                    self.client.identify()
                self.assertNotIn(pulse.PREPARE, self.device.commands)
                self.assert_no_fire()

    def test_reset_or_nonce_mismatch_before_fire_locks_client(self):
        self.prepare_client()
        self.device.nonce ^= 1
        with self.assertRaisesRegex(HostError, "Nonce/sesión"):
            self.client.fire_once()
        self.device.nonce ^= 1
        with self.assertRaises(HostError):
            self.client.fire_once()
        self.assert_no_fire()

    def test_fault_profile_or_outputs_mismatch_before_fire(self):
        for mismatch in ("fault", "profile", "outputs"):
            with self.subTest(mismatch=mismatch):
                self.setUp()
                self.prepare_client()
                if mismatch == "fault":
                    self.device.state, self.device.reason = pulse.FAULT, 9
                elif mismatch == "profile":
                    self.device.profile = pulse.PROFILE + 1
                else:
                    self.device.flags_override = pulse.CAPABLE
                with self.assertRaises(HostError):
                    self.client.fire_once()
                self.assert_no_fire()
                self.assertTrue(self.client.failed)

    def test_fire_without_prepare_is_blocked(self):
        self.client.identify()
        with self.assertRaises(HostError):
            self.client.fire_once()
        self.assert_no_fire()

    def test_fire_is_never_repeated_after_timeout_or_bad_checksum(self):
        for failure in ("silent_command", "bad_checksum_command"):
            with self.subTest(failure=failure):
                self.setUp()
                self.prepare_client()
                setattr(self.device, failure, pulse.FIRE)
                with self.assertRaises(HostError):
                    self.client.fire_once()
                setattr(self.device, failure, None)
                with self.assertRaises(HostError):
                    self.client.fire_once()
                self.assertEqual(self.device.commands.count(pulse.FIRE), 1)
                self.assertTrue(self.client.fire_attempted)

    def test_stale_ready_and_expired_host_prepare_prevent_fire(self):
        self.prepare_client()
        self.clock.sleep(.21)
        with self.assertRaises(HostError):
            self.client.fire_once()
        self.assert_no_fire()

    def test_nonquiet_encoders_abort_without_prepare_or_fire(self):
        calls = 0
        def move_while_waiting(seconds):
            nonlocal calls
            self.clock.sleep(seconds)
            calls += 1
            if calls == 2:
                self.device.encoders[2] += 1
        with self.assertRaisesRegex(HostError, "no quietos"):
            pulse.run_pulse(self.client, sleep=move_while_waiting)
        self.assertNotIn(pulse.PREPARE, self.device.commands)
        self.assert_no_fire()

    def test_done_without_all_low_is_rejected(self):
        self.prepare_client()
        self.client.fire_once()
        self.clock.sleep(3.01)
        self.device.state, self.device.reason = pulse.DONE, 4
        self.device.flags_override = 3
        with self.assertRaisesRegex(HostError, "DONE"):
            self.client.status()

    def test_thousands_of_counts_have_positive_forward_sign_without_cpr_half_limit(self):
        before = [100, 200, 300, 400]
        totals = [-4000, 5000, -6000, 7000]
        after = [(start + total) & 65535 for start, total in zip(before, totals)]
        result = pulse.analyze_counts(before, after, totals)
        self.assertEqual(result["normalized_forward_delta"], [4000, 5000, 6000, 7000])
        self.assertTrue(result["all_forward"])
        self.assertFalse(result["profile_written"])
        self.assertFalse(result["new_visual_confirmations_required"])

    def test_inconclusive_counts_do_not_discard_other_wheels_or_escalate(self):
        result = pulse.analyze_counts([0, 0, 0, 0], [0, 7, 64636, 1000], [0, 7, -900, 1000])
        self.assertFalse(result["all_forward"])
        self.assertEqual([entry["direction"] for entry in result["wheel_results"]],
                         ["inconclusive", "inconclusive", "forward", "forward"])
        self.assertFalse(result["automatic_retries"])

    def test_tracker_unwraps_samples_and_direction_analysis_detects_reverse(self):
        tracker = pulse.EncoderTracker({"encoders": [5, 65530, 5, 65530], "uptime_ms": 100})
        tracker.observe({"encoders": [65520, 20, 65520, 20], "uptime_ms": 120})
        self.assertEqual(tracker.totals, [-21, 26, -21, 26])
        result = pulse.analyze_counts(tracker.before, tracker.previous, tracker.totals)
        self.assertTrue(result["all_forward"])
        wrong = pulse.analyze_counts([0, 0, 0, 0], [20, 30, 65500, 65500], [20, 30, -36, -36])
        self.assertFalse(wrong["all_forward"])
        self.assertEqual([entry["direction"] for entry in wrong["wheel_results"]],
                         ["reverse", "forward", "forward", "reverse"])

    def test_tracker_rejects_jump_gap_and_excess_total(self):
        for time_ms, count, message in ((20, 30000, "Salto"), (251, 0, "Intervalo")):
            with self.subTest(time_ms=time_ms):
                tracker = pulse.EncoderTracker({"encoders": [0] * 4, "uptime_ms": 0})
                with self.assertRaisesRegex(HostError, message):
                    tracker.observe({"encoders": [count, 0, 0, 0], "uptime_ms": time_ms})
        tracker = pulse.EncoderTracker({"encoders": [0] * 4, "uptime_ms": 0})
        with self.assertRaisesRegex(HostError, "Total"):
            for index in range(1, 133):
                tracker.observe({"encoders": [(250 * index) & 65535, 0, 0, 0], "uptime_ms": 25 * index})

    def test_active_heartbeat_lapse_and_missing_done_abort(self):
        for mode in ("lease-gap", "missing-done"):
            with self.subTest(mode=mode):
                self.setUp()
                if mode == "lease-gap":
                    self.device.active_lease_delay = .15
                else:
                    self.device.never_done = True
                with self.assertRaises(HostError):
                    pulse.run_pulse(self.client, sleep=self.clock.sleep)
                self.assertEqual(self.device.commands.count(pulse.FIRE), 1)


class ArtifactAndExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.source = self.root / "main.c"
        self.source.write_text("/* dedicated pulse candidate fixture */\n")
        self.binary = self.build / "pulse.bin"
        binary = b"fixture\x00" + pulse.MARKER + b"\x00"
        self.binary.write_bytes(binary + b"\xff" * (-len(binary) % 4))
        artifacts = {"pulse.bin": pulse.sha256(self.binary.read_bytes())}
        for suffix in (".elf", ".map", ".hex"):
            path = self.build / ("pulse" + suffix)
            path.write_bytes(b"offline artifact fixture " + suffix.encode())
            artifacts[path.name] = pulse.sha256(path.read_bytes())
        self.manifest = self.build / "manifest.json"
        self.manifest.write_text(json.dumps({
            "schema": "h60.forward-3s-build.v1",
            **pulse.MANIFEST_EXPECTED,
            "image_bytes": self.binary.stat().st_size,
            "payload_sha256": pulse.sha256(self.binary.read_bytes()),
            "artifacts": artifacts,
            "sources": {"main.c": pulse.sha256(self.source.read_bytes())}}))
        self.digest = pulse.sha256(self.manifest.read_bytes())
        self.outdir = self.root / "run"
        self.clock = Clock()
        self.device = FakeDevice(self.clock)

    def arguments(self):
        return ["pulse", "--manifest", str(self.manifest), "--manifest-sha256", self.digest,
                "--port", FAKE_PORT, "--outdir", str(self.outdir)]

    def test_default_dryrun_never_opens_port_or_creates_outdir(self):
        output = io.StringIO()
        with mock.patch.object(pulse.DebugTransport, "open", side_effect=AssertionError("hardware")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(pulse.main(self.arguments()), 0)
        self.assertTrue(json.loads(output.getvalue())["port_not_opened"])
        self.assertFalse(self.outdir.exists())

    def test_default_manifest_and_hash_are_resolved_offline(self):
        self.assertTrue(pulse.DEFAULT_MANIFEST.is_absolute())
        self.assertEqual(pulse.DEFAULT_MANIFEST.parts[-4:],
                         ("firmware", "forward-3s", "build", "manifest.json"))
        output = io.StringIO()
        with mock.patch.object(pulse, "DEFAULT_MANIFEST", self.manifest), \
                mock.patch.object(pulse.DebugTransport, "open", side_effect=AssertionError("hardware")), \
                contextlib.redirect_stdout(output):
            result = pulse.main(["identify", "--port", FAKE_PORT, "--outdir", str(self.outdir)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["manifest_sha256"], self.digest)
        self.assertFalse(self.outdir.exists())

    def test_execute_requires_reviewed_hash_before_open(self):
        argv = ["pulse", "--manifest", str(self.manifest), "--port", FAKE_PORT,
                "--outdir", str(self.outdir), "--execute"]
        with mock.patch.object(pulse.DebugTransport, "open", side_effect=AssertionError("hardware")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pulse.main(argv), 1)
        self.assertFalse(self.outdir.exists())

    def test_source_binary_or_manifest_hash_drift_is_rejected_offline(self):
        for target in (self.source, self.binary, self.manifest):
            with self.subTest(target=target):
                original = target.read_bytes()
                target.write_bytes(original + b"modified")
                with self.assertRaises((HostError, ValueError)):
                    pulse.verify_artifacts(self.manifest, self.digest)
                target.write_bytes(original)

    def test_reviewed_hash_does_not_bypass_wrong_envelope_metadata(self):
        value = json.loads(self.manifest.read_text())
        value["pwm_duration_ms"] = 100
        self.manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(HostError, "CAPS/UART/límites"):
            pulse.verify_artifacts(self.manifest, pulse.sha256(self.manifest.read_bytes()))

    def test_execute_only_fake_logs_raw_and_final_evidence(self):
        evidence = pulse.verify_artifacts(self.manifest, self.digest)
        result = pulse.execute("pulse", FAKE_PORT, self.outdir, evidence,
                               factory=lambda **_: self.device, hupcl_setter=lambda _: None,
                               clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(result["status"], "forward-verified")
        self.assertEqual(self.device.open_snapshot, (FAKE_PORT, True, False))
        self.assertEqual(self.device.closed, 1)
        self.assertEqual((self.device.dtr, self.device.rts), (True, False))
        raw = [json.loads(line) for line in (self.outdir / "raw.jsonl").read_text().splitlines()]
        fire_frames = [event for event in raw if event["event"] == "raw"
                       and event["direction"] == "tx-requested"
                       and bytes.fromhex(event["hex"])[3] == pulse.FIRE]
        self.assertEqual(len(fire_frames), 1)
        report = json.loads((self.outdir / "result.json").read_text())
        self.assertEqual(report["final_status"]["flags"], 11)
        self.assertFalse(report["artifact_evidence"]["app_uid_authenticated"])

    def test_execute_failure_sends_separate_stop_without_second_fire(self):
        self.device.silent_command = pulse.FIRE
        with self.assertRaises(HostError):
            pulse.execute("pulse", FAKE_PORT, self.outdir, {},
                          factory=lambda **_: self.device, hupcl_setter=lambda _: None,
                          clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(self.device.commands.count(pulse.FIRE), 1)
        self.assertEqual(self.device.commands[-1], pulse.STOP)
        self.assertEqual(self.device.closed, 1)
        report = json.loads((self.outdir / "result.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertIn("abort_stop_status", report)

    def test_failed_stop_is_not_replayed(self):
        self.device.silent_command = pulse.STOP
        with self.assertRaises(HostError):
            pulse.execute("stop", FAKE_PORT, self.outdir, {},
                          factory=lambda **_: self.device, hupcl_setter=lambda _: None,
                          clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(self.device.commands.count(pulse.STOP), 1)
        self.assertNotIn(pulse.FIRE, self.device.commands)

    def test_active_heartbeat_timeout_sends_stop_without_retry(self):
        self.device.silence_active_lease = True
        with self.assertRaises(HostError):
            pulse.execute("pulse", FAKE_PORT, self.outdir, {},
                          factory=lambda **_: self.device, hupcl_setter=lambda _: None,
                          clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(self.device.commands.count(pulse.FIRE), 1)
        self.assertEqual(self.device.commands[-1], pulse.STOP)
        self.assertEqual(self.device.closed, 1)


if __name__ == "__main__":
    unittest.main()
