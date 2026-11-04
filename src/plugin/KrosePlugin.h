#pragma once

#include "IPlug_include_in_plug_hdr.h"
#include "InstrumentEngine.h"
#include "Parameters.h"
#include <array>
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
  void OnUIClose() override;
  void OnParamChangeUI(int paramIdx, EParamSource source = kUnknown) override;
#endif

private:
  void InitializeParameters();
#if IPLUG_EDITOR
  static constexpr int kEditorTag = 100;
  void ConfigureEditor();
  void HandleEditorMessage(const char* text);
  std::array<bool, 128> mEditorNotes{};
  bool mEditorSustain = false;
  bool mEditorBend = false;
#endif
  std::unique_ptr<segrand::InstrumentEngine> mEngine;
  std::string mError;
  bool mPrepared = true;
};
