#include "voice/NativeVoice.h"
#include "NativeVoiceData.h"
#include "voice/EnvelopeMath.h"
#include <algorithm>
#include <cmath>
#include <cstring>

namespace segrand {
namespace {
using namespace native_data;
int S8(uint8_t x) { return x < 128 ? x : int(x) - 256; }
int S16(const uint8_t *p) {
  int v = p[0] + int(p[1]) * 256;
  return v < 32768 ? v : v - 65536;
}
int32_t S32(int64_t value) {
  uint32_t bits = static_cast<uint32_t>(value);
  int32_t result;
  std::memcpy(&result, &bits, 4);
  return result;
}
int Mod(int intensity, int source) {
  return std::clamp(int((int64_t(intensity) * source * 331) >> 15), -32768, 32767);
}
using namespace envelope_math;
int Tracking(const uint8_t *p, int note, bool amp) {
  int distances[2], ramps[2], count = 1;
  if (note < p[0]) {
    distances[0] = p[0] - note;
    ramps[0] = S8(p[3]);
    distances[1] = p[1] - p[0];
    ramps[1] = S8(p[4]);
    count = 2;
  } else if (note > p[2]) {
    distances[0] = note - p[2];
    ramps[0] = S8(p[6]);
    distances[1] = p[2] - p[1];
    ramps[1] = S8(p[5]);
    count = 2;
  } else if (note < p[1]) {
    distances[0] = p[1] - note;
    ramps[0] = S8(p[4]);
  } else if (note > p[1]) {
    distances[0] = note - p[1];
    ramps[0] = S8(p[5]);
  } else
    return 0;
  for (int i = 0; i < count; ++i)
    if (ramps[i] <= -100)
      return -4096;
  for (int i = 0; i < count; ++i)
    if (ramps[i] >= 100)
      return 4096;
  int total = 0;
  for (int i = 0; i < count; ++i) {
    int r = ramps[i];
    if (amp && r < 0) {
      if (r >= -95)
        r = (r * 134) >> 7;
      else {
        const int special[] = {-118, -169, -297, -594};
        r = special[r + 99];
      }
    }
    total += distances[i] * r;
  }
  const int limit = amp ? 1188 : 5940, scale = amp ? 225985 : 45197;
  if (total > limit)
    return 4096;
  if (total < -limit)
    return -4096;
  return (total * scale) >> 16;
}
int MixerValue(const uint8_t *p, const std::array<int, 46> &sources) {
  auto source = [&](unsigned n) { return n < sources.size() ? sources[n] : 0; };
  auto scaled = [&](int intensity, unsigned n) {
    return S32(int64_t(intensity) * source(n) * 331) >> 15;
  };
  int value = 0;
  if ((p[0] & 7) == 1) {
    int intensity = S8(p[2]) + ((scaled(S8(p[4]), p[3]) * 99) >> 12);
    value = scaled(intensity, p[1]);
  } else if ((p[0] & 7) == 2)
    value = scaled(S16(p + 6), p[1]) + ((S16(p + 8) * 165) >> 2);
  else
    value = scaled(S8(p[2]), p[1]) + scaled(S8(p[4]), p[3]);
  return std::clamp(value, -24576, 24576);
}
} // namespace

void NativeVoice::SetOffsets(EnvelopeOffsets offsets) noexcept {
  const auto previous = mOffsets;
  mOffsets = offsets;
  if (!mOsc || mEnded) return;
  const auto eg = mOsc + 0x118;
  const int phase = mStage >= 8 ? 3 : mStage / 2;
  int target = (mStage & 1) ? mLow : mLow + mDelta;
  double duration = double(std::max<int64_t>(24, mRemaining));
  bool changed = false;
  if (!mReleased && phase >= 2 && phase < 4 && previous.sustain != offsets.sustain) {
    target = std::clamp(int(eg[6]) + offsets.sustain, 0, 99) * 330;
    duration = 48; // Two control ticks; the gain slew removes audio-rate steps.
    changed = true;
  } else if (phase == 0 && previous.attack != offsets.attack) {
    duration *= double(native_data::kEgTime[std::clamp(eg[1] + offsets.attack, 0, 99)]) /
                std::max(1u, native_data::kEgTime[std::clamp(eg[1] + previous.attack, 0, 99)]);
    changed = true;
  } else if (phase == 1 && previous.decay != offsets.decay) {
    duration *= double(native_data::kEgTime[std::clamp(eg[3] + offsets.decay, 0, 99)]) /
                std::max(1u, native_data::kEgTime[std::clamp(eg[3] + previous.decay, 0, 99)]);
    changed = true;
  } else if (mReleased && mStage >= 8 && previous.release != offsets.release) {
    duration *= mProgram == native_data::kProgram ? std::exp2((offsets.release-previous.release)/16.) :
        double(native_data::kEgTime[std::clamp(eg[7] + offsets.release, 0, 99)]) /
        std::max(1u, native_data::kEgTime[std::clamp(eg[7] + previous.release, 0, 99)]);
    changed = true;
  }
  if (!changed) return;
  mStage = phase >= 2 && !mReleased ? 4 : phase == 3 ? 8 : phase * 2;
  if (mLevel >= target) ++mStage;
  mLow = std::min(mLevel, target);
  mDelta = std::abs(mLevel-target);
  mTotal = uint32_t(std::clamp(duration,24.,double(INT32_MAX)));
  mRemaining = mTotal; mProgress = 0;
  mCoefficient = Coefficient(mCurve, mTotal / 24);
}
void NativeVoice::Start(int note, int velocity, int oscillator, int slotLevel) noexcept {
  StartProgram(native_data::kProgram, note, velocity, oscillator, slotLevel);
}
void NativeVoice::StartProgram(const uint8_t *program, int note, int velocity, int oscillator,
                               int slotLevel, const ModulationSources *initial) noexcept {
  mProgram = program;
  mStartVelocity = velocity;
  mStartSlot = slotLevel;
  mOscillator = oscillator;
  mOsc = program + 0x564 + 380 * std::clamp(oscillator, 0, 1);
  note = std::clamp(note, 0, 127);
  velocity = std::clamp(velocity, 1, 127);
  slotLevel = std::clamp(slotLevel, 0, 127);
  mSources.fill(0);
  mSources[14] = (129 * velocity + 1) >> 2;
  mSources[15] = (native_data::kExpVelocity[velocity] + 1) >> 3;
  mSources[9] = Tracking(mOsc + 0xFC, note, false);
  mSources[10] = Tracking(mOsc + 0x13C, note, true);
  mSources[11] = Tracking(program + 0x554, note, false);
  mSources[12] = Tracking(program + 0x55C, note, false);
  if (program != native_data::kProgram)
    mSources[13] = ((std::min(note - 60, 60) * 8739) >> 7);
  mSources[1] = MixerValue(mOsc + 0x14C, mSources);
  mSources[2] = MixerValue(mOsc + 0x164, mSources);
  if (initial) {
    for (unsigned i = 1; i <= 8; ++i)
      mSources[i] = (*initial)[i];
    for (unsigned i = 16; i < mSources.size(); ++i)
      mSources[i] = (*initial)[i];
  }
  mSlotFactor = uint16_t(slotLevel * 258); // 0x201674, both additional offsets zero.
  const int intensity = S8(mOsc[0x105]);
  const int index = std::max(
      0, 255 + int((int64_t(velocity - (intensity > 0 ? 127 : 0)) * intensity * 667) >> 15));
  mVelocityFactor = uint16_t((uint32_t(native_data::kVelocityGain[index]) * mSlotFactor) >> 16);
  uint32_t factor =
      (uint32_t(mVelocityFactor) * unsigned(std::clamp(mSources[10] * 8 + 32768, 0, 65535))) >> 16;
  factor = (factor * 65535u) >> 16;
  factor = (factor * 65535u) >> 16;
  const unsigned mixer = program[0x51C + mOscillator] & 127, amp = mOsc[0x104];
  uint32_t base = (factor * ((mixer * mixer * amp * 131u) >> 14)) >> 14;
  base = uint32_t((uint64_t(base) * 65534u) >> 16); // native full-scale CC7/CC11 path
  mUnmodulatedGain = base;
  const int ams = mOsc[0x108] < mSources.size() ? mSources[mOsc[0x108]] : 0;
  const int depth = S8(mOsc[0x109]);
  if (depth) {
    const int mod = Mod(depth, ams);
    if (mod) {
      unsigned amount = unsigned(std::clamp(mod + 4096, 0, 32767));
      base = uint32_t((uint64_t(uint32_t(base * amount)) * amount * amount) >> 36);
    }
  }
  mBaseGain = std::min(base, 65535u);
  const uint8_t *eg = mOsc + 0x118;
  mTrigger = 99 * Source(eg[31]);
  mReleased = false;
  mLevel = std::clamp(int(eg[0]) * 330 + 12 * Mod(S8(eg[13]), Source(eg[12])), 0, 32767);
  mStage = 0;
  mEnded = false;
  mInitialGain = Gain();
  const int target = std::clamp(int(eg[2]) * 330 + 12 * Mod(S8(eg[14]), Source(eg[12])), 0, 32767);
  Prepare(0, target, native_data::kEgTime[std::clamp(eg[1] + mOffsets.attack, 0, 99)]);
  Tick(); // original note-on setup includes one segment advance
}
void NativeVoice::Retune(int note) noexcept {
  NativeVoice updated;
  updated.SetOffsets(mOffsets);
  updated.StartProgram(mProgram, note, mStartVelocity, mOscillator, mStartSlot);
  mSources = updated.mSources;
  mBaseGain = updated.mBaseGain;
  mUnmodulatedGain = updated.mUnmodulatedGain;
}
void NativeVoice::SetModulation(const ModulationSources &sources,
                                const std::array<NativeLFO, 2> &lfo) noexcept {
  mSources = sources;
  const auto eg = mOsc + 0x118;
  if (!mReleased && eg[31]) {
    const int current = 99 * Source(eg[31]), threshold = S8(eg[32]) * 4096;
    const bool trigger = threshold >= 0 ? (current >= threshold && mTrigger < threshold)
                                        : (current <= threshold && mTrigger > threshold);
    mTrigger = current;
    if (trigger) {
      mLevel = std::clamp(int(eg[0]) * 330 + 12 * Mod(S8(eg[13]), Source(eg[12])), 0, 32767);
      mEnded = false;
      const int target =
          std::clamp(int(eg[2]) * 330 + 12 * Mod(S8(eg[14]), Source(eg[12])), 0, 32767);
      Prepare(0, target, native_data::kEgTime[std::clamp(eg[1] + mOffsets.attack, 0, 99)]);
    }
  }
  mSources[5] = (mLevel * 32770) >> 18;
  uint32_t base = mUnmodulatedGain;
  const auto p = mOsc + 0x104;
  const int modulation = Mod(S8(p[5]), Source(p[4]));
  if (modulation) {
    const unsigned amount = unsigned(std::clamp(modulation + 4096, 0, 32767));
    base = uint32_t((uint64_t(uint32_t(base * amount)) * amount * amount) >> 36);
  }
  int total = 0;
  for (int i = 0; i < 2; ++i) {
    int amount = Mod(S8(p[13 + 4 * i]), Source(p[12 + 4 * i]));
    amount += S32(int64_t(S8(p[8 + i])) * lfo[i].Fade() * 330) >> 19;
    total += S32(int64_t(lfo[i].Value()) * amount) >> 11;
  }
  mBaseGain = uint32_t(
      std::min<uint64_t>(65535, uint64_t(base) * unsigned(std::max(0, 32768 + total)) >> 15));
  if (mProgram[0x51c + mOscillator] & 128)
    mBaseGain = 0;
}
uint16_t NativeVoice::Gain() const noexcept {
  return uint16_t(std::min<uint64_t>(32767, (uint64_t(mBaseGain) * unsigned(mLevel)) >> 14));
}
void NativeVoice::Prepare(int phase, int target, uint32_t baseTime) noexcept {
  const uint8_t *eg = mOsc + 0x118;
  mStage = phase == 3 ? 8 : phase * 2;
  if (mLevel >= target)
    ++mStage;
  mLow = std::min(mLevel, target);
  mDelta = std::abs(mLevel - target);
  int timeMod = 0;
  for (int i = 0; i < 3; ++i) {
    unsigned source = eg[16 + i * 5];
    timeMod += 6 * Mod(S8(eg[17 + i * 5 + phase]), source < mSources.size() ? mSources[source] : 0);
  }
  if (phase != 1)
    timeMod *= 2;
  mCurve = eg[8 + phase];
  mTotal = ::segrand::Duration(baseTime, timeMod);
  mRemaining = mTotal;
  mProgress = 0;
  mAsymptote = native_data::kEgAsymptote[mCurve];
  mCoefficient = Coefficient(mCurve, mTotal / 24);
}
void NativeVoice::NextStage() noexcept {
  const uint8_t *eg = mOsc + 0x118;
  if (mStage <= 1) {
    const int target =
        std::clamp(int(eg[4]) * 330 + 12 * Mod(S8(eg[15]), Source(eg[12])), 0, 32767);
    Prepare(1, target, native_data::kEgTime[std::clamp(eg[3] + mOffsets.decay, 0, 99)]);
  } else if (mStage <= 3)
    Prepare(2, std::clamp(eg[6] + mOffsets.sustain, 0, 99) * 330, native_data::kEgTime[eg[5]]);
  else if (mStage <= 5 && eg[6] + mOffsets.sustain > 0)
    mStage = 6;
  else {
    mStage = 7;
    mLevel = 0;
    mEnded = true;
  }
}
void NativeVoice::Tick() noexcept {
  if (mStage == 7) {
    mStage = 6;
    return;
  }
  if (mStage == 6)
    return;
  mProgress += uint32_t((uint64_t(mCoefficient) * (mAsymptote - (mProgress >> 2))) >> 29);
  mRemaining -= 24;
  uint32_t progress = std::min(mProgress, 0x80000000u);
  if (mStage & 1)
    progress = 0x80000000u - progress;
  mLevel = mLow + int((uint64_t(progress) * unsigned(mDelta)) >> 31);
  if (mRemaining <= 0)
    NextStage();
}
void NativeVoice::Release(double baseSeconds) noexcept {
  if (!mOsc)
    return;
  mReleased = true;
  baseSeconds =
      std::isfinite(baseSeconds) ? std::clamp(baseSeconds, 0.03, 2.0) : kNativeReleaseBaseSeconds;
  mEnded = false;
  Prepare(3, 0, uint32_t(std::lround(baseSeconds * 1500 * std::exp2(mOffsets.release / 16.0))));
}
void NativeVoice::ReleaseProgram(double scale) noexcept {
  if (!mOsc)
    return;
  mReleased = true;
  mEnded = false;
  Prepare(3, 0,
          uint32_t(std::lround(
              native_data::kEgTime[std::clamp(mOsc[0x118 + 7] + mOffsets.release, 0, 99)] *
              std::clamp(scale, 0.1, 8.0))));
}
int NativeSlew::CommandStep(int previousTarget, int target, unsigned durationUnits) noexcept {
  const int difference = target - previousTarget;
  if (!difference)
    return 0;
  const int product =
      int((int64_t(native_data::kTgReciprocal[std::min(durationUnits, 24u)]) * difference) >> 16);
  return product + (product >= 0 ? 1 : -1);
}
void NativeSlew::SetTarget(uint16_t gain, unsigned durationUnits) noexcept {
  if (gain == mTarget)
    return;
  mStep = CommandStep(mTarget, gain, durationUnits);
  mTarget = gain;
}
void NativeSlew::Advance() noexcept {
  if (mStep > 0)
    mCurrent = std::min(mTarget, mCurrent + mStep);
  else if (mStep < 0)
    mCurrent = std::max(mTarget, mCurrent + mStep);
}
} // namespace segrand
