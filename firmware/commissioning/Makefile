# This directory preserves native-testable project code, not a complete MCU image.
HOST_CC ?= cc
.PHONY: all test test-clock
all: test
test:
	$(MAKE) -C tests CC="$(HOST_CC)"
	$(MAKE) test-clock
test-clock: build/test-clock
	./build/test-clock
build/test-clock: build_support/test_clock_validation.c build_support/clock_validation.c build_support/clock_validation.h
	@mkdir -p $(dir $@)
	$(HOST_CC) -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -Ibuild_support build_support/test_clock_validation.c build_support/clock_validation.c -o $@
