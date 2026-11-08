#include "standalone/Runtime.h"
#include <cassert>
#include <iostream>
#include <thread>
#include <vector>
using krose::standalone::Runtime;
struct Event { int offset; uint8_t status, note, velocity; };
int main() {
  Runtime runtime;
  std::vector<Event> events;
  auto emit = [&](int o, uint8_t s, uint8_t n, uint8_t v) { events.push_back({o, s, n, v}); };
  // First callback spans [1.0, 1.01). Delayed delivery retains source intervals.
  runtime.PushMidi(0, 1.002, 0x90, 60, 100);
  runtime.PushMidi(.003, 1.008, 0x90, 64, 100);
  runtime.PushMidi(.003, 1.011, 0x80, 60, 0);
  runtime.PushMidi(.002, 1.012, 0x80, 64, 0);
  runtime.BeginAudio(480, 48000, 1.01);
  runtime.DrainMidi(0, 128, emit);
  assert(events.size() == 1 && events[0].offset == 96);
  runtime.DrainMidi(128, 128, emit);
  assert(events.size() == 2 && events[1].offset == 112);
  runtime.DrainMidi(256, 128, emit);
  assert(events.size() == 2); // Offset 384 belongs to the next slice.
  runtime.DrainMidi(384, 96, emit);
  assert(events.size() == 3 && events[2].offset == 0);
  runtime.BeginAudio(64, 48000, 1.0113333333333333);
  runtime.DrainMidi(0, 64, emit);
  assert(events.size() == 4 && events[3].offset == 0);
  // CoreMIDI can pack an entire chord in one packet. The pinned RtMidi
  // callback repeats that packet's delta for each message; these must not
  // accumulate into artificial future timestamps or smear the chord.
  Runtime packed;
  std::vector<Event> chord;
  packed.PushMidi(0, 5., 0x90, 48, 100);
  packed.BeginAudio(480, 48000, 5.01);
  packed.DrainMidi(0, 480, [](int, uint8_t, uint8_t, uint8_t) {});
  for (uint8_t note : {60, 64, 67, 72})
    packed.PushMidi(.1, 5.1, 0x90, note, 100);
  for (unsigned block = 0; block < 10; ++block) {
    packed.BeginAudio(480, 48000, 5.02 + block * .01);
    packed.DrainMidi(0, 480, [&](int o, uint8_t s, uint8_t n, uint8_t v) {
      chord.push_back({o,s,n,v});
    });
  }
  assert(chord.size() == 4);
  for (const auto &event : chord) assert(event.offset == chord.front().offset);
  // No stale held notes from a stopped stream, even across a rate change.
  runtime.PushMidi(.001, 1.013, 0x90, 72, 100);
  runtime.Reset();
  runtime.BeginAudio(441, 44100, 2.01);
  runtime.DrainMidi(0, 441, emit);
  assert(events.size() == 4);
  runtime.PushMidi(0, 2.005, 0x90, 76, 100);
  runtime.DrainMidi(0, 441, emit);
  assert(events.size() == 5 && events.back().offset == 220);
  // Overflow explicitly releases notes/pedal instead of losing Note Off silently.
  events.clear();
  for (unsigned n = 0; n <= Runtime::kCapacity; ++n)
    runtime.PushMidi(0, 2.005, 0x90, 60, 100);
  runtime.DrainMidi(0, 441, emit);
  assert(events.size() == 32 && events[0].note == 64 && events[1].note == 120);
  runtime.PushMidi(0, 2.005, 0x90, 72, 100);
  runtime.CancelMidi();
  runtime.BeginAudio(441, 44100, 2.02);
  events.clear();
  runtime.DrainMidi(0, 441, emit);
  assert(events.size() == 32 && events[1].note == 120);
  Runtime watchdog;
  watchdog.BeginAudio(64, 48000, 1.);
  assert(!watchdog.NeedsRecovery(1.1, true));
  assert(watchdog.NeedsRecovery(2.1, true)); // Driver claims running but callbacks stopped.
  watchdog.BeginAudio(64, 48000, 2.1);
  assert(watchdog.NeedsRecovery(2.1, true)); // Callback resumes after a sleep-sized gap.
  watchdog.Reset();
  assert(!watchdog.NeedsRecovery(Runtime::Now(), true));
  Runtime drift;
  double now = 3.;
  for (unsigned n = 0; n < 10000; ++n) {
    now += 64. / 48000 * 1.0001; // Hardware clock differs by 100 ppm.
    const double eventTime = now - 32. / 48000;
    drift.PushMidi(n ? 64. / 48000 * 1.0001 : 0, eventTime, 0x90, 60, 100);
    drift.BeginAudio(64, 48000, now);
    unsigned delivered = 0;
    drift.DrainMidi(0, 64, [&](int offset, uint8_t, uint8_t, uint8_t) {
      assert(offset >= 30 && offset <= 34);
      ++delivered;
    });
    assert(delivered == 1);
  }
  // SPSC producer/consumer with repeated stream-generation changes.
  Runtime concurrent;
  std::atomic<bool> done{false};
  std::thread producer([&] {
    for (unsigned n = 0; n < 100000; ++n)
      concurrent.PushMidi(0, 10., 0x90, 60, 100);
    done = true;
  });
  while (!done) {
    concurrent.Reset();
    concurrent.BeginAudio(64, 48000, 10.);
    concurrent.DrainMidi(0, 64, [](int o, uint8_t, uint8_t, uint8_t) { assert(o >= 0 && o < 64); });
  }
  producer.join();
  std::cout << "PASS source MIDI timing, variable block carry, restart/rate epochs, overflow panic and concurrent publication\n";
}
