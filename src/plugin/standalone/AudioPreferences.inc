#ifdef OS_WIN
#include "asio.h"
#endif
// APP-only audio settings shared by the LCD and platform preferences.
std::vector<std::string> IPlugAPPHost::AudioChoices(int kind) {
  std::vector<std::string> result;
  if (mNoIO || ((kind == 1 || kind == 2) && !mDAC)) return result;
  if (kind == 0) {
#ifdef OS_WIN
    return {"WASAPI", "ASIO"};
#else
    return {"CoreAudio"};
#endif
  }
  if (kind == 3) {
    result = {krose::standalone::kAutomaticMidi, OFF_TEXT};
    if (mMidiIn) for (unsigned i=0; i<mMidiIn->getPortCount(); ++i) result.push_back(mMidiIn->getPortName(i));
    return result;
  }
  if (kind == 4) {
    result = {OFF_TEXT};
    if (mMidiOut) for (unsigned i=0; i<mMidiOut->getPortCount(); ++i) result.push_back(mMidiOut->getPortName(i));
    return result;
  }
  if (kind == 5) {
#ifdef OS_WIN
    if (mState.mAudioDriverType == kDeviceASIO) return {"ASIO PANEL"};
#endif
    return result;
  }
  if (kind == 1) {
    ProbeAudioIO();
    for (auto id : mAudioOutputDevIDs) result.push_back(GetAudioDeviceName(id));
  } else if (kind == 2) {
    auto id = GetAudioDeviceID(mState.mAudioOutDev.Get());
    if (!id) id = mDefaultOutputDev;
    if (id) for (auto rate : mDAC->getDeviceInfo(*id).sampleRates)
      if (rate >= 32000 && rate <= 192000) result.push_back(std::to_string(rate));
  }
  return result;
}
std::string IPlugAPPHost::AudioChoice(int kind) {
  if (kind == 0) {
#ifdef OS_WIN
    return mState.mAudioDriverType == kDeviceASIO ? "ASIO" : "WASAPI";
#else
    return "CoreAudio";
#endif
  }
  if (kind == 1) return mState.mAudioOutDev.Get();
  if (kind == 3) return mState.mMidiInDev.Get();
  if (kind == 4) return mState.mMidiOutDev.Get();
  return std::to_string(mState.mAudioSR);
}
bool IPlugAPPHost::SelectAudioChoice(int kind, const std::string& value) {
  const auto choices = AudioChoices(kind);
  if (std::find(choices.begin(), choices.end(), value) == choices.end()) return false;
  if (kind == 5) {
#ifdef OS_WIN
    ASIOControlPanel();
#endif
    return true;
  }
  if (kind == 3 || kind == 4) {
    if (kind == 3) {
      mState.mMidiInDev.Set(value.c_str());
      PollMidi();
    } else {
      if (!SelectMIDIDevice(ERoute::kOutput, value.c_str())) return false;
      mState.mMidiOutDev.Set(value.c_str());
    }
    UpdateINI();
    return true;
  }
  const auto previous = mState;
  if (kind == 0) {
#ifdef OS_WIN
    mState.mAudioDriverType = value == "ASIO" ? kDeviceASIO : kDeviceDS;
#endif
    TryToChangeAudioDriverType();
  } else if (kind == 1) mState.mAudioOutDev.Set(value.c_str());
  else if (kind == 2) mState.mAudioSR = unsigned(std::stoul(value));
  if (TryToChangeAudio()) { UpdateINI(); return true; }
  mState = previous;
  if (kind == 0) TryToChangeAudioDriverType();
  TryToChangeAudio();
  return false;
}

extern "C" void KroseRequestAsioRecovery(void *context) {
  if (context) static_cast<IPlugAPPHost *>(context)->RequestAudioRecovery();
}
