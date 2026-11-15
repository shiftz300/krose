#pragma once
#include <algorithm>
#include <array>
#include <cstddef>

namespace segrand {
inline constexpr int kVoiceTailFrames = 96;

template <class Voice, std::size_t Count, auto Waveform>
class VoiceTails {
public:
  auto begin() noexcept { return mVoices.begin(); }
  auto end() noexcept { return mVoices.end(); }
  auto begin() const noexcept { return mVoices.begin(); }
  auto end() const noexcept { return mVoices.end(); }

  template <class Render>
  void Add(Voice &voice, Render render) noexcept {
    auto tail = std::find_if(begin(), end(), [](const Voice &v) { return !(v.*Waveform); });
    if (tail == end()) {
      tail = std::min_element(begin(), end(),
          [](const Voice &a, const Voice &b) { return a.forcedRemaining < b.forcedRemaining; });
      // Finish the shortest tail into the stereo ring before reusing its voice.
      for (unsigned frame = 0; frame < kVoiceTailFrames && (*tail).*Waveform; ++frame) {
        auto &sample = mOverflow[(mPosition + frame) % kVoiceTailFrames];
        render(*tail, sample[0], sample[1]);
      }
    }
    *tail = voice;
    tail->forcedRemaining = kVoiceTailFrames;
    voice = {};
  }

  std::array<double, 2> PopOverflowSample() noexcept {
    const auto sample = mOverflow[mPosition];
    mOverflow[mPosition] = {};
    mPosition = (mPosition + 1) % kVoiceTailFrames;
    return sample;
  }

  void Reset() noexcept {
    mVoices = {};
    mOverflow = {};
    mPosition = 0;
  }

private:
  std::array<Voice, Count> mVoices{};
  std::array<std::array<double, 2>, kVoiceTailFrames> mOverflow{};
  unsigned mPosition = 0;
};
} // namespace segrand
