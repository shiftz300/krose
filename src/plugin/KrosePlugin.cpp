#include "KrosePlugin.h"
#include "FactoryPrograms.h"
#include "IPlug_include_in_plug_src.h"
#include "ResourcePath.h"
#include "storage/ExpansionLoader.h"
#include <cstdlib>
#include <cstring>

KrosePlugin::KrosePlugin(const InstanceInfo &info)
    : Plugin(info, MakeConfig(kNumParams, segrand::kInstrumentProgramCount + 2)) {
#if defined(APP_API)
  mStandaloneHost = info.pAppHost;
#endif
  InitializeParameters();
  mHardwarePrograms.fill(-1);
  try {
    const auto resources = krose::ResourceDirectory(GetBundleID());
    const auto samples = krose::SampleDirectory(resources);
    mDefaultOasys = krose::DefaultOasysPath(resources, samples);
    WDL_String support;
    iplug::AppSupportPath(support);
    if (support.GetLength())
      mExpansionDirectory = std::filesystem::u8path(support.Get()) / "Krose" / "Expansions";
#ifdef _WIN32
    if (const auto *directory = _wgetenv(L"KROSE_EXPANSION_DIRECTORY"))
      mExpansionDirectory = std::filesystem::path(directory);
#else
    if (const auto *directory = std::getenv("KROSE_EXPANSION_DIRECTORY"))
      mExpansionDirectory = std::filesystem::u8path(directory);
#endif
    segrand::ExpansionPaths expansions;
    if (!mExpansionDirectory.empty())
      expansions = krose::storage::ExpansionLoader(mExpansionDirectory, mDefaultOasys).Sources();
    else
      expansions[1] = mDefaultOasys.u8string();
    auto programs = segrand::ProgramLibrary::Load((samples / "Factory.samples").u8string(),
                                                  false, expansions);
    auto concert = segrand::SampleBank::Load((samples / "SEGrand.samples").u8string(),
                                            false, programs);
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
    mEngine = std::make_unique<segrand::InstrumentEngine>(std::move(concert), programs);
    mProgramLibrary = std::move(programs);
    if (!ProgramAvailable(0))
      GetParam(kParamProgram)->SetDefault(1); // A000 Kross Grand Piano 1.
  } catch (const std::exception &error) {
    mError = error.what();
  }
  InitializeMidiMappings();
  RestoreMidiProfile();
  mNotifiedMapRevision.store(mMidiMap.Revision());
#if IPLUG_EDITOR
  // iPlug2 defines its platform graphics factory in this translation unit.
  mMakeGraphicsFunc = [this]() {
    return MakeGraphics(*this, PLUG_WIDTH, PLUG_HEIGHT, PLUG_FPS,
                        EditorDrawScale(mEditorScale));
  };
  ConfigureEditor();
#endif
}
bool KrosePlugin::ProgramAvailable(int program) const noexcept {
  if (!mProgramLibrary) return true; // Preserve metadata when reporting a broken core library.
  if (program == 0) return mProgramLibrary->HasExpansion(1);
  if (program < 0 || size_t(program) > mProgramLibrary->programs.size()) return false;
  return mProgramLibrary->HasExpansion(
      segrand::ProgramExpansion(mProgramLibrary->programs[program - 1].id.data()));
}
bool KrosePlugin::CanManageExpansions() const noexcept {
  return mProgramLibrary && mProgramLibrary->Split() && !mExpansionDirectory.empty();
}
bool KrosePlugin::ExpansionAvailable(unsigned number) const noexcept {
  return mProgramLibrary && mProgramLibrary->HasExpansion(number);
}
bool KrosePlugin::ExpansionInstalled(unsigned number) const {
  auto loader = krose::storage::ExpansionLoader(mExpansionDirectory, mDefaultOasys);
  for (const auto &pack : krose::storage::kExpansions)
    if (pack.number == number) return loader.Installed(pack);
  return false;
}
unsigned KrosePlugin::InstallExpansion(const char *path) {
  if (!CanManageExpansions()) throw std::runtime_error("EXPANSION LOADER UNAVAILABLE");
  return krose::storage::ExpansionLoader(mExpansionDirectory, mDefaultOasys)
      .Install(std::filesystem::u8path(path), *mProgramLibrary);
}
void KrosePlugin::UninstallExpansion(unsigned number) {
  if (!CanManageExpansions()) throw std::runtime_error("EXPANSION LOADER UNAVAILABLE");
  auto loader = krose::storage::ExpansionLoader(mExpansionDirectory, mDefaultOasys);
  for (const auto &pack : krose::storage::kExpansions)
    if (pack.number == number) loader.Uninstall(pack);
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
