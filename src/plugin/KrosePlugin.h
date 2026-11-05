#pragma once

#include "IPlug_include_in_plug_hdr.h"
#include "Parameters.h"
#include "engine/InstrumentEngine.h"
#include "midi/ControllerMap.h"
#include "midi/InputControls.h"
#include <array>
#include <atomic>
#include <memory>
#include <string>
#include <vector>

using namespace iplug;
using namespace igraphics;

class KrosePlugin final : public Plugin {
public:
  explicit KrosePlugin(const InstanceInfo &info);
#if defined(VST3_API)
  Steinberg::uint32 PLUGIN_API getProcessContextRequirements() override {
    return kNeedProjectTimeMusic | kNeedTempo | kNeedTransportState;
  }
#endif
  void OnParamChange(int paramIdx, EParamSource source, int sampleOffset = -1) override;
  int UnserializeState(const IByteChunk &chunk, int startPos) override;
  bool SerializeState(IByteChunk &chunk) const override;
  static constexpr unsigned kTargetNext = kNumParams, kTargetPrevious = kNumParams + 1,
                            kTargetPanic = kNumParams + 2, kMapTargets = kNumParams + 3;
  krose::midi::ControllerMap &MidiMappings() noexcept { return mMidiMap; }
  unsigned MidiProfile() const noexcept { return mMidiProfile.load(); }
  bool LoadMidiProfile(unsigned profile);
  bool StoreMidiProfile(unsigned profile);
  bool MidiSettingsError() const noexcept { return mMidiSettingsError; }
  void StandardMidiMappings();

#if IPLUG_DSP
  void ProcessBlock(sample **inputs, sample **outputs, int nFrames) override;
  void ProcessMidiMsg(const IMidiMsg &msg) override;
  void OnReset() override;
#if defined(VST3_API)
  void QueueHostParameter(int id, double value, int offset, int frames);
  void FlushHostParameters();
#endif
#endif
#if IPLUG_EDITOR
  void OnIdle() override;
  void OnUIClose() override;
  void OnParamChangeUI(int paramIdx, EParamSource source = kUnknown) override;
#endif

private:
  void InitializeParameters();
  void InitializeMidiMappings();
  void ConfigureAudio(int offset);
  template <class RenderTo>
  void HandleControllerMidi(krose::midi::Message message, const int &position, RenderTo renderTo);
  void SetMidiParameter(unsigned id, double normalized);
  void ApplySwitches();
  void RestoreMidiProfile();
#if IPLUG_EDITOR
  static constexpr int kEditorTag = 100;
  void ConfigureEditor();
#endif
  std::unique_ptr<segrand::InstrumentEngine> mEngine;
  krose::midi::ControllerMap mMidiMap{kMapTargets};
  krose::midi::InputControls mInputControls;
  krose::midi::MidiClock mMidiClock;
  segrand::EventQueue<2048> mIncomingMidi;
#if defined(VST3_API) && IPLUG_DSP
  struct HostParameter {
    int offset = -1, id = 0;
    double value = 0;
  };
  void ApplyHostParameter(const HostParameter &parameter);
  void SortHostParameters();
  void ClearHostParameters() noexcept;
  std::array<HostParameter, 2048> mHostParameters{};
  unsigned mHostParameterCount = 0;
  bool mHostParameterOverflow = false;
#endif
  std::array<std::array<uint8_t, 2>, 16> mProgramBank{};
  std::array<int, 128 * 12> mHardwarePrograms{};
  std::atomic<uint64_t> mMidiChangedParams{0};
  std::atomic<unsigned> mMidiProfile{0};
  std::array<int, 2> mSwitchAssign{{-1, -1}};
  std::array<bool, 2> mSwitchState{};
  uint64_t mInputSamples = 0;
  int mInputFilter = -1;
  bool mMidiSettingsError = false;
  std::atomic<unsigned> mNotifiedMapRevision{0};
  std::vector<int> mNextPrograms, mPreviousPrograms;
  std::string mError;
  bool mPrepared = true;
  std::atomic<double> mDisplayTempo{120.};
  std::atomic<bool> mDisplayHost{false};
};
