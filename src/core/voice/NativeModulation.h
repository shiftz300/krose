#pragma once
#include "voice/PitchEnvelope.h"
namespace segrand {
class NativeModulation {
public:
  void Start(const uint8_t *program, int oscillator, ModulationSources initial, uint32_t seed,
             const std::array<uint8_t, 128> *cc = nullptr) noexcept;
  void Tick(ModulationSources input, uint32_t musicalClock,
            const std::array<uint8_t, 128> *cc = nullptr) noexcept;
  void Release() noexcept { mPitch.Release(sources); }
  int PitchOffset() const noexcept;
  void SetRandomState(uint32_t state) noexcept { mRandom = state; }
  uint32_t RandomState() const noexcept { return mRandom; }
  ModulationSources sources{};
  std::array<NativeLFO, 2> lfo;
  static void Controllers(ModulationSources &sources, const std::array<uint8_t, 128> &cc,
                          int polyPressure, int pressure, int bend) noexcept;

private:
  const uint8_t *mOsc = nullptr;
  PitchEnvelope mPitch;
  std::array<bool, 2> mGate{};
  uint32_t mRandom = 1;
  void Mix(unsigned slot, bool initial) noexcept;
};
} // namespace segrand
