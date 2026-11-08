#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>

namespace krose::standalone {
// One MIDI producer and one audio consumer. Stream restarts invalidate queued
// messages by generation; neither thread resets the other's queue indices.
class Runtime {
public:
  static_assert(std::atomic<double>::is_always_lock_free &&
                    std::atomic<uint64_t>::is_always_lock_free,
                "Audio/MIDI publication requires lock-free atomics");
  static constexpr unsigned kCapacity = 2048;
  static double Now() noexcept {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
  }
  void Reset() noexcept {
    mGeneration.fetch_add(1, std::memory_order_acq_rel);
    mRecover.store(false, std::memory_order_release);
    mLastCallback.store(Now(), std::memory_order_relaxed);
  }
  void RequestRecovery() noexcept { mRecover.store(true, std::memory_order_release); }
  void CancelMidi() noexcept {
    mGeneration.fetch_add(1, std::memory_order_acq_rel);
    mOverflow.store(true, std::memory_order_release);
  }
  bool NeedsRecovery(double now, bool running) noexcept {
    return !running || mRecover.exchange(false, std::memory_order_acq_rel) ||
           now - mLastCallback.load(std::memory_order_relaxed) > 1.;
  }
  void PushMidi(double delta, double now, uint8_t status, uint8_t data1, uint8_t data2) noexcept {
    const auto generation = mGeneration.load(std::memory_order_acquire);
    // Preserve source-clock intervals for delayed callbacks. RtMidi/CoreMIDI
    // repeats a packet delta for every message inside that packet, so the
    // accumulated source time must never run ahead of its actual delivery.
    if (generation != mMidiGeneration || !std::isfinite(delta) || delta < 0 ||
        std::abs(now - (mMidiTime + delta)) > .5) {
      mMidiGeneration = generation;
      mMidiTime = now;
    } else
      mMidiTime = std::min(mMidiTime + delta, now);
    const auto write = mWrite.load(std::memory_order_relaxed);
    if (write - mRead.load(std::memory_order_acquire) == kCapacity) {
      mOverflow.store(true, std::memory_order_release);
      return;
    }
    mEvents[write % kCapacity] = {mMidiTime, generation, status, data1, data2};
    mWrite.store(write + 1, std::memory_order_release);
  }
  void BeginAudio(unsigned frames, double rate, double now) noexcept {
    const double previous = mLastCallback.exchange(now, std::memory_order_relaxed);
    if (previous > 0 && now - previous > 1.)
      RequestRecovery();
    const auto generation = mGeneration.load(std::memory_order_acquire);
    if (generation != mAudioGeneration) {
      mAudioGeneration = generation;
      mOrigin = now - frames / rate;
      mFrames = 0;
    } else {
      // Track slow hardware/monotonic-clock drift without turning callback
      // scheduling jitter into large MIDI jumps (at most one sample per call).
      const double error = now - (mOrigin + (mFrames + frames) / rate);
      mOrigin += std::clamp(error * .01, -1 / rate, 1 / rate);
    }
    mRate = rate;
    mCallbackStart = mOrigin + mFrames / rate;
    mFrames += frames;
  }
  template <class Emit> void DrainMidi(unsigned start, unsigned frames, Emit emit) noexcept {
    auto read = mRead.load(std::memory_order_relaxed);
    const auto write = mWrite.load(std::memory_order_acquire);
    if (mOverflow.exchange(false, std::memory_order_acq_rel)) {
      // Dropping a Note Off must never leave a stuck note or sustain pedal.
      for (unsigned ch = 0; ch < 16; ++ch) {
        emit(0, uint8_t(0xb0 + ch), uint8_t(64), uint8_t(0));
        emit(0, uint8_t(0xb0 + ch), uint8_t(120), uint8_t(0));
      }
      mRead.store(write, std::memory_order_release);
      return;
    }
    const double blockStart = mCallbackStart + start / mRate;
    while (read != write) {
      const auto &event = mEvents[read % kCapacity];
      if (event.generation == mAudioGeneration) {
        const double offset = (event.time - blockStart) * mRate;
        if (offset >= frames - 1e-5)
          break;
        emit(int(std::clamp(std::floor(offset + 1e-5), 0., double(frames - 1))),
             event.status, event.data1, event.data2);
      }
      ++read;
    }
    mRead.store(read, std::memory_order_release);
  }

private:
  struct Event {
    double time = 0;
    uint64_t generation = 0;
    uint8_t status = 0, data1 = 0, data2 = 0;
  };
  std::array<Event, kCapacity> mEvents{};
  std::atomic<unsigned> mRead{0}, mWrite{0};
  std::atomic<uint64_t> mGeneration{1};
  std::atomic<bool> mOverflow{false}, mRecover{false};
  std::atomic<double> mLastCallback{0};
  uint64_t mMidiGeneration = 0, mAudioGeneration = 0, mFrames = 0;
  double mMidiTime = 0, mOrigin = 0, mCallbackStart = 0, mRate = 48000;
};
} // namespace krose::standalone
