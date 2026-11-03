#pragma once
#include "IPlug_include_in_plug_hdr.h"
#include "InstrumentEngine.h"
#include <memory>
#include <string>

enum EParams { kParamTone=0,kParamOutput,kParamSpace,kParamRelease,kParamVelocity,kParamProgram,kParamPan,kParamCutoff,kParamResonance,
  kAmpAttack,kAmpDecay,kAmpSustain,kAmpRelease,kFilterAttack,kFilterDecay,kFilterSustain,kFilterRelease,kNumParams };
using namespace iplug;
using namespace igraphics;
class SEGrand final : public Plugin {
public:
  int UnserializeState(const IByteChunk& chunk,int startPos) override;
  explicit SEGrand(const InstanceInfo& info);
#if IPLUG_DSP
  void ProcessBlock(sample** inputs,sample** outputs,int nFrames) override;
  void ProcessMidiMsg(const IMidiMsg& msg) override;
  void OnReset() override;
#endif
#if IPLUG_EDITOR
  static constexpr int kEditorTag=100;
  void HandleEditorMessage(const char* text);
  void OnUIClose() override;
  void OnParamChangeUI(int paramIdx,EParamSource source=kUnknown) override;
#endif
private:
  std::array<bool,128> mEditorNotes{};
  bool mEditorSustain=false,mEditorBend=false;
  std::unique_ptr<segrand::InstrumentEngine> mEngine;
  std::string mError;
  bool mPrepared=true;
};
