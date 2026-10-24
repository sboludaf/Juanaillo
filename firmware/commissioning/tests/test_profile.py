import os
import subprocess


def preprocess(definitions):
    arguments = [os.environ.get("CC", "cc"), "-x", "c", "-E", "-P", "-I../Robot"]
    arguments.extend(f"-D{name}={value}" for name, value in definitions.items())
    return subprocess.run(arguments + ["-"], input='#include "juanillo_profile.h"\n', text=True, capture_output=True)


assert preprocess({}).returncode == 0
assert preprocess({"JUANILLO_MOTION_ENABLED": 1}).returncode != 0
profile = {
    "JUANILLO_MOTION_ENABLED": 1,
    "JUANILLO_PROFILE_CALIBRATED": 1,
    "JUANILLO_EFFECTIVE_TRACK_MM": 200,
    "JUANILLO_MAX_LINEAR_MM_S": 100,
    "JUANILLO_MAX_ANGULAR_MRAD_S": 100,
    "JUANILLO_MAX_LINEAR_ACCEL_MM_S2": 100,
    "JUANILLO_MAX_ANGULAR_ACCEL_MRAD_S2": 100,
    "JUANILLO_MAX_PWM": 100,
    "JUANILLO_KP": 100,
    "JUANILLO_BATTERY_FULL_SCALE_MV": 36300,
}
for index, wheel in enumerate("ABCD"):
    profile[f"JUANILLO_ENCODER_COUNTS_{wheel}"] = 1000
    profile[f"JUANILLO_ENCODER_SIGN_{wheel}"] = 1
    profile[f"JUANILLO_MOTOR_SIGN_{wheel}"] = 1
    profile[f"JUANILLO_WHEEL_SIDE_{wheel}"] = 1 if index < 2 else 2
assert preprocess(profile).returncode == 0
for name in list(profile):
    if name not in {"JUANILLO_MOTION_ENABLED"}:
        incomplete = dict(profile)
        incomplete[name] = 0
        assert preprocess(incomplete).returncode != 0, name
assert preprocess({"JUANILLO_COMMAND_UART": 2}).returncode != 0
print("PASS: commissioning default and compile-time rejection of incomplete motion profiles; synthetic test profile only")
