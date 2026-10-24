# Juanaillo

Juanaillo provides practical, Spanish-first documentation and portable tooling for the **OpenCTR H60 V3.7, STM32F407VET6**, with future autonomous driving as its goal. It has been tested on Linux with a four-wheel R5 chassis. No Chinese-language knowledge is required to follow the documented workflow.

This is a foundation for future **autonomous driving**, rather than a finished navigation stack. It provides USB bootloader access, verified backups, limited flashing, encoder calibration, and a single-shot three-second forward bench test with heartbeat timeout and STOP.

Start with [hardware](docs/hardware.md), [bring-up](docs/bring-up.md), [firmware preparation](firmware/README.md), and [tested results](docs/tested-results.md). The measured 1561 counts/revolution and motor signs are an example from one assembly, not universal board defaults. Read [AGENTS.md](AGENTS.md) for agent instructions and the bundled skills.

Only original project code is included. Manufacturer/ARM/ST dependencies are imported locally after checksum verification, never bundled as unlicensed archives or device flash dumps. Private board identity, network settings and credentials are excluded. See [THIRD_PARTY.md](THIRD_PARTY.md).

A temporary [local web controller](web/README.md) provides hold-to-run Forward, Reverse, Left and Right controls. Turning on the spot drives the two sides in opposite directions. It requires `manual-hold` profile 6 firmware; the previous profile 5 only supported forward/reverse and must be upgraded. Release, disconnect, stale input and maximum-hold limits stop motion. This is a diagnostic interface, not autonomous navigation.
