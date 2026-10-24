CROSS_COMPILE ?= arm-none-eabi-
CC := $(CROSS_COMPILE)gcc
HOST_CC ?= cc
PYTHON ?= python3
BUILD ?= build
TARGET := $(BUILD)/h60-forward-3s
CPU := -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
# Standard Arm GNU toolchains discover newlib themselves. These optional
# overrides also support toolchains packaged with separate newlib directories.
NEWLIB_INCLUDE ?=
NEWLIB_LIB_DIR ?=
CPPFLAGS := -DSTM32F40_41xxx -DUSE_STDPERIPH_DRIVER -Iinclude -Ivendor/Driver -Ivendor/Robot
CPPFLAGS += -Ibuild_support -Ivendor/Libraries/STM32F4xx_StdPeriph_Driver/inc
CPPFLAGS += -Ivendor/Libraries/CMSIS/Device/ST/STM32F4xx/Include -Ivendor/Libraries/CMSIS/Include
ifneq ($(strip $(NEWLIB_INCLUDE)),)
CPPFLAGS += -isystem $(NEWLIB_INCLUDE)
endif
CFLAGS := $(CPU) -std=c11 -Os -g3 -Wall -Wextra -Werror -Wno-unused-parameter
CFLAGS += -ffunction-sections -fdata-sections -fno-common -fno-strict-aliasing
CFLAGS += -ffile-prefix-map=$(CURDIR)=. -fdebug-prefix-map=$(CURDIR)=.
LDFLAGS := $(CPU) -nostartfiles -nodefaultlibs -Tbuild_support/stm32f407ve.ld
LDFLAGS += -Wl,--gc-sections,--build-id=none,-Map=$(TARGET).map
ifneq ($(strip $(NEWLIB_LIB_DIR)),)
LDFLAGS += -L$(NEWLIB_LIB_DIR)
endif
SOURCES := src/main.c src/pulse.c src/runtime.c vendor/Robot/system_stm32f4xx.c
SOURCES += vendor/Driver/ax_encoder.c build_support/clock_validation.c
SOURCES += $(addprefix vendor/Libraries/STM32F4xx_StdPeriph_Driver/src/,misc.c stm32f4xx_gpio.c stm32f4xx_rcc.c stm32f4xx_tim.c)
OBJECTS := $(addprefix $(BUILD)/obj/,$(SOURCES:.c=.o)) $(BUILD)/obj/startup.o
.PHONY: all test manifest verify-vendor
all: $(TARGET).bin $(TARGET).hex manifest
verify-vendor:
	@$(PYTHON) ../../scripts/import_vendor.py --verify
$(BUILD)/obj/vendor/%.o: CFLAGS += -Wno-misleading-indentation
$(BUILD)/obj/%.o: %.c Makefile include/pulse.h | verify-vendor
	@mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) -MMD -MP -c $< -o $@
$(BUILD)/obj/startup.o: vendor/build_support/startup_stm32f407ve.s Makefile | verify-vendor
	@mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CPU) -g3 -x assembler-with-cpp -c $< -o $@
$(TARGET).elf: $(OBJECTS) build_support/stm32f407ve.ld
	$(CC) $(LDFLAGS) $(OBJECTS) -Wl,--start-group -lc_nano -lgcc -Wl,--end-group -o $@
	$(CROSS_COMPILE)size $@
$(TARGET).bin: $(TARGET).elf
	$(CROSS_COMPILE)objcopy --gap-fill=0xff -O binary $< $@
$(TARGET).hex: $(TARGET).elf
	$(CROSS_COMPILE)objcopy -O ihex $< $@
manifest: $(TARGET).bin $(TARGET).hex
	$(PYTHON) build_manifest.py --build $(BUILD) --compiler $(CC)
$(BUILD)/test-pulse: src/pulse.c include/pulse.h tests/test_pulse.c
	@mkdir -p $(BUILD)
	$(HOST_CC) -std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -Iinclude src/pulse.c tests/test_pulse.c -o $@
test: $(BUILD)/test-pulse
	$(BUILD)/test-pulse
-include $(OBJECTS:.o=.d)
