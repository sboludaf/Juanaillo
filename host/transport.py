"""DEBUG application transport only: no MCU reset or ISP transitions."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import time

try:
    import termios
except ImportError:  # Windows has no HUPCL/termios interface.
    termios = None


class HostError(RuntimeError):
    pass


class RawJournal:
    """New directory, exclusive files, durable raw TX/RX and structured events."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=False, exist_ok=False)
        self.stream = (self.directory / "raw.jsonl").open("x", encoding="utf-8")
        self.closed = False

    def event(self, event, **fields):
        entry = {"monotonic_ns": time.monotonic_ns(), "wall_ns": time.time_ns(),
                 "event": event, **fields}
        self.stream.write(json.dumps(entry, sort_keys=True) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def raw(self, direction, data):
        self.event("raw", direction=direction, length=len(data), hex=bytes(data).hex())

    def report(self, value):
        with (self.directory / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def close(self):
        if not self.closed:
            self.stream.close()
            self.closed = True


def disable_hupcl(serial):
    if sys.platform == "win32":
        return False
    if termios is None:
        raise HostError("Esta plataforma no ofrece termios/HUPCL; no se abre una sesión motriz.")
    attributes = termios.tcgetattr(serial.fileno())
    attributes[2] &= ~termios.HUPCL
    termios.tcsetattr(serial.fileno(), termios.TCSANOW, attributes)
    if termios.tcgetattr(serial.fileno())[2] & termios.HUPCL:
        raise HostError("No se pudo desactivar HUPCL.")
    return True


def valid_port(port):
    if not isinstance(port, str) or not port:
        return False
    if sys.platform == "win32":
        return re.fullmatch(r"(?:\\\\\.\\)?COM[1-9][0-9]*", port, re.IGNORECASE) is not None
    return Path(port).is_absolute()


class DebugTransport:
    def __init__(self, serial, journal):
        self.serial = serial
        self.journal = journal
        self.closed = False

    @classmethod
    def open(cls, port, journal, *, factory=None, hupcl_setter=disable_hupcl):
        if not valid_port(port):
            raise HostError("Se requiere un puerto DEBUG explícito: ruta absoluta POSIX o COM de Windows.")
        if factory is None:
            factory = importlib.import_module("serial").Serial
        options = dict(port=None, baudrate=230400, bytesize=8, parity="N", stopbits=1,
                       timeout=.005, write_timeout=.1, rtscts=False, dsrdtr=False)
        if sys.platform != "win32":
            options["exclusive"] = True
        serial = factory(**options)
        try:
            # pyserial assertions for the demonstrated inverted-both circuit:
            # application BOOT low, NRST released. No reset pulse on this path.
            serial.dtr = True
            serial.rts = False
            serial.port = port
            serial.open()
            hupcl_disabled = hupcl_setter(serial)
            journal.event("debug_application_port_opened", port=port, baud=230400,
                          framing="8N1", dtr=True, rts=False,
                          hupcl_disabled=hupcl_disabled is True, platform=sys.platform,
                          reset_requested=False)
            return cls(serial, journal)
        except BaseException:
            serial.close()
            raise

    def write(self, data):
        data = bytes(data)
        self.journal.raw("tx-requested", data)
        count = self.serial.write(data)
        self.serial.flush()
        if count != len(data):
            self.journal.event("short_write", requested=len(data), written=count)
            raise HostError("Escritura serie incompleta; no se reintenta.")
        self.journal.event("tx-complete", length=count)
        return count

    def read(self, count):
        data = bytes(self.serial.read(count))
        if data:
            if len(data) > count:
                raise HostError("El transporte devolvió demasiados bytes.")
            self.journal.raw("rx", data)
        return data

    def close(self):
        if not self.closed:
            # Deliberately no DTR/RTS restoration or reset transition.
            self.serial.close()
            self.closed = True
            self.journal.event("port_closed_without_line_restore")


def sha256(data):
    return hashlib.sha256(data).hexdigest()
