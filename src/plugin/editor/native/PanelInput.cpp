#include "../../KrosePlugin.h"
#include "../../storage/PresetDialogWin.h"
#include "NativePanel.h"
#include "PanelDrawing.h"
namespace krose::ui {
using namespace detail;
void NativePanel::StepProgram(int delta) {
  const auto &order = mProgramOrder;
  if (order.empty())
    return;
  auto it = std::find(order.begin(), order.end(), int(Value(kParamProgram)));
  int n = int(it - order.begin());
  SetProgram(order[(n + delta + int(order.size())) % order.size()]);
}
void NativePanel::SetProgram(int i) {
  mPresetStatus.clear();
  Set(kParamProgram, i);
  static_cast<KrosePlugin *>(GetDelegate())->CaptureComparison();
  mPage = 0;
  mSlot = 0;
  mBrowsing = false;
  mPresetOpen = false;
  mEdit = -1;
}
void NativePanel::Note(int note, bool down) {
  if (note < 0 || note > 127)
    return;
  if (down && !mHeld[note]) {
    GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0x90, note, 100));
    mHeld[note] = mLit[note] = true;
  } else if (!down && mHeld[note]) {
    GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0x80, note, 0));
    mHeld[note] = false;
    if (!mSustain)
      mLit[note] = false;
  }
  SetDirty(false);
}
void NativePanel::ReleaseHeld() {
  mPointerDown = false;
  mNumericPending = mNumericDragging = false;
  ReleaseSwitches();
  static_cast<KrosePlugin *>(GetDelegate())->MidiMappings().CancelLearn();
  for (int i = 0; i < 128; ++i)
    Note(i, false);
  mLit.fill(false);
  mSustain = false;
  GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xb0, 64, 0));
  GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xe0, 0, 64));
  mPitch = mMod = 0;
  GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xb0, 1, 0));
  mParameters.End(*GetDelegate());
  mDrag = mDragNote = -1;
  SetDirty(false);
}
void NativePanel::FinishEdit() {
  if (mMapEdit >= 0) {
    auto &map = static_cast<KrosePlugin *>(GetDelegate())->MidiMappings();
    auto b = map.Get(mMapEdit);
    char *end = nullptr;
    const long n = std::strtol(mEditText.c_str(), &end, 10);
    if (end != mEditText.c_str() && *end == 0 && n >= 0 && n < 16384) {
      b.number = unsigned(n);
      if (b.Valid(KrosePlugin::kMapTargets))
        map.Set(mMapEdit, b);
      else
        mControllerStatus = "Number outside source range";
    }
    mMapEdit = -1;
  }
  if (mEdit >= 0) {
    char *end = nullptr;
    double v = std::strtod(mEditText.c_str(), &end);
    if (end != mEditText.c_str() && *end == 0 && std::isfinite(v))
      Set(mEdit, v);
  }
  mEdit = -1;
  mSelectAll = false;
  SetDirty(false);
}
void NativePanel::Activate(const Hit &h) {
  if (h.action == "update-open" || h.action == "update-later") {
    if (h.action == "update-open") GetUI()->OpenURL(krose::updates::kReleasePage);
    ShowUpdateNotice("");
    return;
  }
  if (h.action == "save" || h.action == "load") {
    PresetFile(h.action == "save");
  } else if (h.action == "compare") {
    static_cast<KrosePlugin *>(GetDelegate())->ToggleComparison();
  } else if (h.action == "scale" || h.action == "ui-scale") {
    OpenPopup(h);
  } else if (ControllerAction(h)) {
  } else if (h.action == "increment")
    Set(h.id, Value(h.id) + h.value * GetDelegate()->GetParam(h.id)->GetStep());
  else if (h.action == "toggle") {
    if (h.id == kArpHostSync && Value(kClockSource) == 1) {
      Set(kClockSource, 0);
      Set(kArpHostSync, 1);
    } else
      Set(h.id, Value(h.id) ? 0 : 1);
  } else if (h.action == "set")
    Set(h.id, h.value);
  else if (h.action == "eg")
    Set(kEGTarget, h.value);
  else if (h.action == "page") {
    mPage = int(h.value);
    mSlot = 0;
  } else if (h.action == "arp-edit") {
    OpenPopup({LCDRect(R(547,168,420,18)), "arp-edit"});
  } else if (h.action == "fx-toggle") {
    const int enabled = kFxOn1 + int(h.value);
    Set(enabled, Value(enabled) ? 0 : 1);
  } else if (h.action == "fx-module" || h.action == "fx-add") {
    mPage = 2;
    mSlot = int(h.value);
    mFxBand = 0;
    mControllers = false;
    if (h.action == "fx-add")
      OpenPopup({LCDRect(FxTypeField()), "field", kFxType1 + mSlot});
  } else if (h.action == "fx-band") {
    mFxBand = int(h.value);
  } else if (h.action == "step")
    StepProgram(int(h.value));
  else if (h.action == "fold") {
    mFold = !mFold;
    mFXMotion.Target(
        mFold,
        std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count());
  } else if (h.action == "browse") {
    OpenBrowser();
  } else if (h.action == "close") {
    mBrowsing = false;
    mEdit = -1;
  } else if (h.action == "program")
    SetProgram(int(h.value));
  else if (h.action == "presets") {
    OpenPresetMenu();
  } else if (h.action == "preset-category")
    PresetCategory(int(h.value));
  else if (h.action == "favorite") {
    if (mPresetOpen) {
      auto row = std::find(mPresetItems.begin(), mPresetItems.end(), int(h.value));
      if (row != mPresetItems.end())
        mPresetFocus = int(row - mPresetItems.begin());
      mPresetColumn = 1;
    }
    ToggleFavorite(int(h.value));
  } else if (h.action == "group" || h.action == "category")
    OpenPopup(h);
  else if (h.action == "dismiss") {
    mChoices.clear();
    mPresetOpen = false;
  } else if (h.action == "choice") {
    int v = int(h.value);
    auto target = mPopupTarget;
    // Device choices carry an index; preserve its label before dismissing the
    // popup. Numeric choices (buffer sizes, parameter values) keep using v.
    const std::string selected = v >= 0 && size_t(v) < mChoices.size() ? mChoices[v] : "";
    mChoices.clear();
    if (target.action == "arp-edit") {
      if (v == 0) OpenPopup({LCDRect(R(547,168,364,18)), "field", kArpPattern});
      else if (v == 1) static_cast<KrosePlugin *>(GetDelegate())->RestoreFactoryArp();
      else if (v == 2) Set(kArpKeyboard, !Value(kArpKeyboard));
    } else if (target.action == "arp-families") {
      mArpFamily = std::clamp(v, 0, int(mArpFamilies.size())-1);
      OpenPopup({LCDRect(R(547,168,364,18)), "arp-pattern-items", kArpPattern});
    } else if (target.action == "arp-pattern-items") {
      if (v < 0) OpenPopup({LCDRect(R(547,168,364,18)), "field", kArpPattern});
      else Set(kArpPattern, v);
    } else if (target.action == "scale" || target.action == "ui-scale") {
      auto *plugin = static_cast<KrosePlugin *>(GetDelegate());
      const float scale = plugin->EditorDrawScale(v);
#if defined(VST3_API)
      const float platform = GetUI()->GetPlatformWindowScale();
      if (!plugin->EditorResize(int(PLUG_WIDTH * scale * platform), int(PLUG_HEIGHT * scale * platform))) {
        mPresetStatus = "HOST DOES NOT ALLOW WINDOW RESIZE";
        mControllerStatus=mPresetStatus;
        SetDirty(false);
        return;
      }
#endif
      GetUI()->Resize(PLUG_WIDTH, PLUG_HEIGHT, scale);
      mControllerStatus=plugin->SetEditorScalePercent(v) ? "UI size applied and saved" : "UI size applied / SAVE FAILED";
    } else if (target.action == "group") {
      mGroup = v;
      FilterPrograms();
    } else if (target.action == "category") {
      mCategory = v;
      FilterPrograms();
    } else if (target.action == "midi-menu")
      ControllerChoice(target.id, v, selected);
    else {
      const bool adding = IsFxTypeParameter(target.id) && FxType(target.id - kFxType1) <= 1;
      Set(target.id, v);
      if (adding && FxType(target.id - kFxType1) > 1)
        Set(kFxOn1 + target.id - kFxType1, 1);
      if (target.id == kClockSource)
        Set(kArpHostSync, v != 1);
    }
  } else if (h.action == "search")
    mEdit = -2;
  else if (h.action == "octave") {
    ReleaseHeld();
    mOctave = std::clamp(mOctave + int(h.value), -2, 2);
  } else if (h.action == "sustain") {
    mSustain = !mSustain;
    GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xb0, 64, mSustain ? 127 : 0));
    if (!mSustain)
      for (int i = 0; i < 128; ++i)
        if (!mHeld[i])
          mLit[i] = false;
  } else if (h.action == "panic") {
    ReleaseHeld();
    for (int ch = 0; ch < 16; ++ch) {
      GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xb0 + ch, 64, 0));
      GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xb0 + ch, 120, 0));
    }
  } else if (h.action == "edit" || h.action == "field") {
    if (h.action == "field" &&
        (h.id == kParamTone || h.id == kArpPattern || h.id == kArpResolution || IsFxTypeParameter(h.id) ||
         (h.id >= kSW1Assign && h.id <= kClockSource))) {
      OpenPopup(h);
    } else {
      mEdit = h.id;
      mEditText = Format(Value(h.id), GetDelegate()->GetParam(h.id)->GetStep() < 1 ? 2 : 0);
      mSelectAll = true;
    }
  }
  SetDirty(false);
}
void NativePanel::OnMouseDown(float x, float y, const IMouseMod &mod) {
  mMouseX = x;
  mMouseY = y;
  mPointerDown = !mod.R;
  mPressedButton.clear();
  mKeyboardFocus = false;
  FinishEdit();
  for (int i = int(mHits.size()) - 1; i >= 0; --i) {
    auto h = mHits[i];
    if (!h.r.Contains(x, y))
      continue;
    mFocus = i;
    if (!mod.R) {
      mClickX = x; mClickY = y;
      mClickTime = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    if (mod.R && h.action == "fold") {
      OpenPopup({R(38, 57, 140, 30), "scale"});
      return;
    }
    const bool middle = !mod.L && !mod.R && !mod.IsTouch();
    if ((mod.R || middle) && (h.action == "fx-toggle" || h.action == "fx-add" || h.action == "fx-module")) {
      if (mod.R) {
        Activate({h.r, "fx-module", -1, h.value});
        return;
      }
      // OFF removes the module while retaining its amount and algorithm settings.
      // Empty slots ignore right-click; left-click opens their add menu.
      const int slot = int(h.value);
      if (FxType(slot) > 1)
        Set(kFxType1 + slot, 1);
      SetDirty(false);
      return;
    }
    if (middle) return;
    if (mod.R && h.id >= 0 && h.id < kNumParams &&
        (h.action == "knob" || h.action == "fader" || h.action == "field" || h.action == "toggle" ||
         h.action == "set" || h.action == "edit")) {
      BeginLearn(h.id);
      SetDirty(false);
      return;
    }
    if (mod.R && h.action == "switch") {
      mControllers = true;
      mControllerPage = 0;
      SetDirty(false);
      return;
    }
    const auto *parameter = h.id >= 0 && h.id < kNumParams ? GetDelegate()->GetParam(h.id) : nullptr;
    if (!mod.R && parameter && (h.action == "edit" || h.action == "field") &&
        parameter->Type() != IParam::kTypeEnum && parameter->Type() != IParam::kTypeBool) {
      mNumericPress = h;
      mNumericPending = true;
      mNumericDragging = false;
      mDragY = y;
      mDragValue = Value(h.id);
      return;
    }
    if (h.action == "knob" || h.action == "fader") {
      mDrag = h.id;
      mDragY = y;
      mDragValue = Value(h.id);
      mHover = h.action;
      mParameters.Begin(*GetDelegate(), h.id);
      if (h.action == "fader")
        Set(h.id, 99 - 198 * std::clamp((y - 132) / 135.f, 0.f, 1.f), false);
    } else if (h.action == "note") {
      mDragNote = h.id;
      Note(h.id, true);
    } else if (h.action == "mod") {
      mDrag = -3;
      mDragY = y;
      mDragValue = mMod;
    } else if (h.action == "pitch") {
      mDrag = -2;
      mDragY = y;
      mDragValue = mPitch;
    } else
      Activate(h);
    return;
  }
}
void NativePanel::OnMouseDrag(float, float y, float, float, const IMouseMod &mod) {
  if (mNumericPending && !mNumericDragging && std::abs(y - mDragY) >= 3) {
    mNumericDragging = true;
    mDrag = mNumericPress.id;
    mHover = "numeric";
    mEdit = -1;
    mParameters.Begin(*GetDelegate(), mDrag);
  }
  if (mDrag >= 0) {
    auto *p = GetDelegate()->GetParam(mDrag);
    if (mHover == "numeric") {
      const double perPixel = std::max(p->GetStep(), p->GetRange() / 200.);
      Set(mDrag, mDragValue + (mDragY - y) * perPixel * (mod.S ? .1 : 1.), false);
      return;
    }
    Set(mDrag,
        mHover == "fader" ? 99 - 198 * std::clamp((y - 132) / 135.f, 0.f, 1.f)
                          : mDragValue + (mDragY - y) * p->GetRange() / 160. * (mod.S ? .1 : 1.),
        false);
  } else if (mDrag == -3) {
    mMod = std::clamp(mDragValue + (mDragY - y) * 127 / 101.64, 0., 127.);
    GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xb0, 1, int(std::round(mMod))));
    SetDirty(false);
  } else if (mDrag == -2) {
    mPitch = std::clamp(mDragValue + (mDragY - y) * 160., -8192., 8191.);
    int n = int(mPitch) + 8192;
    GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xe0, n & 127, n >> 7));
    SetDirty(false);
  }
}
void NativePanel::OnMouseUp(float, float, const IMouseMod &) {
  mPointerDown = false;
  const bool editNumber = mNumericPending && !mNumericDragging;
  mNumericPending = mNumericDragging = false;
  ReleaseSwitches();
  mParameters.End(*GetDelegate());
  if (editNumber) Activate(mNumericPress);
  if (mDrag == -2) {
    mPitch = 0;
    GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xe0, 0, 64));
  }
  mDrag = -1;
  if (mDragNote >= 0)
    Note(mDragNote, false);
  mDragNote = -1;
  SetDirty(false);
}
bool NativePanel::IsParameterHit(float x, float y) const {
  for (auto it = mHits.rbegin(); it != mHits.rend(); ++it)
    if (it->r.Contains(x, y))
      return it->action == "knob" || it->action == "fader";
  return false;
}
void NativePanel::OnMouseDblClick(float x, float y, const IMouseMod &) {
  for (auto it = mHits.rbegin(); it != mHits.rend(); ++it)
    if (it->r.Contains(x, y)) {
      if (it->action == "knob" || it->action == "fader")
        Set(it->id, GetDelegate()->GetParam(it->id)->GetDefault());
      return;
    }
}
void NativePanel::OnMouseWheel(float x, float y, const IMouseMod &mod, float d) {
  if (!std::isfinite(d))
    return;
  if (!mPresetOpen && mChoices.empty() && !mBrowsing) {
    for (auto it = mHits.rbegin(); it != mHits.rend(); ++it)
      if (it->r.Contains(x, y)) {
        if (it->action == "knob" || it->action == "fader" || it->action == "edit") {
          auto *p = GetDelegate()->GetParam(it->id);
          Set(it->id, Value(it->id) + d * std::max(p->GetStep(), p->GetRange() / (mod.S ? 1000 : 100)));
        } else if (it->action == "mod") {
          mMod = std::clamp(mMod + d * (mod.S ? 1 : 4), 0., 127.);
          GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xb0, 1, int(std::round(mMod))));
        }
        SetDirty(false);
        return;
      }
    return;
  }
  mWheelRemainder += d * 3;
  const int rows = int(std::clamp(mWheelRemainder, -1000., 1000.));
  mWheelRemainder -= rows;
  if (mPresetOpen) {
    if (x >= 675 && mPresetCategory >= -1)
      mPresetScroll = std::clamp(mPresetScroll - rows, 0, std::max(0, int(mPresetItems.size()) - 12));
  } else if (!mChoices.empty()) {
    mPopupScroll = std::clamp(mPopupScroll - rows, 0, std::max(0, int(mChoices.size()) - mPopupRows));
  } else if (mBrowsing)
    mScroll = std::clamp(mScroll - rows, 0, std::max(0, int(mFiltered.size()) - 7));
  SetDirty(false);
}
bool NativePanel::OnKeyDown(float, float, const IKeyPress &key) {
  if (!mUpdateVersion.empty()) {
    if (key.VK == kVK_ESCAPE || key.VK == kVK_RETURN || key.VK == kVK_SPACE)
      ShowUpdateNotice("");
    return true;
  }
  if (mPresetOpen) {
    if (key.VK == kVK_ESCAPE) {
      mPresetOpen = false;
      SetDirty(false);
      return true;
    }
    if (key.VK == kVK_LEFT) {
      mPresetColumn = 0;
      SetDirty(false);
      return true;
    }
    if (key.VK == kVK_RIGHT || key.VK == kVK_RETURN) {
      if (!mPresetColumn)
        PresetCategory(mPresetRootFocus - 1);
      else if (key.VK == kVK_RETURN && !mPresetItems.empty())
        SetProgram(mPresetItems[mPresetFocus]);
    } else if (key.VK == kVK_SPACE && mPresetColumn && !mPresetItems.empty())
      ToggleFavorite(mPresetItems[mPresetFocus]);
    else {
      int &focus = mPresetColumn ? mPresetFocus : mPresetRootFocus;
      int count = mPresetColumn ? int(mPresetItems.size()) : 12;
      if (key.VK == kVK_HOME)
        focus = 0;
      if (key.VK == kVK_END)
        focus = std::max(0, count - 1);
      if (key.VK == kVK_UP || key.VK == kVK_DOWN)
        focus = std::clamp(focus + (key.VK == kVK_UP ? -1 : 1), 0, std::max(0, count - 1));
      if (mPresetColumn)
        mPresetScroll = std::clamp(focus - 6, 0, std::max(0, count - 12));
    }
    SetDirty(false);
    return true;
  }
  if (key.VK == kVK_ESCAPE) {
    if (!mChoices.empty()) {
      mChoices.clear();
      SetDirty(false);
      return true;
    }
    auto &map = static_cast<KrosePlugin *>(GetDelegate())->MidiMappings();
    if (mMapEdit >= 0)
      mMapEdit = -1;
    else if (mConfirmProfile != -1)
      mConfirmProfile = -1;
    else if (map.Learning() >= 0) {
      map.CancelLearn();
      mControllerStatus = "Learning cancelled";
    } else
      mControllers = false;
    mEdit = -1;
    mBrowsing = false;
    SetDirty(false);
    return true;
  }
  if (!mChoices.empty()) {
    if (key.VK == kVK_HOME || key.VK == kVK_END) {
      mPopupFocus = key.VK == kVK_HOME ? 0 : int(mChoices.size()) - 1;
      mPopupScroll = std::clamp(mPopupFocus - mPopupRows / 2, 0,
                                std::max(0, int(mChoices.size()) - mPopupRows));
      SetDirty(false);
      return true;
    }
    if (key.VK == kVK_RETURN || key.VK == kVK_SPACE) {
      Activate({{}, "choice", -1, double(mChoiceValues[mPopupFocus])});
      return true;
    }
    if (key.VK == kVK_UP || key.VK == kVK_DOWN) {
      mPopupFocus =
          std::clamp(mPopupFocus + (key.VK == kVK_UP ? -1 : 1), 0, int(mChoices.size()) - 1);
      mPopupScroll = std::clamp(mPopupFocus - mPopupRows / 2, 0,
                                std::max(0, int(mChoices.size()) - mPopupRows));
      SetDirty(false);
      return true;
    }
    return true;
  }
  if (mMapEdit >= 0) {
    if (key.VK == kVK_RETURN || key.VK == kVK_TAB) {
      FinishEdit();
      return true;
    }
    if (key.C && (key.VK == 65 || key.VK == 97)) {
      mSelectAll = true;
      return true;
    }
    if (key.VK == kVK_BACK) {
      if (mSelectAll)
        mEditText.clear();
      else if (!mEditText.empty())
        mEditText.pop_back();
      mSelectAll = false;
    } else if (key.utf8[0]) {
      if (mSelectAll)
        mEditText.clear();
      mSelectAll = false;
      for (char c : std::string(key.utf8))
        if (c >= '0' && c <= '9' && mEditText.size() < 5)
          mEditText += c;
    }
    SetDirty(false);
    return true;
  }
  if (mEdit == -2 && mBrowsing) {
    if (key.VK == kVK_BACK) {
      if (!mSearch.empty()) {
        auto chars = Chars(mSearch);
        chars.pop_back();
        mSearch.clear();
        for (auto &c : chars)
          mSearch += c;
      }
    } else if (key.VK == kVK_RETURN) {
      if (!mFiltered.empty()) {
        const int current = int(Value(kParamProgram));
        const auto first = mFiltered.begin() + mScroll;
        const auto last = first + std::min(7, int(mFiltered.end() - first));
        SetProgram(std::find(first, last, current) != last ? current : *first);
      }
      return true;
    } else if (key.utf8[0] && !key.C && mSearch.size() < 256)
      mSearch += key.utf8;
    FilterPrograms();
    SetDirty(false);
    return true;
  }
  if (mEdit >= 0 && key.VK == kVK_TAB)
    FinishEdit();
  if (mEdit >= 0) {
    if (key.VK == kVK_UP || key.VK == kVK_DOWN) {
      int id = mEdit;
      FinishEdit();
      Set(id, Value(id) + (key.VK == kVK_UP ? 1 : -1) * GetDelegate()->GetParam(id)->GetStep());
      mEdit = id;
      mEditText = Format(Value(id), GetDelegate()->GetParam(id)->GetStep() < 1 ? 2 : 0);
      mSelectAll = true;
      return true;
    }
    if (key.C && (key.VK == 65 || key.VK == 97)) {
      mSelectAll = true;
      return true;
    }
    if (key.VK == kVK_RETURN) {
      FinishEdit();
      return true;
    }
    if (key.VK == kVK_BACK) {
      if (mSelectAll)
        mEditText.clear();
      else if (!mEditText.empty())
        mEditText.pop_back();
      mSelectAll = false;
    } else if (key.utf8[0]) {
      if (mSelectAll)
        mEditText.clear();
      mSelectAll = false;
      for (char c : std::string(key.utf8))
        if ((c >= '0' && c <= '9') || c == '.' || c == '-' || c == '+')
          mEditText += c;
    }
    SetDirty(false);
    return true;
  }
  if (key.VK == kVK_TAB && mControllers) {
    mKeyboardFocus = true;
    std::vector<int> controls;
    for (int i = 0; i < int(mHits.size()); ++i) {
      const auto &h = mHits[i];
      if (h.r.L >= 431 && h.r.R <= 973 && h.r.T >= 115 && h.r.B <= 284 && !h.action.empty())
        controls.push_back(i);
    }
    if (!controls.empty()) {
      auto at = std::find(controls.begin(), controls.end(), mFocus);
      int n = at == controls.end() ? (key.S ? 0 : -1) : int(at - controls.begin());
      mFocus = controls[(n + (key.S ? -1 : 1) + int(controls.size())) % controls.size()];
    }
    SetDirty(false);
    return true;
  }
  if (key.VK == kVK_TAB) {
    mKeyboardFocus = true;
    if (!mHits.empty())
      mFocus = (mFocus + (key.S ? -1 : 1) + int(mHits.size())) % mHits.size();
    SetDirty(false);
    return true;
  }
  if (mFocus < 0 || mFocus >= int(mHits.size()))
    return false;
  auto h = mHits[mFocus];
  if (h.action == "pitch" && (key.VK == kVK_HOME || key.VK == kVK_UP || key.VK == kVK_DOWN)) {
    mPitch = key.VK == kVK_HOME
                 ? 0
                 : std::clamp(mPitch + (key.VK == kVK_UP ? 128 : -128), -8192., 8191.);
    int n = int(mPitch) + 8192;
    GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xe0, n & 127, n >> 7));
    SetDirty(false);
    return true;
  }
  if (h.action == "knob" || h.action == "fader") {
    if (key.VK == kVK_HOME)
      Set(h.id, GetDelegate()->GetParam(h.id)->GetDefault());
    else if (key.VK == kVK_UP || key.VK == kVK_RIGHT || key.VK == kVK_DOWN || key.VK == kVK_LEFT)
      Set(h.id, Value(h.id) + (key.VK == kVK_UP || key.VK == kVK_RIGHT ? 1 : -1) *
                                  GetDelegate()->GetParam(h.id)->GetStep());
    else
      return false;
    return true;
  }
  if (key.VK == kVK_SPACE || key.VK == kVK_RETURN) {
    if (h.action == "note") {
      mDragNote = h.id;
      Note(h.id, true);
    } else
      Activate(h);
    return true;
  }
  return false;
}
bool NativePanel::OnKeyUp(float, float, const IKeyPress &key) {
  if (key.VK == kVK_SPACE || key.VK == kVK_RETURN)
    ReleaseSwitches();
  if ((key.VK == kVK_SPACE || key.VK == kVK_RETURN) && mDragNote >= 0) {
    Note(mDragNote, false);
    mDragNote = -1;
    return true;
  }
  return false;
}
void NativePanel::OnMouseOver(float x, float y, const IMouseMod &) {
  auto hitAt = [&](float px, float py) {
    for (int i = int(mHits.size()) - 1; i >= 0; --i)
      if (mHits[i].r.Contains(px, py)) return i;
    return -1;
  };
  const bool changed = hitAt(mMouseX, mMouseY) != hitAt(x, y);
  mMouseX = x;
  mMouseY = y;
  if (changed) SetDirty(false);
}
void NativePanel::OnMouseOut() {
  mMouseX = mMouseY = -1;
  SetDirty(false);
}
} // namespace krose::ui

namespace krose::ui {
void NativePanel::PresetFile(bool save) {
  ReleaseHeld();
  const std::weak_ptr<int> alive = mLifetime;
  auto complete = [this, alive, save](const WDL_String &file, const WDL_String &) {
    if (alive.expired() || !file.GetLength())
      return;
    auto *plugin = static_cast<KrosePlugin *>(GetDelegate());
    const bool ok = save ? plugin->SaveUserPreset(file.Get()) : plugin->LoadUserPreset(file.Get());
    mPresetStatus = ok ? (save ? "PRESET SAVED" : "PRESET LOADED") : "PRESET FILE ERROR";
    if (!save) {
      mBrowsing = false;
      mControllers = false;
      mEdit = -1;
      mPage = 0;
    }
    SetDirty(false);
  };
  WDL_String file(save ? "Untitled.krose" : ""), path;
#ifdef _WIN32
  try {
    const auto chosen = krose::storage::PresetDialog(static_cast<HWND>(GetUI()->GetWindow()), save);
    file.Set(chosen.u8string().c_str());
    complete(file, path);
  } catch (const std::exception &) {
    mPresetStatus = "PRESET FILE ERROR";
    SetDirty(false);
  }
  GetUI()->ReleaseMouseCapture();
#else
  GetUI()->PromptForFile(file, path, save ? EFileAction::Save : EFileAction::Open, "krose", complete);
#endif
}
} // namespace krose::ui
