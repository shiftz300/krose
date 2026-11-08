#pragma once
#include "effects/FxRack.h"
#include "midi/ArpPatterns.h"

// Serialized parameter IDs. Append new IDs; never reorder existing entries.
enum EParams {
  kParamTone = 0,
  kParamOutput = 1,
  kParamSpace = 2,
  kParamRelease = 3,
  kParamVelocity = 4,
  kParamProgram = 5,
  kParamPan = 6,
  kParamCutoff = 7,
  kParamResonance = 8,
  kAmpAttack = 9,
  kAmpDecay = 10,
  kAmpSustain = 11,
  kAmpRelease = 12,
  kFilterAttack = 13,
  kFilterDecay = 14,
  kFilterSustain = 15,
  kFilterRelease = 16,
  kVoiceMode = 17,
  kGlide = 18,
  kArpEnabled = 19,
  kArpLatch = 20,
  kArpPattern = 21,
  kArpResolution = 22,
  kArpGate = 23,
  kArpHostSync = 24,
  kArpTempo = 25,
  kArpOctaves = 26,
  kArpSort = 27,
  kArpKeySync = 28,
  kSW1Assign = 29,
  kSW1Mode = 30,
  kSW1State = 31,
  kSW2Assign = 32,
  kSW2Mode = 33,
  kSW2State = 34,
  kInputChannel = 35,
  kProgramChange = 36,
  kClockSource = 37,
  kFXBypass = 38,
  kFxType1 = 39,
  kFxType2 = 40,
  kFxType3 = 41,
  kFxType4 = 42,
  kFxAmount1 = 43,
  kFxAmount2 = 44,
  kFxAmount3 = 45,
  kFxAmount4 = 46,
  kFxOn1 = 47,
  kFxOn2 = 48,
  kFxOn3 = 49,
  kFxOn4 = 50,
  kFxDetails = 51,
  kArpSwing = kFxDetails + 2 * (segrand::kInsertDetailCount + segrand::kSendDetailCount),
  kArpVelocity,
  kArpKeyboard,
  kExtendedFxDetails,
  // All four positions can host native dynamics/EQ/modulation. Original IDs
  // 0..105 are immutable; the missing detail fields are appended here.
  kEGTarget = kExtendedFxDetails + 2 * (segrand::kFxDetailCount - segrand::kInsertDetailCount) +
              2 * (segrand::kFxDetailCount - segrand::kSendDetailCount),
  kFxEditorRequest,
  kNumParams
};

// Keep the three original action targets (39..41) stable in saved MIDI maps.
inline constexpr int kNumMidiParameters = kFXBypass + 1;
inline constexpr int MidiTargetForParameter(int id) { return id < kNumMidiParameters ? id : id + 3; }
inline constexpr int ParameterForMidiTarget(unsigned target) {
  return target < kNumMidiParameters ? int(target) : target >= kNumMidiParameters + 3 &&
      target < kNumParams + 3 ? int(target) - 3 : -1;
}
inline constexpr bool IsFxTypeParameter(int id) { return id >= kFxType1 && id <= kFxType4; }

inline constexpr int FxDetailParameter(int slot, int detail) {
  if (slot < 2) return detail < segrand::kDepth ? kFxDetails + slot*segrand::kInsertDetailCount+detail :
      kExtendedFxDetails + slot*(segrand::kFxDetailCount-segrand::kInsertDetailCount)+detail-segrand::kDepth;
  if (detail >= segrand::kDepth && detail < segrand::kGraphicGain)
    return kFxDetails + 2*segrand::kInsertDetailCount + (slot-2)*segrand::kSendDetailCount+detail-segrand::kDepth;
  return kExtendedFxDetails + 2*(segrand::kFxDetailCount-segrand::kInsertDetailCount) +
      (slot-2)*(segrand::kFxDetailCount-segrand::kSendDetailCount) +
      (detail < segrand::kDepth ? detail : detail-segrand::kSendDetailCount);
}
