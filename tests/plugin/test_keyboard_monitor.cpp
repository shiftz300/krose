#include "midi/KeyboardMonitor.h"
#include <cassert>
#include <iostream>
using krose::midi::KeyboardMonitor;
int main() {
  KeyboardMonitor monitor;
  auto lit = [&](unsigned n) { monitor.Publish(); return (monitor.Read()[n / 64] >> (n % 64)) & 1; };
  monitor.Reset(); assert(!lit(60));
  monitor.Process(0x90, 60, 100); monitor.Process(0x91, 60, 90);
  monitor.Process(0x80, 60, 0); assert(lit(60));
  monitor.Process(0x81, 60, 0); assert(!lit(60));
  monitor.Process(0x90, 72, 100); monitor.Process(0x90, 72, 100);
  monitor.Process(0x80, 72, 0); assert(lit(72));
  monitor.Process(0xb0, 64, 127); monitor.Process(0x90, 72, 0); assert(lit(72));
  monitor.Process(0xb1, 64, 127); monitor.Process(0xb0, 64, 0);
  assert(!lit(72)); assert((monitor.Expression()[2] & 0xffffu) == 1);
  monitor.Process(0xb1, 121, 0); monitor.Publish();
  assert((monitor.Expression()[2] & 0xffffu) == 0);
  monitor.Process(0xe3, 127, 127); monitor.Process(0xb3, 1, 99); monitor.Publish();
  const auto moved = monitor.Expression();
  assert((moved[0] & 0xffffu) == 16383 && (moved[1] & 0xffffu) == 99);
  monitor.Process(0xb3, 121, 0); monitor.Publish();
  assert((monitor.Expression()[0] & 0xffffu) == 8192);
  assert((monitor.Expression()[1] & 0xffffu) == 0);
  assert(monitor.Expression()[0] != moved[0]);
  monitor.Process(0x90, 60, 100); monitor.Process(0xb0, 123, 0); assert(!lit(60));
  monitor.Process(0xb0, 64, 127); monitor.Process(0x90, 60, 100);
  monitor.Process(0xb0, 123, 0); assert(lit(60));
  monitor.Process(0xb0, 120, 0); assert(!lit(60));
  monitor.Process(0xe0, 0, 0); monitor.Reset();
  assert((monitor.Expression()[0] & 0xffffu) == 8192);
  assert(!lit(60));
  std::cout << "PASS realtime key ownership, repeated notes, pedals, all-notes-off, panic and expression revisions\n";
}
