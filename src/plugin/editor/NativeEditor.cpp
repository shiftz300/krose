#include "../KrosePlugin.h"
#include "native/NativePanel.h"
#if IPLUG_EDITOR
void KrosePlugin::ConfigureEditor() {
  mLayoutFunc = [this](IGraphics *graphics) {
    graphics->AttachPanelBackground(IColor(255, 16, 18, 22));
    graphics->AttachControl(new krose::ui::NativePanel(), kEditorTag);
    graphics->EnableMouseOver(true);
    graphics->SetKeyHandlerFunc([graphics](const IKeyPress &key, bool up) {
      auto *panel = graphics->GetControlWithTag(kEditorTag);
      return panel && (up ? panel->OnKeyUp(0, 0, key) : panel->OnKeyDown(0, 0, key));
    });
  };
}
void KrosePlugin::OnParamChangeUI(int id, EParamSource) {
  // VST3 controller/state changes can arrive while processing is suspended.
  if (id == kParamProgram && mEngine)
    mEngine->RequestProgram(GetParam(id)->Int());
  if (GetUI())
    GetUI()->SetAllControlsDirty();
}
void KrosePlugin::OnIdle() {
  if (!GetUI())
    return;
  auto *p = static_cast<krose::ui::NativePanel *>(GetUI()->GetControlWithTag(kEditorTag));
  if (p)
    p->Refresh(mDisplayTempo.load(std::memory_order_relaxed),
               mDisplayHost.load(std::memory_order_relaxed),
               mEngine && !mEngine->SamplesReady(GetParam(kParamProgram)->Int()),
               mEngine && GetParam(kParamProgram)->Int() == mEngine->FailedProgram());
}
void KrosePlugin::OnUIClose() {
  if (GetUI()) {
    auto *p = static_cast<krose::ui::NativePanel *>(GetUI()->GetControlWithTag(kEditorTag));
    if (p)
      p->ReleaseHeld();
  }
  Plugin::OnUIClose();
}
#endif
