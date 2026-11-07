#include "effects/FxRack.h"
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <new>

static bool realtime = false;
static unsigned allocations = 0, frees = 0;
void *operator new(std::size_t n) {
  if (realtime) ++allocations;
  if (void *p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc();
}
void *operator new[](std::size_t n) { return ::operator new(n); }
void operator delete(void *p) noexcept { if (realtime && p) ++frees; std::free(p); }
void operator delete[](void *p) noexcept { ::operator delete(p); }
int main() {
  using namespace segrand;
  FxRack rack;
  for (double rate : {0., -1., double(NAN), double(INFINITY), 192001.}) {
    bool rejected = false;
    try { rack.Prepare(rate); } catch (const std::invalid_argument &) { rejected = true; }
    assert(rejected);
  }
  assert(ResolveFxType(0, -1, false, false) == 1);
  assert(ResolveFxType(999, 0, false, false) == 1);
  assert(ResolveFxType(0, 4, false, false) == 1);
  const auto invalidSends = ResolveFxSends({}, NAN, INFINITY, NAN);
  assert(invalidSends.hall == 0 && invalidSends.chorus == 0);
  for (double rate : {32000., 44100., 48000., 96000., 192000.}) {
    rack.Prepare(rate);
    FxSettings settings{};
    for (auto &slot : settings) slot.type = 1;
    settings[0] = {3, 100};
    settings[0].detail[kAttack] = 0;
    for (double ratio : {1., 2., 4., 20.})
      for (double threshold : {-40., -20., -6.})
        for (double amplitude : {.001, .1, 1.}) {
          settings[0].detail[kRatio] = ratio;
          settings[0].detail[kThreshold] = threshold;
          rack.SetInserts(settings, false); rack.Reset();
          double left = amplitude, right = -amplitude / 2;
          realtime = true; rack.Insert(left, right); realtime = false;
          const double inputDb = 20 * std::log10(amplitude);
          const double outputDb = inputDb <= threshold ? inputDb : threshold + (inputDb - threshold) / ratio;
          const double expected = 1.6 * std::pow(10., outputDb / 20.);
          assert(std::abs(left - expected) < 1e-10);
          assert(std::abs(right + expected / 2) < 1e-10); // Stereo-linked gain.
        }
    settings[0] = {4, 100}; settings[0].detail[kCeiling] = -12;
    rack.SetInserts(settings, false); rack.Reset();
    for (double peak : {.01, .5, 10.}) {
      double l = peak, r = -peak;
      rack.Insert(l, r);
      assert(std::abs(l) <= std::pow(10., -12. / 20) + 1e-12 && r == -l);
    }
    // Automate every algorithm at both parameter extremes. All operations in this
    // loop are realtime entry points; the guard rejects C++ allocations and frees.
    std::array<double, 256> input{}, wet{};
    unsigned seed = 19;
    for (int block = 0; block < 1500; ++block) {
      const int count = block % 3 == 0 ? 1 : block % 3 == 1 ? 31 : 128;
      if (block % 7 == 0) {
        for (int slot = 0; slot < 4; ++slot) {
          seed = seed * 1664525u + 1013904223u;
          settings[slot].type = int(seed % (slot < 2 ? kInsertTypes.size() : kSendTypes.size()));
          settings[slot].amount = block % 11 ? 100 : NAN;
          settings[slot].enabled = block % 23 != 0;
          for (int id = 0; id < kFxDetailCount; ++id)
            settings[slot].detail[id] = block % 13 == 0 ? NAN :
                ((seed >> (id % 16)) & 1 ? kFxValues[id].min : kFxValues[id].max);
        }
        realtime = true;
        rack.SetInserts(settings, false); rack.SetReturns(settings, block % 29 ? 1 : NAN);
        realtime = false;
      }
      realtime = true;
      for (int n = 0; n < count; ++n) {
        double left = block < 1000 ? .04 * std::sin((block * 128 + n) * .071) : 0;
        double right = -left;
        rack.Insert(left, right);
        assert(std::isfinite(left) && std::isfinite(right));
        input[n * 2] = left; input[n * 2 + 1] = right;
      }
      rack.Returns(input.data(), wet.data(), count);
      realtime = false;
      for (int n = 0; n < count * 2; ++n) assert(std::isfinite(wet[n]));
    }
    wet.fill(123);
    rack.Returns(nullptr, wet.data(), 128);
    rack.Returns(input.data(), wet.data(), 129);
    rack.Returns(input.data(), wet.data(), -1);
    for (double v : wet) assert(v == 123);
  }
  assert(allocations == 0 && frees == 0);
  std::cout << "PASS compression curve, stereo link, limiter ceiling, five-rate FX stress, invalid inputs; zero realtime C++ allocations/frees\n";
}
