#ifndef CONCERT_EFFECTS_H
#define CONCERT_EFFECTS_H
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct ConcertEffects ConcertEffects;
/* Stereo, 32..192 kHz. Input coefficients are referenced to 48 kHz and ordered
 * b0,b1,b2,f1,f2 for the eight Concert EQ bands. Other rates use per-band
 * prewarped bilinear remapping; this preserves the 48 kHz reference exactly.
 * Processing uses positive feedback coefficients. Controls are fixed at create.
 * Hall/chorus are perceptual approximations; this is not a TG chip emulator. */
ConcertEffects *concert_effects_create(double sample_rate, const double coefficients[40],
                                       double trim, double reverb_seconds, double reverb_wet,
                                       double chorus_wet, double tone_lowpass_hz);
void concert_effects_process(ConcertEffects *effects, float *stereo, size_t frames);
/* Shared dry EQ for variants with identical coefficients/trim. Keep double
 * precision between stages; downstream tone, chorus and hall states stay separate. */
void concert_effects_equalize(ConcertEffects *effects, const float *input, double *output,
                              size_t frames);
void concert_effects_process_equalized(ConcertEffects *effects, const double *equalized,
                                       float *stereo, size_t frames);
/* Call from the audio thread; transitions are smoothed over approximately 20ms. */
int concert_effects_set_wet(ConcertEffects *effects, double reverb_wet, double chorus_wet);
void concert_effects_set_room(ConcertEffects *effects, double rate, double seconds, double damping,
                              int plate);
void concert_effects_set_chorus(ConcertEffects *effects, double rate, double depth, double hz);
void concert_effects_reset(ConcertEffects *effects);
void concert_effects_destroy(ConcertEffects *effects);
size_t concert_effects_memory_bytes(const ConcertEffects *effects);

#ifdef __cplusplus
}
#endif
#endif
