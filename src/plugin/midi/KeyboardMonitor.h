#pragma once
#include <array>
#include <atomic>
#include <cstdint>

namespace krose::midi {
// Audio-thread state, published once per block through lock-free snapshots.
// Per-channel ownership prevents one track's note-off from unlighting another.
class KeyboardMonitor {
public:
  void Reset() noexcept {
    mDown = {}; mTotal = {}; mPedal = {};
    Change(0, 8192); Change(1, 0); Change(2, 0); Publish();
  }
  void Process(uint8_t status, uint8_t number, uint8_t value) noexcept {
    const auto channel = status & 15, type = status & 240;
    number &= 127; value &= 127;
    if (type == 0x90 && value) {
      auto &down = mDown[channel][number];
      if (down < 65535 && ++down == 1) ++mTotal[number];
    } else if (type == 0x80 || type == 0x90) {
      auto &down = mDown[channel][number];
      if (down && --down == 0) --mTotal[number];
    } else if (type == 0xe0) {
      Change(0, number + 128u * value);
    } else if (type == 0xb0) {
      if (number == 1) Change(1, value);
      if (number == 121) { Change(0, 8192); Change(1, 0); }
      if (number == 64 || number == 120 || number == 121) {
        mPedal[channel] = number == 64 && value >= 64;
        bool pedal = false;
        for (bool down : mPedal) pedal |= down;
        if (pedal != bool(mExpression[2] & 0xffffu)) Change(2, pedal);
      }
      if (number == 120 || number == 123) {
        for (unsigned note = 0; note < 128; ++note)
          if (mDown[channel][note]) --mTotal[note];
        mDown[channel] = {};
      }
    }
  }
  void Publish() noexcept {
    for (unsigned i = 0; i < 3; ++i)
      mPublishedExpression[i].store(mExpression[i], std::memory_order_release);
    for (unsigned half = 0; half < 2; ++half) {
      uint64_t keys = 0;
      for (unsigned i = 0; i < 64; ++i) if (mTotal[half * 64 + i]) keys |= uint64_t(1) << i;
      mPublished[half].store(keys, std::memory_order_release);
    }
  }
  std::array<uint64_t, 2> Read() const noexcept {
    return {mPublished[0].load(std::memory_order_acquire), mPublished[1].load(std::memory_order_acquire)};
  }
  // Low 16 bits are the value, high bits a revision. Revisions stop an old
  // audio snapshot from overriding a more recent mouse drag on the UI thread.
  std::array<uint64_t, 3> Expression() const noexcept {
    return {mPublishedExpression[0].load(std::memory_order_acquire),
            mPublishedExpression[1].load(std::memory_order_acquire),
            mPublishedExpression[2].load(std::memory_order_acquire)};
  }
private:
  static_assert(std::atomic<uint64_t>::is_always_lock_free);
  void Change(unsigned index, unsigned value) noexcept {
    mExpression[index] = ((mExpression[index] + 0x10000ull) & ~0xffffull) | value;
  }
  std::array<std::array<uint16_t, 128>, 16> mDown{};
  std::array<uint8_t, 128> mTotal{};
  std::array<bool, 16> mPedal{};
  std::array<std::atomic<uint64_t>, 2> mPublished{};
  std::array<uint64_t, 3> mExpression{{8192, 0, 0}};
  std::array<std::atomic<uint64_t>, 3> mPublishedExpression{{8192, 0, 0}};
};
}
