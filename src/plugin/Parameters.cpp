#include "KrosePlugin.h"
#include "FactoryPrograms.h"

void KrosePlugin::InitializeParameters() {
  GetParam(kParamTone)->InitEnum("Tone", 0, 3, "", IParam::kFlagsNone, "",
                                 "Concert", "Warm", "Wide");
  GetParam(kParamOutput)->InitDouble("Output", -6, -60, 6, 0.1, "dB");
  GetParam(kParamSpace)->InitDouble("Space", 100, 0, 200, 1, "%");
  GetParam(kParamRelease)->InitDouble("Release", 288, 30, 2000, 1, "ms");
  GetParam(kParamVelocity)->InitDouble("Velocity", 1., 0.5, 3, 0.01, "");
  GetParam(kParamProgram)->InitEnum("Program", 0, segrand::kInstrumentProgramCount);
  for (int i = 0; i < segrand::kInstrumentProgramCount; ++i)
    GetParam(kParamProgram)->SetDisplayText(i, segrand::kInstrumentProgramNames[i]);
  GetParam(kParamPan)->InitInt("Pan", 0, -64, 63);
  GetParam(kParamCutoff)->InitInt("Cutoff", 0, -99, 99);
  GetParam(kParamResonance)->InitInt("Resonance", 0, -99, 99);

  const char* offsets[] = {"Amp Attack", "Amp Decay", "Amp Sustain", "Amp Release",
                           "Filter Attack", "Filter Decay", "Filter Sustain", "Filter Release"};
  for (int i = 0; i < 8; ++i)
    GetParam(kAmpAttack + i)->InitInt(offsets[i], 0, -99, 99);

  MakeDefaultPreset("Concert");
  MakePresetFromNamedParams("Warm", 1, kParamTone, 1);
  MakePresetFromNamedParams("Wide", 1, kParamTone, 2);
  for (int i = 1; i < segrand::kInstrumentProgramCount; ++i)
    MakePresetFromNamedParams(segrand::kInstrumentProgramNames[i], 2,
                              kParamProgram, i, kParamSpace, 20.);
}

int KrosePlugin::UnserializeState(const IByteChunk& chunk, int startPos) {
  // Original projects stored six doubles, with a trailing bypass int in VST3.
  constexpr int legacyBytes = 6 * sizeof(double);
  const int available = chunk.Size() - startPos;
  if (startPos >= 0 &&
      (available == legacyBytes || available == legacyBytes + int(sizeof(int32_t)))) {
    IByteChunk upgraded;
    upgraded.PutBytes(chunk.GetData() + startPos, legacyBytes);
    for (int i = kParamPan; i < kNumParams; ++i) {
      const double value = GetParam(i)->GetDefault();
      upgraded.Put(&value);
    }
    if (UnserializeParams(upgraded, 0) < 0)
      return -1;
    return startPos + legacyBytes;
  }
  return Plugin::UnserializeState(chunk, startPos);
}
