#include "voice/PitchEnvelope.h"
#include "voice/EnvelopeMath.h"
namespace segrand {
namespace {
int S8(uint8_t x) { return x < 128 ? x : int(x) - 256; }
int Source(const ModulationSources &s, unsigned n) { return n < s.size() ? s[n] : 0; }
int Mod(int a, int b) { return std::clamp(int(int64_t(a) * b * 331 >> 15), -32768, 32767); }
} // namespace
void PitchEnvelope::Initialize(const ModulationSources &s) noexcept {
  auto p = mParameters;
  mTrigger = 99 * Source(s, p[24]);
  mLevel = std::clamp(330 * S8(p[0]) + 12 * Mod(S8(p[13]), Source(s, p[12])) +
                          12 * Mod(S8(p[17]), Source(s, p[16])),
                      -32767, 32767);
}
void PitchEnvelope::Segment(unsigned phase, const ModulationSources &s) noexcept {
  auto p = mParameters;
  const int times[] = {p[1], p[3], p[5], p[6]}, levels[] = {S8(p[2]), S8(p[4]), 0, S8(p[7])};
  const int a = phase < 2 ? S8(p[14 + phase]) : 0, b = phase < 2 ? S8(p[18 + phase]) : 0;
  const int target = std::clamp(330 * levels[phase] + 12 * Mod(a, Source(s, p[12])) +
                                    12 * Mod(b, Source(s, p[16])),
                                -32767, 32767);
  mStage = (phase == 3 ? 8 : 2 * phase) + (mLevel >= target);
  mLow = std::min(mLevel, target);
  mDelta = std::abs(mLevel - target);
  mCurve = p[8 + phase];
  const int amount = phase < 3 ? 12 * Mod(S8(p[21 + phase]), Source(s, p[20])) : 0;
  mRemaining =
      envelope_math::Duration(native_data::kEgTime[std::clamp(times[phase], 0, 99)], amount);
  mCoefficient = envelope_math::Coefficient(mCurve, unsigned(mRemaining) / 24);
  mAsymptote = native_data::kEgAsymptote[mCurve];
  mProgress = 0;
}
void PitchEnvelope::Start(const uint8_t *p, const ModulationSources &s) noexcept {
  *this = {};
  mParameters = p;
  Initialize(s);
  Segment(0, s);
  // The original start entry advances the segment once without changing stage.
  mProgress += uint32_t(uint64_t(mCoefficient) * (mAsymptote - (mProgress >> 2)) >> 29);
  mRemaining -= 24;
  uint32_t v = std::min(mProgress, 0x80000000u);
  if (mStage & 1)
    v = 0x80000000u - v;
  mLevel = mLow + int(uint64_t(v) * unsigned(mDelta) >> 31);
}
void PitchEnvelope::Release(const ModulationSources &s) noexcept {
  if (mParameters && mStage <= 7)
    Segment(3, s);
}
void PitchEnvelope::Tick(const ModulationSources &s) noexcept {
  Advance(s);
  Refresh(s);
}
void PitchEnvelope::Advance(const ModulationSources &s) noexcept {
  if (!mParameters)
    return;
  if (mStage != 6 && mStage != 7) {
    mProgress += uint32_t(uint64_t(mCoefficient) * (mAsymptote - (mProgress >> 2)) >> 29);
    mRemaining -= 24;
    uint32_t v = std::min(mProgress, 0x80000000u);
    if (mStage & 1)
      v = 0x80000000u - v;
    mLevel = mLow + int(uint64_t(v) * unsigned(mDelta) >> 31);
    if (mRemaining <= 0) {
      if (mStage <= 1)
        Segment(1, s);
      else if (mStage <= 3)
        Segment(2, s);
      else
        mStage = 6;
    }
  }
}
void PitchEnvelope::Refresh(const ModulationSources &s) noexcept {
  if (!mParameters)
    return;
  const auto p = mParameters;
  bool retrigger = false;
  if (p[24]) {
    const int current = 99 * Source(s, p[24]), threshold = S8(p[25]) * 4096;
    retrigger = threshold >= 0 ? (current >= threshold && mTrigger < threshold)
                               : (current <= threshold && mTrigger > threshold);
    mTrigger = current;
  }
  if (retrigger) {
    Initialize(s);
    Segment(0, s);
  }
}
} // namespace segrand
