#!/usr/bin/env python3
"""Import a checked, minimal private vendor dependency set; never access hardware.

Accept the original vendor ZIP, either named inner ZIP, or an extracted directory.
No download, archive extraction, or unverified source substitution is performed.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "firmware/forward-3s/vendor-lock.json"
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transformed(entry, data):
    if sha(data) != entry["pristine_sha256"]:
        raise ValueError("Pristine checksum mismatch: " + entry["member"])
    operation = entry.get("transform")
    if operation == "startup-fatal-stop-v1":
        data = data.replace(b"\r\n", b"\n")
        before = b"  b  Infinite_Loop\n"
        if data.count(before) != 1:
            raise ValueError("Startup handler anchor is not unique")
        data = data.replace(before, b"  b.w JUANILLO_FatalStop\n") + b"\n"
    elif operation is not None:
        raise ValueError("Unknown source transformation: " + operation)
    if sha(data) != entry["output_sha256"]:
        raise ValueError("Output checksum mismatch: " + entry["output"])
    return data


def checked_read(archive, name, limit=MAX_MEMBER_BYTES):
    info = archive.getinfo(name)
    if info.file_size > limit:
        raise ValueError("Archive member is larger than its allowed limit: " + name)
    return archive.read(info)


def locate_in_zip(source, entries):
    found = {}
    with zipfile.ZipFile(source) as outer:
        names = set(outer.namelist())
        direct = [e for e in entries if e["member"] in names]
        for entry in direct:
            found[entry["output"]] = transformed(entry, checked_read(outer, entry["member"]))
        for archive_name in sorted({e["archive"] for e in entries}):
            candidates = sorted(n for n in names if PurePosixPath(n).name == archive_name)
            for candidate in candidates:
                packed = checked_read(outer, candidate, MAX_ARCHIVE_BYTES)
                expected = {e["archive_sha256"] for e in entries if e["archive"] == archive_name}
                if sha(packed) not in expected:
                    raise ValueError("Inner archive checksum mismatch: " + archive_name)
                with zipfile.ZipFile(io.BytesIO(packed)) as inner:
                    for entry in entries:
                        if entry["archive"] == archive_name:
                            found[entry["output"]] = transformed(entry, checked_read(inner, entry["member"]))
    return found


def locate_in_directory(source, entries):
    found = {}
    # Match the full package-relative suffix as well as the pristine checksum.
    # A directory can be either the package root or its enclosing extraction.
    for entry in entries:
        suffix = PurePosixPath(entry["member"])
        candidates = [source / suffix]
        candidates.extend(source.rglob(suffix.name))
        for candidate in sorted(set(candidates)):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            parts = candidate.parts
            if tuple(parts[-len(suffix.parts):]) != suffix.parts:
                continue
            if candidate.stat().st_size > MAX_MEMBER_BYTES:
                continue
            data = candidate.read_bytes()
            if sha(data) == entry["pristine_sha256"]:
                found[entry["output"]] = transformed(entry, data)
                break
    # The outer ZIP may itself already have been extracted, leaving inner ZIPs.
    for archive_name in sorted({e["archive"] for e in entries}):
        for candidate in sorted(source.rglob(archive_name)):
            if candidate.is_file() and not candidate.is_symlink():
                found.update(locate_in_zip(candidate, entries))
    return found


def destination_path(destination, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Unsafe output path in vendor lock")
    result = destination.joinpath(*path.parts)
    # Refuse symlink parents instead of following a pre-existing private import.
    if result.is_symlink() or any(p.is_symlink() for p in result.parents if p != destination.parent):
        raise ValueError("Symlink in vendor destination: " + relative)
    return result


def verify(entries, destination):
    for entry in entries:
        path = destination_path(destination, entry["output"])
        if not path.is_file() or sha(path.read_bytes()) != entry["output_sha256"]:
            raise ValueError("Missing or changed vendor file: " + entry["output"])
    return {"verified_files": len(entries), "hardware_accessed": False}


def import_files(entries, sources, destination):
    found = {}
    for source in sources:
        if source.is_dir():
            found.update(locate_in_directory(source, entries))
        elif source.is_file() and not source.is_symlink():
            found.update(locate_in_zip(source, entries))
        else:
            raise ValueError("Source is not a regular ZIP or directory: " + str(source))
    missing = [entry["member"] for entry in entries if entry["output"] not in found]
    if missing:
        raise ValueError("Required original files not found:\n" + "\n".join(missing))
    # Validate all inputs and all existing outputs before creating any file.
    for entry in entries:
        path = destination_path(destination, entry["output"])
        if path.exists() and (not path.is_file() or path.read_bytes() != found[entry["output"]]):
            raise ValueError("Refusing to overwrite a different file: " + entry["output"])
    for entry in entries:
        path = destination_path(destination, entry["output"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(found[entry["output"]])
    return verify(entries, destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", type=Path, default=[],
                        help="Original vendor ZIP or extracted directory; repeatable")
    parser.add_argument("--destination", type=Path,
                        default=ROOT / "firmware/forward-3s/vendor")
    parser.add_argument("--verify", action="store_true", help="Only verify the existing private import")
    args = parser.parse_args(argv)
    entries = json.loads(LOCK.read_text())["files"]
    try:
        if args.verify:
            if args.source:
                parser.error("--verify does not take --source")
            result = verify(entries, args.destination)
        else:
            if not args.source:
                parser.error("At least one --source is required")
            result = import_files(entries, args.source, args.destination)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
