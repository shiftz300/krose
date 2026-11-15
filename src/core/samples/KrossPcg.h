#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace segrand {
class ProgramLibrary;
inline constexpr unsigned kPcgBanks = 16;
inline constexpr unsigned kPcgBankSize = 128;
inline constexpr unsigned kPcgProgramCount = kPcgBanks * kPcgBankSize;
using PcgSources = std::array<std::string, kPcgBanks>;

namespace pcg {
using Bytes = std::vector<uint8_t>;
struct InstallReport {
  unsigned playable = 0, missingPcm = 0, skipped = 0;
};
inline constexpr size_t kMaxFileSize = 8 * 1024 * 1024;
Bytes Read(const std::filesystem::path &file);
InstallReport Check(const ProgramLibrary &factory, const Bytes &file);
} // namespace pcg
} // namespace segrand
