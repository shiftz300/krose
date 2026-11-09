#include "../KrosePlugin.h"
#include "KeyLabEssential.h"
#include "KeyLabParameters.h"
#include <algorithm>
using namespace krose::midi;
#if defined(VST3_API)
Steinberg::tresult PLUGIN_API KrosePlugin::setParamNormalized(Steinberg::Vst::ParamID tag,
                                                            Steinberg::Vst::ParamValue value) {
  if (!std::isfinite(value))
    return Steinberg::kResultFalse;
  return Plugin::setParamNormalized(tag, std::clamp(value, 0., 1.));
}
#endif
void KrosePlugin::SetMidiParameter(unsigned id, double normalized) {
  if (!std::isfinite(normalized)) return;
  const int parameter = ParameterForMidiTarget(id);
  if (parameter < 0) {
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
      mKeyboard.Reset();
      mInputControls.Reset();
      mSwitchAssign.fill(-1);
    }
    return;
  }
  id = unsigned(parameter);
  auto *p = GetParam(id);
  const double before = p->GetNormalized();
  p->SetNormalized(std::clamp(normalized, 0., 1.));
  if (p->GetNormalized() == before)
    return;
  mHardwareParameter.store(int(id), std::memory_order_relaxed);
  if (id == kParamProgram)
    mComparisonNeedsCapture.store(true, std::memory_order_relaxed);
  OnParamChange(id, kDelegate, 0);
  mMidiChangedParams[id / 64].fetch_or(uint64_t(1) << (id % 64), std::memory_order_release);
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
                             [&](Message m) {
                               mKeyboard.Process(m.status, m.data1, m.data2);
                               mEngine->Queue({0, m.status, m.data1, m.data2});
                             });
    if (old >= 0 && old != assignment)
      setAction(SwitchAssignment(old), mInputControls.Active(SwitchAssignment(old)));
    setAction(SwitchAssignment(assignment), mInputControls.Active(SwitchAssignment(assignment)));
  }
}
template <class RenderTo>
void KrosePlugin::HandleControllerMidi(Message m, const int &position, RenderTo renderTo) {
  const unsigned type = m.status & 240, ch = m.status & 15;
  bool reconfigure = false;
#if defined(APP_API)
  if (type == 0xf0) {
    const bool clockEvent = m.status == 0xf2 || m.status == 0xf8 ||
                            (m.status >= 0xfa && m.status <= 0xfc);
    reconfigure = clockEvent && GetParam(kClockSource)->Int() == 2 &&
                  GetParam(kArpHostSync)->Bool();
    if (reconfigure)
      renderTo(m.offset);
    mMidiClock.Process(m, mInputSamples + uint64_t(m.offset), GetSampleRate());
  }
#endif
  // Only the standalone's selected, positively matched mk3 input can use this
  // map. VST3 delegates controller ownership to Live's remote script.
#if defined(APP_API)
  if (mArturiaConnected.load(std::memory_order_relaxed)) {
    using namespace krose::midi::essential;
    const auto control = Decode(m.status, m.data1);
    if (control.kind != Kind::None) {
      const int program = GetParam(kParamProgram)->Int();
      const bool filterEG = GetParam(kEGTarget)->Bool();
      if (program != mPickupProgram) { mArturiaPickup.Reset(); mPickupProgram = program; }
      if (int(filterEG) != mPickupEG) { mArturiaPickup.Reset(0,8); mPickupEG = int(filterEG); }
      auto set = [&](int id, double value) {
        renderTo(m.offset);
        SetMidiParameter(MidiTargetForParameter(id), value);
        ConfigureAudio(position);
      };
      if (control.kind == Kind::Knob) {
        mHardwareControlTouched.store(true, std::memory_order_relaxed);
        if (kKnobControls[control.index].parameter >= 0)
          set(kKnobControls[control.index].parameter, m.data2 / 127.);
      }
      if (control.kind == Kind::Fader) {
        mHardwareControlTouched.store(true, std::memory_order_relaxed);
        int id = FaderParameter(control.index, filterEG);
        const auto *p = GetParam(id);
        if (mArturiaPickup.Accept(control.index, m.data2 / 127., p->GetNormalized())) {
          set(id, m.data2 / 127.);
          mArturiaPickup.Applied(control.index, p->GetNormalized());
        }
      }
      if (control.kind == Kind::Program && Relative(m.data2)) {
        if (unsigned(program) < mNextPrograms.size())
          set(kParamProgram, GetParam(kParamProgram)->ToNormalized(Relative(m.data2) > 0 ? mNextPrograms[program] : mPreviousPrograms[program]));
      }
      if (control.kind == Kind::FxEdit) {
        if (mFxButtonProgram!=program) { mArturiaFxButtons.Reset(); mFxButtonProgram=program; }
        const auto action=mArturiaFxButtons.Input(control.index,m.data2!=0,
            (mInputSamples+uint64_t(m.offset))/GetSampleRate());
        if (action==FxPressAction::Edit) RequestFxEditor(control.index);
        if (action==FxPressAction::Toggle) {
          const unsigned slot=control.index;
          const bool concert=program==0;
          if (segrand::ResolveFxType(GetParam(kFxType1+slot)->Int(),slot,concert,
              concert && GetParam(kParamTone)->Int()==2)>1)
            set(kFxOn1+slot,GetParam(kFxOn1+slot)->Bool() ? 0 : 1);
        }
      }
      if (control.kind == Kind::Pad) {
        const int id = kPadParameters[control.index];
        const bool down = type == 0x90 && m.data2;
        if (control.index >= 6 && GetParam(id - 1)->Bool()) {
          mArturiaHeld[control.index - 6] = down;
          set(id, down ? 1 : 0);
        }
        else if (down) set(id, GetParam(id)->Bool() ? 0 : 1);
      }
      return;
    }
  }
#endif
  const int filter = GetParam(kInputChannel)->Int();
  if (type < 0xf0 && filter && filter != int(ch + 1))
    return;
  auto write = [&](unsigned target, double value) {
    renderTo(m.offset);
    SetMidiParameter(target, value);
    reconfigure = true;
  };
  auto emit = [&](Message event) {
    mKeyboard.Process(event.status, event.data1, event.data2);
    mEngine->Queue({event.offset - position, event.status, event.data1, event.data2});
  };
  const bool consumed = mMidiMap.Process(
      m,
      [&](unsigned target) {
        const int id = ParameterForMidiTarget(target);
        return id >= 0 ? GetParam(id)->GetNormalized() : 0.;
      },
      write);
  if (consumed) {
    if ((type == 0x80 || (type == 0x90 && !m.data2)) && mInputControls.HasHeld(ch, m.data1 & 127))
      mInputControls.Process(m, emit);
  } else if (type == 0xc0 && GetParam(kProgramChange)->Int()) {
    int program = -1;
    if (GetParam(kProgramChange)->Int() == 1)
      program = ((mProgramBank[ch][0] * 128 + mProgramBank[ch][1]) * 128) + (m.data1 & 127);
    else if (!mProgramBank[ch][1] && mProgramBank[ch][0] < 12)
      program = mHardwarePrograms[mProgramBank[ch][0] * 128 + (m.data1 & 127)];
    if (program >= 0 && program <= GetParam(kParamProgram)->GetMax())
      write(kParamProgram, GetParam(kParamProgram)->ToNormalized(program));
  } else if (type < 0xf0) {
    if (type == 0xb0 && (m.data1 == 0 || m.data1 == 32))
      mProgramBank[ch][m.data1 == 0 ? 0 : 1] = m.data2 & 127;
    mInputControls.Process(m, emit);
  }
  if (reconfigure)
    ConfigureAudio(position);
}
void KrosePlugin::ConfigureAudio(int offset) {
  const auto generation = mSoundGeneration.load(std::memory_order_acquire);
  if (uint32_t(generation)) return;
  mEngine->EnableMonitoring(mVisualsEnabled.load(std::memory_order_relaxed));
#if defined(APP_API)
  if (!mArturiaConnected.load(std::memory_order_relaxed))
    for (unsigned i = 0; i < mArturiaHeld.size(); ++i)
      if (mArturiaHeld[i]) {
        mArturiaHeld[i] = false;
        SetMidiParameter(MidiTargetForParameter(kSW1State + int(i) * 3), 0);
      }
#endif
  mMidiMap.Synchronize([&](unsigned target, double value) { SetMidiParameter(target, value); });
  ApplySwitches();
  const int filter = GetParam(kInputChannel)->Int();
  if (mInputFilter != filter) {
    if (mInputFilter >= 0) {
      mEngine->Panic();
      mKeyboard.Reset();
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
  controls.filterEgIntensity = GetParam(kFilterEGIntensity)->Int();
  controls.resonance = GetParam(kParamResonance)->Int();
  controls.fxBypass = GetParam(kFXBypass)->Bool();
  for (int i = 0; i < int(controls.fx.size()); ++i) {
    auto &slot = controls.fx[i];
    slot.type = GetParam(kFxType1 + i)->Int();
    slot.amount = GetParam(kFxAmount1 + i)->Value();
    slot.enabled = GetParam(kFxOn1 + i)->Bool();
    if (!slot.enabled || slot.type < 2)
      continue;
    const int first = 0, end = segrand::kFxDetailCount;
    for (int j = first; j < end; ++j)
      slot.detail[j] = GetParam(FxDetailParameter(i, j))->Value();
  }
  auto envelope = [&](int first) {
    return segrand::EnvelopeOffsets{GetParam(first)->Int(), GetParam(first + 1)->Int(),
                                    GetParam(first + 2)->Int(), GetParam(first + 3)->Int()};
  };
  controls.ampEg = envelope(kAmpAttack);
  controls.filterEg = envelope(kFilterAttack);
  segrand::ArpControls arp;
  arp.enabled = GetParam(kArpEnabled)->Bool();
  arp.latch = GetParam(kArpLatch)->Bool();
  arp.pattern = GetParam(kArpPattern)->Int();
  arp.swing = GetParam(kArpSwing)->Int();
  arp.velocity = GetParam(kArpVelocity)->Int();
  arp.keyboard = GetParam(kArpKeyboard)->Bool();
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
    transport.midiClock = true;
    transport.positionRevision = mMidiClock.PositionRevision();
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
  if (mSoundGeneration.load(std::memory_order_acquire) != generation) return;
  if (!mEngine->SetControls(controls, GetRenderingOffline())) return;
  mEngine->SetArpeggiator(arp);
  mEngine->SetTransport(transport);
  mDisplayTempo.store(mEngine->Tempo(), std::memory_order_relaxed);
  mDisplayHost.store(arp.hostSync && transport.available, std::memory_order_relaxed);
}

#if IPLUG_DSP
#if defined(VST3_API)
void KrosePlugin::ApplyHostParameter(const HostParameter &parameter) {
  GetParam(parameter.id)->SetNormalized(parameter.value);
  OnParamChange(parameter.id, kHost, parameter.offset);
}

void KrosePlugin::QueueHostParameter(int id, double value, int offset, int frames) {
  if (id < 0 || id >= kNumParams || !std::isfinite(value))
    return;
  value = std::clamp(value, 0., 1.);
  if (frames <= 0) {
    ApplyHostParameter({0, id, value});
    return;
  }
  const HostParameter parameter{std::clamp(offset, 0, frames - 1), id, value};
  if (!mHostParameterOverflow && mHostParameterCount == mHostParameters.size()) {
    // Keep the final point for every parameter when a host floods the queue.
    // All points for one parameter arrive in time order from its VST3 queue.
    std::array<HostParameter, kNumParams> last{};
    for (const auto &point : mHostParameters)
      last[point.id] = point;
    std::copy(last.begin(), last.end(), mHostParameters.begin());
    mHostParameterOverflow = true;
  }
  if (mHostParameterOverflow)
    mHostParameters[id] = parameter;
  else
    mHostParameters[mHostParameterCount++] = parameter;
}

void KrosePlugin::SortHostParameters() {
  auto begin = mHostParameters.begin();
  if (mHostParameterOverflow)
    mHostParameterCount = unsigned(std::remove_if(begin, begin + kNumParams,
        [](const HostParameter &point) { return point.offset < 0; }) - begin);
  std::sort(begin, begin + mHostParameterCount,
            [](const HostParameter &a, const HostParameter &b) { return a.offset == b.offset ? a.id < b.id : a.offset < b.offset; });
}

void KrosePlugin::ClearHostParameters() noexcept {
  mHostParameterCount = 0;
  mHostParameterOverflow = false;
}

void KrosePlugin::FlushHostParameters() {
  SortHostParameters();
  for (unsigned i = 0; i < mHostParameterCount; ++i)
    ApplyHostParameter(mHostParameters[i]);
  ClearHostParameters();
}
#endif

void KrosePlugin::ProcessBlock(sample **, sample **outputs, int nFrames) {
  if (nFrames <= 0 || !outputs)
    return;
  const int channels = NOutChansConnected();
  if (!mEngine || !mPrepared) {
#if defined(VST3_API)
    FlushHostParameters();
#endif
    for (int ch = 0; ch < channels; ++ch)
      std::fill(outputs[ch], outputs[ch] + nFrames, sample(0));
    return;
  }

  if (mIncomingMidi.Overflowed()) {
    mEngine->Panic();
    mKeyboard.Reset();
    mIncomingMidi.Clear();
    mInputControls.Reset();
    mSwitchAssign.fill(-1);
  }
  const unsigned count = mIncomingMidi.ReadyCount(nFrames);
  int position = 0;
  std::array<float, 256> left{}, right{};
  std::array<float, 2> fxPeaks{};
  float outputPeak = 0, outputReduction = 0;
  auto renderTo = [&](int end) {
    while (position < end) {
      const int n = std::min(256, end - position);
      mEngine->Process(left.data(), right.data(), n);
      outputPeak = std::max(outputPeak, mEngine->OutputPeak());
      outputReduction = std::max(outputReduction, mEngine->OutputReduction());
      const auto peaks = mEngine->FxPeaks();
      for (unsigned slot = 0; slot < peaks.size(); ++slot)
        fxPeaks[slot] = std::max(fxPeaks[slot], peaks[slot]);
      for (int ch = 0; ch < channels; ++ch)
        for (int i = 0; i < n; ++i)
          outputs[ch][position + i] = ch == 0   ? sample(left[i])
                                      : ch == 1 ? sample(right[i])
                                                : sample(0);
      position += n;
    }
  };
#if defined(VST3_API)
  SortHostParameters();
  unsigned parameter = 0;
  auto applyThrough = [&](int offset) {
    while (parameter < mHostParameterCount && mHostParameters[parameter].offset <= offset) {
      const int at = mHostParameters[parameter].offset;
      renderTo(at);
      do {
        ApplyHostParameter(mHostParameters[parameter++]);
      } while (parameter < mHostParameterCount && mHostParameters[parameter].offset == at);
      if (at > 0)
        ConfigureAudio(at);
    }
  };
  applyThrough(0);
#endif
#if defined(APP_API)
  const int fxProgram=GetParam(kParamProgram)->Int();
  if (!mArturiaConnected.load(std::memory_order_relaxed) || mFxButtonProgram!=fxProgram) {
    mArturiaFxButtons.Reset();mFxButtonProgram=fxProgram;
  }
  const unsigned fxHeld=mArturiaFxButtons.Tick(mInputSamples/GetSampleRate());
  for (unsigned slot=0;slot<4;++slot) if (fxHeld & (1u<<slot)) {
    const bool concert=fxProgram==0;
    if (segrand::ResolveFxType(GetParam(kFxType1+slot)->Int(),slot,concert,
        concert && GetParam(kParamTone)->Int()==2)>1) {
      const int id=kFxOn1+slot;
      SetMidiParameter(MidiTargetForParameter(id),GetParam(id)->Bool() ? 0 : 1);
    }
  }
#endif
  ConfigureAudio(0);
  for (unsigned i = 0; i < count; ++i) {
    const auto &event = mIncomingMidi[i];
#if defined(VST3_API)
    applyThrough(event.offset);
#endif
    HandleControllerMidi({event.offset, event.status, event.data1, event.data2}, position, renderTo);
  }
#if defined(VST3_API)
  applyThrough(nFrames - 1);
  ClearHostParameters();
#endif
  renderTo(nFrames);
  for (unsigned slot = 0; slot < fxPeaks.size(); ++slot) {
    // One audio writer and one UI reader. At most one bounded CAS per block;
    // a concurrent read simply defers this transient to the next block.
    auto previous = mFxPeaks[slot].load(std::memory_order_relaxed);
    if (fxPeaks[slot] > previous)
      mFxPeaks[slot].compare_exchange_strong(previous, fxPeaks[slot], std::memory_order_relaxed);
  }
  auto publish = [](std::atomic<float> &meter, float value) {
    auto old = meter.load(std::memory_order_relaxed);
    if (value > old) meter.compare_exchange_strong(old, value, std::memory_order_relaxed);
  };
  publish(mOutputPeak, outputPeak);
  publish(mOutputReduction, outputReduction);
  mKeyboard.Publish();
  mIncomingMidi.Advance(count, nFrames);
  mInputSamples += uint64_t(nFrames);
}
#endif
