#pragma once
#include <array>
#include <cstdint>
namespace segrand {
using ModulationSources = std::array<int, 46>;
// Integer control-domain port. Timing is supplied by the voice's sample clock.
class NativeLFO {
public:
  void Start(const uint8_t *parameters, uint32_t clock, uint32_t &random,
             const ModulationSources &sources, int delayOverride = -1) noexcept;
  int Wave(const ModulationSources &sources, uint32_t &random) noexcept;
  void Advance(const ModulationSources &sources, uint32_t clock,
               int frequencyOverride = -1) noexcept;
  int Source() const noexcept;
  int Value() const noexcept { return mValue; }
  unsigned Fade() const noexcept { return mFade; }
  unsigned Phase() const noexcept { return mPhase; }
  static int Depth(int value) noexcept;

private:
  const uint8_t *mParameters = nullptr;
  uint32_t mClock = 0;
  uint16_t mPhase = 0, mStartPhase = 0, mDelay = 0, mFadeStep = 0, mFade = 0;
  uint16_t mCurrent = 0, mPrevious = 0;
  int16_t mRandomStep = 0, mValue = 0;
  bool mRunning = false, mWrapped = true;
};
} // namespace segrand
