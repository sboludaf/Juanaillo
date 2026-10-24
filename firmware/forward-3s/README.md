This is the source of the four-wheel forward test: profile 4, A/C raw positive,
B/D raw negative, 10% duty at 5 kHz, one three-second activation per boot. The
application source and native tests are preserved unchanged from the tested
candidate. The build layout and toolchain selection are portable adaptations.

The firmware can energize motors. It requires a fresh boot nonce, recent STOP,
one second of encoder quiet, PREPARE and one FIRE. Heartbeats maintain a 100 ms
lease during the test. STOP, expired lease, malformed input or timing faults
disable all motor outputs. SysTick/main-loop DWT checks stop PWM after 3000 ms;
the absolute envelope is 3005 ms from FIRE. These are software cutoffs with an
independent watchdog backup. There is no autonomous three-second timer cutoff.

From the repository root, import the dependencies from your own original vendor
package, then build using an Arm GNU toolchain installed on PATH:

```sh
python3 scripts/import_vendor.py --source '/path/to/OpenCTR H60 code.zip'
make -C firmware/forward-3s test
make -C firmware/forward-3s all
```

`CROSS_COMPILE` can select another compiler prefix. `NEWLIB_INCLUDE` and
`NEWLIB_LIB_DIR` are optional overrides for toolchains with separately packaged
newlib. The build produces ELF, BIN, HEX, map and `build/manifest.json`; it does
not open a serial port or flash a board. `BUILD=/tmp/another-build` selects an
independent output directory for reproducibility checks.

The dependency lock contains the exact original member names, pristine SHA-256
hashes, resulting hashes and attribution for the 41 required third-party files.
The imported `vendor/` directory and all build outputs stay outside version
control. The import preserves source notices and applies one checked startup
change: unexpected interrupts branch to the application's motor-off handler.
No manufacturer firmware binary, backup, chip UID or device-specific flash plan
is included.
