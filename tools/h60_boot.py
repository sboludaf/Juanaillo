#!/usr/bin/env python3
"""Explicit boot of a verified image via the demonstrated inverted-both circuit.

No UART bytes are transmitted. Reset clears application one-shot state, so this
operation is separate from flash and from every motion client. Offline by default.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from h60_common import (FLASH_BYTES, SECTOR_ZERO_BYTES, H60Error, identity_key, open_link,
                        read_file, read_json, require, sha256, utc_now)


def prepare(result_path, expected_sha256, record_path=None):
    result_path = Path(result_path)
    result = read_json(result_path, expected_sha256)
    require(result.get("schema") == "h60.lab-flash-result.v1" and result.get("status") == "verified"
            and result.get("preserved_sectors_1_to_7") is True and result.get("no_go") is True
            and result.get("no_protection_changes") is True, "Not a verified bounded flash result.")
    identity_key(result.get("identity"))
    name = result.get("readback_file")
    require(isinstance(name, str) and Path(name).name == name, "Invalid readback filename.")
    data = read_file(result_path.parent / name, result["readback_sha256"])
    length = result.get("payload_bytes")
    require(len(data) == FLASH_BYTES and type(length) is int and 8 <= length <= SECTOR_ZERO_BYTES
            and length % 4 == 0 and sha256(data[:length]) == result["payload_sha256"],
            "Full readback/payload verification failed.")
    record_path = Path(record_path) if record_path is not None else result_path.parent / "boot-request.json"
    require(not record_path.exists(), "Boot already attempted; no automatic repeat.")
    return record_path, {"schema": "h60.lab-boot-request.v1", "created_utc": utc_now(),
                         "flash_result_sha256": expected_sha256, "payload_sha256": result["payload_sha256"],
                         "readback_sha256": result["readback_sha256"], "tx_bytes": 0,
                         "motor_commands": 0, "boot_requested": False,
                         "application_response_verified": False, "automatic_retry": False}


def boot(port, record_path, record, *, factory=None, hupcl=None, sleep=time.sleep):
    with Path(record_path).open("x", encoding="utf-8") as stream:
        def save():
            stream.seek(0)
            json.dump(record, stream, indent=2)
            stream.write("\n")
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        try:
            save()  # Reserve the attempt durably before opening/resetting.
            options = {"application": True, "factory": factory}
            if hupcl is not None:
                options["hupcl"] = hupcl
            with open_link(port, 230400, **options) as link:
                sleep(.05)
                record.update(boot_requested=True, requested_reset_pulse_ms=80,
                              requested_final_dtr=True, requested_final_rts=False,
                              line_profile="inverted-both")
                save()
                link.rts = True
                sleep(.08)
                link.rts = False
                sleep(.25)
                record["reset_sequence_completed"] = True
        except BaseException as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            save()
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flash-result", required=True)
    parser.add_argument("--result-sha256", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--record", help="Default: boot-request.json beside the flash result.")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        path, record = prepare(args.flash_result, args.result_sha256, args.record)
        result = {"dry_run": True, "port_not_opened": True, "explicit_reset_count": 1, **record}
        if args.execute:
            result = boot(args.port, path, record)
        print(json.dumps(result, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Interrupted; boot is not automatically repeated.", file=sys.stderr)
        return 130
    except (H60Error, OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
