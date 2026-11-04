// Fixed MIDI/control workload; compares callback cost and exact output hashes.
// No device, GUI, installation, cache purge or user-state writes.
#include "engine/InstrumentEngine.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <vector>

using namespace segrand;
int main(int argc, char **argv) {
  if (argc != 3)
    return 2;
  auto factory = ProgramLibrary::Load(argv[1], false);
  auto concert = SampleBank::Load(argv[2], false);
  struct Case {
    const char *name;
    int program, notes;
    double rate;
  };
  const Case cases[] = {{"idle", 1, 0, 48000},
                        {"concert-16", 0, 16, 48000},
                        {"factory-8", 1, 8, 48000},
                        {"factory-32", 1, 32, 48000},
                        {"concert-16-96k", 0, 16, 96000}};
  std::cout << "{\"scope\":\"SetControls + Process, 128 frames, 256 warmup + 2000 measured blocks, "
               "selected Program preloaded\",\"cases\":[";
  bool first = true;
  for (const auto &test : cases) {
    InstrumentEngine engine(concert, factory);
    Controls controls;
    controls.program = test.program;
    controls.space = .3;
    engine.Prepare(test.rate);
    engine.SetControls(controls, true);
    for (int i = 0; i < test.notes; ++i)
      engine.Queue({0, 0x90, uint8_t(40 + i), 100});
    std::array<float, 128> left{}, right{};
    std::vector<double> times;
    times.reserve(2000);
    uint64_t hash = 14695981039346656037ull;
    for (int block = -256; block < 2000; ++block) {
      const auto start = std::chrono::steady_clock::now();
      engine.SetControls(controls);
      engine.Process(left.data(), right.data(), 128);
      const auto end = std::chrono::steady_clock::now();
      if (block < 0)
        continue;
      times.push_back(std::chrono::duration<double, std::micro>(end - start).count());
      for (int i = 0; i < 128; ++i)
        for (float value : {left[i], right[i]}) {
          uint32_t bits;
          std::memcpy(&bits, &value, 4);
          for (int byte = 0; byte < 4; ++byte) {
            hash ^= (bits >> (byte * 8)) & 255;
            hash *= 1099511628211ull;
          }
        }
    }
    std::sort(times.begin(), times.end());
    if (!first)
      std::cout << ',';
    first = false;
    std::cout << "{\"case\":\"" << test.name << "\",\"median_us\":" << times[1000]
              << ",\"p95_us\":" << times[1900] << ",\"hash\":\"" << std::hex << hash << std::dec
              << "\"}";
  }
  std::cout << "]}\n";
}
