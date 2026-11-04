#include "../KrosePlugin.h"
#include "native/NativePanel.h"
#if IPLUG_EDITOR
namespace {
// The composite panel treats double-clicks as ordinary presses, retaining
// iPlug's mouse capture for keys and wheels. Only knobs/faders use reset-on-double-
// click. A non-drawing input control routes those hits through iPlug's existing
// double-click handling; modal menus take priority in the panel's hit list.
class ParameterInput final : public IControl {
public:
  explicit ParameterInput(krose::ui::NativePanel &panel)
      : IControl(panel.GetRECT()), mPanel(panel) {}
  void Draw(IGraphics &) override {}
  bool IsHit(float x, float y) const override { return mPanel.IsParameterHit(x, y); }
  void OnMouseDown(float x, float y, const IMouseMod &m) override { mPanel.OnMouseDown(x, y, m); }
  void OnMouseDrag(float x, float y, float dx, float dy, const IMouseMod &m) override {
    mPanel.OnMouseDrag(x, y, dx, dy, m);
  }
  void OnMouseUp(float x, float y, const IMouseMod &m) override { mPanel.OnMouseUp(x, y, m); }
  void OnMouseDblClick(float x, float y, const IMouseMod &m) override {
    mPanel.OnMouseDblClick(x, y, m);
  }
  void OnMouseOver(float x, float y, const IMouseMod &m) override { mPanel.OnMouseOver(x, y, m); }
  void OnMouseOut() override { mPanel.OnMouseOut(); }
  void OnMouseWheel(float x, float y, const IMouseMod &m, float d) override {
    mPanel.OnMouseWheel(x, y, m, d);
  }

private:
  krose::ui::NativePanel &mPanel;
};
} // namespace
void KrosePlugin::ConfigureEditor() {
  mLayoutFunc = [this](IGraphics *graphics) {
    graphics->AttachPanelBackground(IColor(255, 16, 18, 22));
    auto *panel = new krose::ui::NativePanel();
    graphics->AttachControl(panel, kEditorTag);
    graphics->AttachControl(new ParameterInput(*panel));
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
