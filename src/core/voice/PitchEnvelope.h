#pragma once
#include "voice/NativeLFO.h"
namespace segrand {
class PitchEnvelope {
public:
  void Start(const uint8_t *parameters, const ModulationSources &sources) noexcept;
  void Tick(const ModulationSources &sources) noexcept;
  void Advance(const ModulationSources &sources) noexcept;
  void Refresh(const ModulationSources &sources) noexcept;
  void Release(const ModulationSources &sources) noexcept;
  int Level() const noexcept { return mLevel; }
  int Stage() const noexcept { return mStage; }

private:
  const uint8_t *mParameters = nullptr;
  int mLevel = 0, mLow = 0, mDelta = 0, mStage = 6, mCurve = 0;
  uint32_t mProgress = 0, mCoefficient = 0, mAsymptote = 0;
  int64_t mRemaining = 0;
  int mTrigger = 0;
  void Initialize(const ModulationSources &sources) noexcept;
  void Segment(unsigned phase, const ModulationSources &sources) noexcept;
};
} // namespace segrand
