#pragma once
#include "ControllerMap.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
namespace krose::midi {
enum class SwitchAssignment : unsigned {
  Off,
  Mod,
  Portamento,
  OctaveDown,
  OctaveUp,
  PitchLock,
  Arp,
  Latch,
  Sustain,
  MonoLegato,
  FXBypass
};
class InputControls {
public:
  void Reset() noexcept {
    mHeld = {};
    mBend.fill(8192);
    mState = {};
    mAssign = {};
  }
  template <class Emit>
  void Configure(unsigned index, SwitchAssignment assignment, bool state, Emit emit) noexcept {
    if (index > 1)
      return;
    const auto old = mAssign[index];
    const bool was = mState[index];
    const bool wasLocked = Active(SwitchAssignment::PitchLock);
    if (old == assignment && was == state)
      return;
    auto send = [&](SwitchAssignment a, bool on) {
      const int cc = a == SwitchAssignment::Mod          ? 80 + int(index)
                     : a == SwitchAssignment::Portamento ? 65
                     : a == SwitchAssignment::Sustain    ? 64
                                                         : -1;
      if (cc >= 0)
        for (int ch = 0; ch < 16; ++ch)
          emit(Message{0, uint8_t(0xb0 + ch), uint8_t(cc), uint8_t(on ? 127 : 0)});
    };
    mAssign[index] = assignment;
    mState[index] = state;
    if (old != assignment && was)
      send(old, old == SwitchAssignment::Mod ? false : Active(old));
    if (old != assignment || was != state)
      send(assignment, assignment == SwitchAssignment::Mod ? state : Active(assignment));
    if (wasLocked && !Active(SwitchAssignment::PitchLock))
      for (int ch = 0; ch < 16; ++ch)
        emit(Message{0, uint8_t(0xe0 + ch), uint8_t(mBend[ch] & 127), uint8_t(mBend[ch] >> 7)});
  }
  bool HasHeld(unsigned channel, unsigned note) const noexcept {
    return channel < 16 && note < 128 && mHeld[channel][note].count;
  }
  bool Active(SwitchAssignment a) const noexcept {
    return (mAssign[0] == a && mState[0]) || (mAssign[1] == a && mState[1]);
  }
  template <class Emit> void Process(Message m, Emit emit) noexcept {
    const unsigned ch = m.status & 15, type = m.status & 240, n = m.data1 & 127;
    if (type == 0xe0) {
      mBend[ch] = (m.data1 & 127) + 128 * (m.data2 & 127);
      if (Active(SwitchAssignment::PitchLock))
        return;
    }
    if (type == 0xb0 && (n == 120 || n == 123)) {
      mHeld[ch] = {};
      emit(m);
      return;
    }
    if (type == 0x90 && m.data2) {
      auto &key = mHeld[ch][n];
      if (key.count == key.notes.size()) {
        mHeld[ch] = {};
        emit(Message{m.offset, uint8_t(0xb0 + ch), 120, 0});
      }
      const int shift = (Active(SwitchAssignment::OctaveUp) ? 12 : 0) -
                        (Active(SwitchAssignment::OctaveDown) ? 12 : 0);
      const int pitch = int(n) + shift;
      // Out-of-range notes still reserve a release entry, never wrap to another key.
      key.notes[(key.head + key.count) % key.notes.size()] =
          pitch < 0 || pitch > 127 ? 255 : uint8_t(pitch);
      ++key.count;
      if (pitch < 0 || pitch > 127)
        return;
      m.data1 = uint8_t(pitch);
    } else if (type == 0x80 || (type == 0x90 && !m.data2)) {
      auto &key = mHeld[ch][n];
      if (key.count) {
        const unsigned pitch = key.notes[key.head];
        key.head = (key.head + 1) % key.notes.size();
        --key.count;
        if (pitch == 255)
          return;
        m.data1 = uint8_t(pitch);
      }
    } else if (type == 0xa0) {
      const auto &key = mHeld[ch][n];
      if (key.count) {
        for (unsigned i = 0; i < key.count; ++i) {
          auto v = m;
          v.data1 = key.notes[(key.head + i) % key.notes.size()];
          if (v.data1 != 255)
            emit(v);
        }
        return;
      }
    }
    emit(m);
  }

private:
  struct Key {
    std::array<uint8_t, 8> notes{};
    unsigned head = 0, count = 0;
  };
  std::array<std::array<Key, 128>, 16> mHeld{};
  std::array<unsigned, 16> mBend{};
  std::array<SwitchAssignment, 2> mAssign{};
  std::array<bool, 2> mState{};
};
class MidiClock {
public:
  void Reset() noexcept { *this = {}; }
  void Process(Message m, uint64_t sample, double rate) noexcept {
    if (m.status == 0xfa) {
      ++mPositionRevision;
      mTicks = 0;
      mAnchor = sample;
      mStarted = true;
      mRunning = true;
      mSeen = false;
    }
    if (m.status == 0xfb) {
      mRunning = true;
      mStarted = true;
      mAnchor = sample;
    }
    if (m.status == 0xfc) {
      mRunning = false;
      mStarted = true;
    }
    if (m.status == 0xf2) {
      ++mPositionRevision;
      mTicks = unsigned(m.data1 + 128 * m.data2) * 6;
      mAnchor = sample;
      mSeen = false;
    }
    if (m.status != 0xf8)
      return;
    if (mSeen && sample > mLast) {
      const double interval = double(sample - mLast);
      if (interval > rate / 1000 && interval < rate) {
        mPeriod = mPeriod ? mPeriod + .2 * (interval - mPeriod) : interval;
      }
    }
    if (!mStarted)
      mRunning = true; // Clock-only controllers can drive a held arp.
    if (mRunning && mSeen)
      ++mTicks;
    mSeen = true;
    mAnchor = mLast = sample;
  }
  bool Available(uint64_t sample, double rate) const noexcept {
    return mSeen && sample >= mLast && sample - mLast < std::max(rate * .5, mPeriod * 8);
  }
  bool Running(uint64_t sample, double rate) const noexcept {
    return mRunning && Available(sample, rate);
  }
  double Tempo(double rate, double fallback) const noexcept {
    return mPeriod ? std::clamp(rate * 60 / (24 * mPeriod), 20., 300.) : fallback;
  }
  double Beat(uint64_t sample) const noexcept {
    return mTicks / 24. +
           (mRunning && mPeriod && sample >= mAnchor ? (sample - mAnchor) / (24 * mPeriod) : 0);
  }
  uint64_t PositionRevision() const noexcept { return mPositionRevision; }

private:
  uint64_t mAnchor = 0, mLast = 0, mTicks = 0;
  uint64_t mPositionRevision = 0;
  double mPeriod = 0;
  bool mSeen = false, mStarted = false, mRunning = false;
};
} // namespace krose::midi
