// Build-time musical workload. This executable is never bundled or run by a host.
#include "engine/InstrumentEngine.h"
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string_view>

using namespace segrand;
namespace {
unsigned Program(const ProgramLibrary &library, std::string_view id) {
  if (id == "Concert") return 0;
  for (unsigned i = 0; i < library.programs.size(); ++i)
    if (id == library.programs[i].id.data()) return i + 1;
  throw std::runtime_error("PGO training Program is missing");
}
}
int main(int argc, char **argv) {
  if (argc != 3) return 2;
  try {
    auto library = ProgramLibrary::Load(argv[1], false);
    auto concert = SampleBank::Load(argv[2], false);
    // Keep the default set pinned during training to avoid repeatedly decoding it.
    auto pinned = SampleBank::Load(argv[2]);
    (void)pinned;
    constexpr std::array ids{"Concert", "A000", "A065", "B020", "C002", "D010",
                             "D104", "E099", "F036", "EXPCM001:001", "EXPCM002:011", "EXPCM004:001"};
    constexpr std::array noteCounts{1, 8, 16, 32, 64};
    constexpr std::array blockSizes{64, 128, 257};
    constexpr std::array velocities{1, 42, 85, 86, 106, 107, 127};
    unsigned index = 0;
    double checksum = 0;
    for (double rate : {44100., 48000., 96000.}) for (auto id : ids) {
      InstrumentEngine engine(concert, library);
      engine.Prepare(rate);
      Controls controls;
      controls.program = int(Program(*library, id));
      controls.preset = int(index % 3);
      controls.space = .65;
      controls.voiceMode = index % 5 == 1 ? 1 : index % 5 == 2 ? 2 : 0;
      controls.glide = controls.voiceMode ? 45 : 0;
      engine.SetControls(controls, true);
      ArpControls arp;
      arp.enabled = index % 5 == 0;
      arp.hostSync = false;
      arp.pattern = int((index / 5) % 5);
      arp.tempo = 137;
      engine.SetArpeggiator(arp);
      const int notes = noteCounts[(index + index / 5) % noteCounts.size()];
      const int frames = blockSizes[index % blockSizes.size()];
      std::array<float, 257> left{}, right{};
      for (int block = 0; block < 512; ++block) {
        if (block == 0 || block == 256) for (int i = 0; i < notes; ++i)
          engine.Queue({i % 17, 0x90, uint8_t(21 + (i * 7 + index * 3) % 88),
                        uint8_t(velocities[(index + i) % velocities.size()])});
        if (block == 64) engine.Queue({3, 0xb0, 64, 127});
        if (block == 128 || block == 384) for (int i = 0; i < notes; ++i)
          engine.Queue({i % 17, 0x80, uint8_t(21 + (i * 7 + index * 3) % 88), 0});
        if (block == 192) engine.Queue({11, 0xb0, 64, 0});
        if (block % 96 == 0) {
          controls.pan = int(index % 5) * 12 - 24;
          controls.cutoff = int(index % 7) * 3 - 9;
          controls.space = block % 192 ? .15 : .8;
          engine.Queue({0, 0xe0, 0, uint8_t(block % 192 ? 68 : 64)});
        }
        if (block == 480) engine.Panic();
        engine.SetControls(controls);
        engine.Process(left.data(), right.data(), frames);
        for (int i = 0; i < frames; ++i) {
          if (!std::isfinite(left[i]) || !std::isfinite(right[i]))
            throw std::runtime_error("Nonfinite audio in PGO training");
          checksum += std::abs(left[i]) + std::abs(right[i]);
        }
      }
      ++index;
    }
    if (!(checksum > 0)) throw std::runtime_error("PGO training produced no audio");
    std::cout << "Trained " << index << " musical workloads\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
