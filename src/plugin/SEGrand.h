#pragma once
#include "IPlug_include_in_plug_hdr.h"
#include "InstrumentEngine.h"
#include <memory>
#include <string>

enum EParams { kParamTone=0,kParamOutput,kParamSpace,kParamRelease,kParamVelocity,kParamProgram,kNumParams };
using namespace iplug;
using namespace igraphics;
class SEGrand final : public Plugin {
public:
  explicit SEGrand(const InstanceInfo& info);
#if IPLUG_DSP
  void ProcessBlock(sample** inputs,sample** outputs,int nFrames) override;
  void ProcessMidiMsg(const IMidiMsg& msg) override;
  void OnReset() override;
#endif
#if IPLUG_EDITOR
  void OnParamChangeUI(int paramIdx,EParamSource source=kUnknown) override;
#endif
private:
  std::unique_ptr<segrand::InstrumentEngine> mEngine;
  std::string mError;
  bool mPrepared=true;
};
