#include "engine/InstrumentEngine.h"
#include "storage/ExpansionLoader.h"
#include <algorithm>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <random>

namespace fs = std::filesystem;
using namespace krose::storage;

namespace {
struct Scratch {
  fs::path path = fs::temp_directory_path() /
                  ("krose-expansions-" + std::to_string(std::random_device{}()));
  Scratch() { assert(fs::create_directory(path)); }
  ~Scratch() {
    std::error_code ignored;
    fs::remove_all(path, ignored);
  }
};

void ExpectRejected(ExpansionLoader &loader, const fs::path &file,
                    const segrand::ProgramLibrary &library) {
  bool rejected = false;
  try { loader.Install(file, library); }
  catch (const std::exception &) { rejected = true; }
  assert(rejected);
}

std::array<float, 8192> Render(const fs::path &reference,
                               const std::shared_ptr<const segrand::ProgramLibrary> &library,
                               int program, uint8_t note = 60, uint8_t velocity = 100) {
  auto concert = segrand::SampleBank::Load(reference.u8string(), false, library);
  // Match the plugin lifetime and keep the voice/FX storage off the Windows test stack.
  auto engine = std::make_unique<segrand::InstrumentEngine>(concert, library);
  engine->Prepare(48000);
  segrand::Controls controls;
  controls.program = program;
  assert(engine->SetControls(controls, true));
  engine->Queue({0, 0x90, note, velocity});
  std::array<float, 8192> left{}, right{};
  engine->Process(left.data(), right.data(), int(left.size()));
  return left;
}

void ComparePayload(const fs::path &actual, const fs::path &original, unsigned bank,
                    const segrand::ProgramLibrary &library) {
  std::ifstream expected(original, std::ios::binary), installed(actual, std::ios::binary);
  for (const auto &sample : library.samples) {
    if (sample.id / 10000 != bank) continue;
    std::vector<char> legacy(sample.frames), native(sample.frames);
    expected.seekg(static_cast<std::streamoff>(sample.offset));
    assert(expected.read(legacy.data(), legacy.size()));
    assert(installed.read(native.data(), native.size()));
    assert(legacy == native);
  }
  assert(installed.peek() == std::char_traits<char>::eof());
}

void CopyLegacyFutureSynth(const fs::path &destination, const fs::path &original,
                           const segrand::ProgramLibrary &library) {
  std::ifstream source(original, std::ios::binary);
  std::ofstream output(destination, std::ios::binary);
  uint64_t bytes = 0;
  for (const auto &sample : library.samples) {
    if (sample.id / 10000 != 4 || bytes == segrand::kLegacyFutureSynthPcmBytes) continue;
    source.seekg(static_cast<std::streamoff>(sample.offset));
    std::vector<char> raw(sample.frames);
    assert(source.read(raw.data(), raw.size()));
    assert(output.write(raw.data(), raw.size()));
    bytes += raw.size();
  }
  assert(bytes == segrand::kLegacyFutureSynthPcmBytes);
}
} // namespace

int main(int argc, char **argv) {
  assert(argc >= 4);
  const fs::path bundled = fs::u8path(argv[1]), original = fs::u8path(argv[2]),
                 concert = fs::u8path(argv[3]);
  Scratch scratch;
  const auto defaultOasys = scratch.path / "default" / "EXPCM001.pcm";
  fs::create_directory(defaultOasys.parent_path());
  fs::copy_file(bundled / "EXPCM001.pcm", defaultOasys);
  ExpansionLoader loader(scratch.path, defaultOasys);
  const auto factory = (bundled / "Factory.samples").u8string();
  auto complete = segrand::ProgramLibrary::Load(original.u8string(), false);
  const auto electric = std::find_if(complete->programs.begin(), complete->programs.end(),
      [](const auto &p) { return std::string_view(p.id.data()) == "EXPCM004:043"; });
  assert(electric != complete->programs.end());
  const int electricProgram = int(electric - complete->programs.begin()) + 1;
  // KORG KG4 drum catalog entries 7 / 34 / 17 / 16 and their decoded PCM IDs.
  constexpr unsigned zones[][5] = {
      {45, 1, 40181, 1, 127}, {83, 0, 40194, 1, 127},
      {96, 0, 40191, 85, 127}, {96, 1, 40190, 1, 84},
  };
  for (const auto &zone : zones) {
    const auto region = electric->lookup[0][zone[0]][zone[1]];
    assert(region >= 0);
    const auto &layer = complete->regions[region];
    assert(complete->samples[layer.sample[0]].id == zone[2]);
    assert(layer.velocityLow == int(zone[3]) && layer.velocityHigh == int(zone[4]));
    const auto audio = Render(concert, complete, electricProgram, uint8_t(zone[0]),
                              uint8_t((zone[3] + zone[4]) / 2));
    assert(std::any_of(audio.begin(), audio.end(), [](float x) { return x != 0; }));
  }
  auto defaults = segrand::ProgramLibrary::Load(factory, false, loader.Sources());
  assert(defaults->Split());
  assert(defaults->HasExpansion(0) && defaults->HasExpansion(1));
  assert(!defaults->HasExpansion(2) && !defaults->HasExpansion(4));
  assert(defaults->programs.size() == complete->programs.size());
  for (size_t i = 0; i < defaults->programs.size(); ++i)
    assert(defaults->programs[i].id == complete->programs[i].id);

  ComparePayload(defaultOasys, original, 1, *complete);
  auto originalConcert = Render(concert, complete, 0);
  assert(std::any_of(originalConcert.begin(), originalConcert.end(), [](float x) { return x != 0; }));
  assert(Render(concert, defaults, 0) == originalConcert);
  loader.Uninstall(kExpansions[0]);
  defaults.reset(); // Windows can finish deleting an open file once its last reader closes.
  assert(!fs::exists(defaultOasys) && !loader.Installed(kExpansions[0]));
  assert(!fs::exists(scratch.path / "EXPCM001.pcm"));
  auto onboard = segrand::ProgramLibrary::Load(factory, false, loader.Sources());
  assert(!onboard->HasExpansion(1));
  assert((Render(concert, onboard, 0) == std::array<float, 8192>{}));
  auto piano = Render(concert, onboard, 1);
  assert(std::any_of(piano.begin(), piano.end(), [](float x) { return x != 0; }));
  assert(piano == Render(concert, complete, 1));
  auto ep = std::find_if(onboard->programs.begin(), onboard->programs.end(),
                         [](const auto &p) { return segrand::ProgramExpansion(p.id.data()) == 2; });
  assert(ep != onboard->programs.end());
  assert((Render(concert, onboard, int(ep - onboard->programs.begin()) + 1) ==
          std::array<float, 8192>{}));

  auto corrupt = scratch.path / "corrupt.KEP";
  {
    std::ofstream file(corrupt, std::ios::binary);
    file.seekp(kExpansions[1].kepSize - 1);
    file.put(0);
  }
  ExpectRejected(loader, corrupt, *onboard);
  assert(!loader.Installed(kExpansions[1]));
  {
    std::ofstream file(corrupt, std::ios::binary);
    file.write("PK\003\004", 4);
  }
  ExpectRejected(loader, corrupt, *onboard);

  // Pass original KEP/ZIP files explicitly for a byte-for-byte import check.
  for (int i = 4; i < argc; ++i) {
    const auto number = loader.Install(fs::u8path(argv[i]), *onboard);
    const auto &pack = *std::find_if(kExpansions.begin(), kExpansions.end(),
                                     [&](const auto &entry) { return entry.number == number; });
    assert(loader.Installed(pack));
    const auto installedPath = scratch.path / pack.file;
    ComparePayload(installedPath, original, number, *complete);
    auto snapshot = segrand::ProgramLibrary::Load(factory, false, loader.Sources());
    assert(snapshot->HasExpansion(number));
    loader.Uninstall(pack);
    assert(!loader.Installed(pack) && !fs::exists(installedPath));
    assert(loader.Install(fs::u8path(argv[i]), *onboard) == number);
    // This existing instance can still decode from the old read handle.
    auto sample = std::find_if(snapshot->samples.begin(), snapshot->samples.end(),
                               [&](const auto &s) { return s.id / 10000 == number; });
    const uint32_t index = uint32_t(sample - snapshot->samples.begin());
    assert(snapshot->LoadSamples({index})[index]);
    loader.Uninstall(pack);
    if (number == 4) {
      CopyLegacyFutureSynth(installedPath, original, *complete);
      auto legacy = segrand::ProgramLibrary::Load(factory, false, loader.Sources());
      assert(legacy->HasExpansion(number));
      assert(legacy->programs[electricProgram - 1].lookup[0][96][1] < 0);
      assert((Render(concert, legacy, electricProgram, 96, 60) == std::array<float, 8192>{}));
      assert(loader.Install(fs::u8path(argv[i]), *onboard) == number);
      auto upgraded = segrand::ProgramLibrary::Load(factory, false, loader.Sources());
      assert(upgraded != legacy && upgraded->programs[electricProgram - 1].lookup[0][96][1] >= 0);
      assert(Render(concert, upgraded, electricProgram, 96, 60) ==
             Render(concert, complete, electricProgram, 96, 60));
      loader.Uninstall(pack);
    }
    std::cout << "EXPCM00" << number << " bit-exact ZIP/KEP import and uninstall\n";
  }
}
