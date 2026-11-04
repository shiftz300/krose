// Realtime handoff and sample residency. OS file cache is not forcibly purged.
#include "engine/InstrumentEngine.h"
#include <algorithm>
#include <chrono>
#include <iostream>
#include <thread>
#include <vector>
#ifdef __APPLE__
#include <mach/mach.h>
#endif
using namespace segrand;
size_t footprint() {
#ifdef __APPLE__
  task_vm_info_data_t info{};
  mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
  if (task_info(mach_task_self(), TASK_VM_INFO, reinterpret_cast<task_info_t>(&info), &count) ==
      KERN_SUCCESS)
    return info.phys_footprint;
#endif
  return 0;
}
int main(int argc, char **argv) {
  if (argc != 3)
    return 2;
  auto library = ProgramLibrary::Load(argv[1], false);
  auto concert = SampleBank::Load(argv[2], false);
  InstrumentEngine engine(concert, library);
  engine.Prepare(48000);
  Controls c;
  std::array<float, 128> l{}, r{};
  std::vector<int> programs{0, 1, 2, 5, 400, 700, 1161};
  for (unsigned i = 0; i < library->programs.size(); ++i)
    if (std::string(library->programs[i].id.data()) == "EXPCM001:000")
      programs.push_back(i + 1);
  programs.push_back(1);
  programs.push_back(2);
  programs.push_back(1);
  std::vector<double> callback;
  std::cout << "{\"scope\":\"48kHz / 128 frames; cache miss at plugin level, OS file cache "
               "unspecified; no DAW\",\"programs\":[";
  bool first = true;
  for (int program : programs) {
    engine.Panic();
    c.program = program;
    auto begin = std::chrono::steady_clock::now();
    do {
      auto start = std::chrono::steady_clock::now();
      engine.SetControls(c);
      engine.Process(l.data(), r.data(), 128);
      callback.push_back(
          std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - start)
              .count());
      if (engine.FailedProgram() == program)
        return 3;
      std::this_thread::sleep_until(start + std::chrono::microseconds(2667));
    } while (engine.CurrentProgram() != program);
    double millis =
        std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begin).count();
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    if (!first)
      std::cout << ',';
    first = false;
    std::cout << "{\"program\":" << program << ",\"id\":\""
              << (program ? library->programs[program - 1].id.data() : "Concert")
              << "\",\"switch_ms\":" << millis << ",\"pcm_bytes\":" << engine.ResidentBytes()
              << ",\"footprint_bytes\":" << footprint() << '}';
  }
  std::sort(callback.begin(), callback.end());
  std::cout << "],\"callback_us\":{\"median\":" << callback[callback.size() / 2]
            << ",\"p95\":" << callback[size_t(callback.size() * .95)]
            << ",\"max\":" << callback.back() << "}}\n";
}
