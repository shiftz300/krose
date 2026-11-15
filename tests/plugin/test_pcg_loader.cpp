#include "engine/InstrumentEngine.h"
#include "storage/ExpansionLoader.h"

#include <cassert>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <random>

namespace fs = std::filesystem;
namespace pcg = segrand::pcg;
namespace {
constexpr size_t kDirectory = 40, kSection = 120, kRecords = kSection + 24;
constexpr unsigned kRecordSize = 2140;

void Tag(pcg::Bytes &bytes, size_t offset, const char *tag) {
  std::memcpy(bytes.data() + offset, tag, 4);
}
void BigEndian(pcg::Bytes &bytes, size_t offset, uint32_t value) {
  for (unsigned i = 0; i < 4; ++i) bytes[offset + i] = uint8_t(value >> (24 - i * 8));
}
pcg::Bytes Fixture(const segrand::InstrumentProgram &piano) {
  pcg::Bytes file(kRecords + segrand::kPcgBankSize * kRecordSize);
  Tag(file, 0, "KORG");
  BigEndian(file, 4, 0x96000201);
  Tag(file, 16, "PCG1");
  BigEndian(file, 20, uint32_t(file.size() - 28));
  Tag(file, 28, "DIV1");
  Tag(file, kDirectory, "INI2");
  BigEndian(file, kDirectory + 4, 68);
  BigEndian(file, kDirectory + 12, 1);
  Tag(file, kDirectory + 16, "PRG1");
  BigEndian(file, kDirectory + 28, uint32_t(file.size() - kSection));
  BigEndian(file, kDirectory + 32, kSection);
  Tag(file, kSection, "PBK1");
  BigEndian(file, kSection + 4, uint32_t(file.size() - kSection - 12));
  BigEndian(file, kSection + 12, segrand::kPcgBankSize);
  BigEndian(file, kSection + 16, kRecordSize);
  BigEndian(file, kSection + 20, 4);
  std::copy(piano.controls.begin(), piano.controls.end(), file.begin() + kRecords);
  Tag(file, kRecords, "Test");
  const size_t osc = kRecords + 0x564;
  const auto multisample = [&](unsigned slot, uint8_t bank, unsigned number) {
    file[osc + 8 * slot + 1] = bank;
    file[osc + 8 * slot + 2] = uint8_t(number);
    file[osc + 8 * slot + 3] = uint8_t(number >> 8);
  };
  multisample(0, 1, 5);   // Legacy stereo strings become mono.
  multisample(1, 0, 8);   // Upright Piano has a new number.
  multisample(2, 1, 4);   // Brass stays stereo and moves by one.
  multisample(3, 0, 333); // No remap entry. Ramp uses PCM absent from the previous bank.
  file[osc + 0x78] = file[osc + 0x79] = 0;
  file[osc + 0x7c] = 10;
  // Out-of-range envelope indices are rejected without losing the rest of the bank.
  std::copy(piano.controls.begin(), piano.controls.end(), file.begin() + kRecords + kRecordSize);
  file[kRecords + kRecordSize + 0x528] = 255;
  return file;
}
void Write(const fs::path &path, const pcg::Bytes &data) {
  std::ofstream file(path, std::ios::binary);
  assert(file.write(reinterpret_cast<const char *>(data.data()), std::streamsize(data.size())));
}

void Render(const std::string &concertPath, const std::shared_ptr<const segrand::ProgramLibrary> &lib) {
  auto engine = std::make_unique<segrand::InstrumentEngine>(
      segrand::SampleBank::Load(concertPath, false, lib), lib);
  engine->Prepare(48000);
  for (unsigned i = 0; i < segrand::kPcgProgramCount; ++i) {
    if (!lib->HasPcgProgram(i)) continue;
    const int program = lib->PcgEngineProgram(i);
    const auto &p = lib->programs[program - 1];
    const auto end = lib->regions.begin() + p.firstRegion + p.regionCount;
    auto zone = std::find_if(lib->regions.begin() + p.firstRegion, end, [](const auto &r) {
      return r.noteLow <= 60 && r.noteHigh >= 60;
    });
    if (zone == end) zone = end - 1;
    const auto *osc = p.controls.data() + 0x564 + zone->oscillator * 380;
    const int lower = std::max(zone->velocityLow, int(std::min(osc[0x2d], osc[0x2e])));
    const int upper = std::min(zone->velocityHigh, int(std::max(osc[0x2d], osc[0x2e])));

    segrand::Controls controls;
    controls.program = program;
    controls.fx = engine->FactoryEffects(program).slots;
    assert(engine->SetControls(controls, true));
    engine->Panic();
    engine->SetArpeggiator(engine->FactoryArp(program));
    engine->Queue({0, 0x90, uint8_t(std::clamp(60, zone->noteLow, zone->noteHigh)),
                   uint8_t((lower + upper) / 2)});
    std::array<float, 512> left{}, right{};
    float peak = 0;
    for (int frame = 0; frame < 192000; frame += int(left.size())) {
      engine->Process(left.data(), right.data(), int(left.size()));
      for (unsigned n = 0; n < left.size(); ++n) {
        assert(std::isfinite(left[n]) && std::isfinite(right[n]));
        peak = std::max({peak, std::abs(left[n]), std::abs(right[n])});
      }
    }
    if (peak < 1e-7f) std::cerr << p.id.data() << " silent: " << p.name.data() << '\n';
    assert(peak >= 1e-7f && peak <= 1);
  }
}
} // namespace

int main(int argc, char **argv) {
  assert(argc >= 3 && argc < int(segrand::kPcgBanks) + 3);
  const auto library = segrand::ProgramLibrary::Load(argv[1], false);
  struct Scratch {
    fs::path folder = fs::temp_directory_path() /
                      ("krose-pcg-" + std::to_string(std::random_device{}()));
    Scratch() { assert(fs::create_directory(folder)); }
    ~Scratch() { std::error_code error; fs::remove_all(folder, error); }
  } scratch;
  const auto installed = scratch.folder / "PCG";
  const auto fixture = scratch.folder / "Bank U.PCG";
  auto bytes = Fixture(library->programs.front());
  Write(fixture, bytes);
  auto damaged = bytes;
  BigEndian(damaged, kDirectory + 32, UINT32_MAX);
  const auto invalid = scratch.folder / "Broken.PCG";
  Write(invalid, damaged);
  bool rejected = false;
  try {
    krose::storage::InstallPcg(installed, invalid, *library);
  } catch (const std::runtime_error &) {
    rejected = true;
  }
  assert(rejected && !fs::exists(installed));

  const auto report = krose::storage::InstallPcg(installed, fixture, *library);
  assert(report.playable == 1 && report.skipped == 127);
  krose::storage::InstallPcg(installed, fixture, *library);
  auto sources = krose::storage::InstalledPcgs(installed);
  assert(sources[1].empty());
  const auto expected = installed / "1" / "KORG" / "KROSS" / "DATA" / fixture.filename();
  assert(fs::u8path(sources[0]) == expected && pcg::Read(expected) == bytes);
  fs::remove(fixture);

  // Optional local original files exercise full-bank parsing and rendering.
  for (int i = 3; i < argc; ++i) {
    const fs::path path = fs::u8path(argv[i]);
    const auto actual = krose::storage::InstallPcg(installed, path, *library);
    assert(actual.playable == 128 && actual.skipped == 0 && actual.missingPcm == 0);
    std::cout << path.filename().u8string() << " " << actual.playable << " Programs, "
              << actual.missingPcm << " with missing PCM\n";
    sources = krose::storage::InstalledPcgs(installed);
    assert(fs::u8path(sources[i - 2]).filename() == path.filename());
    assert(pcg::Read(fs::u8path(sources[i - 2])) == pcg::Read(path));
  }
  const auto imported = segrand::ProgramLibrary::Load(argv[1], false, {}, &sources);
  assert(imported == segrand::ProgramLibrary::Load(argv[1], false, {}, &sources));
  assert(imported->HasPcgProgram(0) && !imported->HasPcgProgram(1));
  const int program = imported->PcgEngineProgram(0);
  assert(program > int(library->programs.size()));
  const auto &preset = imported->programs[program - 1];
  assert(preset.pcgFingerprint && preset.name[0] == 'T' && !preset.missingPcm);
  const auto *osc = preset.controls.data() + 0x564;
  const std::array<std::array<unsigned, 2>, 4> expectedMs = {{{0, 199}, {0, 14}, {1, 5}, {0, 333}}};
  const std::array<unsigned, 4> expectedSample = {2834, 3035, 2464, 2212};
  for (unsigned slot = 0; slot < 4; ++slot) {
    const auto *descriptor = osc + 8 * slot;
    assert(descriptor[1] == expectedMs[slot][0]);
    assert((descriptor[2] | unsigned(descriptor[3]) << 8) == expectedMs[slot][1]);
    assert(preset.lookup[0][60][slot] >= 0);
    const auto &zone = imported->regions[preset.lookup[0][60][slot]];
    assert(imported->samples[zone.sample[0]].id == expectedSample[slot]);
    if (slot == 2)
      assert(imported->samples[zone.sample[1]].id == 2465);
    else
      assert(zone.sample[1] == UINT32_MAX);
    assert(preset.lookup[0][121][slot] < 0);
  }
  const int missing = imported->PcgEngineProgram(segrand::kPcgProgramCount);
  assert(imported->programs[missing - 1].regionCount == 0);
  Render(argv[2], imported);
}
