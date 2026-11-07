/* Firmware-informed EQ + original, perceptual chorus/hall reconstruction.
 * FDN uses the public Householder feedback construction described by J. O. Smith:
 * https://dsprelated.com/freebooks/pasp/Householder_Feedback_Matrix.html
 * No third-party implementation code is copied. Fixed buffers, no allocation,
 * locks, file access or parameter calculation in the processing callback.
 */
#include "effects/concert_effects.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define PI 3.14159265358979323846
#define LINES 8
#define POSITION_MASK 16383
// Retain the original coordinate for fractional delay arithmetic.
#define CHORUS_POSITION_MASK 8191

typedef struct {
  double eq[8][5], trim, reverb_wet, chorus_wet, tone_alpha;
  double feedback[LINES], damp_alpha, eq_low_alpha, eq_high_alpha;
  double lfo_step, chorus_delay[2], chorus_depth, mix_smoothing;
  unsigned eq_count;
  unsigned lengths[LINES], ap_lengths[2][2], early_delays[3];
} Configuration;

typedef struct {
  double eq_z[8][2][2], damp[LINES], eq_low[2], eq_high[2], tone[2];
  unsigned position;
  int clean;
  double phase;
  double reverb_wet, chorus_wet;
} State;

struct ConcertEffects {
  Configuration c;
  State s;
  size_t history_size;
  unsigned delay_mask, short_mask, ap_mask;
  float *history, *early[2], *chorus[2], *diffuse[2][2];
};

static const unsigned lengths[LINES] = {1423, 1601, 1867, 2053, 2281, 2539, 2797, 3163};
static const unsigned ap_lengths[2][2] = {{149, 263}, {211, 293}};
static const unsigned early_delays[3] = {337, 631, 1103};
static const double sign_l[LINES] = {1, 1, -1, -1, 1, -1, 1, -1};
static const double sign_r[LINES] = {1, -1, 1, -1, -1, -1, 1, 1};
static const double centers[8] = {80, 1600, 7300, 13400, 60, 70, 300, 20000};

static void remap_biquad(double *c, double rate, double center) {
  if (rate == 48000)
    return;
  double target = fmin(center, rate * 0.45);
  double ratio = tan(PI * center / 48000) / tan(PI * target / rate);
  double a = 1 - ratio, b = 1 + ratio, a2 = a * a, b2 = b * b, ab = a * b;
  double norm = b2 - c[3] * ab - c[4] * a2;
  double result[5] = {(c[0] * b2 + c[1] * ab + c[2] * a2) / norm,
                      (2 * c[0] * ab + c[1] * (a2 + b2) + 2 * c[2] * ab) / norm,
                      (c[0] * a2 + c[1] * ab + c[2] * b2) / norm,
                      -(2 * ab - c[3] * (a2 + b2) - 2 * c[4] * ab) / norm,
                      -(a2 - c[3] * ab - c[4] * b2) / norm};
  memcpy(c, result, sizeof(result));
}

static double tiny_zero(double x) { return fabs(x) < 1e-25 ? 0 : x; }

static double biquad(double x, const double *b, double *z) {
  double y = b[0] * x + z[0];
  z[0] = tiny_zero(b[1] * x + b[3] * y + z[1]);
  z[1] = tiny_zero(b[2] * x + b[4] * y);
  return y;
}

static unsigned ring_size(unsigned longest_delay) {
  unsigned size = 1;
  while (size <= longest_delay)
    size <<= 1;
  return size;
}

static double fractional_read(const float *buffer, unsigned mask, unsigned position, double delay) {
  double location = position - delay;
  int base = (int)floor(location);
  double fraction = location - base;
  return buffer[(unsigned)base & mask] * (1 - fraction) +
         buffer[(unsigned)(base + 1) & mask] * fraction;
}

ConcertEffects *concert_effects_create(double rate, const double coefficients[40], double trim,
                                      double seconds, double reverb_wet, double chorus_wet,
                                      double tone_hz) {
  if (!isfinite(rate) || rate < 32000 || rate > 192000 || !coefficients || !isfinite(trim) ||
      trim < 0 || trim > 2 || !isfinite(seconds) || seconds < 0.3 || seconds > 6 ||
      !isfinite(reverb_wet) || reverb_wet < 0 || reverb_wet > 0.5 || !isfinite(chorus_wet) ||
      chorus_wet < 0 || chorus_wet > 0.5 || !isfinite(tone_hz) ||
      (tone_hz != 0 && (tone_hz < 2000 || tone_hz > 20000)))
    return NULL;
  for (int i = 0; i < 8; ++i) {
    const double *b = coefficients + i * 5;
    for (int j = 0; j < 5; ++j)
      if (!isfinite(b[j]))
        return NULL;
    if (fabs(b[4]) >= 1 || 1 - b[3] - b[4] <= 0 || 1 + b[3] - b[4] <= 0)
      return NULL;
  }
  const unsigned delay_frames = ring_size((unsigned)round(lengths[LINES - 1] * rate / 48000));
  const unsigned short_frames = ring_size((unsigned)ceil((.024 + .0035) * rate));
  const unsigned ap_frames = ring_size((unsigned)round(ap_lengths[1][1] * rate / 48000));
  const size_t history_size = LINES * delay_frames + 4 * short_frames + 4 * ap_frames;
  ConcertEffects *e = (ConcertEffects *)calloc(1, sizeof(*e) + history_size * sizeof(float));
  if (!e)
    return NULL;
  e->history_size = history_size;
  e->delay_mask = delay_frames - 1;
  e->short_mask = short_frames - 1;
  e->ap_mask = ap_frames - 1;
  e->history = (float *)(e + 1);
  float *next = e->history + LINES * delay_frames;
  for (int ch = 0; ch < 2; ++ch) {
    e->early[ch] = next;
    e->chorus[ch] = next + short_frames;
    next += 2 * short_frames;
    for (int stage = 0; stage < 2; ++stage) {
      e->diffuse[ch][stage] = next;
      next += ap_frames;
    }
  }
  for (int i = 0; i < 8; ++i) {
    double b[5];
    memcpy(b, coefficients + i * 5, sizeof(b));
    remap_biquad(b, rate, centers[i]);
    if (b[0] != 1 || b[1] != 0 || b[2] != 0 || b[3] != 0 || b[4] != 0)
      memcpy(e->c.eq[e->c.eq_count++], b, sizeof(b));
  }
  e->c.trim = trim;
  e->c.reverb_wet = reverb_wet;
  e->c.chorus_wet = chorus_wet;
  e->c.tone_alpha = tone_hz == 0 ? 1 : 1 - exp(-2 * PI * tone_hz / rate);
  /* HiDamp 62 inspires this cutoff, rather than a claimed recovered mapping. */
  e->c.damp_alpha = 1 - exp(-2 * PI * 4500 / rate);
  e->c.eq_low_alpha = 1 - exp(-2 * PI * 400 / rate);
  e->c.eq_high_alpha = 1 - exp(-2 * PI * 6000 / rate);
  e->c.lfo_step = 0.5 / rate;
  e->c.chorus_delay[0] = rate * 0.024;
  e->c.chorus_delay[1] = rate * 0.013;
  e->c.chorus_depth = rate * 0.0035;
  e->c.mix_smoothing = 1 - exp(-1 / (rate * 0.02));
  for (int i = 0; i < LINES; ++i) {
    e->c.lengths[i] = (unsigned)round(lengths[i] * rate / 48000);
    e->c.feedback[i] = pow(10, -3.0 * e->c.lengths[i] / (rate * seconds));
  }
  for (int ch = 0; ch < 2; ++ch)
    for (int i = 0; i < 2; ++i)
      e->c.ap_lengths[ch][i] = (unsigned)round(ap_lengths[ch][i] * rate / 48000);
  for (int i = 0; i < 3; ++i)
    e->c.early_delays[i] = (unsigned)round(early_delays[i] * rate / 48000);
  e->s.clean = 1;
  e->s.reverb_wet = reverb_wet;
  e->s.chorus_wet = chorus_wet;
  return e;
}

void concert_effects_equalize(ConcertEffects *e, const float *input, double *output,
                              size_t frames) {
  for (size_t n = 0; n < frames; ++n)
    for (int ch = 0; ch < 2; ++ch) {
      double x = input[n * 2 + ch] * e->c.trim;
      for (unsigned band = 0; band < e->c.eq_count; ++band)
        x = biquad(x, e->c.eq[band], e->s.eq_z[band][ch]);
      output[n * 2 + ch] = x;
    }
}
void concert_effects_process_equalized(ConcertEffects *e, const double *equalized, float *stereo,
                                       size_t frames) {
  concert_effects_process_components(e, equalized, stereo, frames, NULL, NULL);
}
void concert_effects_process_components(ConcertEffects *e, const double *equalized, float *stereo,
                                       size_t frames, double *chorus_output, double *hall_output) {
  if (!e || !stereo)
    return;
  if (chorus_output) memset(chorus_output, 0, frames * 2 * sizeof(double));
  if (hall_output) memset(hall_output, 0, frames * 2 * sizeof(double));
  Configuration *c = &e->c;
  State *s = &e->s;
  const int chorus_active = c->chorus_wet != 0 || s->chorus_wet != 0;
  if (s->clean) {
    for (size_t i = 0; i < frames * 2; ++i)
      if (equalized[i] != 0) {
        s->clean = 0;
        break;
      }
    if (s->clean) {
      for (size_t n = 0; n < frames; ++n) {
        s->reverb_wet += c->mix_smoothing * (c->reverb_wet - s->reverb_wet);
        s->chorus_wet += c->mix_smoothing * (c->chorus_wet - s->chorus_wet);
        s->position = (s->position + 1) & POSITION_MASK;
        s->phase += c->lfo_step;
        if (s->phase >= 1)
          s->phase -= 1;
        stereo[n * 2] = stereo[n * 2 + 1] = 0;
      }
      return;
    }
  }
  for (size_t n = 0; n < frames; ++n) {
    unsigned pos = s->position, short_pos = pos & e->short_mask;
    double dry[2], colored[2], diffused[2], chorus[2];
    double triangle = 1 - 4 * fabs(s->phase - 0.5);
    s->reverb_wet += c->mix_smoothing * (c->reverb_wet - s->reverb_wet);
    s->chorus_wet += c->mix_smoothing * (c->chorus_wet - s->chorus_wet);
    for (int ch = 0; ch < 2; ++ch) {
      double x = equalized[n * 2 + ch];
      s->tone[ch] = tiny_zero(s->tone[ch] + c->tone_alpha * (x - s->tone[ch]));
      dry[ch] = s->tone[ch];
      e->chorus[ch][short_pos] = (float)dry[ch];
      /* Recovered L/R base delay 24/13 ms, triangle 0.5 Hz, opposite phase.
       * Depth70 -> +/-3.5 ms is an explicitly approximate control mapping. */
      double delay =
          c->chorus_delay[ch] + (ch == 0 ? c->chorus_depth : -c->chorus_depth) * triangle;
      chorus[ch] = chorus_active ? fractional_read(e->chorus[ch], e->short_mask,
                                                   pos & CHORUS_POSITION_MASK, delay)
                                 : 0;
      s->eq_low[ch] = tiny_zero(s->eq_low[ch] + c->eq_low_alpha * (dry[ch] - s->eq_low[ch]));
      s->eq_high[ch] = tiny_zero(s->eq_high[ch] + c->eq_high_alpha * (dry[ch] - s->eq_high[ch]));
      /* Hall send coloration: -3 dB lows / +2 dB highs, approximate Fc. */
      colored[ch] = 0.98 * (dry[ch] + (0.707945784 - 1) * s->eq_low[ch] +
                            (1.258925412 - 1) * (dry[ch] - s->eq_high[ch]));
      e->early[ch][short_pos] = (float)colored[ch];
      double ap = colored[ch];
      for (int stage = 0; stage < 2; ++stage) {
        unsigned len = c->ap_lengths[ch][stage];
        double d = e->diffuse[ch][stage][(pos - len) & e->ap_mask];
        double y = d - 0.6 * ap;
        e->diffuse[ch][stage][pos & e->ap_mask] = (float)tiny_zero(ap + 0.6 * y);
        ap = y;
      }
      diffused[ch] = ap;
    }
    double sum = 0, values[LINES], wet[2] = {0, 0};
    for (int i = 0; i < LINES; ++i) {
      values[i] = e->history[((pos - c->lengths[i]) & e->delay_mask) * LINES + i];
      s->damp[i] = tiny_zero(s->damp[i] + c->damp_alpha * (values[i] - s->damp[i]));
      sum += s->damp[i];
      wet[0] += values[i] * sign_l[i] * 0.3535533905932738;
      wet[1] += values[i] * sign_r[i] * 0.3535533905932738;
    }
    for (int i = 0; i < LINES; ++i) {
      double input = (diffused[0] * sign_l[i] + diffused[1] * sign_r[i]) * 0.25;
      double feedback = s->damp[i] - sum * 0.25; /* I - 2/N * 11^T, N=8. */
      e->history[(pos & e->delay_mask) * LINES + i] =
          (float)tiny_zero(input + c->feedback[i] * feedback);
    }
    for (int ch = 0; ch < 2; ++ch) {
      double early = 0.3 * e->early[ch][(pos - c->early_delays[0]) & e->short_mask] +
                     0.2 * e->early[1 - ch][(pos - c->early_delays[1]) & e->short_mask] -
                     0.15 * e->early[ch][(pos - c->early_delays[2]) & e->short_mask];
      const double chorus_wet = s->chorus_wet * chorus[ch];
      const double hall_wet = s->reverb_wet * (0.8 * wet[ch] + early);
      if (chorus_output) chorus_output[n * 2 + ch] = chorus_wet;
      if (hall_output) hall_output[n * 2 + ch] = hall_wet;
      stereo[n * 2 + ch] = (float)(dry[ch] + chorus_wet + hall_wet);
    }
    s->position = (pos + 1) & POSITION_MASK;
    s->phase += c->lfo_step;
    if (s->phase >= 1)
      s->phase -= 1;
  }
}

void concert_effects_process(ConcertEffects *e, float *stereo, size_t frames) {
  if (!e || !stereo)
    return;
  double equalized[256];
  for (size_t at = 0; at < frames; at += 128) {
    size_t count = frames - at < 128 ? frames - at : 128;
    concert_effects_equalize(e, stereo + at * 2, equalized, count);
    concert_effects_process_equalized(e, equalized, stereo + at * 2, count);
  }
}

int concert_effects_set_wet(ConcertEffects *e, double reverb, double chorus) {
  if (!e || !isfinite(reverb) || reverb < 0 || reverb > 0.5 || !isfinite(chorus) || chorus < 0 ||
      chorus > 0.5)
    return 0;
  e->c.reverb_wet = reverb;
  e->c.chorus_wet = chorus;
  return 1;
}
void concert_effects_set_room(ConcertEffects *e, double rate, double seconds, double damping,
                              int plate) {
  const double scale = plate ? .62 : 1;
  e->c.damp_alpha = 1 - exp(-2 * PI * (2200 + 10000 * (1 - damping)) / rate);
  for (int i = 0; i < LINES; ++i) {
    e->c.lengths[i] = (unsigned)round(lengths[i] * scale * rate / 48000);
    e->c.feedback[i] = pow(10, -3.0 * e->c.lengths[i] / (rate * seconds));
  }
  for (int ch = 0; ch < 2; ++ch)
    for (int i = 0; i < 2; ++i)
      e->c.ap_lengths[ch][i] = (unsigned)round(ap_lengths[ch][i] * scale * rate / 48000);
  for (int i = 0; i < 3; ++i)
    e->c.early_delays[i] = (unsigned)round(early_delays[i] * scale * rate / 48000);
}

void concert_effects_set_chorus(ConcertEffects *e, double rate, double depth, double hz) {
  e->c.lfo_step = hz / rate;
  e->c.chorus_depth = rate * .005 * depth;
}

void concert_effects_reset(ConcertEffects *e) {
  if (e) {
    if (!e->s.clean)
      memset(e->history, 0, e->history_size * sizeof(float));
    memset(&e->s, 0, sizeof(e->s));
    e->s.clean = 1;
    e->s.reverb_wet = e->c.reverb_wet;
    e->s.chorus_wet = e->c.chorus_wet;
  }
}
void concert_effects_destroy(ConcertEffects *e) { free(e); }
size_t concert_effects_memory_bytes(const ConcertEffects *e) {
  return sizeof(*e) + e->history_size * sizeof(float);
}
