#include "KrosePlugin.h"
#include "IPlug_include_in_plug_src.h"
#include "FactoryPrograms.h"
#include "IPlugPaths.h"
#include <algorithm>
#include <array>

KrosePlugin::KrosePlugin(const InstanceInfo& info)
    : Plugin(info, MakeConfig(kNumParams, segrand::kInstrumentProgramCount + 2)) {
  InitializeParameters();
  try {
    WDL_String path;
    BundleResourcePath(path, GetBundleID());
    path.Append("/SEGrand.samples");
    auto concert = segrand::SampleBank::Load(path.Get());
    BundleResourcePath(path, GetBundleID());
    path.Append("/Factory.samples");
    auto programs = segrand::ProgramLibrary::Load(path.Get());
    mEngine = std::make_unique<segrand::InstrumentEngine>(std::move(concert), std::move(programs));
  } catch (const std::exception& error) {
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

#if IPLUG_DSP
void KrosePlugin::OnReset() {
  if (!mEngine)
    return;
  try {
    mEngine->Prepare(GetSampleRate());
    mPrepared = true;
  } catch (const std::exception&) {
    mPrepared = false;
    mEngine->Panic();
  }
}

void KrosePlugin::ProcessMidiMsg(const IMidiMsg& msg) {
  if (mEngine && mPrepared)
    mEngine->Queue({msg.mOffset, msg.mStatus, msg.mData1, msg.mData2});
}

void KrosePlugin::ProcessBlock(sample**, sample** outputs, int nFrames) {
  const int channels = NOutChansConnected();
  if (!mEngine || !mPrepared) {
    for (int ch = 0; ch < channels; ++ch)
      std::fill(outputs[ch], outputs[ch] + nFrames, sample(0));
    return;
  }

  segrand::Controls controls;
  controls.voiceMode = GetParam(kVoiceMode)->Int();
  controls.glide = GetParam(kGlide)->Int();
  controls.program = GetParam(kParamProgram)->Int();
  controls.preset = GetParam(kParamTone)->Int();
  controls.outputDb = GetParam(kParamOutput)->Value();
  controls.space = GetParam(kParamSpace)->Value() / 100;
  controls.releaseSeconds = GetParam(kParamRelease)->Value() / 1000;
  controls.velocityCurve = GetParam(kParamVelocity)->Value();
  controls.pan = GetParam(kParamPan)->Int();
  controls.cutoff = GetParam(kParamCutoff)->Int();
  controls.resonance = GetParam(kParamResonance)->Int();
  auto envelope = [this](int first) {
    return segrand::EnvelopeOffsets{GetParam(first)->Int(), GetParam(first + 1)->Int(),
                                   GetParam(first + 2)->Int(), GetParam(first + 3)->Int()};
  };
  controls.ampEg = envelope(kAmpAttack);
  controls.filterEg = envelope(kFilterAttack);
  mEngine->SetControls(controls);
  segrand::ArpControls arp;
  arp.enabled=GetParam(kArpEnabled)->Bool();arp.latch=GetParam(kArpLatch)->Bool();
  arp.pattern=GetParam(kArpPattern)->Int();arp.resolution=GetParam(kArpResolution)->Int();
  arp.gate=GetParam(kArpGate)->Int();arp.hostSync=GetParam(kArpHostSync)->Bool();
  arp.tempo=GetParam(kArpTempo)->Value();arp.octaves=GetParam(kArpOctaves)->Int();
  arp.sort=GetParam(kArpSort)->Bool();arp.keySync=GetParam(kArpKeySync)->Bool();
  mEngine->SetArpeggiator(arp);
  segrand::Transport transport;
#if defined(VST3_API)
  // iPlug2 marks sample position valid when VST3 supplies musical position.
  transport.available=GetSamplePos()!=-1. && GetTempo()>0;
  transport.running=GetTransportIsRunning();transport.tempo=GetTempo();transport.ppq=GetPPQPos();
#endif
  mEngine->SetTransport(transport);
  mDisplayTempo.store(mEngine->Tempo(),std::memory_order_relaxed);
  mDisplayHost.store(arp.hostSync&&transport.available,std::memory_order_relaxed);

  // Fixed stack buffers support arbitrary host block lengths without allocation.
  std::array<float, 256> left, right;
  for (int start = 0; start < nFrames; start += 256) {
    const int count = std::min(256, nFrames - start);
    mEngine->Process(left.data(), right.data(), count);
    if (channels > 0)
      for (int n = 0; n < count; ++n)
        outputs[0][start + n] = sample(left[n]);
    if (channels > 1)
      for (int n = 0; n < count; ++n)
        outputs[1][start + n] = sample(right[n]);
    for (int ch = 2; ch < channels; ++ch)
      std::fill(outputs[ch] + start, outputs[ch] + start + count, sample(0));
  }
}
#endif
