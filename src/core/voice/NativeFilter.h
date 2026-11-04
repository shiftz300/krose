#pragma once
#include "voice/NativeVoice.h"
#include <array>
#include <cstdint>

namespace segrand {
// Factory control-domain port with dynamic sources and per-OSC LFO targets.
// TG words are not Hz/Q; the audio implementation below is an explicitly
// separate, calibratable approximation, not an emulation of TG silicon.
class NativeFilter {
public:
  void SetOffsets(EnvelopeOffsets eg, int cutoff, int resonance) noexcept {
    mOffsets = eg;
    mCutoff = cutoff;
    mResonance = resonance;
  }
  void Start(const NativeVoice &amplitude, int oscillator, int velocity,
             double sampleRate) noexcept;
  void StartProgram(const uint8_t *program, const NativeVoice &amplitude, int oscillator,
                    int velocity, double sampleRate) noexcept;
  void Retune(const NativeVoice &amplitude) noexcept;
  void Tick() noexcept;
  void SetModulation(const ModulationSources &sources,
                     const std::array<NativeLFO, 2> &lfo) noexcept;
  void AdvanceModulationEnvelope() noexcept { AdvanceEnvelope(); }
  void Release() noexcept;
  uint16_t Word(int branch, int field) const noexcept { return mWords[branch * 4 + field]; }
  int Level() const noexcept { return mLevel; }
  int Stage() const noexcept { return mStage; }
  uint32_t Duration() const noexcept { return mTotal; }
  void Process(double &left, double &right) noexcept;
  static double ApproximateHz(int cutoffWord) noexcept;
  static double ApproximateQ(int resonanceWord) noexcept;

private:
  struct Biquad {
    std::array<double, 5> coefficient{}, target{}, delta{};
    std::array<double, 2> z1{}, z2{};
    unsigned remaining = 0;
    void Set(const std::array<double, 5> &next, unsigned frames) noexcept;
    void Process(double &left, double &right) noexcept;
  };
  std::array<Biquad, 2> mBranches{};
  std::array<int, 46> mSources{};
  std::array<uint16_t, 8> mWords{};
  std::array<int, 2> mLFO{}, mFade{};
  EnvelopeOffsets mOffsets;
  int mCutoff = 0, mResonance = 0;
  int mTrigger = 0;
  const uint8_t *mOsc = nullptr;
  double mRate = 48000;
  uint32_t mTotal = 0, mProgress = 0, mCoefficient = 0, mAsymptote = 0;
  int64_t mRemaining = 0;
  int mVelocity = 0, mStage = 6, mLevel = 0, mLow = 0, mDelta = 0, mCurve = 0;
  void Prepare(int phase) noexcept;
  void AdvanceEnvelope() noexcept;
  void UpdateWords() noexcept;
  void UpdateAudio(unsigned smoothingFrames) noexcept;
};
} // namespace segrand
