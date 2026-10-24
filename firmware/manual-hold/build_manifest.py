import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument("--build", required=True)
parser.add_argument("--compiler", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent
build = Path(args.build)
target = build / "h60-manual-hold"
binary = target.with_suffix(".bin").read_bytes()
marker = "H60_MANUAL_TURN_CONTROL_V1__"
if len(binary) > 16384 or len(binary) % 4 or marker.encode() + b"\0" not in binary:
    raise SystemExit("Invalid sector-zero image alignment, size or marker.")
files = [root / "Makefile", root / "build_manifest.py", root / "vendor-lock.json"]
for part in ("src", "include", "build_support", "vendor", "tests"):
    files.extend(p for p in (root / part).rglob("*")
                 if p.is_file() and p.suffix.lower() in (".c", ".h", ".s", ".ld", ".py"))
caps = struct.pack(">BBBBHHHHII", 1, 6, 15, 10, 100, 5000, 4, 10000, 10000000, 150) + marker.encode()
record = {
    "schema": "h60.manual-hold-build.v1", "target": "STM32F407VE", "profile": 6,
    "marker": marker, "motor_capable": True, "control_mode": "leased-manual-hold",
    "fixed_motor_channels": ["A", "B", "C", "D"], "fixed_motor_mask": 15,
    "fixed_reversed_mask": 10, "forward_raw_directions": [1, -1, 1, -1],
    "reverse_raw_directions": [-1, 1, -1, 1],
    "left_raw_directions": [1, 1, 1, 1], "right_raw_directions": [-1, -1, -1, -1],
    "supported_directions": [1, -1, 2, -2], "duty_permille": 100, "pwm_hz": 5000,
    "lease_ms": 150, "max_burst_ms": 10000, "wake_min_ms": 4,
    "absolute_envelope_us": 10000000, "one_fire_per_boot": False,
    "requires_stop_after_limit": True, "sticky_fault": True,
    "uart": 1, "uart_pins": ["PA9", "PA10"], "baudrate": 230400, "framing": "8N1",
    "caps_hex": caps.hex(), "status_payload_bytes": 44, "move_payload_bytes": 9,
    "nonce_source": "STM32 hardware RNG per boot; failure leaves FAULT and outputs off",
    "hardware_cutoff": "No autonomous timer duration cutoff",
    "software_cutoff": "SysTick priority0 and main/DWT absolute10s plus150ms MOVE lease; IWDG backup",
    "image_bytes": len(binary), "payload_sha256": hashlib.sha256(binary).hexdigest(),
    "sources": {str(p.relative_to(root)): digest(p) for p in sorted(files)},
    "artifacts": {target.with_suffix(ext).name: digest(target.with_suffix(ext))
                  for ext in (".elf", ".bin", ".hex", ".map")},
    "compiler": subprocess.check_output([args.compiler, "--version"], text=True).splitlines()[0],
    "hardware_tested": False,
}
(build / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({key: record[key] for key in ("schema", "image_bytes", "payload_sha256")}, indent=2))
