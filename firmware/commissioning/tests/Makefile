CC ?= cc
CFLAGS = -std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow -Wstrict-prototypes -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer

.PHONY: all test
all: test

.build/test_safety: test_safety.c ../Robot/juanillo_safety.c ../Robot/juanillo_safety.h
	mkdir -p .build
	$(CC) $(CFLAGS) -I../Robot test_safety.c ../Robot/juanillo_safety.c -lm -o $@

.build/test_control: test_control.c synthetic_profile.h ../Robot/ax_kinematics.c ../Robot/ax_speed.c ../Robot/juanillo_safety.c
	mkdir -p .build
	$(CC) $(CFLAGS) -Istubs -I../Robot -include synthetic_profile.h test_control.c ../Robot/ax_kinematics.c ../Robot/ax_speed.c ../Robot/juanillo_safety.c -lm -o $@

.build/test_imu: test_imu.c ../Driver/ax_imu.c ../Driver/ax_imu.h ../Robot/juanillo_safety.c
	mkdir -p .build
	$(CC) $(CFLAGS) -DJUANILLO_NATIVE_TEST -I../Driver -I../Robot test_imu.c ../Driver/ax_imu.c ../Robot/juanillo_safety.c -lm -o $@

test: .build/test_safety .build/test_control .build/test_imu
	./.build/test_safety
	./.build/test_control
	./.build/test_imu
	python3 test_profile.py
