#ifndef AX_IMU_H
#define AX_IMU_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    void *context;
    bool (*read)(void *context, uint8_t reg, uint8_t *data, size_t length);
    bool (*write)(void *context, uint8_t reg, uint8_t value);
    bool (*delay_us)(void *context, uint32_t microseconds);
    uint32_t (*now_us)(void *context);
} AX_IMU_Bus;

typedef struct {
    AX_IMU_Bus bus;
    bool initialized;
    bool has_timestamp;
    uint32_t timestamp;
} AX_IMU_Device;

typedef struct {
    int16_t acceleration[3];
    int16_t gyroscope[3];
    bool valid;
} AX_IMU_Sample;

bool AX_IMU_InitWithBus(AX_IMU_Device *device, const AX_IMU_Bus *bus);
bool AX_IMU_ReadWithBus(AX_IMU_Device *device, AX_IMU_Sample *sample);
bool AX_IMU_InitChecked(void);
bool AX_IMU_ReadChecked(AX_IMU_Sample *sample);

#endif
