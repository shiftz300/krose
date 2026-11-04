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

  GetParam(kVoiceMode)->InitEnum("Voice Mode",0,3,"",IParam::kFlagsNone,"","Poly","Mono","Legato");
  GetParam(kGlide)->InitInt("Glide",0,0,127);

  MakeDefaultPreset("Concert");
  MakePresetFromNamedParams("Warm", 1, kParamTone, 1);
  MakePresetFromNamedParams("Wide", 1, kParamTone, 2);
  for (int i = 1; i < segrand::kInstrumentProgramCount; ++i)
    MakePresetFromNamedParams(segrand::kInstrumentProgramNames[i], 2,
                              kParamProgram, i, kParamSpace, 20.);
}

int KrosePlugin::UnserializeState(const IByteChunk& chunk, int startPos) {
  // Historical releases stored 6 or 17 doubles, followed by a VST3 bypass int.
  if(startPos<0||startPos>chunk.Size())return -1;
  const int available=chunk.Size()-startPos;
  for(int count:{6,17}){
    const int bytes=count*int(sizeof(double));
    if(available!=bytes&&available!=bytes+int(sizeof(int32_t)))continue;
    IByteChunk upgraded;
    upgraded.PutBytes(chunk.GetData()+startPos,bytes);
    for(int id=count;id<kNumParams;++id){const double value=GetParam(id)->GetDefault();upgraded.Put(&value);}
    if(UnserializeParams(upgraded,0)<0)return -1;
    return startPos+bytes;
  }
  return Plugin::UnserializeState(chunk,startPos);
}
