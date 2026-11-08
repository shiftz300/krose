#include "../KrosePlugin.h"
#include "native/NativePanel.h"
#if defined(OS_WIN) && defined(APP_API)
#include "../resources/resource.h"
#include <windows.h>
#endif
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
void KrosePlugin::OnParamChangeUI(int id, EParamSource source) {
  if (id == kFxEditorRequest) HandleFxEditorParameter(source);
  if (source == kUI) mHardwareParameter.store(id, std::memory_order_relaxed);
  // VST3 controller/state changes can arrive while processing is suspended.
  if (id == kParamProgram) SelectProgramDefaults();
  if (id == kParamProgram && source != kUI)
    mComparisonNeedsCapture.store(true, std::memory_order_relaxed);
  if (GetUI())
    GetUI()->SetAllControlsDirty();
}
void KrosePlugin::OnIdle() {
  PollArturia();
  if (mComparisonNeedsCapture.exchange(false, std::memory_order_relaxed))
    CaptureComparison();
#if defined(VST3_API)
  const unsigned revision = mMidiMap.Revision();
  if (mNotifiedMapRevision.exchange(revision) != revision)
    setDirty(true);
#endif
  for (unsigned word = 0; word < mMidiChangedParams.size(); ++word) {
    const uint64_t changed = mMidiChangedParams[word].exchange(0, std::memory_order_acq_rel);
    for (unsigned bit = 0; bit < 64 && word * 64 + bit < kNumParams; ++bit)
      if (changed & (uint64_t(1) << bit)) {
        const int id = int(word * 64 + bit);
        const double value = GetParam(id)->GetNormalized();
#if defined(VST3_API)
        // MIDI changes the DSP's IParam directly. Keep VST3's separate
        // controller cache synchronized before notifying the host/editor.
        SetVST3ParamNormalized(id, value);
#endif
        BeginInformHostOfParamChange(id);
        InformHostOfParamChange(id, value);
        EndInformHostOfParamChange(id);
        SendParameterValueFromDelegate(id, value, true);
      }
  }
  if (!GetUI())
    return;
  auto *p = static_cast<krose::ui::NativePanel *>(GetUI()->GetControlWithTag(kEditorTag));
  if (p) {
    const int slot=mFxEditorRequest.exchange(-1,std::memory_order_acq_rel);
    if (slot>=0) p->OpenFxEditor(unsigned(slot));
  }
  if (p)
    p->Refresh(mDisplayTempo.load(std::memory_order_relaxed),
               mDisplayHost.load(std::memory_order_relaxed),
               mEngine && !mEngine->SamplesReady(GetParam(kParamProgram)->Int()),
               mEngine && GetParam(kParamProgram)->Int() == mEngine->FailedProgram());
}
#if defined(OS_WIN) && defined(APP_API)
void KrosePlugin::OnUIOpen() {
  Plugin::OnUIOpen();
  if (!GetUI())
    return;
  const HWND window = GetAncestor(static_cast<HWND>(GetUI()->GetWindow()), GA_ROOT);
  if (!window)
    return;
  // The standalone owns the top-level window; never change a DAW's window icon.
  const HINSTANCE instance = GetModuleHandleW(nullptr);
  for (int iconSize = 0; iconSize < 2; ++iconSize) {
    const auto icon = LoadImageW(instance, MAKEINTRESOURCEW(IDI_ICON1), IMAGE_ICON,
                                GetSystemMetrics(iconSize ? SM_CXSMICON : SM_CXICON),
                                GetSystemMetrics(iconSize ? SM_CYSMICON : SM_CYICON), LR_SHARED);
    if (icon)
      SendMessageW(window, WM_SETICON, iconSize ? ICON_SMALL : ICON_BIG,
                   reinterpret_cast<LPARAM>(icon));
  }
}
#endif
void KrosePlugin::OnUIClose() {
  EnableVisuals(false);
  if (GetUI()) {
    auto *p = static_cast<krose::ui::NativePanel *>(GetUI()->GetControlWithTag(kEditorTag));
    if (p)
      p->ReleaseHeld();
  }
  Plugin::OnUIClose();
}
#endif
