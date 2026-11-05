#include "ConcertEqData.h"
#include "effects/concert_effects.h"
#include "effects/FxRack.h"
#include <array>
#include <cassert>
#include <cmath>
#include <iostream>
int main() {
  for (double rate : {32000., 48000., 192000.}) {
    segrand::FxRack rack;
    rack.Prepare(rate);
    segrand::FxSettings settings{};
    const auto automatic = segrand::ResolveFxSends(settings, .15, .18, 1);
    assert(automatic.hall == .15 && automatic.chorus == .18);
    settings = {{{5, 70}, {1, 50}, {3, 100}, {3, 50}}};
    settings[3].detail[segrand::kDelayLeft] = 51;
    rack.SetInserts(settings, false);
    rack.SetReturns(settings, 1);
    rack.Reset();
    double left = .01, right = 0;
    rack.Insert(left, right);
    assert(left > .016 && left < .018 && right == 0);
    const int early = int(std::round(rate * .051));
    const int late = int(std::round(rate * .244));
    for (int n = 0; n <= late; ++n) {
      const double input[2] = {n == 0 ? left : 0, 0};
      double wet[2];
      rack.Returns(input, wet, 1);
      const double expected = n == early ? .25 * left : n == late ? .5 * left : 0;
      assert(std::abs(wet[0] - expected) < 1e-8);
    }
    settings[2].enabled = false;
    settings[3].enabled = false;
    rack.SetReturns(settings, 1);
    rack.Reset();
    const double impulse[2] = {1, 0}, silence[2] = {0, 0};
    double wet[2];
    for (int n = 0; n <= late; ++n) {
      rack.Returns(n == 0 ? impulse : silence, wet, 1);
      assert(wet[0] == 0 && wet[1] == 0);
    }
    settings[2] = {5, 60};
    settings[3] = {4, 50};
    rack.SetReturns(settings, 1);
    rack.Reset();
    double tail = 0;
    for (int n = 0; n < int(rate / 8); ++n) {
      rack.Returns(n == 0 ? impulse : silence, wet, 1);
      assert(std::isfinite(wet[0]) && std::isfinite(wet[1]));
      assert(n || (wet[0] == 0 && wet[1] == 0));
      tail += std::abs(wet[0]) + std::abs(wet[1]);
    }
    assert(tail > .01);
  }
  double identity[40]{};
  for (int i = 0; i < 8; ++i)
    identity[i * 5] = 1;
  assert(!concert_effects_create(0, identity, 1, 1.8, .15, .18, 0));
  assert(!concert_effects_create(48000, identity, 1, NAN, .15, .18, 0));
  size_t historyAt48k = 0;
  for (double rate : {32000., 44100., 48000., 96000., 192000.}) {
    std::array<ConcertEffects *, 3> separate{}, shared{};
    const double times[] = {1.8, 1.5, 2.6}, wet[] = {.15, .12, .23}, chorus[] = {0., 0., .18},
                 tone[] = {0., 8500., 0.};
    for (int i = 0; i < 3; ++i) {
      separate[i] = concert_effects_create(rate, segrand::kConcertEq, segrand::kConcertTrim,
                                           times[i], wet[i], chorus[i], tone[i]);
      shared[i] = concert_effects_create(rate, segrand::kConcertEq, segrand::kConcertTrim, times[i],
                                         wet[i], chorus[i], tone[i]);
      assert(separate[i] && shared[i]);
    }
    if (rate == 48000)
      historyAt48k = concert_effects_memory_bytes(separate[0]);
    if (rate == 192000)
      assert(historyAt48k * 3 < concert_effects_memory_bytes(separate[0]));
    std::array<float, 514> input{};
    std::array<double, 514> eq{};
    for (int block = 0; block < 1000; ++block) {
      const int count = block % 3 == 0 ? 257 : block % 3 == 1 ? 31 : 128;
      for (int n = 0; n < count; ++n) {
        double t = (block * 257. + n) / rate;
        input[n * 2] = block >= 10 && block < 100
                           ? float(.17 * std::sin(t * 1973) + .03 * std::cos(t * 631))
                           : 0;
        input[n * 2 + 1] = block >= 10 && block < 100 ? float(.13 * std::cos(t * 1311)) : 0;
      }
      if (block == 300 || block == 600)
        for (int p = 0; p < 3; ++p) {
          concert_effects_set_wet(separate[p], block == 300 ? 0 : wet[p],
                                  block == 300 ? 0 : chorus[p]);
          concert_effects_set_wet(shared[p], block == 300 ? 0 : wet[p],
                                  block == 300 ? 0 : chorus[p]);
        }
      concert_effects_equalize(shared[0], input.data(), eq.data(), count);
      for (int p = 0; p < 3; ++p) {
        auto reference = input;
        std::array<float, 518> output;
        output.fill(123);
        concert_effects_process(separate[p], reference.data(), count);
        concert_effects_process_equalized(shared[p], eq.data(), output.data() + 2, count);
        assert(output[0] == 123 && output[1] == 123 && output[count * 2 + 2] == 123 &&
               output[count * 2 + 3] == 123);
        for (int i = 0; i < count * 2; ++i)
          assert(std::isfinite(output[i + 2]) && output[i + 2] == reference[i]);
      }
    }
    for (int p = 0; p < 3; ++p) {
      concert_effects_destroy(separate[p]);
      concert_effects_destroy(shared[p]);
    }
  }
  std::cout << "PASS shared EQ vs independent paths, five rates, wet transitions, long tails, odd "
               "blocks and buffer guards\n";
}
