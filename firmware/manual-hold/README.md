# Manual hold, profile 5

This isolated bench firmware provides fixed-duty forward and reverse while a
controller actively renews MOVE. It is intended for the local two-button UI,
not speed regulation or autonomous driving. Boot, STATUS and CAPS never start
motors. The previous profile4 three-second candidate remains separate.

Four channels run at 10% differential duty and 5 kHz. Forward uses raw motor
directions `[+1,-1,+1,-1]` in A/B/C/D order; reverse inverts all four. Every start
or reversal disables all PWM timers and drives all bridge inputs00 before a
brake/wake11 phase of at least4ms. The hardware DWT guard accepts4..5ms before
enabling the new PWM; a missed timing window faults with outputs off.

Each valid MOVE refreshes a150ms lease. The absolute burst limit is10000ms from
the first MOVE, including wake phases and reversals; repeated MOVE and direction
changes do not extend it. Reaching the limit leaves LIMIT and ignores MOVE until
an explicit STOP. Normal STOP leaves IDLE and permits a later new press without
resetting the board. A lease expiry, malformed frame, wrong nonce or timing
fault leaves sticky FAULT; STOP still disables outputs but does not clear FAULT.
Reset must be a separate deliberate operation. It never starts motion.

The limits depend on priority0 SysTick, the main loop and DWT software checks,
with IWDG backup. They are not an autonomous timer cutoff or an external
measurement of motor voltage, current or mechanical stopping distance.

## Build and native verification

From the repository root:

```sh
python3 scripts/import_vendor.py --source '/path/to/OpenCTR H60 code.zip' --destination firmware/manual-hold/vendor
make -C firmware/manual-hold test
make -C firmware/manual-hold all
```

The same checked dependency set as forward-3s is imported locally and ignored
by Git. Select a toolchain with `CROSS_COMPILE`; optional `NEWLIB_INCLUDE` and
`NEWLIB_LIB_DIR` support separately packaged newlib. No build or native test
opens a serial port. A fresh `build/manifest.json` binds the local image and
sources; loading it is a separate reviewed operation.

## Wire contract

USB-DEBUG, USART1 PA9/PA10,2304008N1. Framing remains
`AA 55 LEN ID PAYLOAD SUM8`, with big-endian multibyte values. MOVE frames are
14bytes total, including a9byte payload. Responses retain the request ID.

| ID | Request | Response payload |
|---|---|---|
| `0x70` STATUS | Empty |44bytes |
| `0x76` CAPS | Empty |48bytes |
| `0x77` MOVE | Boot nonce `uint64` + direction `int8` (`+1` or `-1`) | STATUS |
| `0x74` STOP | Empty | STATUS |
| `0x63` ENCODERS | Empty | Four `uint16` |

Compatibility STOP accepts `0x62` empty or `0x50` plus six zero bytes. Old
FIRE/KEEPALIVE/ARM or arbitrary PWM commands are rejected. A partial frame times
out after30ms. MOVE is the only lease renewal; STATUS never keeps motors moving.

CAPS is `>BBBBHHHHII` followed by28ASCII bytes:

```text
(1,5,15,10,100,5000,4,10000,10000000,150)
H60_MANUAL_HOLD_CONTROL_V1__
```

Fields are version,profile,channel mask,forward reversed mask,duty permille,
PWMHz,wake minimum ms,max burst ms,envelope us and lease ms.

STATUS is `>BBBBIIQ4HIIiI`: version,profile,state,flags,uptime_ms,
lease_remaining_ms,nonce,countersA/B/C/D,burst_count,reason,direction,
burst_remaining_ms. States are IDLE0,WAKE1,RUNNING2,LIMIT3,FAULT4. Flags are
capable1,burst-active2,outputs-requested4,all-motor-GPIO-low/timers-off8. Idle,
LIMIT and FAULT normally report9; WAKE/RUNNING report7. The low flag uses GPIO
MODER/ODR/IDR and timer register readback, not an external motor measurement.

Reasons: BOOT0,STOP1,MOVE3,LIMIT4,LEASE5,FRAME6,NONCE7,DIRECTION8,LATE10,
HARDWARE11,RNG12. `burst_count` increments only for a new IDLE-to-WAKE press,
not for direction changes or lease renewal.

The RNG nonce rejects requests from previous boots; it is not authentication.
The backend must serialize access, discard queued MOVE on release, require a
fresh active browser hold and stop on release, disconnect, blur or error.
It must never generate MOVE indefinitely from a stale browser command, clear a
LIMIT by itself, or reset FAULT automatically. Keep only one motor controller
connected. This candidate has not been physically tested merely by compiling it.
