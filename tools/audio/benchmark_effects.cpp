#include "ConcertEqData.h"
#include "effects/concert_effects.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <iostream>
#include <vector>
// Full precision baseline comparison: identical compiler/options, fixed input,
// wet automation, silence and wake-up; hash is recorded, not a cross-CPU oracle.
int main() {
  std::cout << "{\"profiles\":[";
  bool first = true;
  for (int mode = 0; mode < 3; ++mode) {
    double identity[40]{};
    for (int n = 0; n < 8; ++n)
      identity[n * 5] = 1;
    auto *fx = concert_effects_create(48000, mode == 0 ? identity : segrand::kConcertEq,
                                      mode == 0 ? 1 : segrand::kConcertTrim, 1.8, .15,
                                      mode == 2 ? .18 : 0, mode == 1 ? 8500 : 0);
    std::vector<double> timings;
    uint64_t hash = 1469598103934665603ull;
    for (int block = 0; block < 12000; ++block) {
      std::array<float, 256> audio{};
      if ((block >= 50 && block < 500) || block > 11500)
        for (int n = 0; n < 128; ++n) {
          audio[n * 2] = float(.2 * std::sin((block * 128 + n) * .043));
          audio[n * 2 + 1] = float(.15 * std::cos((block * 128 + n) * .019));
        }
      if (block == 700 || block == 9000)
        concert_effects_set_wet(fx, block == 700 ? 0 : .15, block == 700 ? 0 : mode == 2 ? .18 : 0);
      const auto start = std::chrono::steady_clock::now();
      concert_effects_process(fx, audio.data(), 128);
      if (block < 500)
        timings.push_back(
            std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - start)
                .count());
      for (float value : audio) {
        uint32_t bits;
        std::memcpy(&bits, &value, 4);
        hash ^= bits;
        hash *= 1099511628211ull;
      }
    }
    concert_effects_destroy(fx);
    std::sort(timings.begin(), timings.end());
    if (!first)
      std::cout << ',';
    first = false;
    std::cout << "{\"mode\":" << mode << ",\"median_us\":" << timings[timings.size() / 2]
              << ",\"p95_us\":" << timings[size_t(timings.size() * .95)] << ",\"hash\":\"" << hash
              << "\"}";
  }
  std::cout << "]}\n";
}
