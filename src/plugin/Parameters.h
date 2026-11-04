#pragma once

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
  kNumParams = 19
};
