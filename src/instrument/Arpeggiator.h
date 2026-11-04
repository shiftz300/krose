#pragma once
#include "EngineTypes.h"
#include <array>
#include <cstdint>

namespace segrand {
struct ArpControls {
  bool enabled = false, latch = false, hostSync = true, sort = true, keySync = true;
  int pattern = 0, resolution = 3, gate = 80, octaves = 1;
  double tempo = 120;
};
struct Transport {
  bool available = false, running = false;
  double tempo = 120, ppq = 0;
};

// A single preset generator per MIDI channel. All queues and key sets have
// bounded storage; generated events feed the same engine path as direct MIDI.
class Arpeggiator {
public:
  using Emit = void (*)(void*, MidiEvent);
  static constexpr std::array<int,8> kTicks{40,60,80,120,160,240,320,480};
  void Prepare(double sampleRate) noexcept;
  void Reset() noexcept;
  void SetControls(ArpControls controls) noexcept;
  void SetTransport(Transport transport) noexcept;
  void Process(int frames, const MidiEvent* events, unsigned count, void* context, Emit emit) noexcept;
  const ArpControls& Controls() const noexcept { return mControls; }
  double Tempo() const noexcept { return mTempo; }
  static uint16_t RandomNext(uint16_t state) noexcept;
  static unsigned Position(int pattern, unsigned count, uint64_t step, uint16_t& random) noexcept;
private:
  struct Channel {
    std::array<uint8_t,128> order{}, velocity{};
    std::array<bool,128> down{};
    unsigned count = 0;
    uint64_t step = 0;
    int sounding = -1;
    bool pedal = false, scheduled = false;
    double next = 0, off = 0;
    void Remove(unsigned note) noexcept;
    void RemoveReleased() noexcept;
    unsigned Ordered(unsigned index, bool sort) const noexcept;
  };
  void Input(MidiEvent event, int offset, void* context, Emit emit) noexcept;
  void Silence(int channel, int offset, void* context, Emit emit) noexcept;
  void Schedule(Channel& channel) noexcept;
  void UpdateClock() noexcept;
  std::array<Channel,16> mChannels{};
  ArpControls mControls;
  Transport mTransport;
  double mRate = 48000, mTempo = 120, mBeat = 0, mIncrement = 0;
  bool mClockRunning = true, mTransportSeen = false;
  bool mRoutingReset = false, mRestart = false, mDropReleased = false;
  uint16_t mRandom = 1;
};
}
