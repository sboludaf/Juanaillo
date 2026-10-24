"""Shared STM32F407VE image, transport and read-only ROM primitives.

Original implementation of the public ST AN3155 protocol. Device identity and
backups are generated locally; this module contains no device-specific UID.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import struct
import time

FLASH_BASE = 0x08000000
FLASH_BYTES = 512 * 1024
SECTOR_ZERO_BYTES = 16 * 1024
SIGNATURE_BASE = 0x1FFF7A00
EXPECTED_PID = 0x0413
ACK, NACK = 0x79, 0x1F
ROM_BAUDS = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)


class H60Error(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise H60Error(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_file(path, digest=None):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), f"Missing file or symlink: {path.name}")
    data = path.read_bytes()
    require(digest is None or sha256(data) == digest, f"SHA256 mismatch: {path.name}")
    return data


def read_json(path, digest=None):
    value = json.loads(read_file(path, digest))
    require(isinstance(value, dict), "Expected a JSON object.")
    return value


def write_json_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def relative(path, directory):
    return Path(os.path.relpath(Path(path).resolve(), Path(directory).resolve())).as_posix()


def resolve(directory, name):
    require(isinstance(name, str) and not Path(name).is_absolute(), "Expected a relative file path.")
    return (Path(directory) / name).resolve()


class Journal:
    def __init__(self, path):
        self.stream = Path(path).open("x", encoding="utf-8")

    def event(self, name, **fields):
        self.stream.write(json.dumps({"utc": utc_now(), "event": name, **fields}) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


def inspect_image(path):
    """Strict BIN/Intel HEX parsing; structural validation is not a safety audit."""
    path = Path(path)
    raw = read_file(path)
    require(0 < len(raw) <= 2 * 1024 * 1024, "Empty or excessive image.")
    if path.suffix.lower() == ".bin":
        payload = raw
    elif path.suffix.lower() == ".hex":
        memory, address_base, ended = {}, 0, False
        for line in raw.decode("ascii").splitlines():
            require(not ended and line.startswith(":"), "Invalid HEX record or data after EOF.")
            record = bytes.fromhex(line[1:])
            require(len(record) >= 5 and len(record) == record[0] + 5 and sum(record) % 256 == 0,
                    "Invalid HEX length/checksum.")
            count, address, kind = record[0], int.from_bytes(record[1:3], "big"), record[3]
            data = record[4:-1]
            if kind == 0:
                require(count > 0, "Empty HEX data record.")
                for offset, byte in enumerate(data):
                    target = address_base + address + offset
                    require(FLASH_BASE <= target < FLASH_BASE + FLASH_BYTES and target not in memory,
                            "HEX outside Flash or overlapping records.")
                    memory[target] = byte
            elif kind == 1:
                require(count == address == 0, "Invalid HEX EOF.")
                ended = True
            elif kind in (2, 4):
                require(count == 2 and address == 0, "Invalid HEX address record.")
                address_base = int.from_bytes(data, "big") << (4 if kind == 2 else 16)
            elif kind == 5:
                require(count == 4 and address == 0, "Invalid HEX start-address record.")
            else:
                raise H60Error("Unsupported HEX record type.")
        require(ended and memory and all(FLASH_BASE + n in memory for n in range(8)),
                "Missing HEX EOF or initial vectors.")
        require(min(memory) == FLASH_BASE, "HEX must start at Flash base.")
        payload = bytes(memory.get(n, 255) for n in range(FLASH_BASE, max(memory) + 1))
    else:
        raise H60Error("Use a .bin or .hex image.")
    require(8 <= len(payload) <= FLASH_BYTES, "Image outside the 512 KiB target.")
    stack, reset = struct.unpack_from("<II", payload)
    require((0x20000000 < stack <= 0x20020000 or 0x10000000 < stack <= 0x10010000)
            and stack % 8 == 0 and reset & 1
            and FLASH_BASE <= (reset & ~1) < FLASH_BASE + len(payload), "Invalid stack/reset vector.")
    if path.suffix.lower() == ".hex":
        require((reset & ~1) in memory, "Reset vector points into a HEX gap.")
    return {"length": len(payload), "sha256_file": sha256(raw), "sha256_payload": sha256(payload),
            "initial_stack": stack, "reset_vector": reset, "structural_validation_only": True}, payload


def identity_key(identity):
    require(isinstance(identity, dict) and identity.get("schema") == "h60.rom-identity.v1",
            "Unsupported device identity.")
    require(type(identity.get("pid")) is int and identity["pid"] == EXPECTED_PID
            and type(identity.get("flash_size_kib")) is int and identity["flash_size_kib"] == 512
            and identity.get("base") == FLASH_BASE
            and identity.get("board_revision_operator_asserted") == "V3.7", "Not the expected H60 V3.7/512 KiB target.")
    try:
        uid = bytes.fromhex(identity.get("uid_hex", ""))
    except (TypeError, ValueError) as exc:
        raise H60Error("Malformed local device identity.") from exc
    require(len(uid) == 12 and uid not in (bytes(12), b"\xff" * 12), "Invalid local device identity.")
    return identity["pid"], uid, identity["flash_size_kib"], identity["base"]


def read_exact(link, count, timeout=2.0):
    deadline, data = time.monotonic() + timeout, bytearray()
    while len(data) < count:
        require(time.monotonic() < deadline, f"Serial timeout ({len(data)}/{count} bytes).")
        block = link.read(count - len(data))
        require(len(block) <= count - len(data), "Transport returned excess bytes.")
        data.extend(block)
    return bytes(data)


def send(link, data):
    require(link.write(data) == len(data), "Short serial write; transaction is not replayed.")
    link.flush()


def disable_hupcl(link):
    if os.name != "posix":
        return
    import termios
    attributes = termios.tcgetattr(link.fileno())
    attributes[2] &= ~termios.HUPCL
    termios.tcsetattr(link.fileno(), termios.TCSANOW, attributes)
    require(not termios.tcgetattr(link.fileno())[2] & termios.HUPCL, "Could not disable HUPCL.")


@contextmanager
def open_link(port, baud, *, application=False, factory=None, hupcl=disable_hupcl):
    require(isinstance(port, str) and (Path(port).is_absolute() or re.fullmatch(r"COM[1-9][0-9]*", port, re.I)),
            "Use an explicit absolute device path or COM number.")
    if factory is None:
        factory = importlib.import_module("serial").Serial
    options = dict(port=None, baudrate=baud, bytesize=8, parity="N" if application else "E",
                   stopbits=1, timeout=.02, write_timeout=1, rtscts=False, dsrdtr=False)
    if os.name == "posix":
        options["exclusive"] = True
    link = factory(**options)
    try:
        link.dtr, link.rts = bool(application), False
        link.port = port
        link.open()
        hupcl(link)
        yield link
    finally:
        link.close()  # No line restoration, reset, GO or protection changes.


def enter_rom(link, entry, journal, sleep=time.sleep):
    require(entry in ("manual", "inverted-both"), "Unsupported ROM entry profile.")
    if entry == "inverted-both":
        for dtr, rts, seconds in ((True, False, .05), (False, False, .02),
                                  (False, True, .08), (False, False, .18)):
            journal.event("rom_entry_lines_requested", dtr=dtr, rts=rts)
            link.dtr, link.rts = dtr, rts
            sleep(seconds)
    link.reset_input_buffer()
    link.reset_output_buffer()


class Rom:
    """Read-only AN3155 subset. No arbitrary command passthrough."""
    def __init__(self, link, timeout=2.0):
        self.link, self.timeout, self.commands, self.version = link, timeout, set(), None

    def ack(self):
        reply = read_exact(self.link, 1, self.timeout)[0]
        require(reply == ACK, "ROM NACK; no unprotect attempted." if reply == NACK
                else f"Unexpected ROM byte 0x{reply:02X}; no retry/resynchronization.")

    def command(self, number):
        require(number in (0x00, 0x02, 0x11), "Read-only ROM command rejected.")
        send(self.link, bytes((number, number ^ 255)))
        self.ack()

    def connect(self):
        send(self.link, b"\x7f")
        self.ack()
        self.command(0)
        count = read_exact(self.link, 1, self.timeout)[0]
        require(2 <= count <= 31, "Invalid GET response length.")
        data = read_exact(self.link, count + 1, self.timeout)
        self.ack()
        self.version, self.commands = data[0], set(data[1:])
        require({0, 2, 0x11}.issubset(self.commands), "ROM lacks required read commands.")

    def read_memory(self, address, length):
        require(type(length) is int and 1 <= length <= 256, "Read length must be 1..256.")
        require((FLASH_BASE <= address and address + length <= FLASH_BASE + FLASH_BYTES)
                or (address == SIGNATURE_BASE and length == 256), "Read outside Flash/signature scope.")
        self.command(0x11)
        data = address.to_bytes(4, "big")
        send(self.link, data + bytes((xor(data),)))
        self.ack()
        send(self.link, bytes((length - 1, (length - 1) ^ 255)))
        self.ack()
        return read_exact(self.link, length, self.timeout)

    def identify(self):
        self.command(2)
        require(read_exact(self.link, 1, self.timeout) == b"\x01", "GET ID must contain two bytes.")
        pid = int.from_bytes(read_exact(self.link, 2, self.timeout), "big")
        self.ack()
        require(pid == EXPECTED_PID, "Unexpected MCU family; no fallback capacity.")
        block = self.read_memory(SIGNATURE_BASE, 256)
        identity = {"schema": "h60.rom-identity.v1", "pid": pid,
                    "uid_hex": block[0x10:0x1c].hex(),
                    "flash_size_kib": int.from_bytes(block[0x22:0x24], "little"),
                    "board_revision_operator_asserted": "V3.7", "base": FLASH_BASE,
                    "bootloader_version": self.version,
                    "family_only_identified_by_pid": True, "private_local_record": True}
        identity_key(identity)
        return identity


def xor(data):
    result = 0
    for byte in data:
        result ^= byte
    return result


def read_flash(rom, path, journal, phase):
    with Path(path).open("xb") as stream:
        for offset in range(0, FLASH_BYTES, 256):
            stream.write(rom.read_memory(FLASH_BASE + offset, 256))
            if (offset + 256) % 65536 == 0:
                journal.event("read_progress", phase=phase, completed=offset + 256, total=FLASH_BYTES)
        stream.flush()
        os.fsync(stream.fileno())
    return read_file(path)


def load_baseline(directory):
    directory = Path(directory)
    metadata = read_json(directory / "baseline.json")
    require(metadata.get("schema") == "h60.lab-baseline.v1" and metadata.get("status") == "verified",
            "Baseline is incomplete or unsupported.")
    identity_key(metadata.get("identity"))
    kind, records = metadata.get("source_kind"), metadata.get("reads")
    required = {"two-rom-reads": 2, "verified-flash-readback": 1}.get(kind)
    require(required is not None and type(metadata.get("read_count")) is int
            and metadata["read_count"] == required and isinstance(records, list) and len(records) == required,
            "Baseline provenance/read count mismatch.")
    files, images = [directory / "baseline.json"], []
    names = set()
    for record in records:
        name = record["filename"]
        require(isinstance(name, str) and Path(name).name == name and name not in names,
                "Invalid/repeated baseline filename.")
        names.add(name)
        data = read_file(directory / name, record["sha256"])
        require(record["length"] == len(data) == FLASH_BYTES, "Baseline must contain all 512 KiB.")
        files.append(directory / name)
        images.append(data)
    require(all(image == images[0] for image in images), "The baseline reads differ.")
    if kind == "verified-flash-readback":
        source_path = directory / "source-result.json"
        source = read_json(source_path, metadata["source_result_sha256"])
        require(source.get("schema") == "h60.lab-flash-result.v1" and source.get("status") == "verified"
                and source.get("readback_sha256") == sha256(images[0])
                and source.get("preserved_sectors_1_to_7") is True
                and identity_key(source.get("identity")) == identity_key(metadata["identity"]),
                "Source result does not verify this complete readback/device.")
        count = source.get("payload_bytes")
        require(type(count) is int and 8 <= count <= SECTOR_ZERO_BYTES and count % 4 == 0
                and sha256(images[0][:count]) == source.get("payload_sha256"),
                "Source payload does not match the complete readback.")
        files.append(source_path)
    return metadata, images[0], files
