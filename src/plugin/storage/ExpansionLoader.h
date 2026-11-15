#pragma once

#include "samples/ProgramLibrary.h"
#include <filesystem>

namespace krose::storage {

struct ExpansionInfo {
  unsigned number;
  const char *name;
  const char *file;
  uint64_t kepSize;
  uint64_t pcmSize;
  const char *kepHash;
  uint64_t legacyPcmSize = 0;
};

inline constexpr std::array<ExpansionInfo, 3> kExpansions{{
    {1, "OASYS PIANO", "EXPCM001.pcm", 47474840, 47372124,
     "ca8e77bac45e731a09b50a4e9446ec72d8fad81a423e243cac34c9ae3e75be8c"},
    {2, "E.P. COLLECTION", "EXPCM002.pcm", 9139496, 9008034,
     "4ec7d6c8f740fadce55aa257628e4e284449ef44e75d400eb0d5156405e49688"},
    {4, "FUTURE SYNTH", "EXPCM004.pcm", 8513952, 8379080,
     "297d8687f4aa339927c1b792e69a44370b7746ec6eeb7ee109fe9a92b1594864",
     segrand::kLegacyFutureSynthPcmBytes},
}};
const ExpansionInfo *FindExpansion(unsigned number) noexcept;

class ExpansionLoader {
public:
  ExpansionLoader(std::filesystem::path userDirectory, std::filesystem::path defaultOasys);
  segrand::ExpansionPaths Sources() const;
  bool Installed(const ExpansionInfo &pack) const;
  unsigned Install(const std::filesystem::path &file, const segrand::ProgramLibrary &library);
  void Uninstall(const ExpansionInfo &pack);

private:
  std::filesystem::path mUserDirectory;
  std::filesystem::path mDefaultOasys;
  std::filesystem::path Source(const ExpansionInfo &pack) const;
};

segrand::PcgSources InstalledPcgs(const std::filesystem::path &directory);
segrand::pcg::InstallReport InstallPcg(const std::filesystem::path &directory,
                                      const std::filesystem::path &file,
                                      const segrand::ProgramLibrary &library);
} // namespace krose::storage
