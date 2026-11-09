#include "../KrosePlugin.h"
#include "KeyLabParameters.h"
#if defined(APP_API)
#include "../standalone/ArturiaController.h"
#include "IPlugAPP_host.h"
#include "ControllerPrograms.h"
#endif

std::string KrosePlugin::ArturiaStatus() const {
#if defined(APP_API)
  if (!mArturiaEnabled) return "ARTURIA: OFF";
  return mArturia && mArturia->status != "ARTURIA: OFF" ? mArturia->status : "ARTURIA: SELECT KEYLAB MK3 MIDI";
#else
  return "ARTURIA: ABLETON REMOTE SCRIPT";
#endif
}
void KrosePlugin::PollArturia() {
#if defined(APP_API)
  if (std::getenv("KROSE_NO_HARDWARE_FEEDBACK")) return;
  if (!mArturia) mArturia = std::make_shared<krose::standalone::ArturiaController>();
  using namespace krose::midi::essential;
  const double now = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
  auto *host = static_cast<iplug::IPlugAPPHost *>(mStandaloneHost);
  const bool selected = host && PortScore(host->ActiveMidiInput()) > 0;
  const bool connected = mArturia->Poll(mArturiaEnabled && selected, now);
  mArturiaConnected.store(connected, std::memory_order_relaxed);
  if (!connected) return;
  if (now < mHardwareNextUpdate) return;
  mHardwareNextUpdate = now + .1;
  const bool touched = mHardwareControlTouched.exchange(false, std::memory_order_relaxed);
  if (touched) mArturia->feedback.ControlTouched(now);
  const bool filterEG = GetParam(kEGTarget)->Bool();
  for (unsigned i = 0; i < 18; ++i) {
    const unsigned index = i < 8 ? i : i < 16 ? i - 8 : 8;
    const bool knob = i < 8 || i == 16;
    const int id = knob ? kKnobControls[index].parameter : FaderParameter(index, filterEG);
    if (id < 0) {
      mArturia->feedback.Control(i,"Unassigned","--");
      continue;
    }
    const auto *p = GetParam(id);
    WDL_String value;
    p->GetDisplay(value);
    std::string text = value.Get();
    if (*p->GetLabel()) text += " " + std::string(p->GetLabel());
    mArturia->feedback.Control(i, knob ? kKnobControls[index].label : ParameterLabel(p->GetName()), text);
  }
  const int program = GetParam(kParamProgram)->Int();
  const int focus = mHardwareParameter.exchange(-1, std::memory_order_relaxed);
  if (program != mHardwareProgram) {
    WDL_String name;
    GetParam(kParamProgram)->GetDisplay(name);
    std::string context = "PROG";
    if (program >= 0 && program < int(kProgramContext.size()))
      context = std::string(kProgramContext[program].id) + " " + std::string(kProgramContext[program].category);
    mArturia->feedback.Program(name.Get(), context, program >= 0 && program < int(kProgramContext.size()) ?
        CategoryIcon(kProgramContext[program].category) : 0x18);
    mHardwareProgram = program;
  } else if (!touched && focus >= 0 && focus < kNumParams && focus != kParamProgram) {
    WDL_String value;
    auto *parameter = GetParam(focus);
    parameter->GetDisplay(value);
    std::string text = value.Get();
    if (IsFxTypeParameter(focus)) {
      const unsigned slot=unsigned(focus-kFxType1);
      const bool concert=program==0;
      const int type=segrand::ResolveFxType(parameter->Int(),slot,concert,
          concert && GetParam(kParamTone)->Int()==2);
      text=slot<2 ? segrand::kInsertTypes[type] : segrand::kSendTypes[type];
    }
    if (*parameter->GetLabel()) text += " " + std::string(parameter->GetLabel());
    mArturia->feedback.Parameter(parameter->GetName(), text, now);
  }
  std::array<bool, 8> state{};
  std::array<RGB,4> fxColours{};
  for (unsigned i = 0; i < state.size(); ++i) {
    state[i] = GetParam(kPadParameters[i])->Bool();
    if (i >= 2 && i < 6) {
      const unsigned slot = i - 2;
      const bool concert = program == 0;
      const int type = segrand::ResolveFxType(GetParam(kFxType1 + slot)->Int(), slot, concert,
                                             concert && GetParam(kParamTone)->Int() == 2);
      state[i] = state[i] && !GetParam(kFXBypass)->Bool() && type > 1;
      fxColours[slot]=EffectColour(unsigned(segrand::FxAlgorithm(type,slot)),state[i]);
    }
  }
  mArturia->feedback.FxButtons(fxColours);
  mArturia->Update(now, state);
#endif
}
