This directory preserves the project's own commissioning safety, control and IMU
modules and their native tests. It is not a complete flashable MCU application.

```sh
make -C firmware/commissioning test
```

The tests cover protocol state, profile rejection, control with synthetic motor
backends, IMU transactions with a fake I2C bus, and clock-register validation.
`tests/synthetic_profile.h` contains invented software-test values; it is not a
robot calibration. Default profile macros keep motion disabled.

The earlier complete commissioning build also depended on vendor-derived motor,
UART and RTOS integration. Those sources are omitted because this repository
does not establish redistribution permission for the XTARK portions. No ARM
build is promised for this directory. The separate `../forward-3s/` candidate
has a complete checked dependency-import and build path.
