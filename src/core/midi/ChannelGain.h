#pragma once
#include <array>
#include <cmath>

namespace segrand {
// MIDI gain steps begin on the event's sample. The short ramp avoids a
// discontinuity in sounding voices and is shared by all voices on the channel.
class ChannelGain {
public:
  void Prepare(double sampleRate) noexcept { mRampFrames = int(std::round(sampleRate * .001)); }
  void Reset() noexcept {
    mChannels = {};
    mRamping = 0;
  }
  void Set(int channel, int controller, int value) noexcept {
    auto &c = mChannels[channel];
    switch (controller) {
    case 7: c.volume = value / 127.; break;
    case 11: c.expression = value / 127.; break;
    case 67: c.soft = value >= 64 ? .75 : 1.; break;
    case 121: c.volume = c.expression = c.soft = 1.; break;
    default: return;
    }
    const double target = c.volume * c.expression * c.soft;
    if (target == c.target)
      return;
    c.target = target;
    c.step = (target - c.current) / mRampFrames;
    c.remaining = mRampFrames;
    mRamping |= 1u << channel;
  }
  void Advance() noexcept {
    if (!mRamping)
      return;
    for (unsigned ch = 0; ch < mChannels.size(); ++ch) {
      auto &c = mChannels[ch];
      if (!c.remaining)
        continue;
      c.current += c.step;
      if (!--c.remaining) {
        c.current = c.target;
        mRamping &= ~(1u << ch);
      }
    }
  }
  double Current(int channel) const noexcept { return mChannels[channel].current; }

private:
  struct Channel {
    double volume = 1, expression = 1, soft = 1;
    double current = 1, target = 1, step = 0;
    int remaining = 0;
  };
  std::array<Channel, 16> mChannels{};
  unsigned mRamping = 0;
  int mRampFrames = 48;
};
} // namespace segrand
