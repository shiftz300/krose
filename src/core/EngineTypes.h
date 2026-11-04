#pragma once
#include "voice/VoiceTypes.h"
#include <cstdint>
namespace segrand {
struct Controls {
  int preset = 0;
  double outputDb = -6, space = 1, releaseSeconds = kNativeReleaseBaseSeconds, velocityCurve = 1;
  bool filterEnabled = true;
  int pan = 0, cutoff = 0, resonance = 0;
  EnvelopeOffsets ampEg, filterEg;
  int voiceMode = 0, glide = 0; // 0 Poly, 1 Mono retrigger, 2 Normal legato; glide 0..127.
  int program = 0; // Stable selector: 0 is the accepted Concert path, then factory Programs.
};
struct MidiEvent {
  int offset = 0;
  uint8_t status = 0, data1 = 0, data2 = 0;
};
} // namespace segrand
