#pragma once
#include <algorithm>
#include <array>
namespace krose::standalone {
inline constexpr std::array<unsigned, 11> kBufferSizes{32,64,96,128,192,256,512,1024,2048,4096,8192};
inline bool ValidBufferSize(unsigned frames) {
  return std::find(kBufferSizes.begin(), kBufferSizes.end(), frames) != kBufferSizes.end();
}
}
