#pragma once
#include "EngineTypes.h"
#include "PerformanceData.h"
#include <algorithm>
#include <array>
#include <cmath>

namespace segrand {
// The original ten-entry priority list: duplicates remain separate, a full
// list drops its tail, and fallback uses the last selected note's velocity.
class MonoKeys {
public:
  bool On(int note, int velocity, int priority) noexcept {
    const bool selected = !mCount || priority == 2 ||
        (priority == 0 ? note < mNotes[0] : note > mNotes[0]);
    if (mCount == mNotes.size()) --mCount;
    unsigned at = 0;
    if (!selected)
      while (at < mCount && (priority == 0 ? mNotes[at] <= note : mNotes[at] >= note)) ++at;
    for (unsigned i = mCount; i > at; --i) mNotes[i] = mNotes[i - 1];
    mNotes[at] = note;
    ++mCount;
    if (selected) mVelocity = velocity;
    return selected;
  }
  bool Off(int note) noexcept {
    unsigned at = 0;
    while (at < mCount && mNotes[at] != note) ++at;
    if (at == mCount) return false;
    for (unsigned i = at + 1; i < mCount; ++i) mNotes[i - 1] = mNotes[i];
    --mCount;
    return at == 0;
  }
  int Note() const noexcept { return mCount ? mNotes[0] : -1; }
  int Velocity() const noexcept { return mVelocity; }
  unsigned Count() const noexcept { return mCount; }
  void Reset() noexcept { mCount = 0; mVelocity = 0; }
private:
  std::array<int,10> mNotes{};
  unsigned mCount = 0;
  int mVelocity = 0;
};

class MonoPerformance {
public:
  void Reset() noexcept { for (auto& keys : mChannels) keys.Reset(); }
  template<class Select, class Release>
  bool Handle(const MidiEvent& e, int priority, Select select, Release release) noexcept {
    const int channel = e.status & 15, type = e.status & 240;
    auto& keys = mChannels[channel];
    if (type == 0x90 && e.data2) {
      const bool connected = keys.Count() != 0;
      if (keys.On(e.data1, e.data2, priority))
        select(keys.Note(), keys.Velocity(), channel, connected);
      return true;
    }
    if (type == 0x80 || (type == 0x90 && !e.data2)) {
      if (keys.Off(e.data1)) {
        if (keys.Count()) select(keys.Note(), keys.Velocity(), channel, true);
        else release(channel);
      }
      return true;
    }
    if (type == 0xb0 && (e.data1 == 120 || e.data1 == 123)) keys.Reset();
    return false;
  }
private:
  std::array<MonoKeys,16> mChannels{};
};

// Original Q16 offset accumulator and Time-mode coefficient scaling. The
// host schedules updates on its nominal 62.5 Hz control clock; physical TG
// timing and pitch interpolation are separate from this integer recurrence.
class PitchGlide {
public:
  void Start(int previousQ16, int note, int amount) noexcept {
    mPhase = 0;
    mTarget = note * 65536;
    mPosition = mTarget;
    mStep = 0;
    const int coefficient = kPortamentoCoefficients[std::clamp(amount, 0, 127)];
    if (previousQ16 < 0 || !coefficient || previousQ16 == mTarget) return;
    mPosition = previousQ16;
    const int distance = std::abs(mTarget - mPosition);
    const auto step = std::max<int64_t>(1, int64_t(coefficient) * (distance / 256) / 3072);
    mStep = int(step) * (mTarget > mPosition ? 1 : -1);
  }
  void Tick() noexcept {
    if (!mStep) return;
    const int64_t next = int64_t(mPosition) + mStep;
    if ((mStep > 0 && next > mTarget) || (mStep < 0 && next < mTarget)) {
      mPosition = mTarget;
      mStep = 0;
    } else mPosition = int(next);
  }
  // Interpolate the control recurrence in the host to avoid stepped pitch.
  // This interpolation does not claim to reproduce the TG transfer function.
  double Ratio() const noexcept { return mPosition == mTarget ? 1. : std::exp2((InterpolatedPitch() - mTarget) / (12 * 65536)); }
  int CurrentPitch() const noexcept { return int(std::round(InterpolatedPitch())); }
  double Advance(double sampleRate) noexcept {
    if (!mStep) return Ratio();
    mPhase += kNativeControlHz / sampleRate;
    if (mPhase >= 1) { mPhase -= 1; Tick(); }
    return Ratio();
  }
  int Pitch() const noexcept { return mPosition; }
  int Step() const noexcept { return mStep; }
private:
  double InterpolatedPitch() const noexcept {
    const double next = double(mPosition) + mStep * mPhase;
    return mStep > 0 ? std::min(next, double(mTarget)) : mStep < 0 ? std::max(next, double(mTarget)) : mPosition;
  }
  double mPhase = 0;
  int mPosition = 0, mTarget = 0, mStep = 0;
};
}
