#include "KrosePlugin.h"
#include "FactoryPrograms.h"
#include "IPlug_include_in_plug_src.h"
#include "ResourcePath.h"
#include <cstdlib>
#include <cstring>

KrosePlugin::KrosePlugin(const InstanceInfo &info)
    : Plugin(info, MakeConfig(kNumParams, segrand::kInstrumentProgramCount + 2)) {
#if defined(APP_API)
  mStandaloneHost = info.pAppHost;
#endif
  InitializeParameters();
  InitializeMidiMappings();
  RestoreMidiProfile();
  mNotifiedMapRevision.store(mMidiMap.Revision());
  mHardwarePrograms.fill(-1);
  try {
    const auto resources = krose::SampleDirectory(krose::ResourceDirectory(GetBundleID()));
    auto concert = segrand::SampleBank::Load((resources / "SEGrand.samples").u8string(), false);
    auto programs =
        segrand::ProgramLibrary::Load((resources / "Factory.samples").u8string(), false);
    for (unsigned i = 0; i < programs->programs.size(); ++i) {
      const char *id = programs->programs[i].id.data();
      int bank = -1, number = -1;
      if (id[0] >= 'A' && id[0] <= 'F' && id[1] >= '0' && id[1] <= '9') {
        bank = id[0] - 'A';
        number = std::atoi(id + 1);
      } else if (id[0] == 'G' && id[1] >= '0' && id[1] <= '9') {
        bank = 6;
        number = std::atoi(id + 1) - 1;
      } else if (std::strncmp(id, "EXPCM001:", 9) == 0) {
        bank = 7;
        number = std::atoi(id + 9);
      } else if (std::strncmp(id, "EXPCM002:", 9) == 0) {
        bank = 8;
        number = std::atoi(id + 9);
      } else if (std::strncmp(id, "EXPCM004:", 9) == 0) {
        bank = 9;
        number = std::atoi(id + 9);
      }
      if (bank >= 0 && number >= 0 && number < 128)
        mHardwarePrograms[bank * 128 + number] = int(i) + 1;
    }
    mEngine = std::make_unique<segrand::InstrumentEngine>(std::move(concert), std::move(programs));
  } catch (const std::exception &error) {
    mError = error.what();
  }
#if IPLUG_EDITOR
  // iPlug2 defines its platform graphics factory in this translation unit.
  mMakeGraphicsFunc = [this]() {
    return MakeGraphics(*this, PLUG_WIDTH, PLUG_HEIGHT, PLUG_FPS,
                        EditorDrawScale(mEditorScale));
  };
  ConfigureEditor();
#endif
}
float KrosePlugin::EditorDrawScale(int percentage) const {
#if IPLUG_EDITOR
  return percentage > 0 ? percentage/100.f : GetScaleForScreen(PLUG_WIDTH,PLUG_HEIGHT);
#else
  return percentage > 0 ? percentage/100.f : 1.f;
#endif
}

void KrosePlugin::OnParamChange(int paramIdx, EParamSource source, int) {
  if (paramIdx == kFxEditorRequest) HandleFxEditorParameter(source);
  if (paramIdx == kParamProgram) SelectProgramDefaults();
}
void KrosePlugin::RequestFxEditor(unsigned slot) noexcept {
  if (slot >= 4) return;
  mFxEditorRequest.store(int(slot),std::memory_order_release);
  mHardwareParameter.store(kFxType1+int(slot),std::memory_order_relaxed);
}
void KrosePlugin::HandleFxEditorParameter(EParamSource source) {
  const int code=GetParam(kFxEditorRequest)->Int();
  const int previous=mLastFxEditorCode.exchange(code,std::memory_order_relaxed);
  if (source==kReset || source==kPresetRecall ||
      uint32_t(mSoundGeneration.load(std::memory_order_acquire))) {
    mFxEditorRequest.store(-1,std::memory_order_release);
    return;
  }
  if (code!=previous) RequestFxEditor(unsigned(code)%4);
}
void KrosePlugin::SelectProgramDefaults() {
  if (!mEngine) return;
  const int program = GetParam(kParamProgram)->Int();
  mEngine->RequestProgram(program);
  if (uint32_t(mSoundGeneration.load(std::memory_order_acquire))) {
    mDefaultsProgram.store(program, std::memory_order_release);
    return; // A saved sound owns its FX, ARP and Tone Adjust values.
  }
  if (mDefaultsProgram.exchange(program, std::memory_order_acq_rel) != program)
    LoadFactoryEffects(program);
}

#if IPLUG_DSP
void KrosePlugin::OnReset() {
  if (!mEngine)
    return;
  try {
    mEngine->Prepare(GetSampleRate());
    const double rate = GetSampleRate();
    mAudioRate.store(rate, std::memory_order_relaxed);
    mVisualRate.store(rate, std::memory_order_relaxed);
    mIncomingMidi.Clear();
    mKeyboard.Reset();
#if defined(VST3_API)
    ClearHostParameters();
#endif
    mInputControls.Reset();
    mMidiMap.ResetRuntime();
    mMidiClock.Reset();
#if defined(APP_API)
    mArturiaFxButtons.Reset();
    mFxButtonProgram=-1;
#endif
    mSwitchAssign.fill(-1);
    mInputSamples = 0;
    mInputFilter = -1;
    mProgramBank = {};
    mPrepared = true;
  } catch (const std::exception &) {
    mPrepared = false;
    mEngine->Panic();
  }
}

void KrosePlugin::ProcessMidiMsg(const IMidiMsg &msg) {
  if (mEngine && mPrepared)
    mIncomingMidi.Push({msg.mOffset, msg.mStatus, msg.mData1, msg.mData2}, false);
}

#endif
