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
  PCM24() = default;
  ~PCM24();
  PCM24(const PCM24 &) = delete;
  PCM24 &operator=(const PCM24 &) = delete;
  PCM24(PCM24 &&) noexcept;
  PCM24 &operator=(PCM24 &&) noexcept;
  // Allocate a fresh zeroed loading buffer; previous contents are discarded.
  void resize(std::size_t samples);
  uint8_t *data() noexcept { return mData; }
  std::size_t size() const noexcept { return mSize; }
  std::size_t storageBytes() const noexcept { return mSize ? mSize * 3 + 1 : 0; }
  float operator[](std::size_t i) const noexcept {
    const auto *p = mData + i * 3;
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
  std::vector<uint8_t> mSmall;
  uint8_t *mData = nullptr;
  std::size_t mSize = 0, mMappedBytes = 0;
  void clear() noexcept;
};
} // namespace segrand
