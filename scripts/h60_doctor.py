#!/usr/bin/env python3
"""Inspect the computer and USB enumeration without opening a serial port."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


# These IDs were observed on the reference board. An adapter ID is not board ID.
USB_REFERENCE = {
    ("1a86", "7523"): {"chip_family": "CH340/CH341", "h60_port_candidate": "USB-DEBUG", "expected_linux_driver": "ch341"},
    ("1a86", "55d4"): {"chip_family": "CH9102", "h60_port_candidate": "USB-COM", "expected_linux_driver": "cdc_acm"},
}
TTY_NAME = re.compile(r"(?:ttyUSB\d+|ttyACM\d+|ttyCH\w+)")


def read_text(path, limit=4096):
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as stream:
            return stream.read(limit).strip()
    except OSError:
        return ""


def usb_identity(path):
    vendor, product = read_text(path / "idVendor"), read_text(path / "idProduct")
    if not re.fullmatch(r"[0-9a-fA-F]{4}", vendor) or not re.fullmatch(r"[0-9a-fA-F]{4}", product):
        return None
    return vendor.lower(), product.lower()


def visible_port_users(devices, proc_root=Path("/proc")):
    """Read fd symlinks only; never inspect a process command line or device data."""
    resolved = {os.path.realpath(device): device for device in devices}
    found = {device: [] for device in devices}
    denied = False
    try:
        processes = sorted(proc_root.iterdir(), key=lambda p: p.name)
    except OSError:
        return found, True
    for process in processes:
        if not process.name.isdigit():
            continue
        try:
            descriptors = list((process / "fd").iterdir())
        except PermissionError:
            denied = True
            continue
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            device = resolved.get(os.path.realpath(target))
            if device is not None and int(process.name) not in found[device]:
                found[device].append(int(process.name))
    return found, denied


def linux_usb(sys_root=Path("/sys"), dev_root=Path("/dev"), proc_root=Path("/proc")):
    enumerated, ports = [], []
    try:
        devices = sorted((sys_root / "bus/usb/devices").iterdir())
    except OSError:
        devices = []
    for device in devices:
        identity = usb_identity(device)
        if identity in USB_REFERENCE:
            enumerated.append({"vid_pid": ":".join(identity), **USB_REFERENCE[identity]})
    try:
        ttys = sorted((sys_root / "class/tty").iterdir())
    except OSError:
        ttys = []
    for tty in ttys:
        if not TTY_NAME.fullmatch(tty.name):
            continue
        try:
            location = (tty / "device").resolve(strict=True)
        except OSError:
            continue
        identity, driver = None, None
        for parent in (location, *location.parents):
            if driver is None:
                try:
                    driver = (parent / "driver").resolve(strict=True).name
                except OSError:
                    pass
            identity = usb_identity(parent)
            if identity is not None:
                break
        if identity is None:
            continue
        device = str(dev_root / tty.name)
        ports.append({"device": device, "vid_pid": ":".join(identity),
                      **USB_REFERENCE.get(identity, {"chip_family": "other USB serial", "h60_port_candidate": None}),
                      "driver": driver, "readable": os.access(device, os.R_OK),
                      "writable": os.access(device, os.W_OK)})
    users, limited = visible_port_users([p["device"] for p in ports], proc_root)
    for port in ports:
        port["visible_owner_pids"] = users[port["device"]]
    return {"reference_usb_devices": enumerated, "ports": ports,
            "busy_scan": {"scope": "visible process fd symlinks only", "permission_limited": limited,
                          "empty_result_proves_free": False},
            "kernel_drivers_loaded_or_builtin": {name: (sys_root / "module" / name).is_dir()
                                                  for name in ("ch341", "cdc_acm")}}


def portable_ports():
    try:
        from serial.tools import list_ports
        values = list_ports.comports()
    except (ImportError, OSError):
        return {"ports": [], "enumeration_available": False,
                "hint": "Install requirements.txt in the Python environment to enumerate ports on this OS."}
    ports = []
    for port in sorted(values, key=lambda p: p.device):
        identity = (f"{port.vid:04x}", f"{port.pid:04x}") if port.vid is not None and port.pid is not None else None
        # On macOS the port filename itself can contain the hardware serial.
        device = re.sub(r"^(/dev/(?:cu|tty)\.(?:wchusbserial|usbserial|usbmodem)).+$", r"\1[redacted]", port.device)
        ports.append({"device": device, "device_name_redacted": device != port.device,
                      "vid_pid": ":".join(identity) if identity else None,
                      **USB_REFERENCE.get(identity, {"h60_port_candidate": None})})
    return {"ports": ports, "enumeration_available": True,
            "hint": "USB IDs identify adapters only; confirm the connector label. For a redacted macOS name, inspect /dev/cu.* locally."}


def tool_version(name):
    executable = shutil.which(name)
    if executable is None:
        return {"available": False}
    try:
        result = subprocess.run([executable, "--version"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", timeout=3, check=False)
        line = result.stdout.splitlines()[0][:180] if result.stdout else ""
        # Do not include personal build paths in the diagnostic report.
        line = re.sub(r"(?:[A-Za-z]:[\\/]|/)[^\s()]+", "[path]", line)
        return {"available": True, "version": line, "version_query_ok": result.returncode == 0}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": True, "version_query_ok": False}


def diagnose():
    system = platform.system()
    report = {"schema_version": 1, "read_only": True, "serial_port_opened": False,
              "os": system, "python": platform.python_version(),
              "python_supported": sys.version_info >= (3, 10),
              "python_dependencies": {name: importlib.util.find_spec(module) is not None
                                      for name, module in (("pyserial", "serial"), ("aiohttp", "aiohttp"))},
              "build_tools": {name: tool_version(name) for name in ("make", "cc", "arm-none-eabi-gcc", "arm-none-eabi-objcopy")},
              "board_identity_verified": False,
              "note": "Enumeration is not a firmware handshake. No UART bytes, DTR/RTS or resets were sent."}
    report["usb"] = linux_usb() if system == "Linux" else portable_ports()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit a structured report without serial numbers or user identity.")
    args = parser.parse_args(argv)
    report = diagnose()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Computer: {report['os']}; Python {report['python']}")
        print("Read-only USB enumeration: no serial port opened, no reset or UART data.")
        for name, present in report["python_dependencies"].items():
            print(f"Python dependency {name}: {'available' if present else 'MISSING'}")
        for name, tool in report["build_tools"].items():
            print(f"Build tool {name}: {tool.get('version', 'available' if tool['available'] else 'MISSING')}")
        for adapter in report["usb"].get("reference_usb_devices", []):
            print(f"USB enumerated: {adapter['vid_pid']} — {adapter['h60_port_candidate']} candidate")
        for port in report["usb"]["ports"]:
            candidate = port.get("h60_port_candidate") or "confirm connector"
            print(f"{port['device']}: {port.get('vid_pid')} — {candidate}")
            if report["os"] == "Linux":
                print(f"  driver={port['driver']}; access(read/write)={port['readable']}/{port['writable']}; visible owner PIDs={port['visible_owner_pids']}")
        if not report["usb"]["ports"]:
            print("No USB serial port found. Check the data cable, connector, OS driver and USB enumeration.")
        if report["os"] == "Linux":
            print("An empty owner list does not guarantee that a port is free; other users may be hidden.")
        print("Next: docs/getting-started.md and docs/usb-drivers.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
