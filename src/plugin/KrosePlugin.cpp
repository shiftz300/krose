#include "KrosePlugin.h"
#include "FactoryPrograms.h"
#include "IPlug_include_in_plug_src.h"
#include "ResourcePath.h"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <cstring>

KrosePlugin::KrosePlugin(const InstanceInfo &info)
    : Plugin(info, MakeConfig(kNumParams, segrand::kInstrumentProgramCount + 2)) {
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
                        GetScaleForScreen(PLUG_WIDTH, PLUG_HEIGHT));
  };
  ConfigureEditor();
#endif
}

void KrosePlugin::OnParamChange(int paramIdx, EParamSource, int) {
  if (paramIdx == kParamProgram && mEngine)
    mEngine->RequestProgram(GetParam(kParamProgram)->Int());
}
#if IPLUG_DSP
void KrosePlugin::OnReset() {
  if (!mEngine)
    return;
  try {
    mEngine->Prepare(GetSampleRate());
    mIncomingMidi.Clear();
    mInputControls.Reset();
    mMidiMap.ResetRuntime();
    mMidiClock.Reset();
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

void KrosePlugin::ProcessBlock(sample **, sample **outputs, int nFrames) {
  const int channels = NOutChansConnected();
  if (!mEngine || !mPrepared) {
    for (int ch = 0; ch < channels; ++ch)
      std::fill(outputs[ch], outputs[ch] + nFrames, sample(0));
    return;
  }

  if (mIncomingMidi.Overflowed()) {
    mEngine->Panic();
    mIncomingMidi.Clear();
    mInputControls.Reset();
    mSwitchAssign.fill(-1);
  }
  const unsigned count = mIncomingMidi.ReadyCount(nFrames);
  ConfigureAudio(0);
  std::array<float, 256> left{}, right{};
  auto render = [&](int first, int frames) {
    for (int start = first; start < first + frames; start += 256) {
      const int n = std::min(256, first + frames - start);
      mEngine->Process(left.data(), right.data(), n);
      for (int ch = 0; ch < channels; ++ch)
        for (int i = 0; i < n; ++i)
          outputs[ch][start + i] = ch == 0   ? sample(left[i])
                                   : ch == 1 ? sample(right[i])
                                             : sample(0);
    }
  };
  int position = 0;
  for (unsigned i = 0; i < count; ++i) {
    const auto &event = mIncomingMidi[i];
    if (event.offset > position)
      render(position, event.offset - position);
    position = event.offset;
    HandleControllerMidi({event.offset, event.status, event.data1, event.data2});
    ConfigureAudio(position);
  }
  if (position < nFrames)
    render(position, nFrames - position);
  mIncomingMidi.Advance(count, nFrames);
  mInputSamples += uint64_t(nFrames);
}
#endif
