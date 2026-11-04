#include "voice/NativeFilter.h"
#include "NativeVoiceData.h"
#include "voice/EnvelopeMath.h"
#include <algorithm>
#include <cmath>

namespace segrand {
namespace {
using namespace native_data;
int Signed(uint8_t x) { return x < 128 ? x : int(x) - 256; }
int Mod(int intensity, int source) {
  return std::clamp(int((int64_t(intensity) * source * 331) >> 15), -32768, 32767);
}
using namespace envelope_math;
} // namespace

void NativeFilter::Start(const NativeVoice &amplitude, int oscillator, int velocity,
                         double sampleRate) noexcept {
  StartProgram(native_data::kProgram, amplitude, oscillator, velocity, sampleRate);
}
void NativeFilter::StartProgram(const uint8_t *program, const NativeVoice &amplitude,
                                int oscillator, int velocity, double sampleRate) noexcept {
  mOsc = program + 0x564 + 380 * std::clamp(oscillator, 0, 1);
  mVelocity = std::clamp(velocity, 1, 127);
  mRate = sampleRate;
  mBranches = {};
  mLFO = {};
  mFade = {};
  for (unsigned i = 0; i < mSources.size(); ++i)
    mSources[i] = amplitude.Source(i);
  auto eg = mOsc + 0xD8;
  mTrigger = 99 * (eg[32] < mSources.size() ? mSources[eg[32]] : 0);
  mLevel =
      std::clamp(Signed(eg[4]) * 330 +
                     12 * Mod(Signed(eg[14]), (eg[13] < mSources.size() ? mSources[eg[13]] : 0)),
                 -32767, 32767);
  Prepare(0);
  AdvanceEnvelope();
  UpdateWords();
  UpdateAudio(0);
}
void NativeFilter::Retune(const NativeVoice &amplitude) noexcept {
  for (unsigned i = 0; i < mSources.size(); ++i)
    mSources[i] = amplitude.Source(i);
  UpdateWords();
  UpdateAudio(unsigned(mRate / kNativeControlHz));
}
void NativeFilter::Prepare(int phase) noexcept {
  const auto p = mOsc + 0xD8;
  const int depth = phase == 0 ? Signed(p[15]) : phase == 1 ? Signed(p[16]) : 0;
  const int target =
      std::clamp((Signed(p[6 + phase * 2]) + (phase == 2 ? mOffsets.sustain : 0)) * 330 +
                     12 * Mod(depth, (p[13] < mSources.size() ? mSources[p[13]] : 0)),
                 -32767, 32767);
  mStage = phase < 3 ? phase * 2 : 8;
  if (mLevel >= target)
    ++mStage;
  mLow = std::min(mLevel, target);
  mDelta = std::abs(mLevel - target);
  mCurve = p[phase];
  int modulation = 0;
  for (int i = 0; i < 3; ++i) {
    unsigned source = p[17 + 5 * i];
    modulation +=
        12 * Mod(Signed(p[18 + 5 * i + phase]), source < mSources.size() ? mSources[source] : 0);
  }
  const int offset = phase == 0   ? mOffsets.attack
                     : phase == 1 ? mOffsets.decay
                     : phase == 3 ? mOffsets.release
                                  : 0;
  uint32_t base = native_data::kEgTime[std::clamp(p[5 + phase * 2] + offset, 0, 99)];
  if (modulation > 0 && base <= 7)
    base = 8;
  mTotal = uint32_t(std::min<uint64_t>(INT32_MAX, (uint64_t(base) * Exp(modulation * 16)) >> 16));
  mRemaining = mTotal;
  mProgress = 0;
  mAsymptote = native_data::kEgAsymptote[mCurve];
  mCoefficient = Coefficient(mCurve, mTotal / 24);
}
void NativeFilter::AdvanceEnvelope() noexcept {
  if (mStage == 6)
    return;
  mProgress += uint32_t((uint64_t(mCoefficient) * (mAsymptote - (mProgress >> 2))) >> 29);
  mRemaining -= 24;
  uint32_t progress = std::min(mProgress, 0x80000000u);
  if (mStage & 1)
    progress = 0x80000000u - progress;
  mLevel = mLow + int((uint64_t(progress) * unsigned(mDelta)) >> 31);
  if (mRemaining <= 0) {
    if (mStage <= 1)
      Prepare(1);
    else if (mStage <= 3)
      Prepare(2);
    else
      mStage = 6;
  }
}
void NativeFilter::Tick() noexcept {
  AdvanceEnvelope();
  UpdateWords();
  UpdateAudio(unsigned(std::lround(mRate / kNativeControlHz)));
}
void NativeFilter::SetModulation(const ModulationSources &sources,
                                 const std::array<NativeLFO, 2> &lfo) noexcept {
  mSources = sources;
  const auto eg = mOsc + 0xd8;
  if (eg[32]) {
    const int current = 99 * (eg[32] < mSources.size() ? mSources[eg[32]] : 0),
              threshold = Signed(eg[33]) * 4096;
    const bool trigger = threshold >= 0 ? (current >= threshold && mTrigger < threshold)
                                        : (current <= threshold && mTrigger > threshold);
    mTrigger = current;
    if (trigger) {
      mLevel =
          std::clamp(Signed(eg[4]) * 330 +
                         12 * Mod(Signed(eg[14]), eg[13] < mSources.size() ? mSources[eg[13]] : 0),
                     -32767, 32767);
      Prepare(0);
    }
  }
  for (int i = 0; i < 2; ++i) {
    mLFO[i] = lfo[i].Value();
    mFade[i] = int(lfo[i].Fade());
  }
  UpdateWords();
  UpdateAudio(unsigned(std::lround(mRate / kNativeControlHz)));
}
void NativeFilter::Release() noexcept {
  if (mOsc)
    Prepare(3);
}
void NativeFilter::UpdateWords() noexcept {
  mSources[4] = (mLevel * 32770) >> 18;
  auto source = [&](unsigned n) { return n < mSources.size() ? mSources[n] : 0; };
  for (int branch = 0; branch < 2; ++branch) {
    if (branch && (mOsc[0x88] & 3) == 3) {
      for (int i = 0; i < 4; ++i)
        mWords[4 + i] = mWords[i];
      mWords[4] = 32767;
      mWords[6] = uint16_t(unsigned(mWords[6]) * 115 >> 8);
      mWords[3] = 32767;
      continue;
    }
    const auto p = mOsc + 0x90 + branch * 0x24;
    const int tracking = (source(9) * Signed(p[21])) >> 5;
    const int egDepth = Signed(p[22]) * 63 + ((mVelocity * Signed(p[23])) >> 1) +
                        ((source(mOsc[0x89]) * Signed(p[24])) >> 6);
    int raw = p[19] * 32767 + ((egDepth * mLevel) >> 6) + tracking * 256;
    raw += 8 * Signed(p[9]) * source(p[8]) + 8 * Signed(p[13]) * source(p[12]);
    for (int i = 0; i < 2; ++i) {
      const int variable = (source(mOsc[0x8a + i]) * Signed(p[31 + i])) >> 5;
      const int amount = (variable >> 2) + ((Signed(p[25 + i]) * mFade[i]) >> 11);
      raw += int((int64_t(amount) * mLFO[i]) >> 4);
    }
    const int cutoff = std::min(31744, ((std::max(raw, 0) >> 2) * 317) >> 13);
    const int resonance = std::clamp(p[20] * 321 + 8 * Mod(Signed(p[5]), source(p[4])), 0, 31744);
    const int trim = p[17] == 99 ? 32767 : p[17] * 331;
    const int output = std::clamp(
        (p[18] >= 99 ? 32767 : p[18] * 331) + 8 * Mod(Signed(p[1]), source(p[0])), 0, 32767);
    mWords[branch * 4] = uint16_t(trim);
    mWords[branch * 4 + 1] = uint16_t(cutoff);
    mWords[branch * 4 + 2] = uint16_t(resonance);
    mWords[branch * 4 + 3] = uint16_t(output);
  }
}

// Engineering transfer law: 10 display units/octave and 20 kHz at index99.
// The firmware does NOT establish these anchors or this resonance->Q law.
double NativeFilter::ApproximateHz(int word) noexcept {
  return 20000 * std::exp2((std::clamp(word, 0, 31744) / 317.0 - 99) / 10);
}
double NativeFilter::ApproximateQ(int word) noexcept {
  return 0.7071067811865476 * std::exp2(6 * std::clamp(word, 0, 31744) / 31744.0);
}
void NativeFilter::UpdateAudio(unsigned frames) noexcept {
  // Standard RBJ biquads: https://www.w3.org/TR/audio-eq-cookbook/
  constexpr double pi = 3.14159265358979323846;
  for (int branch = 0; branch < 2; ++branch) {
    double frequency = std::min(ApproximateHz(Word(branch, 1) + 317 * mCutoff), mRate * 0.45),
           q = ApproximateQ(Word(branch, 2) + 321 * mResonance);
    const double w = 2 * pi * frequency / mRate, c = std::cos(w), alpha = std::sin(w) / (2 * q),
                 a0 = 1 + alpha;
    const int type = mOsc[0xA0 + ((mOsc[0x88] & 3) == 3 ? 0 : branch * 0x24)] & 3;
    double b0 = 0, b1 = 0, b2 = 0;
    if (type == 0) {
      b0 = (1 - c) / 2;
      b1 = 1 - c;
      b2 = b0;
    } else if (type == 1) {
      b0 = (1 + c) / 2;
      b1 = -1 - c;
      b2 = b0;
    } else if (type == 2) {
      b0 = alpha;
      b2 = -alpha;
    } else {
      b0 = 1;
      b1 = -2 * c;
      b2 = 1;
    }
    const double gain = (Word(branch, 0) / 32768.0) * (Word(branch, 3) / 32768.0);
    mBranches[branch].Set(
        {b0 / a0 * gain, b1 / a0 * gain, b2 / a0 * gain, -2 * c / a0, (1 - alpha) / a0}, frames);
  }
}
void NativeFilter::Biquad::Set(const std::array<double, 5> &next, unsigned frames) noexcept {
  target = next;
  remaining = frames;
  for (unsigned i = 0; i < 5; ++i) {
    if (frames)
      delta[i] = (target[i] - coefficient[i]) / frames;
    else
      coefficient[i] = target[i];
  }
}
void NativeFilter::Biquad::Process(double &left, double &right) noexcept {
  if (remaining) {
    for (unsigned i = 0; i < 5; ++i)
      coefficient[i] += delta[i];
    if (!--remaining)
      coefficient = target;
  }
  auto process = [&](double input, int ch) {
    const double output = coefficient[0] * input + z1[ch];
    z1[ch] = coefficient[1] * input - coefficient[3] * output + z2[ch];
    z2[ch] = coefficient[2] * input - coefficient[4] * output;
    // Clear only subnormal tails, with no effect at meaningful signal levels.
    if (std::abs(z1[ch]) < 1e-30)
      z1[ch] = 0;
    if (std::abs(z2[ch]) < 1e-30)
      z2[ch] = 0;
    return output;
  };
  left = process(left, 0);
  right = process(right, 1);
}
void NativeFilter::Process(double &left, double &right) noexcept {
  const unsigned routing = mOsc[0x88] & 3;
  if (routing != 2) {
    mBranches[0].Process(left, right);
    if (routing)
      mBranches[1].Process(left, right);
    return;
  }
  double aL = left, aR = right, bL = left, bR = right;
  mBranches[0].Process(aL, aR);
  mBranches[1].Process(bL, bR);
  left = aL + bL;
  right = aR + bR; // Parallel; no invented normalization
}
} // namespace segrand
