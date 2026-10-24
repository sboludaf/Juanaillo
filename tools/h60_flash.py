#!/usr/bin/env python3
"""Prepare/review a portable plan; optionally replace ONLY Flash sector zero."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

from h60_common import (FLASH_BASE, FLASH_BYTES, SECTOR_ZERO_BYTES, ROM_BAUDS, H60Error,
                        Journal, Rom, enter_rom, identity_key, inspect_image, load_baseline,
                        open_link, read_file, read_flash, read_json, relative, require,
                        resolve, send, sha256, utc_now, write_json_new, xor)


def verify_build(image, manifest_path):
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent.parent
    manifest = read_json(manifest_path)
    info, payload = inspect_image(image)
    require(Path(image).suffix.lower() == ".bin", "Plan the BIN image; the manifest must also bind its HEX.")
    require(manifest.get("target") == "STM32F407VE" and manifest.get("image_bytes") == len(payload)
            and manifest.get("payload_sha256") == sha256(payload), "Build target/length/payload mismatch.")
    marker = manifest.get("marker")
    require(isinstance(marker, str) and 0 < len(marker) <= 128
            and marker.encode("ascii") + b"\0" in payload, "Missing declared firmware marker.")
    require(8 <= len(payload) <= SECTOR_ZERO_BYTES and len(payload) % 4 == 0,
            "Only aligned images wholly inside sector zero are supported.")
    files = [manifest_path]
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, dict) and len(artifacts) == 4
            and {Path(n).suffix for n in artifacts} == {".bin", ".hex", ".elf", ".map"},
            "Manifest must bind BIN, HEX, ELF and map artifacts.")
    bins = []
    for name, digest in artifacts.items():
        require(isinstance(name, str) and Path(name).name == name, "Invalid artifact filename.")
        path = manifest_path.parent / name
        read_file(path, digest)
        files.append(path)
        if path.suffix == ".bin":
            bins.append(path.resolve())
        if path.suffix == ".hex":
            require(inspect_image(path)[1] == payload, "HEX and BIN differ.")
    require(bins == [Path(image).resolve()], "The image is not the manifest BIN.")
    sources = manifest.get("sources")
    require(isinstance(sources, dict) and bool(sources), "Missing build source inventory.")
    for name, digest in sources.items():
        require(isinstance(name, str) and not Path(name).is_absolute(), "Invalid source path.")
        path = (root / name).resolve()
        require(path.is_relative_to(root), "Source escapes build root.")
        read_file(path, digest)
        files.append(path)
    return info, payload, manifest, files


def create_plan(image, manifest_path, baseline_dir, output, port, baud=115200, entry="manual"):
    output = Path(output).resolve()
    require(not output.exists(), "Plan output already exists.")
    require(baud in ROM_BAUDS and entry in ("manual", "inverted-both"), "Invalid ROM transport settings.")
    require(isinstance(port, str) and bool(port), "An explicit device port is required.")
    info, payload, manifest, build_files = verify_build(image, manifest_path)
    baseline, previous, baseline_files = load_baseline(baseline_dir)
    expected = payload + b"\xff" * (SECTOR_ZERO_BYTES - len(payload)) + previous[SECTOR_ZERO_BYTES:]
    tool_files = [Path(__file__).with_name(name) for name in
                  ("h60_common.py", "h60_recovery.py", "h60_flash.py", "h60_boot.py")]
    inputs = {relative(p, output.parent): sha256(read_file(p))
              for p in build_files + baseline_files + tool_files}
    plan = {"schema": "h60.lab-flash-plan.v1", "created_utc": utc_now(),
            "private_local_record": True, "port": port, "rom_baud": baud, "rom_entry": entry,
            "identity": baseline["identity"], "baseline_dir": relative(baseline_dir, output.parent),
            "baseline_source_kind": baseline["source_kind"], "baseline_read_count": baseline["read_count"],
            "baseline_sha256": sha256(previous), "image": relative(image, output.parent),
            "manifest": relative(manifest_path, output.parent), "image_info": info,
            "firmware_marker": manifest["marker"], "payload_sha256": sha256(payload),
            "payload_bytes": len(payload), "expected_flash_sha256": sha256(expected),
            "erase_sectors": [0], "flash_base": FLASH_BASE, "flash_bytes": FLASH_BYTES,
            "auto_go": False, "auto_reset": False, "protection_changes": False,
            "input_sha256": inputs}
    write_json_new(output, plan)
    return {"plan_sha256": sha256(read_file(output)), "payload_bytes": len(payload),
            "expected_flash_sha256": sha256(expected), "input_files": len(inputs),
            "port_not_opened": True}


@dataclass(frozen=True)
class Prepared:
    plan: dict
    payload: bytes
    baseline: bytes
    expected: bytes
    plan_sha256: str


def prepare(plan_path, expected_plan_sha256):
    plan_path = Path(plan_path).resolve()
    plan = read_json(plan_path, expected_plan_sha256)
    require(plan.get("schema") == "h60.lab-flash-plan.v1"
            and plan.get("erase_sectors") == [0] and plan.get("auto_go") is False
            and plan.get("auto_reset") is False and plan.get("protection_changes") is False
            and plan.get("flash_base") == FLASH_BASE and plan.get("flash_bytes") == FLASH_BYTES,
            "Plan exceeds the supported sector-zero/no-GO/no-protection scope.")
    require(plan.get("rom_baud") in ROM_BAUDS and plan.get("rom_entry") in ("manual", "inverted-both"),
            "Unsupported transport settings.")
    identity_key(plan.get("identity"))
    inputs = plan.get("input_sha256")
    require(isinstance(inputs, dict) and bool(inputs), "Missing plan input inventory.")
    for name, digest in inputs.items():
        read_file(resolve(plan_path.parent, name), digest)
    baseline, previous, _ = load_baseline(resolve(plan_path.parent, plan["baseline_dir"]))
    require(identity_key(baseline["identity"]) == identity_key(plan["identity"])
            and sha256(previous) == plan["baseline_sha256"]
            and baseline["source_kind"] == plan["baseline_source_kind"]
            and baseline["read_count"] == plan["baseline_read_count"], "Baseline differs from reviewed plan.")
    info, payload, manifest, _ = verify_build(resolve(plan_path.parent, plan["image"]),
                                              resolve(plan_path.parent, plan["manifest"]))
    require(info == plan["image_info"] and manifest["marker"] == plan["firmware_marker"]
            and sha256(payload) == plan["payload_sha256"] and len(payload) == plan["payload_bytes"],
            "Firmware differs from reviewed plan.")
    expected = payload + b"\xff" * (SECTOR_ZERO_BYTES - len(payload)) + previous[SECTOR_ZERO_BYTES:]
    require(sha256(expected) == plan["expected_flash_sha256"], "Complete Flash expectation mismatch.")
    return Prepared(plan, payload, previous, expected, expected_plan_sha256)


class SectorZeroWriter(Rom):
    """Two bounded mutation methods; inherited command() remains read-only."""
    def __init__(self, link, payload, journal):
        super().__init__(link)
        require(8 <= len(payload) <= SECTOR_ZERO_BYTES and len(payload) % 4 == 0, "Invalid fixed payload.")
        self.payload, self.journal = bytes(payload), journal
        self.erase_attempted = self.write_attempted = self.erased = False
        self.next_address = FLASH_BASE

    def erase_zero(self):
        require(not self.erase_attempted and self.next_address == FLASH_BASE, "Erase is never repeated.")
        require({0x11, 0x31, 0x44}.issubset(self.commands), "ROM lacks required commands.")
        self.erase_attempted = True  # Set before logging/TX, including failed first attempts.
        self.journal.event("erase_requested", sector=0, command=0x44)
        send(self.link, b"\x44\xbb")
        self.ack()
        send(self.link, bytes(5))  # One sector; sector number zero; XOR zero.
        old = self.timeout
        try:
            self.timeout = 5.0
            self.ack()
        finally:
            self.timeout = old
        self.erased = True

    def write_image(self):
        require(self.erased and not self.write_attempted and self.next_address == FLASH_BASE,
                "Write needs one successful erase; write attempts are never replayed.")
        self.write_attempted = True
        for offset in range(0, len(self.payload), 256):
            address, block = FLASH_BASE + offset, self.payload[offset:offset + 256]
            require(address == self.next_address and address % 4 == 0 and len(block) % 4 == 0
                    and 0 < len(block) <= 256 and address + len(block) <= FLASH_BASE + len(self.payload),
                    "Write outside the reviewed payload.")
            self.journal.event("write_requested", address=address, length=len(block), command=0x31)
            send(self.link, b"\x31\xce")
            self.ack()
            encoded = address.to_bytes(4, "big")
            send(self.link, encoded + bytes((xor(encoded),)))
            self.ack()
            packet = bytes((len(block) - 1,)) + block
            send(self.link, packet + bytes((xor(packet),)))
            self.ack()
            self.next_address += len(block)


def apply(prepared, outdir, *, factory=None, hupcl=None, sleep=None):
    outdir = Path(outdir)
    outdir.mkdir(parents=False, exist_ok=False)
    journal = Journal(outdir / "events.jsonl")
    plan = prepared.plan
    result = {"schema": "h60.lab-flash-result.v1", "status": "failed", "created_utc": utc_now(),
              "private_local_record": True, "plan_sha256": prepared.plan_sha256,
              "payload_bytes": len(prepared.payload), "payload_sha256": sha256(prepared.payload),
              "no_go": True, "no_reset_on_exit": True, "no_protection_changes": True,
              "post_close_hardware_state_not_measured": True}
    try:
        options = {"factory": factory}
        if hupcl is not None:
            options["hupcl"] = hupcl
        with open_link(plan["port"], plan["rom_baud"], **options) as link:
            result["stage"] = "rom-entry"
            entry_options = {} if sleep is None else {"sleep": sleep}
            enter_rom(link, plan["rom_entry"], journal, **entry_options)
            writer = SectorZeroWriter(link, prepared.payload, journal)
            writer.connect()
            identity = writer.identify()
            result["identity"] = identity
            require(identity_key(identity) == identity_key(plan["identity"]), "Live identity differs; no erase.")
            require({0x11, 0x31, 0x44}.issubset(writer.commands), "Missing commands; no erase.")
            result["stage"] = "full-compare-before-erase"
            current = read_flash(writer, outdir / "preflash.bin", journal, "before-erase")
            require(current == prepared.baseline, "Current Flash differs from the baseline; no erase.")
            journal.event("full_baseline_match", sha256=sha256(current))
            result["stage"] = "erase-sector-zero"
            writer.erase_zero()
            result["stage"] = "write-reviewed-image"
            writer.write_image()
            result["stage"] = "full-readback"
            readback = read_flash(writer, outdir / "readback.bin", journal, "after-write")
            require(readback == prepared.expected, "Full readback mismatch; remain in ROM.")
            result.update(status="verified", readback_file="readback.bin", readback_sha256=sha256(readback),
                          preserved_sectors_1_to_7=True)
            journal.event("complete_flash_verified", sha256=sha256(readback))
    except BaseException as exc:
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        journal.event("failed", error=result["error"])
        raise
    finally:
        try:
            write_json_new(outdir / "result.json", result)
        finally:
            journal.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan", help="Offline: bind a build and local baseline into a reviewable plan.")
    for name in ("image", "manifest", "baseline", "output", "port"):
        plan.add_argument("--" + name, required=True)
    plan.add_argument("--baud", type=int, choices=ROM_BAUDS, default=115200)
    plan.add_argument("--entry", choices=("manual", "inverted-both"), default="manual")
    run = sub.add_parser("apply", help="Offline validation unless --execute is present.")
    run.add_argument("--plan", required=True)
    run.add_argument("--plan-sha256", required=True)
    run.add_argument("--out-dir", required=True)
    run.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            summary = create_plan(args.image, args.manifest, args.baseline, args.output,
                                  args.port, args.baud, args.entry)
        else:
            prepared = prepare(args.plan, args.plan_sha256)
            require(not Path(args.out_dir).exists(), "Output directory must be new.")
            summary = {"dry_run": True, "port_not_opened": True, "write_bytes": len(prepared.payload),
                       "erase_sectors": [0], "readback_bytes": FLASH_BYTES, "no_go": True,
                       "baseline_kind": prepared.plan["baseline_source_kind"],
                       "baseline_read_count": prepared.plan["baseline_read_count"]}
            if args.execute:
                result = apply(prepared, args.out_dir)
                summary = {"status": result["status"], "readback_sha256": result["readback_sha256"],
                           "result_sha256": sha256(read_file(Path(args.out_dir) / "result.json")), "no_go": True}
        print(json.dumps(summary, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Interrupted; no automatic retry, GO or protection changes.", file=sys.stderr)
        return 130
    except (H60Error, OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
