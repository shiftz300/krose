#pragma once
#include <array>
#include <algorithm>
#include <atomic>
#include <cstddef>
#include <cmath>

namespace segrand {
struct FxVisualSample {
  float input = 0, left = 0, right = 0, reduction = 0;
};
// One audio producer and one editor consumer. Publish once per processing call;
// a slow/closed editor drops visual samples, never waits in the audio thread.
class FxMonitor {
public:
  static constexpr unsigned kCapacity = 8192;
  void Prepare(double rate) noexcept {
    (void) rate; // Preserve the full stream: decimation would alias high frequencies.
  }
  void Enable(bool enabled) noexcept { mEnabled = enabled; }
  bool Enabled() const noexcept { return mEnabled; }
  void Push(unsigned slot, double input, double left, double right, double reduction = 0) noexcept {
    if (!mEnabled) return;
    auto &ring = mSlots[slot];
    if (ring.written - ring.read.load(std::memory_order_acquire) >= kCapacity) return;
    ring.samples[ring.written % kCapacity] = {float(input), float(left), float(right), float(reduction)};
    ++ring.written;
  }
  void Publish() noexcept {
    if (!mEnabled) return;
    for (auto &ring : mSlots) ring.published.store(ring.written, std::memory_order_release);
  }
  unsigned Read(unsigned slot, FxVisualSample *output, unsigned capacity) noexcept {
    auto &ring = mSlots[slot];
    const auto at = ring.read.load(std::memory_order_relaxed);
    const auto end = ring.published.load(std::memory_order_acquire);
    const unsigned count = std::min(capacity, end - at);
    for (unsigned i = 0; i < count; ++i) output[i] = ring.samples[(at + i) % kCapacity];
    ring.read.store(at + count, std::memory_order_release);
    return count;
  }
private:
  struct Ring {
    std::array<FxVisualSample, kCapacity> samples{};
    unsigned written = 0;
    std::atomic<unsigned> published{0}, read{0};
  };
  std::array<Ring, 4> mSlots;
  bool mEnabled = false;
};
}
