#pragma once
#include "NativeVoiceData.h"
#include <algorithm>
#include <cstdint>
namespace segrand::envelope_math {
using namespace native_data;
inline uint32_t Exp(int exponent) {
  const int whole = exponent >> 16;
  if (whole < -16)
    return 0;
  if (whole > 15)
    return UINT32_MAX;
  const unsigned fraction = unsigned(exponent) & 65535, index = fraction >> 8,
                 residue = fraction & 255;
  const unsigned a = kExpFraction[index], b = index == 255 ? 65536 : kExpFraction[index + 1];
  const uint64_t factor = 65536 + a + (((b - a) * residue) >> 8);
  return uint32_t(std::min<uint64_t>(UINT32_MAX, ((uint64_t(1) << (whole + 16)) * factor) >> 16));
}
inline uint32_t Duration(uint32_t base, int modulation) {
  if (modulation > 0 && base <= 7)
    base = 8;
  return uint32_t(std::min<uint64_t>(INT32_MAX, (uint64_t(base) * Exp(modulation * 16)) >> 16));
}
inline uint32_t Coefficient(int curve, uint32_t steps) {
  if (steps <= 640)
    return kEgShort[(steps ? steps - 1 : 0) * 11 + curve];
  if (steps < 6400) {
    unsigned row = (steps - 640) / 64, f = (steps - 640) % 64;
    int64_t a = kEgMedium[row * 11 + curve], b = kEgMedium[(row + 1) * 11 + curve];
    return uint32_t(a + (((b - a) * f) >> 6));
  }
  int64_t a = kEgLong[curve], b = kEgLong[curve + 11];
  if (steps >= 230400)
    return uint32_t(b);
  return uint32_t(a + (b - a) * (steps - 6400) / 224000);
}
} // namespace segrand::envelope_math
