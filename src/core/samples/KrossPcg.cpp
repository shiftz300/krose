#include "samples/KrossPcg.h"
#include "samples/KrossPcgMap.h"
#include "samples/ProgramLibrary.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <utility>

namespace segrand {
namespace {
constexpr size_t kProgramBytes = 2140;
constexpr unsigned kOscStart = 0x564, kOscSize = 380;
using RawProgram = std::array<uint8_t, kProgramBytes>;

uint32_t BigEndian(const uint8_t *b) {
  return uint32_t(b[0]) << 24 | uint32_t(b[1]) << 16 | uint32_t(b[2]) << 8 | b[3];
}
unsigned SampleNumber(const uint8_t *b) {
  return b[2] | unsigned(b[3]) << 8;
}
bool Tag(const uint8_t *b, const char *name) { return std::memcmp(b, name, 4) == 0; }

const uint8_t *UserBank(const pcg::Bytes &data) {
  constexpr uint8_t model[] = {'K', 'O', 'R', 'G', 0x96, 0, 2, 1};
  if (data.size() < 40 || std::memcmp(data.data(), model, sizeof(model)) ||
      !Tag(data.data() + 16, "PCG1"))
    throw std::runtime_error("SELECT A KROSS 1 .PCG");
  const auto *b = data.data();
  if (BigEndian(b + 20) != data.size() - 28 || !Tag(b + 28, "DIV1"))
    throw std::runtime_error("DAMAGED PCG HEADER");
  const uint64_t directory = 40ull + BigEndian(b + 32);
  if (directory + 16 > data.size() || !Tag(b + directory, "INI2"))
    throw std::runtime_error("DAMAGED PCG DIRECTORY");
  const uint64_t directoryEnd = directory + 12 + BigEndian(b + directory + 4);
  if (directoryEnd > data.size() || directoryEnd < directory + 16)
    throw std::runtime_error("DAMAGED PCG DIRECTORY");
  uint64_t count = BigEndian(b + directory + 12);
  if (count > (directoryEnd - directory - 16) / 64)
    throw std::runtime_error("DAMAGED PCG DIRECTORY");
  for (uint64_t i = 0; i < count; ++i) {
    const auto *entry = b + directory + 16 + i * 64;
    if (!Tag(entry, "PRG1")) continue;
    const uint64_t begin = BigEndian(entry + 16);
    const uint64_t end = begin + BigEndian(entry + 12);
    if (begin < directoryEnd || end > data.size())
      throw std::runtime_error("DAMAGED PCG PROGRAM SECTION");
    for (uint64_t pos = begin; pos < end;) {
      if (end - pos < 24 || !Tag(b + pos, "PBK1"))
        throw std::runtime_error("DAMAGED PCG PROGRAM BANK");
      const auto *bank = b + pos;
      const uint64_t size = 12ull + BigEndian(bank + 4);
      if (size < 24 || size > end - pos)
        throw std::runtime_error("DAMAGED PCG PROGRAM BANK");
      if (BigEndian(bank + 20) == 4) { // Bank U
        if (BigEndian(bank + 12) != kPcgBankSize || BigEndian(bank + 16) != kProgramBytes ||
            size != 24 + kPcgBankSize * kProgramBytes)
          throw std::runtime_error("UNSUPPORTED PCG BANK U");
        return bank + 24;
      }
      pos += size;
    }
  }
  throw std::runtime_error("PCG HAS NO PROGRAM BANK U");
}

void RemapMultisample(uint8_t *slot) {
  const unsigned number = SampleNumber(slot);
  pcg::Multisample target{slot[1], uint16_t(number)};
  if (target.bank == 0 && number < pcg::kMono.size())
    target.number = pcg::kMono[number];
  else if (target.bank == 1 && number < pcg::kStereo.size())
    target = pcg::kStereo[number];
  slot[1] = target.bank;
  slot[2] = uint8_t(target.number);
  slot[3] = uint8_t(target.number >> 8);
}

int RomMultisample(unsigned bank, unsigned number) {
  if (bank == 0 && number + 1 < pcg::kRomStarts.size()) return int(number);
  if (bank == 1 && number < pcg::kFactoryStereo.size()) return pcg::kFactoryStereo[number];
  return -1;
}

const pcg::RomZone *FindZone(unsigned multisample, unsigned pitch) {
  const auto begin = pcg::kRomZones.begin() + pcg::kRomStarts[multisample];
  const auto end = pcg::kRomZones.begin() + pcg::kRomStarts[multisample + 1];
  const auto zone = std::lower_bound(begin, end, pitch,
                                    [](const auto &z, unsigned key) { return z.top < key; });
  return zone == end ? nullptr : &*zone;
}

class Waveforms {
public:
  explicit Waveforms(const ProgramLibrary &library) {
    mSampleIndex.fill(UINT32_MAX);
    for (uint32_t index = 0; index < library.samples.size(); ++index) {
      const auto id = library.samples[index].id;
      if (id < mSampleIndex.size()) mSampleIndex[id] = index;
    }
  }
  uint32_t operator[](const pcg::RomZone &zone) const { return mSampleIndex[zone.sample]; }
private:
  std::array<uint32_t, pcg::kRomSampleCount> mSampleIndex;
};

void VelocityRange(ProgramRegion &region, const uint8_t *b, int slot) {
  int upper = 127, previousUpper = 127;
  for (int i = 0; i < slot; ++i) {
    previousUpper = upper;
    upper = std::min(upper, int(b[4 * i]) - 1);
  }
  const int lower = slot < 3 ? std::max(1, int(b[4 * slot])) : 1;
  region.velocityLow = lower <= upper ? lower : 128;
  region.velocityHigh = lower <= upper ? upper : 0;
  if (slot < 3) {
    region.fadeInWidth = b[4 * slot + 1];
    region.fadeInCurve = b[4 * slot + 2] & 3;
  }
  if (slot) {
    const auto *previous = b + 4 * (slot - 1);
    region.fadeOutBottom = previous[0];
    region.fadeOutWidth = previous[1];
    region.fadeOutCurve = previous[2] & 3;
    const int end = std::min(previousUpper, int(previous[0]) + previous[1] - 1);
    if (previous[1] && std::max(1, int(previous[0])) <= end) {
      region.velocityLow = std::min(region.velocityLow, std::max(1, int(previous[0])));
      region.velocityHigh = std::max(region.velocityHigh, end);
    }
  }
}

bool ValidControls(const RawProgram &p) {
  if ((p[0x508] & 7) > 1) return false; // KROSS 1 Drum Kit data has its own sample references.
  for (unsigned phase = 0; phase < 4; ++phase)
    if (p[0x528 + phase] > 10) return false;
  for (unsigned osc = 0; osc < 2; ++osc) {
    const auto *b = p.data() + kOscStart + kOscSize * osc;
    for (unsigned phase = 0; phase < 4; ++phase)
      if (b[0x118 + 1 + phase * 2] >= 100 || b[0x118 + 8 + phase] > 10 ||
          b[0xd8 + 5 + phase * 2] >= 100 || b[0xd8 + phase] > 10)
        return false;
    if (p[0x518 + osc * 2] > 127 || p[0x519 + osc * 2] > 127)
      return false;
    for (unsigned slot = 0; slot < 3; ++slot)
      if (b[0x20 + slot * 4] > 127 || b[0x21 + slot * 4] > 127) return false;
  }
  return true;
}

std::vector<ProgramRegion> BuildProgram(const ProgramLibrary &library, const Waveforms &waveforms,
                                        InstrumentProgram &program, bool &missingPcm) {
  std::vector<ProgramRegion> regions;
  auto &p = program.controls;
  if (!ValidControls(p)) return regions;
  // The hardware remaps all four descriptors of both oscillator records.
  for (unsigned osc = 0; osc < 2; ++osc)
    for (unsigned slot = 0; slot < 4; ++slot)
      RemapMultisample(p.data() + kOscStart + kOscSize * osc + 8 * slot);
  for (auto &osc : program.lookup)
    for (auto &note : osc) note.fill(-1);
  // User arpeggios are part of the separate ARP section of the backup.
  const unsigned pattern = p[0x4dc] | unsigned(p[0x4dd]) << 8;
  if (pattern >= 921) p[0x4d8] &= ~1;
  for (int osc = 0; osc <= (p[0x508] & 7); ++osc) {
    const auto *b = p.data() + kOscStart + kOscSize * osc;
    for (int slot = 0; slot < 4; ++slot) {
      const auto *d = b + slot * 8;
      if (!(d[0] & 3) || !d[4]) continue;
      ProgramRegion region;
      VelocityRange(region, b + 0x20, slot);
      if (region.velocityLow > region.velocityHigh ||
          region.velocityLow > std::max(b[0x2d], b[0x2e]) ||
          region.velocityHigh < std::min(b[0x2d], b[0x2e]))
        continue;
      const int first = RomMultisample(d[1], SampleNumber(d));
      if (first < 0) {
        missingPcm = true;
        continue;
      }
      const bool stereo = d[1] == 1;
      region.oscillator = osc;
      region.slot = slot;
      region.slotLevel = std::min(int(d[4]), 127);
      region.pan = b[0x149] & 127;
      const auto keys = std::minmax(p[0x518 + 2 * osc], p[0x519 + 2 * osc]);
      for (int note = keys.first; note <= keys.second; ++note) {
        const auto pitch = unsigned(ProgramLibrary::SelectionPitch(program, osc, note) >> 8);
        const auto *left = FindZone(unsigned(first), pitch);
        const auto *right = stereo ? FindZone(unsigned(first) + 1, pitch) : nullptr;
        if (!left || (stereo && !right)) continue;
        region.sample = {waveforms[*left], right ? waveforms[*right] : UINT32_MAX};
        if (region.sample[0] == UINT32_MAX || (right && region.sample[1] == UINT32_MAX)) {
          missingPcm = true;
          continue;
        }
        region.root = {left->root, right ? right->root : 0};
        region.fine = {left->fine, right ? right->fine : 0};
        region.flags = (left->fixed ? 2 : 0) | (right && right->fixed ? 4 : 0);
        if ((d[5] & 128) && !(library.samples[region.sample[0]].flags & 1) &&
            (!right || !(library.samples[region.sample[1]].flags & 1)))
          region.flags |= 1;
        const auto previous = note ? program.lookup[osc][note - 1][slot] : -1;
        if (previous >= 0 && regions[previous].sample == region.sample &&
            regions[previous].root == region.root && regions[previous].fine == region.fine &&
            regions[previous].flags == region.flags) {
          regions[previous].noteHigh = note;
          program.lookup[osc][note][slot] = previous;
        } else {
          program.lookup[osc][note][slot] = int32_t(regions.size());
          region.noteLow = region.noteHigh = note;
          regions.push_back(region);
        }
      }
    }
  }
  return regions;
}

template <typename Commit>
pcg::InstallReport DecodeBank(const pcg::Bytes &data, const ProgramLibrary &library,
                              const Waveforms &waveforms, Commit commit) {
  const auto *bank = UserBank(data);
  pcg::InstallReport report;
  for (unsigned i = 0; i < kPcgBankSize; ++i) {
    InstrumentProgram program;
    std::copy_n(bank + i * kProgramBytes, kProgramBytes, program.controls.begin());
    // Stable across filename, installation order and revisions to waveform mapping.
    uint64_t fingerprint = 14695981039346656037ull;
    for (auto byte : program.controls) fingerprint = (fingerprint ^ byte) * 1099511628211ull;
    size_t length = 0;
    for (; length < 24 && program.controls[length]; ++length) {
      const auto letter = program.controls[length];
      program.name[length] = letter >= 32 && letter <= 126 ? char(letter) : '?';
    }
    while (length > 0 && program.name[length - 1] == ' ') program.name[--length] = 0;
    bool missingPcm = false;
    auto regions = length ? BuildProgram(library, waveforms, program, missingPcm)
                          : std::vector<ProgramRegion>{};
    if (regions.empty()) {
      ++report.skipped;
      continue;
    }
    ++report.playable;
    report.missingPcm += missingPcm;
    program.pcgFingerprint = fingerprint ? fingerprint : 1;
    program.missingPcm = missingPcm;
    commit(i, program, regions);
  }
  return report;
}
} // namespace

namespace pcg {
Bytes Read(const std::filesystem::path &file) {
  if (!std::filesystem::is_regular_file(file))
    throw std::runtime_error("SELECT A KROSS 1 .PCG");
  const auto size = std::filesystem::file_size(file);
  if (!size || size > kMaxFileSize) throw std::runtime_error("UNSUPPORTED PCG FILE SIZE");
  Bytes data(static_cast<size_t>(size));
  std::ifstream input(file, std::ios::binary);
  if (!input.read(reinterpret_cast<char *>(data.data()), std::streamsize(data.size())) ||
      input.peek() != std::char_traits<char>::eof())
    throw std::runtime_error("CANNOT READ PCG FILE");
  return data;
}

InstallReport Check(const ProgramLibrary &library, const Bytes &data) {
  return DecodeBank(data, library, Waveforms(library), [](auto, auto &, auto &) {});
}
} // namespace pcg

void ProgramLibrary::ImportPcgPrograms(const PcgSources &sources) {
  if (std::any_of(sources.begin(), sources.end(), [](const auto &path) { return !path.empty(); })) {
    const Waveforms waveforms(*this);
    for (unsigned slot = 0; slot < sources.size(); ++slot) {
      if (sources[slot].empty()) continue;
      try {
        DecodeBank(pcg::Read(std::filesystem::u8path(sources[slot])), *this, waveforms,
                   [&](unsigned position, InstrumentProgram &p, const auto &zones) {
          std::snprintf(p.id.data(), p.id.size(), "PCG%02u-U%03u", slot + 1, position);
          p.firstRegion = uint32_t(regions.size());
          p.regionCount = uint32_t(zones.size());
          for (auto &osc : p.lookup)
            for (auto &key : osc)
              for (auto &index : key)
                if (index >= 0) index += int32_t(p.firstRegion);
          regions.insert(regions.end(), zones.begin(), zones.end());
          programs.push_back(std::move(p));
          mPcgPrograms[slot * kPcgBankSize + position] = int(programs.size());
        });
      } catch (const std::runtime_error &) {
        // A deleted or damaged user file must not prevent the factory bank from loading.
      }
    }
  }
  InstrumentProgram missing;
  for (auto &osc : missing.lookup)
    for (auto &key : osc) key.fill(-1);
  programs.push_back(std::move(missing));
  mMissingPcgProgram = int(programs.size());
  mProgramWindows.resize(programs.size());
}

bool ProgramLibrary::HasPcgProgram(unsigned selection) const noexcept {
  return selection < mPcgPrograms.size() && mPcgPrograms[selection] != 0;
}
int ProgramLibrary::PcgEngineProgram(unsigned selection) const noexcept {
  return HasPcgProgram(selection) ? mPcgPrograms[selection] : mMissingPcgProgram;
}
} // namespace segrand
