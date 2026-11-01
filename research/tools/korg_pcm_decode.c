/* KROSS 2 1.2.4 research decoder.
 * Mirrors the encoder's reconstruction path, not an emulation of TG01.
 * LUT: firmware 0x3fd180; prediction: 0x1f5254..0x1f5304;
 * inverse quantizer and saturated feedback: 0x1f55b0..0x1f5698.
 */
#include <stdint.h>
#include <stddef.h>

static int32_t saturate(int64_t value, uint64_t *count) {
    if (value > INT32_MAX) { ++*count; return INT32_MAX; }
    if (value < -INT32_MAX) { ++*count; return -INT32_MAX; }
    return (int32_t)value;
}

void korg_pcm_decode(const uint8_t *source, size_t frames,
                     int16_t a1, int16_t a2, const int16_t *lut,
                     int32_t *output, uint64_t *counts) {
    int32_t previous = 0, older = 0;
    counts[0] = counts[1] = 0;
    for (size_t i = 0; i < frames; ++i) {
        /* C99 signed division truncates towards zero, as the ARM code does. */
        int64_t sum = (int64_t)a1 * previous + (int64_t)a2 * older;
        int32_t prediction = saturate(sum / 16384, &counts[0]);
        unsigned index = ((unsigned)source[i] + 128) & 255;
        int32_t value = saturate((int64_t)prediction +
                                (int64_t)lut[index] * 65536, &counts[1]);
        output[i] = value;
        older = previous;
        previous = value;
    }
}
