#include "../../src/plugin/editor/native/UIMotion.h"
#include <cassert>
#include <cmath>
#include <iostream>
using krose::ui::UIMotion;
int main() {
  UIMotion a, b;
  a.Target(.3, 10); assert(a.At(10) == .3 && !a.Active(10));
  a.Target(1, 11); b.Snap(.3); b.Target(1, 11);
  double previous = .3;
  for (int i = 0; i <= 120; ++i) {
    double t = 11 + i / 1000.;
    double v = a.At(t);
    assert(v >= previous && v <= 1); previous = v;
    // A redraw/repeated target cannot restart the clock. Extra 144 Hz
    // sampling cannot change a path sampled by a 60 Hz display.
    a.Target(1, t);
    b.At(t + 1. / 144);
    assert(a.At(t) == b.At(t));
  }
  assert(a.At(11.2) == 1 && !a.Active(11.2));
  for (int i = 0; i < 200; ++i) {
    double now = 12 + i * .007;
    double before = a.At(now);
    a.Target(i % 2 ? 1 : 0, now, .1);
    assert(a.At(now) == before);
    assert(a.At(now + .003) >= 0 && a.At(now + .003) <= 1);
  }
  assert(!a.Active(20));
  a.Target(0, 20); a.Snap(.75); // Direct drag never trails the pointer.
  assert(a.At(20) == .75 && !a.Active(20));
  a.Target(-1, 21); assert(a.At(22) == -1); // Bipolar pitch wheel.
  a.Target(1, 30, .09); assert(a.At(31) == 1); // Background/sleep catch-up.
  std::cout << "PASS UI motion continuity, bounds, idle settling and refresh independence\n";
}
