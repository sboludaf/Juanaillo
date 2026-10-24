"""Profile-5 wire client and simulation. No ROM, reset or automatic reconnect."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import struct
import time

from host.transport import HostError, disable_hupcl, sha256, valid_port

PROFILE = 5
MARKER = b"H60_MANUAL_HOLD_CONTROL_V1__"
CAPS_BYTES = struct.pack(">BBBBHHHHII", 1, 5, 15, 10, 100, 5000, 4, 10000, 10000000, 150) + MARKER
STATUS_FORMAT = ">BBBBIIQ4HIIiI"
STATUS_BYTES = struct.calcsize(STATUS_FORMAT)
IDLE, WAKE, RUNNING, LIMIT, FAULT = range(5)
STATE_NAMES = ("idle", "wake", "running", "limit", "fault")
STATUS, INFO, STOP, MOVE = 0x70, 0x76, 0x74, 0x77
EXPECTED = {"target": "STM32F407VE", "profile": 5, "marker": MARKER.decode(),
            "motor_capable": True, "fixed_motor_mask": 15, "fixed_reversed_mask": 10,
            "forward_raw_directions": [1, -1, 1, -1], "reverse_raw_directions": [-1, 1, -1, 1],
            "requires_stop_after_limit": True, "sticky_fault": True,
            "status_payload_bytes": 44, "move_payload_bytes": 9,
            "uart": 1, "uart_pins": ["PA9", "PA10"],
            "baudrate": 230400, "framing": "8N1", "duty_permille": 100, "pwm_hz": 5000,
            "wake_min_ms": 4, "max_burst_ms": 10000, "lease_ms": 150, "caps_hex": CAPS_BYTES.hex()}


class DeviceError(HostError):
    pass


class StaleHold(DeviceError):
    """The requested movement was cancelled before transmission."""


def require(condition, message):
    if not condition:
        raise DeviceError(message)


def verify_manifest(path, digest):
    require(isinstance(digest, str) and len(digest) == 64, "A reviewed manifest SHA256 is required.")
    path = Path(path).resolve()
    require(path.is_file(), "Manual-hold build manifest is missing.")
    raw = path.read_bytes()
    require(sha256(raw) == digest, "Manifest SHA256 mismatch.")
    manifest = json.loads(raw)
    require(all(type(manifest.get(k)) is type(v) and manifest.get(k) == v for k, v in EXPECTED.items()),
            "Manifest does not describe the fixed profile-5 manual controller.")
    root, binaries = path.parent.parent, []
    artifacts, sources = manifest.get("artifacts"), manifest.get("sources")
    require(isinstance(artifacts, dict) and len(artifacts) == 4
            and {Path(n).suffix for n in artifacts} == {".bin", ".hex", ".elf", ".map"}
            and isinstance(sources, dict) and bool(sources), "Incomplete build inventory.")
    for name, expected in artifacts.items():
        require(isinstance(name, str) and Path(name).name == name, "Invalid artifact filename.")
        artifact = path.parent / name
        require(artifact.is_file() and not artifact.is_symlink(), "Missing or linked artifact.")
        data = artifact.read_bytes()
        require(sha256(data) == expected, "Build artifact changed.")
        if artifact.suffix == ".bin":
            binaries.append(data)
    require(len(binaries) == 1 and MARKER + b"\0" in binaries[0]
            and len(binaries[0]) == manifest.get("image_bytes")
            and sha256(binaries[0]) == manifest.get("payload_sha256")
            and 8 <= len(binaries[0]) <= 16384 and len(binaries[0]) % 4 == 0, "Invalid manual-control BIN.")
    for name, expected in sources.items():
        source = (root / name).resolve()
        require(not Path(name).is_absolute() and source.is_relative_to(root)
                and source.is_file() and sha256(source.read_bytes()) == expected, "Build source changed.")
    return {"manifest_sha256": digest, "payload_sha256": manifest["payload_sha256"], "profile": PROFILE}


def frame(command, payload=b""):
    data = bytes((0xAA, 0x55, len(payload) + 5, command)) + payload
    return data + bytes((sum(data) & 255,))


class SerialTransport:
    def __init__(self, serial, journal):
        self.serial, self.journal = serial, journal

    @classmethod
    def open(cls, port, journal, *, factory=None, hupcl=disable_hupcl, sleep=None):
        require(valid_port(port), "An explicit DEBUG serial port is required.")
        if factory is None:
            factory = importlib.import_module("serial").Serial
        import sys
        options = dict(port=None, baudrate=230400, bytesize=8, parity="N", stopbits=1,
                       timeout=.005, write_timeout=.025, rtscts=False, dsrdtr=False)
        if sys.platform != "win32":
            options["exclusive"] = True
        serial = factory(**options)
        try:
            serial.dtr, serial.rts, serial.port = True, False, port
            serial.open()
            hupcl(serial)
            # CH340 may transiently reset this board on open. Wait ONCE before
            # INFO; runtime response deadlines and the firmware lease stay fixed.
            journal.event("serial_settling", milliseconds=350, reset_requested=False)
            (sleep or time.sleep)(.350)
            journal.event("serial_opened", reset_requested=False, open_reset_transient_possible=True, baud=230400)
            return cls(serial, journal)
        except BaseException:
            serial.close()
            raise

    def write(self, data):
        self.journal.event("serial_tx", hex=data.hex())
        require(self.serial.write(data) == len(data), "Short write; movement is never replayed.")

    def read(self, count):
        data = bytes(self.serial.read(count))
        require(len(data) <= count, "Serial returned excess bytes.")
        return data

    def close(self):
        self.serial.close()  # No line restoration, reset or reconnect.


class ManualClient:
    def __init__(self, transport, *, clock=time.monotonic):
        self.transport, self.clock = transport, clock
        self.nonce, self.verified, self.failed = None, False, False

    def _exchange(self, command, payload, length, *, permit=None, emergency=False):
        require(emergency or not self.failed, "Serial session is locked after an error.")
        if permit is not None and not permit():
            raise StaleHold("Hold cancelled before serial transmission.")
        try:
            self.transport.write(frame(command, payload))
            deadline, data = self.clock() + .04, bytearray()
            while len(data) < length + 5:
                require(self.clock() < deadline, "Serial response timeout; no replay.")
                block = self.transport.read(length + 5 - len(data))
                require(len(block) <= length + 5 - len(data), "Oversized serial response.")
                data.extend(block)
            require(data[:4] == bytes((0xAA, 0x55, length + 5, command))
                    and sum(data[:-1]) & 255 == data[-1], "Unexpected frame/checksum; no resynchronization.")
            return bytes(data[4:-1])
        except BaseException:
            self.failed = True
            raise

    def _status(self, raw):
        values = struct.unpack(STATUS_FORMAT, raw)
        version, profile, state, flags, uptime, lease, nonce = values[:7]
        encoders, bursts, reason, direction, remaining = list(values[7:11]), *values[11:]
        try:
            require(version == 1 and profile == PROFILE and state in range(5), "Unexpected firmware profile/state.")
            require(nonce != 0 and (self.nonce is None or self.nonce == nonce), "Firmware reset/nonce changed.")
            require(direction in (-1, 0, 1) and 0 <= lease <= 150 and 0 <= remaining <= 10000,
                    "Inconsistent firmware limits.")
            active = state in (WAKE, RUNNING)
            require(flags == (7 if active else 9) and (direction != 0) == active,
                    "Firmware outputs/flags do not match its state.")
            require((lease > 0 and remaining > 0) if active else (lease == 0 and remaining == 0),
                    "Inconsistent lease/burst state.")
            require(reason in (0, 1, 3, 4, 5, 6, 7, 8, 10, 11, 12), "Unknown firmware reason.")
            if self.nonce is None:
                self.nonce = nonce
            return {"state": STATE_NAMES[state], "state_id": state, "flags": flags,
                    "uptime_ms": uptime, "firmware_lease_ms": lease, "encoders": encoders,
                    "burst_count": bursts, "reason": reason, "direction_value": direction,
                    "burst_remaining_ms": remaining, "all_low": bool(flags & 8)}
        except BaseException:
            self.failed = True
            raise

    def identify(self):
        require(self._exchange(INFO, b"", 48) == CAPS_BYTES, "Wrong manual-hold firmware descriptor.")
        status = self.status()
        self.verified = True
        return status

    def status(self):
        return self._status(self._exchange(STATUS, b"", STATUS_BYTES))

    def move(self, direction, *, permit=None):
        require(self.verified and self.nonce is not None and type(direction) is int and direction in (-1, 1),
                "MOVE requires a verified session and fixed direction.")
        return self._status(self._exchange(MOVE, struct.pack(">Qb", self.nonce, direction), STATUS_BYTES,
                                          permit=permit))

    def stop(self):
        return self._status(self._exchange(STOP, b"", STATUS_BYTES, emergency=True))

    def close(self):
        self.transport.close()


class SimulatedDevice:
    """The same lease/limit behavior, without importing or opening serial."""
    def __init__(self, *, clock=time.monotonic):
        self.clock, self.boot_at = clock, clock()
        self.state, self.direction, self.started, self.last_move = "idle", 0, 0.0, 0.0
        self.bursts, self.closed, self.move_calls, self.stop_calls = 0, False, [], 0

    def _tick(self):
        now = self.clock()
        if self.state in ("wake", "running"):
            if now - self.last_move >= .150:
                self.state, self.direction = "fault", 0
            elif now - self.started >= 10.0:
                self.state, self.direction = "limit", 0
            elif now - self.started >= .005:
                self.state = "running"

    def identify(self):
        return self.status()

    def status(self):
        self._tick()
        active = self.state in ("wake", "running")
        return {"state": self.state, "flags": 7 if active else 9, "all_low": not active,
                "direction_value": self.direction, "uptime_ms": int((self.clock() - self.boot_at) * 1000),
                "firmware_lease_ms": max(1, int((.150 - (self.clock() - self.last_move)) * 1000)) if active else 0,
                "burst_remaining_ms": max(1, int((10 - (self.clock() - self.started)) * 1000)) if active else 0,
                "burst_count": self.bursts, "reason": 5 if self.state == "fault" else 4 if self.state == "limit" else 1,
                "encoders": [0, 0, 0, 0]}

    def move(self, direction, *, permit=None):
        if permit is not None and not permit():
            raise StaleHold("Hold cancelled.")
        self._tick()
        if self.state not in ("fault", "limit"):
            if self.state == "idle":
                self.started, self.bursts = self.clock(), self.bursts + 1
            self.direction, self.last_move = direction, self.clock()
            self.state = "wake" if self.clock() - self.started < .005 else "running"
            self.move_calls.append((self.clock(), direction))
        return self.status()

    def stop(self):
        self._tick()
        self.stop_calls += 1
        if self.state != "fault":
            self.state, self.direction = "idle", 0
        return self.status()

    def close(self):
        self.closed = True
