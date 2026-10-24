#!/usr/bin/env python3
"""Offline image inspection, explicit ROM identification/backup and baseline import."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys

from h60_common import (FLASH_BYTES, ROM_BAUDS, H60Error, Journal, Rom, enter_rom,
                        identity_key, inspect_image, open_link, read_file, read_flash,
                        read_json, require, sha256, utc_now, write_json_new)


def recover(action, port, outdir, *, baud=115200, entry="manual", factory=None, hupcl=None, sleep=None):
    require(action in ("identify", "backup") and baud in ROM_BAUDS, "Invalid recovery operation.")
    outdir = Path(outdir)
    outdir.mkdir(parents=False, exist_ok=False)
    journal = Journal(outdir / "events.jsonl")
    result = {"schema": "h60.lab-recovery-result.v1", "status": "failed", "action": action,
              "private_local_record": True, "no_flash_writes": True, "no_go": True,
              "no_protection_changes": True, "post_close_hardware_state_not_measured": True}
    baseline = {"schema": "h60.lab-baseline.v1", "status": "incomplete", "created_utc": utc_now(),
                "source_kind": "two-rom-reads", "read_count": 2, "reads": [],
                "private_local_record": True, "same_rom_session": True}
    try:
        options = {"factory": factory}
        if hupcl is not None:
            options["hupcl"] = hupcl
        with open_link(port, baud, **options) as link:
            enter_rom(link, entry, journal, **({} if sleep is None else {"sleep": sleep}))
            rom = Rom(link)
            rom.connect()
            identity = rom.identify()
            baseline["identity"] = identity
            write_json_new(outdir / "identity.json", identity)
            if action == "backup":
                for number in (1, 2):
                    name = f"flash-read-{number}.bin"
                    data = read_flash(rom, outdir / name, journal, f"read-{number}")
                    baseline["reads"].append({"filename": name, "length": len(data), "sha256": sha256(data)})
                require(baseline["reads"][0]["sha256"] == baseline["reads"][1]["sha256"],
                        "The two ROM reads differ; baseline is NOT verified.")
                baseline["status"] = "verified"
            result.update(status="identified" if action == "identify" else "verified",
                          flash_bytes=FLASH_BYTES)
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        journal.event("failed", error=result["error"])
        raise
    finally:
        try:
            if action == "backup":
                if result["status"] != "verified":
                    baseline["status"] = "incomplete"
                write_json_new(outdir / "baseline.json", baseline)
            write_json_new(outdir / "result.json", result)
        finally:
            journal.close()
    return result


def import_readback(result_path, outdir):
    """Reuse one verified full readback honestly; no new ROM read is claimed."""
    result_path, outdir = Path(result_path), Path(outdir)
    source = read_json(result_path)
    require(source.get("schema") == "h60.lab-flash-result.v1" and source.get("status") == "verified"
            and source.get("preserved_sectors_1_to_7") is True, "Not a verified lab flash result.")
    identity_key(source.get("identity"))
    filename = source.get("readback_file")
    require(isinstance(filename, str) and Path(filename).name == filename, "Invalid readback filename.")
    data = read_file(result_path.parent / filename, source["readback_sha256"])
    count = source.get("payload_bytes")
    require(len(data) == FLASH_BYTES and type(count) is int and 8 <= count <= 16384 and count % 4 == 0
            and sha256(data[:count]) == source["payload_sha256"], "Incomplete or inconsistent source readback.")
    outdir.mkdir(parents=False, exist_ok=False)
    with (outdir / "flash-readback.bin").open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    with (outdir / "source-result.json").open("xb") as stream:
        stream.write(read_file(result_path))
        stream.flush()
        os.fsync(stream.fileno())
    metadata = {"schema": "h60.lab-baseline.v1", "status": "verified", "created_utc": utc_now(),
                "source_kind": "verified-flash-readback", "read_count": 1,
                "not_two_independent_backups": True, "private_local_record": True,
                "source_result_sha256": sha256(read_file(outdir / "source-result.json")),
                "identity": source["identity"],
                "reads": [{"filename": "flash-readback.bin", "length": len(data), "sha256": sha256(data)}]}
    write_json_new(outdir / "baseline.json", metadata)
    return {"status": "verified", "source_kind": metadata["source_kind"], "read_count": 1,
            "sha256": sha256(data), "port_not_opened": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("ports", help="Enumerate USB serial ports without opening them.")
    image = sub.add_parser("inspect", help="Validate a BIN/HEX offline.")
    image.add_argument("image")
    baseline = sub.add_parser("baseline", help="Offline: copy one verified full flash readback into a baseline.")
    baseline.add_argument("--flash-result", required=True)
    baseline.add_argument("--out-dir", required=True)
    for name in ("identify", "backup"):
        command = sub.add_parser(name, help="No hardware access unless --execute is supplied.")
        command.add_argument("--port", required=True)
        command.add_argument("--out-dir", required=True)
        command.add_argument("--baud", type=int, choices=ROM_BAUDS, default=115200)
        command.add_argument("--entry", choices=("manual", "inverted-both"), default="manual")
        command.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "ports":
            module = importlib.import_module("serial.tools.list_ports")
            result = [{"device": p.device, "description": p.description, "vid": p.vid, "pid": p.pid}
                      for p in module.comports()]
        elif args.action == "inspect":
            result = inspect_image(args.image)[0]
        elif args.action == "baseline":
            result = import_readback(args.flash_result, args.out_dir)
        else:
            require(not Path(args.out_dir).exists(), "Output directory must be new.")
            result = {"dry_run": True, "port_not_opened": True, "action": args.action,
                      "baud": args.baud, "entry": args.entry, "no_flash_writes": True}
            if args.execute:
                result = recover(args.action, args.port, args.out_dir, baud=args.baud, entry=args.entry)
        print(json.dumps(result, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Interrupted; no transaction replay, GO or unprotect.", file=sys.stderr)
        return 130
    except (H60Error, OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
