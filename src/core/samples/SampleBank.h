#pragma once
#include "samples/PCM24.h"
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
namespace segrand {
struct Sample {
  unsigned root = 0, top = 0, loopStart = 0, loopEnd = 0;
  uint32_t frameCount = 0;
  PCM24 stereo;
  size_t frames() const { return frameCount; }
};
struct SampleBank {
  double rootRate = 42017.578125;
  std::array<std::vector<Sample>, 3> layers;
  static std::shared_ptr<const SampleBank> Load(const std::string &path, bool preload = true);
  std::string path;
  bool preloaded = true;
  const Sample &Select(unsigned layer, unsigned note) const;
};

} // namespace segrand
