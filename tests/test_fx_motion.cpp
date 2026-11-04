#include "../src/plugin/editor/native/FXMotion.h"
#include <cassert>
#include <cmath>
#include <iostream>
using krose::ui::FXMotion;
int main() {
  FXMotion motion;
  assert(motion.At(100).position == 0 && motion.At(100).velocity == 0);
  motion.Target(true, 100);
  assert(motion.At(100).position == 0 && motion.At(100).velocity == 0);
  double previous = 0, maxStep = 0;
  for (int frame = 1; frame <= 36; ++frame) {
    const auto state = motion.At(100 + frame / 60.);
    assert(state.position >= previous && state.position <= 1);
    maxStep = std::max(maxStep, state.position - previous);
    previous = state.position;
  }
  assert(motion.At(100.6).position == 1 && motion.At(100.6).velocity == 0);
  assert(motion.At(100.2).position > .95);
  const double oldFirstStep = 1 - std::pow(1 - 1. / 60 / .22, 3);
  assert(maxStep < oldFirstStep * .75);
  // Rapid toggles preserve both value and velocity, remain bounded, and settle.
  motion.Target(false, 101);
  for (int i = 1; i <= 100; ++i) {
    const double now = 101 + i * .019;
    const auto before = motion.At(now);
    motion.Target(i % 2, now);
    const auto after = motion.At(now);
    assert(std::abs(before.position - after.position) < 1e-12);
    assert(std::abs(before.velocity - after.velocity) < 1e-12);
    for (int j = 0; j < 19; ++j) {
      auto s = motion.At(now + j * .001);
      assert(s.position >= 0 && s.position <= 1 && std::isfinite(s.velocity));
    }
  }
  assert(motion.At(104).position == 0 && motion.At(104).velocity == 0);
  // Sampling the path at 120 Hz does not change values at shared 60 Hz times.
  FXMotion a, b;
  a.Target(true, 0);
  b.Target(true, 0);
  for (int i = 1; i <= 60; ++i) {
    b.At((i - .5) / 60.);
    assert(a.At(i / 60.).position == b.At(i / 60.).position);
  }
  std::cout << "PASS FX reversal continuity, bounds, settling, frame-rate independence; "
            << "60Hz max radius step " << maxStep * 550 << " px (old " << oldFirstStep * 550
            << ")\n";
}
