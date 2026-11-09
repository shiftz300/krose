// Project-owned adaptations of the pinned iPlug2 APP host. Included in the
// generated host translation unit, never in the VST3 build.
#include <string_view>
#include "standalone/MidiDevices.h"
#include "standalone/AudioSettings.h"
bool IPlugAPPHost::SetAudioBufferSize(unsigned frames) {
  if (mNoIO || IsScreenshotMode() || !mDAC || !mDAC->isStreamRunning() ||
      !krose::standalone::ValidBufferSize(frames)) return false;
  if (frames == mBufferSize) return true;
  const auto previous = mState.mBufferSize;
  mState.mBufferSize = frames;
  if (TryToChangeAudio()) {
    mState.mBufferSize = mBufferSize; // Show/persist the driver's accepted size.
    UpdateINI();
    return true;
  }
  mState.mBufferSize = previous;
  TryToChangeAudio(); // Restore the working configuration after a rejected size.
  return false;
}
bool IPlugAPPHost::SelectMIDIDevice(ERoute direction, const char *name) {
  if ((direction == ERoute::kInput && !mMidiIn) || (direction == ERoute::kOutput && !mMidiOut))
    return false;
  const bool missing = mMidiInputMissing;
  try {
    if (direction == ERoute::kInput && std::string_view(name) == krose::standalone::kAutomaticMidi) {
      PollMidi();
      return true;
    }
    const bool selected = SelectMIDIDeviceImpl(direction, name);
    if (direction == ERoute::kInput && selected)
      mActiveMidiInput = std::string_view(name) == OFF_TEXT ? "" : name;
    return selected;
  } catch (const RtMidiError &) {
    if (direction == ERoute::kInput) {
      if (!missing) mRuntime.CancelMidi();
      mMidiInputMissing = true;
    }
    return false;
  }
}

bool IPlugAPPHost::TryToChangeAudio() {
  if (mNoIO || IsScreenshotMode())
    return true;
  mRuntime.RequestRecovery();
  PollAudio();
  return mDAC && mDAC->isStreamRunning();
}

void IPlugAPPHost::CloseAudio() {
  mAudioReady.store(false, std::memory_order_release);
  mAudioEnding = true;
  if (mDAC && mDAC->isStreamOpen()) {
    if (mDAC->isStreamRunning()) {
      const auto deadline = krose::standalone::Runtime::Now() + .1;
      while (!mAudioDone && krose::standalone::Runtime::Now() < deadline)
        Sleep(1);
      mDAC->abortStream();
    }
    mDAC->closeStream();
  }
  mRuntime.Reset();
}

void IPlugAPPHost::PollAudio() {
  if (mExiting || mNoIO || IsScreenshotMode() || !mDAC)
    return;
  const bool running = mDAC->isStreamRunning();
  bool recover = mRuntime.NeedsRecovery(krose::standalone::Runtime::Now(), running);
  if (!recover && mFallbackOutput) {
    auto preferred = GetAudioDeviceID(mState.mAudioOutDev.Get());
    recover = preferred && *preferred != mRecoveryOutput;
  }
  if (!recover)
    return;
  CloseAudio();
  ProbeAudioIO();
  auto preferred = GetAudioDeviceID(mState.mAudioOutDev.Get());
  auto output = preferred ? preferred : mDefaultOutputDev;
  if (!output)
    return; // Retry on the main-thread timer, without modal dialogs.
  auto input = GetAudioDeviceID(mState.mAudioInDev.Get());
  if (!input)
    input = mDefaultInputDev;
  if (GetPlug()->MaxNChannels(ERoute::kInput) && !input)
    return;
  const auto info = mDAC->getDeviceInfo(*output);
  auto rate = mState.mAudioSR;
  const auto supported = [&](unsigned candidate) {
    return candidate >= 32000 && candidate <= 192000 &&
           std::find(info.sampleRates.begin(), info.sampleRates.end(), candidate) != info.sampleRates.end();
  };
  if (!supported(rate)) {
    auto usable = std::find_if(info.sampleRates.begin(), info.sampleRates.end(),
                               [](unsigned r) { return r >= 32000 && r <= 192000; });
    if (usable == info.sampleRates.end())
      return;
    rate = supported(info.preferredSampleRate) ? info.preferredSampleRate : *usable;
  }
  if (InitAudio(input.value_or(0), *output, rate, mState.mBufferSize)) {
    mRecoveryOutput = *output;
    mFallbackOutput = !preferred;
  }
}

void IPlugAPPHost::PollMidi() {
  if (mExiting || mNoIO || IsScreenshotMode() || !mMidiIn)
    return;
  try {
    std::vector<std::string> ports;
    for (unsigned i = 0; i < mMidiIn->getPortCount(); ++i)
      ports.push_back(mMidiIn->getPortName(i));
    if (ports != mMidiPorts) {
      mMidiPorts = ports;
      mMidiListDirty = true;
      ProbeMidiIO();
    }
    RefreshMidiPreferences();
    const std::string preferred = mState.mMidiInDev.Get();
    const auto desired = preferred == "virtual input" ? preferred :
        krose::standalone::ChooseMidiInput(preferred, mActiveMidiInput, ports);
    if (desired.empty()) {
      if (mMidiIn->isPortOpen()) {
        mMidiIn->closePort();
        mRuntime.CancelMidi();
      }
      mActiveMidiInput.clear();
      mMidiInputMissing = preferred != OFF_TEXT;
    } else if (desired != mActiveMidiInput || mMidiInputMissing || !mMidiIn->isPortOpen()) {
      if (SelectMIDIDeviceImpl(ERoute::kInput, desired.c_str()))
        mActiveMidiInput = desired;
    }
  } catch (const RtMidiError &) {
    if (!mMidiInputMissing) mRuntime.CancelMidi();
    mActiveMidiInput.clear();
    mMidiInputMissing = true; // Keep the saved preference and retry next tick.
  }
}

int IPlugAPPHost::AudioCallback(void *output, void *input, uint32_t frames, double,
                               RtAudioStreamStatus, void *context) {
  auto &host = *static_cast<IPlugAPPHost *>(context);
  const int inputs = host.GetPlug()->MaxNChannels(ERoute::kInput);
  const int outputs = host.GetPlug()->MaxNChannels(ERoute::kOutput);
  auto *in = static_cast<double *>(input);
  auto *out = static_cast<double *>(output);
  if (!out || !frames)
    return 0;
  if (host.mExiting || host.mAudioDone || !host.mAudioReady.load(std::memory_order_acquire)) {
    std::fill(out, out + size_t(outputs) * frames, 0.);
    if (host.mAudioEnding) host.mAudioDone = true;
    return 0;
  }
  host.mRuntime.BeginAudio(frames, host.mSampleRate, krose::standalone::Runtime::Now());
  // Scratch buffers are preallocated for this maximum in InitAudio. AppProcess
  // receives the actual slice length, including 32/64/96 and odd final slices.
  for (unsigned start = 0; start < frames; start += APP_SIGNAL_VECTOR_SIZE) {
    const auto count = std::min<unsigned>(APP_SIGNAL_VECTOR_SIZE, frames - start);
    for (int ch = 0; ch < inputs; ++ch)
      host.mInputBufPtrs.Set(ch, in ? in + size_t(ch) * frames + start : nullptr);
    for (int ch = 0; ch < outputs; ++ch)
      host.mOutputBufPtrs.Set(ch, out + size_t(ch) * frames + start);
    host.mRuntime.DrainMidi(start, count, [&](int offset, uint8_t status, uint8_t d1, uint8_t d2) {
      IMidiMsg message(offset, status, d1, d2);
      host.mIPlug->DispatchTimedMidi(message);
    });
    host.mIPlug->AppProcess(host.mInputBufPtrs.GetList(), host.mOutputBufPtrs.GetList(), count);
  }
  for (size_t i = 0; i < size_t(outputs) * frames; ++i)
    out[i] *= APP_MULT;
  if (host.mVecWait++ == 0 || host.mAudioEnding)
    ApplyFades(out, outputs, frames, host.mAudioEnding);
  if (host.mAudioEnding)
    host.mAudioDone = true;
  return 0;
}

void IPlugAPPHost::MIDICallback(double delta, std::vector<uint8_t> *message, void *context) {
  auto &host = *static_cast<IPlugAPPHost *>(context);
  if (!message || message->empty() || host.mExiting)
    return;
  if (message->size() > 3) {
    if (message->size() < MAX_SYSEX_SIZE) {
      SysExData data{0, int(message->size()), message->data()};
      host.mIPlug->mSysExMsgsFromCallback.Push(data);
    }
    return;
  }
  host.mRuntime.PushMidi(delta, krose::standalone::Runtime::Now(), (*message)[0],
                        message->size() > 1 ? (*message)[1] : 0,
                        message->size() > 2 ? (*message)[2] : 0);
}

void IPlugAPPHost::ErrorCallback(RtAudioErrorType type, const std::string &) {
  // Driver callbacks only publish a flag. Closing/reopening a driver and all
  // allocations stay on the main thread, including after sleep or removal.
  if (type != RTAUDIO_WARNING && sInstance && !sInstance->mExiting)
    sInstance->mRuntime.RequestRecovery();
}
