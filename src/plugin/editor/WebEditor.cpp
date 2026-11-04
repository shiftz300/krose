#include "../KrosePlugin.h"

#if IPLUG_EDITOR
#include "IControls.h"
#include "IPlugPaths.h"
#include "IWebViewControl.h"
#include "json.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iterator>

namespace {
class KroseEditor final : public IWebViewControl {
public:
  using IWebViewControl::IWebViewControl;
  void OnWebContentLoaded() override {
    IWebViewControl::OnWebContentLoaded();
    EvaluateJavaScript("window.IPlugSendMsg({type:'ready'})");
  }
};
} // namespace

void KrosePlugin::ConfigureEditor() {
  mLayoutFunc = [this](IGraphics* graphics) {
    graphics->AttachPanelBackground(IColor(255, 16, 18, 22));
    graphics->AttachControl(new KroseEditor(
        graphics->GetBounds(), true,
        [this](IWebViewControl* web) {
          WDL_String path;
          BundleResourcePath(path, GetBundleID());
          path.Append("/editor.html");
          std::ifstream input(path.Get(), std::ios::binary);
          std::string html((std::istreambuf_iterator<char>(input)), {});
          web->LoadHTML(html.empty() ? "<p>Krose editor resource unavailable</p>" : html.c_str());
        },
        [this](IWebViewControl*, const char* json) { HandleEditorMessage(json); }), kEditorTag);
  };
}

void KrosePlugin::OnParamChangeUI(int id, EParamSource) {
  if (!GetUI() || id < 0 || id >= kNumParams)
    return;
  auto* web = static_cast<IWebViewControl*>(GetUI()->GetControlWithTag(kEditorTag));
  if (!web)
    return;
  nlohmann::json args = {GetParam(id)->GetName(), id, GetParam(id)->Value()};
  auto script = "window.kroseNative?.receive(..." + args.dump() + ")";
  web->EvaluateJavaScript(script.c_str());
}

void KrosePlugin::OnIdle() {
  const double tempo=mDisplayTempo.load(std::memory_order_relaxed);
  const bool host=mDisplayHost.load(std::memory_order_relaxed);
  if(!GetUI()||(std::abs(tempo-mLastDisplayTempo)<.005&&host==mLastDisplayHost))return;
  auto* web=static_cast<IWebViewControl*>(GetUI()->GetControlWithTag(kEditorTag));
  if(!web)return;
  mLastDisplayTempo=tempo;mLastDisplayHost=host;
  auto script="window.kroseNative?.tempo?.("+std::to_string(tempo)+","+(host?"true":"false")+")";
  web->EvaluateJavaScript(script.c_str());
}
void KrosePlugin::OnUIClose() {
  mLastDisplayTempo=-1;
  for (int note = 0; note < 128; ++note)
    if (mEditorNotes[note])
      SendMidiMsgFromUI(IMidiMsg(0, 0x80, note, 0));
  mEditorNotes.fill(false);
  if (mEditorSustain)
    SendMidiMsgFromUI(IMidiMsg(0, 0xb0, 64, 0));
  if (mEditorBend)
    SendMidiMsgFromUI(IMidiMsg(0, 0xe0, 0, 64));
  mEditorSustain = mEditorBend = false;
  Plugin::OnUIClose();
}

void KrosePlugin::HandleEditorMessage(const char* text) {
  const auto message = nlohmann::json::parse(text, nullptr, false);
  if (!message.is_object())
    return;
  const auto type = message.find("type");
  if (type == message.end() || !type->is_string())
    return;
  if (*type == "ready") {
    mLastDisplayTempo=-1;
    for (int id = 0; id < kNumParams; ++id)
      OnParamChangeUI(id);
    return;
  }
  auto integer = [&](const char* key, int limit) {
    auto value = message.find(key);
    return value != message.end() && value->is_number_integer() && *value >= 0 && *value <= limit
               ? value->get<int>() : -1;
  };
  if (*type == "midi") {
    const int status = integer("status", 239);
    const int a = integer("data1", 127), b = integer("data2", 127);
    if (status < 128 || a < 0 || b < 0)
      return;
    if (status == 0x90 || status == 0x80)
      mEditorNotes[a] = status == 0x90 && b > 0;
    if (status == 0xb0 && a == 64)
      mEditorSustain = b >= 64;
    if (status == 0xe0)
      mEditorBend = a != 0 || b != 64;
    SendMidiMsgFromUI(IMidiMsg(0, status, a, b));
    return;
  }
  const int id = integer("id", kNumParams - 1);
  if (id < 0)
    return;
  if (*type == "begin")
    BeginInformHostOfParamChangeFromUI(id);
  if (*type == "end")
    EndInformHostOfParamChangeFromUI(id);
  if (*type == "set" && message.contains("value") && message["value"].is_number()) {
    const double value = message["value"];
    auto* param = GetParam(id);
    if (std::isfinite(value))
      SendParameterValueFromUI(id, param->ToNormalized(std::clamp(value, param->GetMin(), param->GetMax())));
  }
}
#endif
