#pragma once
#include "voice/NativeLFO.h"
#include "voice/VoiceTypes.h"
#include <array>
#include <cstdint>

namespace segrand {
// Original control-domain model: Start retains the verified Concert default;
// StartProgram accepts immutable Program controls. ProgramEngine supplies
// dynamic sources; the accepted Concert path retains neutral external inputs.
class NativeVoice {
public:
  void SetOffsets(EnvelopeOffsets offsets) noexcept;
  void Start(int note, int velocity, int oscillator, int slotLevel) noexcept;
  void StartProgram(const uint8_t *program, int note, int velocity, int oscillator, int slotLevel,
                    const ModulationSources *initial = nullptr) noexcept;
  void Retune(int note) noexcept;
  void ReleaseProgram(double scale = 1) noexcept;
  void Tick() noexcept;
  void SetModulation(const ModulationSources &sources,
                     const std::array<NativeLFO, 2> &lfo) noexcept;
  void Release(double baseSeconds = kNativeReleaseBaseSeconds) noexcept;
  int Level() const noexcept { return mLevel; }
  int Stage() const noexcept { return mStage; }
  uint32_t Duration() const noexcept { return mTotal; }
  uint16_t Gain() const noexcept;
  uint16_t InitialGain() const noexcept { return mInitialGain; }
  uint16_t VelocityFactor() const noexcept { return mVelocityFactor; }
  uint16_t SlotFactor() const noexcept { return mSlotFactor; }
  int Mixer(int index) const noexcept { return mSources[index + 1]; }
  int Source(unsigned index) const noexcept {
    return index < mSources.size() ? mSources[index] : 0;
  }
  bool Finished() const noexcept { return mEnded; }

private:
  EnvelopeOffsets mOffsets;
  const uint8_t *mOsc = nullptr;
  const uint8_t *mProgram = nullptr;
  int mStartVelocity = 0, mStartSlot = 0, mOscillator = 0;
  std::array<int, 46> mSources{};
  uint32_t mBaseGain = 0, mTotal = 0, mProgress = 0, mCoefficient = 0, mAsymptote = 0;
  uint32_t mUnmodulatedGain = 0;
  int mTrigger = 0;
  bool mReleased = false;
  int64_t mRemaining = 0;
  int mLevel = 0, mStage = 7, mLow = 0, mDelta = 0, mCurve = 0;
  uint16_t mVelocityFactor = 0, mSlotFactor = 0, mInitialGain = 0;
  bool mEnded = true;
  void Prepare(int phase, int target, uint32_t baseTime) noexcept;
  void NextStage() noexcept;
};

// Exact ARM command arithmetic; per-native-audio-frame step/clamp is the host
// interpretation of the TG ramp register, not a silicon execution claim.
class NativeSlew {
public:
  void Reset(uint16_t gain) noexcept {
    mCurrent = mTarget = gain;
    mStep = 0;
  }
  void SetTarget(uint16_t gain, unsigned durationUnits = 24) noexcept;
  void Advance() noexcept;
  int Current() const noexcept { return mCurrent; }
  int Target() const noexcept { return mTarget; }
  int Step() const noexcept { return mStep; }
  bool Silent() const noexcept { return mCurrent == 0 && mTarget == 0; }
  static int CommandStep(int previousTarget, int target, unsigned durationUnits) noexcept;

private:
  int mCurrent = 0, mTarget = 0, mStep = 0;
};
} // namespace segrand
