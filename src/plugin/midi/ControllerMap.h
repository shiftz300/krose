#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>

namespace krose::midi {
enum class Source : uint8_t { Off, CC, CC14, NRPN, RPN, Note, Bend, Pressure, PolyPressure };
enum class Mode : uint8_t { Absolute, Relative1, Relative2, Relative3, Toggle, Momentary };
struct Binding {
  Source source = Source::Off;
  unsigned channel = 0, number = 0, target = 0; // channel 0 = any, otherwise 1..16
  Mode mode = Mode::Absolute;
  bool pickup = true, consume = true, invert = false;
  uint64_t Encode() const noexcept {
    return uint64_t(source) | uint64_t(channel) << 4 | uint64_t(number) << 9 |
           uint64_t(target) << 23 | uint64_t(mode) << 31 | uint64_t(pickup) << 35 |
           uint64_t(consume) << 36 | uint64_t(invert) << 37;
  }
  static Binding Decode(uint64_t word) noexcept {
    return {Source(word & 15),          unsigned(word >> 4 & 31), unsigned(word >> 9 & 16383),
            unsigned(word >> 23 & 255), Mode(word >> 31 & 15),    bool(word >> 35 & 1),
            bool(word >> 36 & 1),       bool(word >> 37 & 1)};
  }
  bool Valid(unsigned targets) const noexcept {
    if (unsigned(source) > unsigned(Source::PolyPressure) || channel > 16 || number >= 16384 ||
        target >= targets || unsigned(mode) > unsigned(Mode::Momentary))
      return false;
    return source == Source::Off || source == Source::RPN || source == Source::NRPN ||
           (source == Source::CC14 ? number < 32 : number < 128);
  }
};
struct Message {
  int offset = 0;
  uint8_t status = 0, data1 = 0, data2 = 0;
};
struct Event {
  Source source;
  unsigned channel, number, value, maximum;
  bool down;
};
class ControllerMap {
public:
  static constexpr unsigned kSlots = 64;
  explicit ControllerMap(unsigned targets) : mTargets(targets) {
    mSteps.fill(1. / 127);
    Clear();
  }
  // Configure once before starting processing; parameter ranges are immutable.
  void SetStep(unsigned target, double step) noexcept {
    if (target < mSteps.size())
      mSteps[target] = std::clamp(step, 0., 1.);
  }
  Binding Get(unsigned slot) const noexcept {
    return slot < kSlots ? Binding::Decode(mBindings[slot].load(std::memory_order_acquire))
                         : Binding{};
  }
  void Set(unsigned slot, Binding binding) noexcept {
    if (slot >= kSlots || !binding.Valid(mTargets))
      return;
    mBindings[slot].store(binding.Encode(), std::memory_order_release);
    mRevision.fetch_add(1, std::memory_order_release);
  }
  void Clear() noexcept {
    for (auto &b : mBindings)
      b.store(Binding{}.Encode(), std::memory_order_relaxed);
    CancelLearn();
    mRevision.fetch_add(1, std::memory_order_release);
  }
  unsigned Revision() const noexcept { return mRevision.load(std::memory_order_acquire); }
  void Learn(unsigned slot, Source filter = Source::Off) noexcept {
    if (slot < kSlots)
      mLearn.store(int(slot) | int(filter) << 8, std::memory_order_release);
  }
  void CancelLearn() noexcept { mLearn.store(-1, std::memory_order_release); }
  int Learning() const noexcept {
    const int n = mLearn.load(std::memory_order_acquire);
    return n < 0 ? -1 : n & 255;
  }
  uint32_t LastMessage() const noexcept { return mLast.load(std::memory_order_acquire); }
  // Audio-thread only; configuration uses whole, lock-free atomic records.
  void ResetRuntime() noexcept {
    mRuntime = {};
    mChannels = {};
  }
  template <class Write> void Synchronize(Write write) noexcept {
    const unsigned revision = mRevision.load(std::memory_order_acquire);
    if (revision == mRuntimeRevision)
      return;
    for (unsigned slot = 0; slot < kSlots; ++slot) {
      auto &r = mRuntime[slot];
      if (r.binding == mBindings[slot].load(std::memory_order_acquire))
        continue;
      if (r.binding != UINT64_MAX && r.down) {
        auto old = Binding::Decode(r.binding);
        if (old.mode == Mode::Momentary)
          write(old.target, 0.);
      }
      r = {};
    }
    mRuntimeRevision = revision;
  }
  template <class Read, class Write> bool Process(Message msg, Read read, Write write) noexcept {
    Synchronize(write);
    const unsigned channel = msg.status & 15, type = msg.status & 240, a = msg.data1 & 127,
                   b = msg.data2 & 127;
    mLast.store(uint32_t(msg.status) | a << 8 | b << 16, std::memory_order_release);
    bool consumed = false;
    auto event = [&](Event e) { consumed = Dispatch(e, read, write) || consumed; };
    if (type == 0xb0) {
      auto &c = mChannels[channel];
      c.cc[a] = uint8_t(b);
      c.valid[a] = true;
      event({Source::CC, channel + 1, a, b, 127, b >= 64});
      if (a < 64) {
        unsigned base = a % 32;
        if (c.valid[base])
          event({Source::CC14, channel + 1, base,
                 unsigned(c.cc[base]) * 128 + (c.valid[base + 32] ? c.cc[base + 32] : 0), 16383,
                 b >= 64});
      }
      if (a == 99 || a == 98) {
        c.nrpn = true;
        c.selection[a == 99 ? 0 : 1] = uint8_t(b);
      }
      if (a == 101 || a == 100) {
        c.nrpn = false;
        c.selection[a == 101 ? 2 : 3] = uint8_t(b);
      }
      const unsigned i = c.nrpn ? 0 : 2;
      if (c.selection[i] != 255 && c.selection[i + 1] != 255 &&
          (c.selection[i] != 127 || c.selection[i + 1] != 127)) {
        if (a == 6)
          c.data = unsigned(b) * 128 + (c.data & 127);
        if (a == 38)
          c.data = (c.data & 16256) + b;
        if (a == 96)
          c.data = std::min(16383u, c.data + 1);
        if (a == 97)
          c.data = c.data ? c.data - 1 : 0;
        if (a == 6 || a == 38 || a == 96 || a == 97)
          event({c.nrpn ? Source::NRPN : Source::RPN, channel + 1,
                 unsigned(c.selection[i]) * 128 + c.selection[i + 1], c.data, 16383,
                 c.data >= 8192});
      }
      if (a == 121)
        c = Channel{};
      if (a == 120 || a == 121 || a == 123)
        consumed = false; // Never swallow safety messages.
    } else if (type == 0x90 || type == 0x80)
      event({Source::Note, channel + 1, a, type == 0x80 ? 0 : b, 127, type == 0x90 && b != 0});
    else if (type == 0xe0)
      event({Source::Bend, channel + 1, 0, a + b * 128, 16383, a + b * 128 >= 8192});
    else if (type == 0xd0)
      event({Source::Pressure, channel + 1, 0, a, 127, a >= 64});
    else if (type == 0xa0)
      event({Source::PolyPressure, channel + 1, a, b, 127, b >= 64});
    return consumed;
  }

private:
  struct Runtime {
    uint64_t binding = UINT64_MAX;
    double previous = -1, lastOutput = -1;
    bool caught = false, down = false;
  };
  struct Channel {
    std::array<uint8_t, 128> cc{};
    std::array<bool, 128> valid{};
    std::array<uint8_t, 4> selection{{255, 255, 255, 255}};
    bool nrpn = true;
    unsigned data = 0;
  };
  unsigned mTargets;
  std::array<double, 256> mSteps{};
  std::array<std::atomic<uint64_t>, kSlots> mBindings{};
  std::array<Runtime, kSlots> mRuntime{};
  std::array<Channel, 16> mChannels{};
  std::atomic<int> mLearn{-1};
  std::atomic<unsigned> mRevision{0};
  std::atomic<uint32_t> mLast{0};
  unsigned mRuntimeRevision = 0;
  template <class Read, class Write> bool Dispatch(Event e, Read read, Write write) noexcept {
    int learning = mLearn.load(std::memory_order_acquire);
    if (learning >= 0) {
      const auto filter = Source(unsigned(learning) >> 8);
      if ((filter == Source::Off || filter == e.source) && (e.source != Source::Note || e.down)) {
        if (mLearn.compare_exchange_strong(learning, -1, std::memory_order_acq_rel)) {
          auto binding = Get(unsigned(learning) & 255);
          binding.source = e.source;
          binding.channel = e.channel;
          binding.number = e.number;
          // One physical source has one active destination unless explicitly edited.
          for (unsigned i = 0; i < kSlots; ++i)
            if (i != (unsigned(learning) & 255)) {
              auto old = Get(i);
              if (old.source == e.source && old.number == e.number &&
                  (old.channel == 0 || old.channel == e.channel)) {
                old.source = Source::Off;
                Set(i, old);
              }
            }
          Set(unsigned(learning) & 255, binding);
        }
        return true; // Learning captures without changing the target.
      }
    }
    bool consumed = false;
    for (unsigned slot = 0; slot < kSlots; ++slot) {
      const uint64_t encoded = mBindings[slot].load(std::memory_order_acquire);
      const auto b = Binding::Decode(encoded);
      if (b.source == Source::Off || b.source != e.source || b.number != e.number ||
          (b.channel && b.channel != e.channel))
        continue;
      consumed |= b.consume;
      auto &r = mRuntime[slot];
      if (r.binding != encoded) {
        r = {};
        r.binding = encoded;
      }
      const double current = std::clamp(read(b.target), 0., 1.);
      double value = e.value / double(e.maximum);
      if (b.invert)
        value = 1 - value;
      const bool down = b.invert ? !e.down : e.down;
      if (b.mode == Mode::Toggle) {
        if (down && !r.down)
          write(b.target, current >= .5 ? 0. : 1.);
        r.down = down;
        continue;
      }
      if (b.mode == Mode::Momentary) {
        write(b.target, down ? 1. : 0.);
        r.down = down;
        continue;
      }
      if (b.mode != Mode::Absolute) {
        const int v = int(e.value) & 127;
        int delta = b.mode == Mode::Relative1   ? (v == 64  ? 0
                                                   : v < 64 ? v
                                                            : v - 128)
                    : b.mode == Mode::Relative2 ? v - 64
                                                : (v & 64 ? -(v & 63) : (v & 63));
        if (b.invert)
          delta = -delta;
        if (delta)
          write(b.target, std::clamp(current + delta * mSteps[b.target], 0., 1.));
        continue;
      }
      const double tolerance = 1.5 / e.maximum;
      if (r.caught && r.lastOutput >= 0 && std::abs(current - r.lastOutput) > tolerance)
        r.caught = false;
      const bool crossed = r.previous >= 0 && (r.previous - current) * (value - current) <= 0;
      if (!b.pickup || r.caught || std::abs(value - current) <= tolerance || crossed) {
        write(b.target, value);
        r.caught = true;
        r.lastOutput = std::clamp(read(b.target), 0., 1.);
      }
      r.previous = value;
    }
    return consumed;
  }
};
static_assert(std::atomic<uint64_t>::is_always_lock_free,
              "MIDI mappings require lock-free 64-bit atomics");
} // namespace krose::midi
