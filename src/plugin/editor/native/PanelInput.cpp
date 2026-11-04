#include "../../KrosePlugin.h"
#include "NativePanel.h"
#include "PanelDrawing.h"
namespace krose::ui {
using namespace detail;
void NativePanel::StepProgram(int delta) {
  auto order = mBrowser["order"].get<std::vector<int>>();
  auto it = std::find(order.begin(), order.end(), int(Value(kParamProgram)));
  int n = int(it - order.begin());
  SetProgram(order[(n + delta + int(order.size())) % order.size()]);
}
void NativePanel::SetProgram(int i) {
  Set(kParamProgram, i);
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
  for (int i = 0; i < 128; ++i)
    Note(i, false);
  mLit.fill(false);
  mSustain = false;
  GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xb0, 64, 0));
  GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xe0, 0, 64));
  mPitch = 0;
  if (mDrag >= 0) {
    GetDelegate()->EndInformHostOfParamChangeFromUI(mDrag);
    mDrag = -1;
  }
  SetDirty(false);
}
void NativePanel::FinishEdit() {
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
  if (h.action == "increment")
    Set(h.id, Value(h.id) + h.value * GetDelegate()->GetParam(h.id)->GetStep());
  else if (h.action == "toggle")
    Set(h.id, Value(h.id) ? 0 : 1);
  else if (h.action == "set")
    Set(h.id, h.value);
  else if (h.action == "eg")
    mEG = int(h.value);
  else if (h.action == "page") {
    mPage = int(h.value);
    mSlot = 0;
  } else if (h.action == "slot")
    mSlot = int(h.value);
  else if (h.action == "step")
    StepProgram(int(h.value));
  else if (h.action == "fold") {
    mFoldFrom = FoldProgress();
    mFold = !mFold;
    mFoldStarted = std::chrono::steady_clock::now();
  } else if (h.action == "browse") {
    ReleaseHeld();
    mBrowsing = true;
    LoadFavorites();
    mEdit = -2;
    FilterPrograms();
  } else if (h.action == "close") {
    mBrowsing = false;
    mEdit = -1;
  } else if (h.action == "program")
    SetProgram(int(h.value));
  else if (h.action == "presets") {
    LoadFavorites();
    mPresetOpen = true;
    mPresetCategory = -2;
    mPresetRootFocus = 0;
    mPresetColumn = 0;
    mChoices.clear();
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
    mChoices.clear();
    if (target.action == "group") {
      mGroup = v;
      FilterPrograms();
    } else if (target.action == "category") {
      mCategory = v;
      FilterPrograms();
    } else
      Set(target.id, v);
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
        (h.id == kParamTone || h.id == kArpPattern || h.id == kArpResolution)) {
      OpenPopup(h);
    } else {
      mEdit = h.id;
      mEditText = Format(Value(h.id), GetDelegate()->GetParam(h.id)->GetStep() < 1 ? 2 : 0);
      mSelectAll = true;
    }
  }
  SetDirty(false);
}
void NativePanel::OnMouseDown(float x, float y, const IMouseMod &) {
  mMouseX = x;
  mMouseY = y;
  mKeyboardFocus = false;
  FinishEdit();
  for (int i = int(mHits.size()) - 1; i >= 0; --i) {
    auto h = mHits[i];
    if (!h.r.Contains(x, y))
      continue;
    mFocus = i;
    if (h.action == "knob" || h.action == "fader") {
      mDrag = h.id;
      mDragY = y;
      mDragValue = Value(h.id);
      mHover = h.action;
      GetDelegate()->BeginInformHostOfParamChangeFromUI(h.id);
      if (h.action == "fader")
        Set(h.id, 99 - 198 * std::clamp((y - 132) / 135.f, 0.f, 1.f), false);
    } else if (h.action == "note") {
      mDragNote = h.id;
      Note(h.id, true);
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
  if (mDrag >= 0) {
    auto *p = GetDelegate()->GetParam(mDrag);
    Set(mDrag,
        mHover == "fader" ? 99 - 198 * std::clamp((y - 132) / 135.f, 0.f, 1.f)
                          : mDragValue + (mDragY - y) * p->GetRange() / 160. * (mod.S ? .1 : 1.),
        false);
  } else if (mDrag == -2) {
    mPitch = std::clamp(mDragValue + (mDragY - y) * 160., -8192., 8191.);
    int n = int(mPitch) + 8192;
    GetDelegate()->SendMidiMsgFromUI(IMidiMsg(0, 0xe0, n & 127, n >> 7));
    SetDirty(false);
  }
}
void NativePanel::OnMouseUp(float, float, const IMouseMod &) {
  if (mDrag >= 0)
    GetDelegate()->EndInformHostOfParamChangeFromUI(mDrag);
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
void NativePanel::OnMouseDblClick(float x, float y, const IMouseMod &) {
  for (auto it = mHits.rbegin(); it != mHits.rend(); ++it)
    if (it->r.Contains(x, y) && (it->action == "knob" || it->action == "fader")) {
      Set(it->id, GetDelegate()->GetParam(it->id)->GetDefault());
      return;
    }
}
void NativePanel::OnMouseWheel(float x, float, const IMouseMod &, float d) {
  if (mPresetOpen) {
    if (x >= 675 && mPresetCategory >= -1)
      mPresetScroll =
          std::clamp(mPresetScroll - int(d * 3), 0, std::max(0, int(mPresetItems.size()) - 12));
    SetDirty(false);
  } else if (!mChoices.empty()) {
    mPopupScroll =
        std::clamp(mPopupScroll - int(d * 3), 0, std::max(0, int(mChoices.size()) - mPopupRows));
    SetDirty(false);
  } else if (mBrowsing) {
    mScroll -= int(d * 3);
    SetDirty(false);
  }
}
bool NativePanel::OnKeyDown(float, float, const IKeyPress &key) {
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
      if (!mFiltered.empty())
        SetProgram(mFiltered[0]);
      return true;
    } else if (key.utf8[0] && !key.C)
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
  if ((key.VK == kVK_SPACE || key.VK == kVK_RETURN) && mDragNote >= 0) {
    Note(mDragNote, false);
    mDragNote = -1;
    return true;
  }
  return false;
}
void NativePanel::OnMouseOver(float x, float y, const IMouseMod &) {
  int before = -1, after = -1;
  for (int i = 0; i < int(mHits.size()); ++i)
    if (mHits[i].action == "tooltip") {
      if (mHits[i].r.Contains(mMouseX, mMouseY))
        before = i;
      if (mHits[i].r.Contains(x, y))
        after = i;
    }
  mMouseX = x;
  mMouseY = y;
  if (before != after)
    SetDirty(false);
}
void NativePanel::OnMouseOut() {
  mMouseX = mMouseY = -1;
  SetDirty(false);
}
} // namespace krose::ui
