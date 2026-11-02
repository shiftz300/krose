/* Research-only stateful form of the recovered encoder feedback arithmetic. */
#include "korg_pcm_decode.c"

void pcm_decode_stateful(const uint8_t *source, size_t frames,
                         int16_t a1, int16_t a2, const int16_t *lut,
                         int32_t previous, int32_t older,
                         int32_t *output, int32_t *state, uint64_t *counts) {
    counts[0] = counts[1] = 0;
    for (size_t i = 0; i < frames; ++i) {
        int64_t product = (int64_t)a1 * previous + (int64_t)a2 * older;
        int32_t prediction = saturate(product / 16384, &counts[0]);
        unsigned index = ((unsigned)source[i] + 128) & 255;
        int32_t value = saturate((int64_t)prediction + (int64_t)lut[index] * 65536, &counts[1]);
        output[i] = value; older = previous; previous = value;
    }
    state[0] = previous; state[1] = older;
}
