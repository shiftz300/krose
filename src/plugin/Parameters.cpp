#include "FactoryPrograms.h"
#include "KrosePlugin.h"

void KrosePlugin::InitializeParameters() {
  GetParam(kParamTone)
      ->InitEnum("Tone", 0, 3, "", IParam::kFlagsNone, "", "Concert", "Warm", "Wide");
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

  const char *offsets[] = {"Amp Attack",    "Amp Decay",    "Amp Sustain",    "Amp Release",
                           "Filter Attack", "Filter Decay", "Filter Sustain", "Filter Release"};
  for (int i = 0; i < 8; ++i)
    GetParam(kAmpAttack + i)->InitInt(offsets[i], 0, -99, 99);

  GetParam(kVoiceMode)
      ->InitEnum("Voice Mode", 0, 3, "", IParam::kFlagsNone, "", "Poly", "Mono", "Legato");
  GetParam(kGlide)->InitInt("Glide", 0, 0, 127);

  GetParam(kArpEnabled)->InitBool("Arp", false);
  GetParam(kArpLatch)->InitBool("Arp Latch", false);
  GetParam(kArpPattern)
      ->InitEnum("Arp Pattern", 0, 5, "", IParam::kFlagsNone, "", "UP", "DOWN", "ALT 1", "ALT 2",
                 "RANDOM");
  GetParam(kArpResolution)
      ->InitEnum("Arp Resolution", 3, 8, "", IParam::kFlagsNone, "", "1/32T", "1/32", "1/16T",
                 "1/16", "1/8T", "1/8", "1/4T", "1/4");
  GetParam(kArpGate)->InitInt("Arp Gate", 80, 1, 100, "%");
  GetParam(kArpHostSync)->InitBool("Arp Host Sync", true);
  GetParam(kArpTempo)->InitDouble("Arp Tempo", 120, 20, 300, .01, "BPM");
  GetParam(kArpOctaves)->InitInt("Arp Octaves", 1, 1, 4);
  GetParam(kArpSort)->InitBool("Arp Sort", true);
  GetParam(kArpKeySync)->InitBool("Arp Key Sync", true);

  for (int sw = 0; sw < 2; ++sw) {
    const int first = kSW1Assign + 3 * sw;
    GetParam(first)->InitEnum(sw ? "SW2 Assign" : "SW1 Assign", 1, 11, "", IParam::kFlagsNone, "",
                              "Off", "Mod CC", "Portamento", "Octave Down", "Octave Up",
                              "Pitch Lock", "Arp", "Latch", "Sustain", "Mono/Legato", "FX Bypass");
    GetParam(first + 1)->InitEnum(sw ? "SW2 Mode" : "SW1 Mode", 0, 2, "", IParam::kFlagsNone, "",
                                  "Toggle", "Momentary");
    GetParam(first + 2)->InitBool(sw ? "SW2" : "SW1", false);
  }
  GetParam(kInputChannel)->InitInt("MIDI Input Channel", 0, 0, 16);
  GetParam(kProgramChange)
      ->InitEnum("MIDI Program Change", 0, 3, "", IParam::kFlagsNone, "", "Off", "Krose Index",
                 "Catalog Banks");
  GetParam(kClockSource)
      ->InitEnum("Clock Source", 0, 3, "", IParam::kFlagsNone, "", "Host/Auto", "Internal",
                 "MIDI Clock");
  GetParam(kFXBypass)->InitBool("FX Bypass", false);
  const char *types[] = {"IFX 1 Type", "IFX 2 Type", "MFX 1 Type", "MFX 2 Type"};
  const char *amounts[] = {"IFX 1 Amount", "IFX 2 Amount", "MFX 1 Send", "MFX 2 Send"};
  for (int i = 0; i < 4; ++i) {
    auto *type = GetParam(kFxType1 + i);
    type->InitEnum(types[i], 0, int(i < 2 ? segrand::kInsertTypes.size() : segrand::kSendTypes.size()));
    for (int n = 0; n <= type->GetMax(); ++n)
      type->SetDisplayText(n, i < 2 ? segrand::kInsertTypes[n] : segrand::kSendTypes[n]);
    GetParam(kFxAmount1 + i)->InitInt(amounts[i], 50, 0, 100, "%");
    const auto slot = std::string(i < 2 ? "IFX " : "MFX ") + std::to_string(i % 2 + 1);
    GetParam(kFxOn1 + i)->InitBool((slot + " On").c_str(), true);
    const int first = i < 2 ? 0 : segrand::kDepth;
    const int end = i < 2 ? int(segrand::kDepth) : int(segrand::kFxDetailCount);
    for (int j = first; j < end; ++j) {
      const auto &spec = segrand::kFxValues[j];
      std::string name = slot + " ";
      if (j < segrand::kThreshold)
        name += "B" + std::to_string(j / 3 + 1) + " ";
      name += spec.label;
      GetParam(FxDetailParameter(i, j))->InitDouble(name.c_str(), spec.initial, spec.min,
                                                    spec.max, spec.step, spec.unit);
    }
  }

  // Factory presets contain sound parameters only; controller profiles are global.
  auto preset = [&](const char *name, int tone, int program, double space) {
    IByteChunk chunk;
    for (int id = 0; id < 29; ++id) {
      double v = GetParam(id)->Value();
      if (id == kParamTone)
        v = tone;
      if (id == kParamProgram)
        v = program;
      if (id == kParamSpace)
        v = space;
      chunk.Put(&v);
    }
    MakePresetFromChunk(name, chunk);
  };
  preset("Concert", 0, 0, 100.);
  preset("Warm", 1, 0, 100.);
  preset("Wide", 2, 0, 100.);
  for (int i = 1; i < segrand::kInstrumentProgramCount; ++i)
    preset(segrand::kInstrumentProgramNames[i], 0, i, 20.);
}
