#pragma once

#include "IPlug_include_in_plug_hdr.h"
#include "InstrumentEngine.h"
#include "Parameters.h"
#include <array>
#include <atomic>
#include <memory>
#include <string>

using namespace iplug;
using namespace igraphics;

class KrosePlugin final : public Plugin {
public:
  explicit KrosePlugin(const InstanceInfo& info);
  int UnserializeState(const IByteChunk& chunk, int startPos) override;

#if IPLUG_DSP
  void ProcessBlock(sample** inputs, sample** outputs, int nFrames) override;
  void ProcessMidiMsg(const IMidiMsg& msg) override;
  void OnReset() override;
#endif
#if IPLUG_EDITOR
  void OnIdle() override;
  void OnUIClose() override;
  void OnParamChangeUI(int paramIdx, EParamSource source = kUnknown) override;
#endif

private:
  void InitializeParameters();
#if IPLUG_EDITOR
  static constexpr int kEditorTag = 100;
  void ConfigureEditor();
#endif
  std::unique_ptr<segrand::InstrumentEngine> mEngine;
  std::string mError;
  bool mPrepared = true;
  std::atomic<double> mDisplayTempo{120.};
  std::atomic<bool> mDisplayHost{false};
};
