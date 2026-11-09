#include "samples/NativeSampleCodec.h"
#include <algorithm>
#include <istream>
#include <limits>
#include <stdexcept>

namespace segrand {
void ReadSamplePCM(std::istream &input, uint32_t codec, int16_t a1, int16_t a2,
                   const std::array<int16_t, 256> &lut, uint32_t frames, PCM24 &output) {
  if (codec > 2)
    throw std::runtime_error("Unsupported sample codec");
  output.resize(frames);
  auto read = [&](void *target, size_t bytes) {
    if (!input.read(static_cast<char *>(target), std::streamsize(bytes)))
      throw std::runtime_error("Incomplete sample payload");
  };
  if (codec == 0) {
    read(output.data(), size_t(frames) * 3);
    return;
  }
  // Small bounded scratch space; no encoded copy of the entire waveform.
  std::array<uint8_t, 4096> bytes{};
  int32_t previous = 0, older = 0;
  const auto saturate = [](int64_t value) {
    constexpr int64_t limit = std::numeric_limits<int32_t>::max();
    return int32_t(std::clamp(value, -limit, limit));
  };
  const unsigned stride = codec == 1 ? 1 : 2;
  for (uint32_t start = 0; start < frames;) {
    const auto count = std::min(frames - start, uint32_t(bytes.size() / stride));
    read(bytes.data(), size_t(count) * stride);
    for (uint32_t i = 0; i < count; ++i) {
      auto *destination = output.data() + size_t(start + i) * 3;
      if (codec == 2) {
        destination[0] = 0;
        destination[1] = bytes[i * 2];
        destination[2] = bytes[i * 2 + 1];
      } else {
        const auto prediction = saturate((int64_t(a1) * previous + int64_t(a2) * older) / 16384);
        const auto value =
            saturate(int64_t(prediction) + int64_t(lut[(bytes[i] + 128) & 255]) * 65536);
        older = previous;
        previous = value;
        const auto bits = uint32_t(value) >> 8;
        destination[0] = uint8_t(bits);
        destination[1] = uint8_t(bits >> 8);
        destination[2] = uint8_t(bits >> 16);
      }
    }
    start += count;
  }
}
} // namespace segrand
