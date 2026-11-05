#include "midi/ControllerMap.h"
#include "midi/InputControls.h"
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <new>
static thread_local bool realtime = false;
void *operator new(std::size_t size) {
  assert(!realtime);
  if (auto *p = std::malloc(size ? size : 1))
    return p;
  throw std::bad_alloc();
}
void *operator new[](std::size_t n) { return ::operator new(n); }
void operator delete(void *p) noexcept { std::free(p); }
void operator delete[](void *p) noexcept { std::free(p); }
void operator delete(void *p, std::size_t) noexcept { std::free(p); }
void operator delete[](void *p, std::size_t) noexcept { std::free(p); }
#include <thread>
#include <vector>
using namespace krose::midi;
int main() {
  ControllerMap map(8);
  std::array<double, 8> parameters{};
  auto read = [&](unsigned target) { return parameters[target]; };
  auto write = [&](unsigned target, double value) { parameters[target] = value; };
  Binding b;
  b.source = Source::CC;
  b.number = 74;
  b.target = 0;
  b.pickup = false;
  map.Set(0, b);
  assert(map.Process({0, 0xb0, 74, 127}, read, write));
  assert(parameters[0] == 1);
  map.Process({0, 0xb1, 74, 0}, read, write);
  assert(parameters[0] == 0);
  b.channel = 1;
  map.Set(0, b);
  map.Process({0, 0xb1, 74, 127}, read, write);
  assert(parameters[0] == 0);
  b.pickup = true;
  parameters[0] = .5;
  map.Set(0, b);
  map.Process({0, 0xb0, 74, 1}, read, write);
  assert(parameters[0] == .5);
  map.Process({0, 0xb0, 74, 100}, read, write);
  assert(parameters[0] == 100. / 127);
  parameters[0] = .2;
  map.Process({0, 0xb0, 74, 101}, read, write);
  assert(parameters[0] == .2);
  map.Process({0, 0xb0, 74, 0}, read, write);
  assert(parameters[0] == 0);
  b.mode = Mode::Relative1;
  map.SetStep(0, .01);
  map.Set(0, b);
  map.Process({0, 0xb0, 74, 1}, read, write);
  assert(parameters[0] == .01);
  map.Process({0, 0xb0, 74, 127}, read, write);
  assert(parameters[0] == 0);
  b.mode = Mode::Relative2;
  map.Set(0, b);
  map.Process({0, 0xb0, 74, 65}, read, write);
  assert(parameters[0] == .01);
  map.Process({0, 0xb0, 74, 63}, read, write);
  assert(parameters[0] == 0);
  b.mode = Mode::Relative3;
  map.Set(0, b);
  map.Process({0, 0xb0, 74, 1}, read, write);
  assert(parameters[0] == .01);
  map.Process({0, 0xb0, 74, 65}, read, write);
  assert(parameters[0] == 0);
  b.source = Source::Note;
  b.number = 60;
  b.mode = Mode::Toggle;
  map.Set(0, b);
  map.Process({0, 0x90, 60, 100}, read, write);
  assert(parameters[0] == 1);
  map.Process({0, 0x90, 60, 100}, read, write);
  assert(parameters[0] == 1);
  map.Process({0, 0x80, 60, 0}, read, write);
  map.Process({0, 0x90, 60, 100}, read, write);
  assert(parameters[0] == 0);
  b.mode = Mode::Momentary;
  map.Set(0, b);
  map.Process({0, 0x90, 60, 100}, read, write);
  assert(parameters[0] == 1);
  map.Process({0, 0x90, 60, 0}, read, write);
  assert(parameters[0] == 0);
  // Editing an unrelated slot must not retrigger a held toggle; clearing a
  // momentary assignment releases its target on the next audio block.
  b.mode = Mode::Momentary;
  map.Set(0, b);
  map.Process({0, 0x90, 60, 100}, read, write);
  assert(parameters[0] == 1);
  map.Clear();
  map.Synchronize(write);
  assert(parameters[0] == 0);
  map.Clear();
  b = {};
  b.target = 3;
  b.pickup = false;
  map.Set(1, b);
  map.Learn(1);
  map.Process({0, 0xb4, 20, 127}, read, write);
  assert(map.Learning() == -1 && map.Get(1).channel == 5 && map.Get(1).number == 20 &&
         parameters[3] == 0);
  map.Process({0, 0xb4, 20, 127}, read, write);
  assert(parameters[3] == 1);
  map.Learn(2);
  map.CancelLearn();
  map.Process({0, 0xb4, 21, 127}, read, write);
  assert(map.Get(2).source == Source::Off);
  b.target = 4;
  map.Set(2, b);
  map.Learn(2);
  map.Process({0, 0xb4, 20, 127}, read, write);
  assert(map.Get(1).source == Source::Off && map.Get(2).target == 4);
  b = {};
  b.source = Source::CC14;
  b.number = 1;
  b.target = 1;
  b.pickup = false;
  map.Set(3, b);
  map.Process({0, 0xb0, 1, 64}, read, write);
  map.Process({0, 0xb0, 33, 127}, read, write);
  assert(parameters[1] == (8192 + 127) / 16383.);
  b.source = Source::NRPN;
  b.number = 130;
  b.target = 2;
  map.Set(4, b);
  map.Process({0, 0xb0, 99, 1}, read, write);
  map.Process({0, 0xb0, 98, 2}, read, write);
  map.Process({0, 0xb0, 6, 100}, read, write);
  map.Process({0, 0xb0, 38, 4}, read, write);
  assert(parameters[2] == 12804. / 16383);
  b.source = Source::RPN;
  b.number = 0;
  b.target = 5;
  map.Set(5, b);
  map.Process({0, 0xb0, 101, 0}, read, write);
  map.Process({0, 0xb0, 100, 0}, read, write);
  map.Process({0, 0xb0, 6, 12}, read, write);
  map.Process({0, 0xb0, 38, 0}, read, write);
  assert(parameters[5] == 1536. / 16383);
  b = {};
  b.source = Source::CC;
  b.number = 120;
  b.pickup = false;
  map.Set(6, b);
  assert(!map.Process({0, 0xb0, 120, 0}, read, write));
  // One audio reader and one configuration writer never observe torn bindings.
  std::thread editor([&] {
    for (unsigned i = 0; i < 100000; ++i) {
      Binding v;
      v.source = Source::CC;
      v.channel = i % 17;
      v.number = i % 128;
      v.target = i % 8;
      map.Set(7, v);
    }
  });
  realtime = true;
  for (unsigned i = 0; i < 100000; ++i) {
    const auto v = map.Get(7);
    assert(v.Valid(8));
    map.Process({0, 0xb0, 1, 64}, read, write);
  }
  realtime = false;
  editor.join();
  InputControls controls;
  std::vector<Message> events;
  auto emit = [&](Message m) { events.push_back(m); };
  controls.Reset();
  controls.Configure(0, SwitchAssignment::OctaveUp, true, emit);
  controls.Process({0, 0x90, 60, 100}, emit);
  assert(events.back().data1 == 72);
  controls.Configure(0, SwitchAssignment::OctaveUp, false, emit);
  controls.Process({0, 0x80, 60, 0}, emit);
  assert(events.back().data1 == 72);
  controls.Configure(0, SwitchAssignment::OctaveDown, true, emit);
  auto size = events.size();
  controls.Process({0, 0x90, 0, 100}, emit);
  controls.Process({0, 0x80, 0, 0}, emit);
  assert(events.size() == size);
  controls.Configure(0, SwitchAssignment::PitchLock, false, emit);
  controls.Process({0, 0xe0, 0, 80}, emit);
  controls.Configure(0, SwitchAssignment::PitchLock, true, emit);
  size = events.size();
  controls.Process({0, 0xe0, 0, 64}, emit);
  assert(events.size() == size);
  controls.Configure(0, SwitchAssignment::PitchLock, false, emit);
  assert(events.back().data2 == 64);
  MidiClock clock;
  clock.Process({0, 0xfa, 0, 0}, 0, 48000);
  for (unsigned i = 0; i < 49; ++i)
    clock.Process({0, 0xf8, 0, 0}, i * 1000, 48000);
  assert(std::abs(clock.Tempo(48000, 100) - 120) < 1e-8);
  assert(clock.Beat(48000) == 2);
  assert(clock.Running(48000, 48000));
  clock.Process({0, 0xfc, 0, 0}, 48000, 48000);
  assert(!clock.Running(48000, 48000));
  assert(!clock.Available(96000, 48000));
  clock.Reset();
  clock.Process({0, 0xf8, 0, 0}, 0, 48000);
  clock.Process({0, 0xf8, 0, 0}, 1000, 48000);
  assert(clock.Running(1000, 48000));
  clock.Process({0, 0xfc, 0, 0}, 1000, 48000);
  clock.Process({0, 0xf8, 0, 0}, 2000, 48000);
  assert(!clock.Running(2000, 48000));
  std::cout << "PASS MIDI learning, mapping modes, pickup, 14-bit/NRPN/RPN, configuration "
               "concurrency, switches and MIDI clock\n";
}
