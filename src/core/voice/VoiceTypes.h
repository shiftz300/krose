#pragma once
namespace segrand {
// Nominal firmware timing, independent of the host's block size/sample rate.
inline constexpr double kNativeControlHz = 62.5;
inline constexpr double kNativeAudioHz = 48000;
inline constexpr double kNativeReleaseBaseSeconds = 0.288;

struct EnvelopeOffsets {
  int attack = 0, decay = 0, sustain = 0, release = 0;
};

} // namespace segrand
