#pragma once
#include "samples/PCM24.h"
#include <array>
#include <cstdint>
#include <iosfwd>

namespace segrand {
// Disk codecs only. Decoding belongs to the sample loader/lifecycle thread.
// The predictive history retains all 32 bits even though playback uses PCM24.
void ReadSamplePCM(std::istream &input, uint32_t codec, int16_t a1, int16_t a2,
                   const std::array<int16_t, 256> &lut, uint32_t frames, PCM24 &output);
} // namespace segrand
