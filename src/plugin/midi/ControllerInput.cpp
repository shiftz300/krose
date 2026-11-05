#include "../KrosePlugin.h"
#include <algorithm>
using namespace krose::midi;
void KrosePlugin::SetMidiParameter(unsigned id, double normalized) {
  if (id >= kNumParams) {
    if (normalized < .5)
      return;
    const unsigned program = unsigned(GetParam(kParamProgram)->Int());
    if (id == kTargetNext && program < mNextPrograms.size())
      SetMidiParameter(kParamProgram,
                       GetParam(kParamProgram)->ToNormalized(mNextPrograms[program]));
    if (id == kTargetPrevious && program < mPreviousPrograms.size())
      SetMidiParameter(kParamProgram,
                       GetParam(kParamProgram)->ToNormalized(mPreviousPrograms[program]));
    if (id == kTargetPanic && mEngine) {
      mEngine->Panic();
      mInputControls.Reset();
      mSwitchAssign.fill(-1);
    }
    return;
  }
  auto *p = GetParam(id);
  const double before = p->GetNormalized();
  p->SetNormalized(std::clamp(normalized, 0., 1.));
  if (p->GetNormalized() == before)
    return;
  OnParamChange(id, kDelegate, 0);
  mMidiChangedParams.fetch_or(uint64_t(1) << id, std::memory_order_release);
}
void KrosePlugin::ApplySwitches() {
  auto setAction = [&](SwitchAssignment a, bool state) {
    int id = a == SwitchAssignment::Arp        ? kArpEnabled
             : a == SwitchAssignment::Latch    ? kArpLatch
             : a == SwitchAssignment::FXBypass ? kFXBypass
                                               : -1;
    if (id >= 0)
      SetMidiParameter(id, state ? 1 : 0);
    if (a == SwitchAssignment::MonoLegato)
      SetMidiParameter(kVoiceMode, GetParam(kVoiceMode)->ToNormalized(state ? 2 : 1));
  };
  for (unsigned sw = 0; sw < 2; ++sw) {
    const int first = kSW1Assign + int(sw) * 3, assignment = GetParam(first)->Int();
    const bool state = GetParam(first + 2)->Bool();
    if (mSwitchAssign[sw] == assignment && mSwitchState[sw] == state)
      continue;
    const int old = mSwitchAssign[sw];
    mSwitchAssign[sw] = assignment;
    mSwitchState[sw] = state;
    mInputControls.Configure(sw, SwitchAssignment(assignment), state,
                             [&](Message m) { mEngine->Queue({0, m.status, m.data1, m.data2}); });
    if (old >= 0 && old != assignment)
      setAction(SwitchAssignment(old), mInputControls.Active(SwitchAssignment(old)));
    setAction(SwitchAssignment(assignment), mInputControls.Active(SwitchAssignment(assignment)));
  }
}
void KrosePlugin::HandleControllerMidi(Message m) {
  const unsigned type = m.status & 240, ch = m.status & 15;
  mMidiClock.Process(m, mInputSamples + uint64_t(m.offset), GetSampleRate());
  const int filter = GetParam(kInputChannel)->Int();
  if (type < 0xf0 && filter && filter != int(ch + 1))
    return;
  const bool consumed = mMidiMap.Process(
      m,
      [&](unsigned target) { return target < kNumParams ? GetParam(target)->GetNormalized() : 0.; },
      [&](unsigned target, double value) { SetMidiParameter(target, value); });
  if (consumed) {
    if ((type == 0x80 || (type == 0x90 && !m.data2)) && mInputControls.HasHeld(ch, m.data1 & 127)) {
      m.offset = 0;
      mInputControls.Process(
          m, [&](Message event) { mEngine->Queue({0, event.status, event.data1, event.data2}); });
    }
    return;
  }
  if (type == 0xb0 && (m.data1 == 0 || m.data1 == 32))
    mProgramBank[ch][m.data1 == 0 ? 0 : 1] = m.data2 & 127;
  if (type == 0xc0 && GetParam(kProgramChange)->Int()) {
    int program = -1;
    if (GetParam(kProgramChange)->Int() == 1)
      program = ((mProgramBank[ch][0] * 128 + mProgramBank[ch][1]) * 128) + (m.data1 & 127);
    else if (!mProgramBank[ch][1] && mProgramBank[ch][0] < 12)
      program = mHardwarePrograms[mProgramBank[ch][0] * 128 + (m.data1 & 127)];
    if (program >= 0 && program <= GetParam(kParamProgram)->GetMax())
      SetMidiParameter(kParamProgram, GetParam(kParamProgram)->ToNormalized(program));
    return;
  }
  m.offset = 0;
  mInputControls.Process(
      m, [&](Message event) { mEngine->Queue({0, event.status, event.data1, event.data2}); });
}
void KrosePlugin::ConfigureAudio(int offset) {
  mMidiMap.Synchronize([&](unsigned target, double value) { SetMidiParameter(target, value); });
  ApplySwitches();
  const int filter = GetParam(kInputChannel)->Int();
  if (mInputFilter != filter) {
    if (mInputFilter >= 0) {
      mEngine->Panic();
      mInputControls.Reset();
      mSwitchAssign.fill(-1);
      ApplySwitches();
    }
    mInputFilter = filter;
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
  controls.fxBypass = GetParam(kFXBypass)->Bool();
  auto envelope = [&](int first) {
    return segrand::EnvelopeOffsets{GetParam(first)->Int(), GetParam(first + 1)->Int(),
                                    GetParam(first + 2)->Int(), GetParam(first + 3)->Int()};
  };
  controls.ampEg = envelope(kAmpAttack);
  controls.filterEg = envelope(kFilterAttack);
  mEngine->SetControls(controls, GetRenderingOffline());
  segrand::ArpControls arp;
  arp.enabled = GetParam(kArpEnabled)->Bool();
  arp.latch = GetParam(kArpLatch)->Bool();
  arp.pattern = GetParam(kArpPattern)->Int();
  arp.resolution = GetParam(kArpResolution)->Int();
  arp.gate = GetParam(kArpGate)->Int();
  arp.hostSync = GetParam(kArpHostSync)->Bool() && GetParam(kClockSource)->Int() != 1;
  arp.tempo = GetParam(kArpTempo)->Value();
  arp.octaves = GetParam(kArpOctaves)->Int();
  arp.sort = GetParam(kArpSort)->Bool();
  arp.keySync = GetParam(kArpKeySync)->Bool();
  segrand::Transport transport;
#if defined(APP_API)
  if (GetParam(kClockSource)->Int() == 2 && GetParam(kArpHostSync)->Bool()) {
    arp.hostSync = true;
    transport.available = true;
    const uint64_t at = mInputSamples + uint64_t(offset);
    transport.running = mMidiClock.Running(at, GetSampleRate());
    transport.tempo = mMidiClock.Tempo(GetSampleRate(), arp.tempo);
    transport.ppq = mMidiClock.Beat(at);
  } else
#endif
  {
#if defined(VST3_API)
    transport.available = GetSamplePos() != -1. && GetTempo() > 0;
    transport.running = GetTransportIsRunning();
    transport.tempo = GetTempo();
    transport.ppq = GetPPQPos() + offset * GetTempo() / (60 * GetSampleRate());
#endif
  }
  mEngine->SetArpeggiator(arp);
  mEngine->SetTransport(transport);
  mDisplayTempo.store(mEngine->Tempo(), std::memory_order_relaxed);
  mDisplayHost.store(arp.hostSync && transport.available, std::memory_order_relaxed);
}
