#pragma once

#include "IPlug_include_in_plug_hdr.h"
#include "Parameters.h"
#include "engine/InstrumentEngine.h"
#include "midi/ControllerMap.h"
#include "midi/InputControls.h"
#include "midi/KeyboardMonitor.h"
#include "midi/KeyLabControls.h"
#include <array>
#include <atomic>
#include <memory>
#include <string>
#include <vector>

using namespace iplug;
using namespace igraphics;
namespace krose::standalone { class ArturiaController; }

class KrosePlugin final : public Plugin {
public:
  explicit KrosePlugin(const InstanceInfo &info);
#if defined(VST3_API)
  Steinberg::tresult PLUGIN_API setParamNormalized(Steinberg::Vst::ParamID tag,
                                                 Steinberg::Vst::ParamValue value) override;
  Steinberg::uint32 PLUGIN_API getProcessContextRequirements() override {
    return kNeedProjectTimeMusic | kNeedTempo | kNeedTransportState;
  }
#endif
  void OnParamChange(int paramIdx, EParamSource source, int sampleOffset = -1) override;
  int UnserializeState(const IByteChunk &chunk, int startPos) override;
  bool SerializeState(IByteChunk &chunk) const override;
  static constexpr unsigned kTargetNext = kNumMidiParameters, kTargetPrevious = kNumMidiParameters + 1,
                            kTargetPanic = kNumMidiParameters + 2, kMapTargets = kNumParams + 3;
  static_assert(kMapTargets <= 256, "MIDI target encoding uses eight bits");
  krose::midi::ControllerMap &MidiMappings() noexcept { return mMidiMap; }
  unsigned MidiProfile() const noexcept { return mMidiProfile.load(); }
  bool LoadMidiProfile(unsigned profile);
  bool StoreMidiProfile(unsigned profile);
  struct ControllerProfileFile { std::string name, path; bool builtin, valid = true; };
  std::vector<ControllerProfileFile> ControllerProfileFiles() const;
  std::string ControllerSupportFolder(bool builtin) const;
  bool ImportControllerProfile(const std::string& path);
  bool ExportControllerProfile();
  bool MidiSettingsError() const noexcept { return mMidiSettingsError; }
  bool ArturiaEnabled() const noexcept { return mArturiaEnabled; }
  bool SetArturiaEnabled(bool enabled);
  std::string ArturiaStatus() const;
  void RequestFxEditor(unsigned slot) noexcept;
  int EditorScalePercent() const noexcept { return mEditorScale; }
  float EditorDrawScale(int percentage) const;
  bool SetEditorScalePercent(int percentage);
  unsigned AudioBufferSize() const;
  bool SetAudioBufferSize(unsigned frames);
  std::vector<std::string> AudioChoices(int kind);
  std::string AudioChoice(int kind);
  bool SelectAudioChoice(int kind, const std::string &value);
  void StandardMidiMappings();
  void CaptureComparison();
  void ToggleComparison();
  bool Comparing() const { return mComparing; }
  bool ComparisonReady() const { return mComparisonReady; }
  bool SaveUserPreset(const std::string &path);
  bool LoadUserPreset(const std::string &path);
  std::array<uint64_t, 2> KeyboardKeys() const noexcept { return mKeyboard.Read(); }
  std::array<uint64_t, 3> MidiExpression() const noexcept { return mKeyboard.Expression(); }
  segrand::ProgramEffects FactoryEffects() const noexcept {
    return mEngine ? mEngine->FactoryEffects(GetParam(kParamProgram)->Int()) : segrand::ProgramEffects{};
  }
  void RestoreFactoryArp();
  void EnableVisuals(bool enabled) noexcept { mVisualsEnabled.store(enabled, std::memory_order_relaxed); }
  unsigned ReadFxVisual(unsigned slot, segrand::FxVisualSample *data, unsigned capacity) noexcept {
    return mEngine ? mEngine->ReadVisual(slot, data, capacity) : 0;
  }
  double AudioRate() const noexcept { return mAudioRate.load(std::memory_order_relaxed); }
  double VisualRate() const noexcept { return mVisualRate.load(std::memory_order_relaxed); }
  float TakeOutputPeak() noexcept { return mOutputPeak.exchange(0, std::memory_order_relaxed); }
  float TakeOutputReduction() noexcept { return mOutputReduction.exchange(0, std::memory_order_relaxed); }
  float TakeFxPeak(unsigned slot) noexcept { return mFxPeaks[slot].exchange(0, std::memory_order_relaxed); }

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
#if defined(OS_WIN) && defined(APP_API)
  void OnUIOpen() override;
#endif
  void OnUIClose() override;
  void OnParamChangeUI(int paramIdx, EParamSource source = kUnknown) override;
#endif

private:
  void PollArturia();
  void HandleFxEditorParameter(EParamSource source);
  std::atomic<int> mFxEditorRequest{-1};
  std::atomic<int> mLastFxEditorCode{0};
  bool mArturiaEnabled = true;
  int mEditorScale = 0; // Auto-fit until the user explicitly chooses a size.
  std::atomic<int> mHardwareParameter{-1};
  std::atomic<bool> mHardwareControlTouched{false};
#if defined(APP_API)
  std::shared_ptr<krose::standalone::ArturiaController> mArturia;
  void *mStandaloneHost = nullptr;
  std::atomic<bool> mArturiaConnected{false};
  krose::midi::essential::Pickup mArturiaPickup;
  krose::midi::essential::FxButtonPresses mArturiaFxButtons;
  int mFxButtonProgram = -1;
  std::array<bool, 2> mArturiaHeld{};
  int mPickupProgram = -1;
  int mPickupEG = -1;
  int mHardwareProgram = -1;
  double mHardwareNextUpdate = 0;
#endif
  krose::midi::KeyboardMonitor mKeyboard;
  void SelectProgramDefaults();
  void LoadFactoryEffects(int program);
  std::atomic<int> mDefaultsProgram{0};
  void ApplySound(const std::array<double, kNumParams> &values);
  std::array<double, kNumParams> mComparison{};
  bool mComparisonReady = false, mComparing = false;
  std::atomic<bool> mComparisonNeedsCapture{false};
  std::atomic<uint64_t> mSoundGeneration{0};
  std::atomic<bool> mVisualsEnabled{false};
  std::atomic<double> mVisualRate{48000}, mAudioRate{48000};
  std::atomic<float> mOutputPeak{0}, mOutputReduction{0};
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
  std::array<std::atomic<uint64_t>, (kNumParams + 63) / 64> mMidiChangedParams{};
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
  std::array<std::atomic<float>, 2> mFxPeaks{};
};
