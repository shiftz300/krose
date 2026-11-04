#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

namespace segrand {
// Immutable after loading. Playback performs no allocation, locks or file access.
// One guard byte makes the last unaligned 32-bit load safe as well.
class PCM24 {
public:
  void resize(std::size_t samples) { mBytes.resize(samples * 3 + 1); }
  uint8_t *data() noexcept { return mBytes.data(); }
  std::size_t size() const noexcept { return mBytes.empty() ? 0 : (mBytes.size() - 1) / 3; }
  std::size_t storageBytes() const noexcept { return mBytes.size(); }
  float operator[](std::size_t i) const noexcept {
    const auto *p = mBytes.data() + i * 3;
#if defined(_WIN32) || (defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__)
    uint32_t bits;
    std::memcpy(&bits, p, sizeof(bits));
    bits <<= 8;
    int32_t value;
    std::memcpy(&value, &bits, sizeof(value));
    return float(value) * (1.f / 2147483648.f);
#else
    int32_t value = int32_t(uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16));
    if (value & 0x800000)
      value -= 16777216;
    return float(value) * (1.f / 8388608.f);
#endif
  }

private:
  std::vector<uint8_t> mBytes;
};
} // namespace segrand
