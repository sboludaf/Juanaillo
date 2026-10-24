#ifndef JUANILLO_PROFILE_H
#define JUANILLO_PROFILE_H

#ifndef JUANILLO_MOTION_ENABLED
#define JUANILLO_MOTION_ENABLED 0
#endif
#ifndef JUANILLO_PROFILE_CALIBRATED
#define JUANILLO_PROFILE_CALIBRATED 0
#endif
#ifndef JUANILLO_COMMAND_UART
#define JUANILLO_COMMAND_UART 3
#endif
#ifndef JUANILLO_WHEEL_DIAMETER_MM
#define JUANILLO_WHEEL_DIAMETER_MM 65
#endif
#ifndef JUANILLO_EFFECTIVE_TRACK_MM
#define JUANILLO_EFFECTIVE_TRACK_MM 0
#endif
#ifndef JUANILLO_MAX_LINEAR_MM_S
#define JUANILLO_MAX_LINEAR_MM_S 0
#endif
#ifndef JUANILLO_MAX_ANGULAR_MRAD_S
#define JUANILLO_MAX_ANGULAR_MRAD_S 0
#endif
#ifndef JUANILLO_MAX_LINEAR_ACCEL_MM_S2
#define JUANILLO_MAX_LINEAR_ACCEL_MM_S2 0
#endif
#ifndef JUANILLO_MAX_ANGULAR_ACCEL_MRAD_S2
#define JUANILLO_MAX_ANGULAR_ACCEL_MRAD_S2 0
#endif
#ifndef JUANILLO_MAX_PWM
#define JUANILLO_MAX_PWM 0
#endif
#ifndef JUANILLO_KP
#define JUANILLO_KP 0
#endif
#ifndef JUANILLO_KI
#define JUANILLO_KI 0
#endif
#ifndef JUANILLO_KD
#define JUANILLO_KD 0
#endif
#ifndef JUANILLO_BATTERY_FULL_SCALE_MV
#define JUANILLO_BATTERY_FULL_SCALE_MV 0
#endif
#ifndef JUANILLO_IMU_AXIS_MAP
#define JUANILLO_IMU_AXIS_MAP 1
#endif
#ifndef JUANILLO_QMI_ADDRESS
#define JUANILLO_QMI_ADDRESS 0x6A
#endif
#ifndef JUANILLO_ENCODER_COUNTS_A
#define JUANILLO_ENCODER_COUNTS_A 0
#endif
#ifndef JUANILLO_ENCODER_COUNTS_B
#define JUANILLO_ENCODER_COUNTS_B 0
#endif
#ifndef JUANILLO_ENCODER_COUNTS_C
#define JUANILLO_ENCODER_COUNTS_C 0
#endif
#ifndef JUANILLO_ENCODER_COUNTS_D
#define JUANILLO_ENCODER_COUNTS_D 0
#endif
#ifndef JUANILLO_ENCODER_SIGN_A
#define JUANILLO_ENCODER_SIGN_A 0
#endif
#ifndef JUANILLO_ENCODER_SIGN_B
#define JUANILLO_ENCODER_SIGN_B 0
#endif
#ifndef JUANILLO_ENCODER_SIGN_C
#define JUANILLO_ENCODER_SIGN_C 0
#endif
#ifndef JUANILLO_ENCODER_SIGN_D
#define JUANILLO_ENCODER_SIGN_D 0
#endif
#ifndef JUANILLO_MOTOR_SIGN_A
#define JUANILLO_MOTOR_SIGN_A 0
#endif
#ifndef JUANILLO_MOTOR_SIGN_B
#define JUANILLO_MOTOR_SIGN_B 0
#endif
#ifndef JUANILLO_MOTOR_SIGN_C
#define JUANILLO_MOTOR_SIGN_C 0
#endif
#ifndef JUANILLO_MOTOR_SIGN_D
#define JUANILLO_MOTOR_SIGN_D 0
#endif
#ifndef JUANILLO_WHEEL_SIDE_A
#define JUANILLO_WHEEL_SIDE_A 0
#endif
#ifndef JUANILLO_WHEEL_SIDE_B
#define JUANILLO_WHEEL_SIDE_B 0
#endif
#ifndef JUANILLO_WHEEL_SIDE_C
#define JUANILLO_WHEEL_SIDE_C 0
#endif
#ifndef JUANILLO_WHEEL_SIDE_D
#define JUANILLO_WHEEL_SIDE_D 0
#endif

#if JUANILLO_COMMAND_UART != 3 && JUANILLO_COMMAND_UART != 4
#error Select exactly one command UART: 3 (PD8/PD9) or 4 (PC10/PC11).
#endif
#if JUANILLO_MOTION_ENABLED != 0 && JUANILLO_MOTION_ENABLED != 1
#error JUANILLO_MOTION_ENABLED must be zero or one.
#endif
#if JUANILLO_MOTION_ENABLED
#if JUANILLO_PROFILE_CALIBRATED != 1
#error Motion requires an explicitly calibrated physical profile.
#endif
#if JUANILLO_WHEEL_DIAMETER_MM <= 0 || JUANILLO_EFFECTIVE_TRACK_MM <= 0
#error Measured wheel diameter and effective track are required.
#endif
#if JUANILLO_ENCODER_COUNTS_A <= 0 || JUANILLO_ENCODER_COUNTS_B <= 0 || JUANILLO_ENCODER_COUNTS_C <= 0 || JUANILLO_ENCODER_COUNTS_D <= 0
#error Measured wheel encoder counts are required for every wheel.
#endif
#if (JUANILLO_ENCODER_SIGN_A != 1 && JUANILLO_ENCODER_SIGN_A != -1) || (JUANILLO_ENCODER_SIGN_B != 1 && JUANILLO_ENCODER_SIGN_B != -1) || (JUANILLO_ENCODER_SIGN_C != 1 && JUANILLO_ENCODER_SIGN_C != -1) || (JUANILLO_ENCODER_SIGN_D != 1 && JUANILLO_ENCODER_SIGN_D != -1)
#error Every encoder direction must be confirmed as +1 or -1.
#endif
#if (JUANILLO_MOTOR_SIGN_A != 1 && JUANILLO_MOTOR_SIGN_A != -1) || (JUANILLO_MOTOR_SIGN_B != 1 && JUANILLO_MOTOR_SIGN_B != -1) || (JUANILLO_MOTOR_SIGN_C != 1 && JUANILLO_MOTOR_SIGN_C != -1) || (JUANILLO_MOTOR_SIGN_D != 1 && JUANILLO_MOTOR_SIGN_D != -1)
#error Every motor direction must be confirmed as +1 or -1.
#endif
#if (JUANILLO_WHEEL_SIDE_A != 1 && JUANILLO_WHEEL_SIDE_A != 2) || (JUANILLO_WHEEL_SIDE_B != 1 && JUANILLO_WHEEL_SIDE_B != 2) || (JUANILLO_WHEEL_SIDE_C != 1 && JUANILLO_WHEEL_SIDE_C != 2) || (JUANILLO_WHEEL_SIDE_D != 1 && JUANILLO_WHEEL_SIDE_D != 2)
#error Every wheel side must be confirmed: 1=left, 2=right.
#endif
#if ((JUANILLO_WHEEL_SIDE_A == 1) + (JUANILLO_WHEEL_SIDE_B == 1) + (JUANILLO_WHEEL_SIDE_C == 1) + (JUANILLO_WHEEL_SIDE_D == 1)) != 2
#error Exactly two motors must belong to each differential side.
#endif
#if JUANILLO_MAX_LINEAR_MM_S <= 0 || JUANILLO_MAX_LINEAR_MM_S > 1500 || JUANILLO_MAX_ANGULAR_MRAD_S <= 0 || JUANILLO_MAX_ANGULAR_MRAD_S > 6280
#error Positive confirmed velocity limits within the supported envelope are required.
#endif
#if JUANILLO_MAX_LINEAR_ACCEL_MM_S2 <= 0 || JUANILLO_MAX_ANGULAR_ACCEL_MRAD_S2 <= 0
#error Positive confirmed acceleration limits are required.
#endif
#if JUANILLO_MAX_PWM <= 0 || JUANILLO_MAX_PWM > 4200
#error A confirmed PWM limit in 1..4200 is required.
#endif
#if JUANILLO_KP <= 0 || JUANILLO_KI < 0 || JUANILLO_KD < 0
#error Confirmed nonnegative PID gains with positive KP are required.
#endif
#if JUANILLO_BATTERY_FULL_SCALE_MV <= 0 || JUANILLO_BATTERY_FULL_SCALE_MV > 655350
#error A confirmed positive battery ADC full-scale voltage in mV is required.
#endif
#if JUANILLO_IMU_AXIS_MAP != 1
#error Supported confirmed IMU map is X=rawY, Y=-rawX, Z=rawZ (map 1).
#endif
#if JUANILLO_QMI_ADDRESS != 0x6A && JUANILLO_QMI_ADDRESS != 0x6B
#error QMI I2C address must be confirmed as 0x6A or 0x6B.
#endif
#endif

#define JUANILLO_BAUD 230400u
#define JUANILLO_CONTROL_PERIOD_MS 20u
#define JUANILLO_COMMAND_TIMEOUT_MS 250u
#define JUANILLO_FRAME_TIMEOUT_MS 50u
#if JUANILLO_MOTION_ENABLED
#define JUANILLO_FIRMWARE_SIGNATURE "Juanillo V3.7/R5 DRIVE-PROFILE"
#define JUANILLO_ARTIFACT_MARKER "H60_DRIVE_PROFILE_V1"
#else
#define JUANILLO_FIRMWARE_SIGNATURE "Juanillo V3.7/R5 COMMISSION-LOCKED"
#define JUANILLO_ARTIFACT_MARKER "H60_COMMISSIONING_LOCKED_V1"
#endif

#endif
