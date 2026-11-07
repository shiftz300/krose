#pragma once
#include "EngineTypes.h"
#include "midi/ArpPatterns.h"
#include <array>
#include <algorithm>
#include <cstdint>

namespace segrand {
struct ArpControls {
  bool enabled = false, latch = false, hostSync = true, sort = true, keySync = true, keyboard = false;
  int pattern = 0, resolution = 3, gate = 80, octaves = 1, swing = 0, velocity = 129;
  double tempo = 120;
};
inline ArpControls ProgramArpeggiator(const uint8_t *p) noexcept {
  ArpControls c;
  if (!p) return c;
  c.enabled = p[0x4d8] & 1;
  c.pattern = std::clamp(int(p[0x4dc] | unsigned(p[0x4dd]) << 8), 0, kArpPatternCount-1);
  c.resolution = (p[0x4de] >> 2) & 7;
  c.octaves = (p[0x4de] & 3) + 1;
  c.sort = p[0x4df] & 1; c.latch = p[0x4df] & 2;
  c.keySync = p[0x4df] & 4; c.keyboard = p[0x4df] & 8;
  c.gate = std::clamp(int(p[0x4e0]),1,101);
  c.velocity = std::clamp(int(p[0x4e1]),1,129);
  c.swing = std::clamp(int(int8_t(p[0x4e2])),-100,100);
  c.tempo = std::clamp((p[0x4d4] + 256u*p[0x4d5] + 65536u*p[0x4d6])/100.,20.,300.);
  if (c.enabled && c.pattern >= 5) {
    const auto pattern = Pattern(c.pattern);
    bool content = false;
    for (int i = 0; i < pattern.Length(); ++i) content |= pattern.Step(i).tones != 0;
    // Expansion libraries may reference user patterns absent from PRELOAD.
    // Keep the playable instrument instead of silently routing it into an empty sequence.
    if (!content) c.enabled = false;
  }
  return c;
}
struct Transport {
  bool available = false, running = false;
  double tempo = 120, ppq = 0;
  bool midiClock = false;
  uint64_t positionRevision = 0;
};

// A single preset generator per MIDI channel. All queues and key sets have
// bounded storage; generated events feed the same engine path as direct MIDI.
class Arpeggiator {
public:
  using Emit = void (*)(void *, MidiEvent);
  static constexpr std::array<int, 8> kTicks{40, 60, 80, 120, 160, 240, 320, 480};
  void Prepare(double sampleRate) noexcept;
  void Reset() noexcept;
  void SetControls(ArpControls controls) noexcept;
  void SetTransport(Transport transport) noexcept;
  void Process(int frames, const MidiEvent *events, unsigned count, void *context,
               Emit emit) noexcept;
  const ArpControls &Controls() const noexcept { return mControls; }
  double Tempo() const noexcept { return mTempo; }
  static uint16_t RandomNext(uint16_t state) noexcept;
  static unsigned Position(int pattern, unsigned count, uint64_t step, uint16_t &random) noexcept;

private:
  struct Channel {
    std::array<uint8_t, 128> order{}, velocity{};
    std::array<bool, 128> down{};
    unsigned count = 0;
    uint64_t step = 0;
    int sounding = -1;
    struct Note {
      int pitch = -1, velocity = 0, tone = 0;
      bool playing = false, tie = false;
      double on = 0, off = 0;
    };
    std::array<Note,20> notes;
    bool pedal = false, scheduled = false;
    double next = 0, off = 0, eventDue = 1e100;
    void Remove(unsigned note) noexcept;
    void RemoveReleased() noexcept;
    unsigned Ordered(unsigned index, bool sort) const noexcept;
  };
  void Input(MidiEvent event, int offset, void *context, Emit emit) noexcept;
  void Silence(int channel, int offset, void *context, Emit emit) noexcept;
  void Schedule(Channel &channel) noexcept;
  void UpdateClock() noexcept;
  void PatternStep(Channel &, int channel, int frame, double step, void *, Emit) noexcept;
  void PatternNotes(Channel &, int channel, int frame, void *, Emit) noexcept;
  std::array<Channel, 16> mChannels{};
  ArpControls mControls;
  Transport mTransport;
  double mRate = 48000, mTempo = 120, mBeat = 0, mIncrement = 0;
  bool mClockRunning = true, mTransportSeen = false;
  bool mRoutingReset = false, mRestart = false, mDropReleased = false;
  uint16_t mRandom = 1;
};
} // namespace segrand
