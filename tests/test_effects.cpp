#include "ConcertEqData.h"
#include "concert_effects.h"
#include <array>
#include <cassert>
#include <cmath>
#include <iostream>
int main() {
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
