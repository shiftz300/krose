#pragma once
#include "IControl.h"
#include "json.hpp"
#include <array>
#include <chrono>
#include <map>
#include <string>
#include <vector>

namespace krose::ui {
using namespace iplug;
using namespace iplug::igraphics;
class NativePanel final : public IControl {
public:
  NativePanel();
  void OnInit() override;
  void Draw(IGraphics &) override;
  void OnMouseDown(float, float, const IMouseMod &) override;
  void OnMouseDrag(float, float, float, float, const IMouseMod &) override;
  void OnMouseUp(float, float, const IMouseMod &) override;
  void OnMouseDblClick(float, float, const IMouseMod &) override;
  void OnMouseWheel(float, float, const IMouseMod &, float) override;
  bool OnKeyDown(float, float, const IKeyPress &) override;
  bool OnKeyUp(float, float, const IKeyPress &) override;
  void OnMouseOver(float, float, const IMouseMod &) override;
  void OnMouseOut() override;
  void Refresh(double tempo, bool host);
  void ReleaseHeld();

private:
  using Json = nlohmann::json;
  struct Hit {
    IRECT r;
    std::string action;
    int id = -1;
    double value = 0;
  };
  struct Font {
    IBitmap image;
    std::vector<std::string> chars;
    std::vector<double> advances;
    int size;
  };
  void Render(IGraphics &);
  double FoldProgress() const;
  void LCD(IGraphics &);
  void Browser(IGraphics &);
  void Popup(IGraphics &);
  void OpenPopup(const Hit &);
  void Text(IGraphics &, const std::string &, const std::string &, const IRECT &, int align = 0);
  double TextWidth(const std::string &, const std::string &) const;
  void Bitmap(IGraphics &, const std::string &, float, float);
  void Button(IGraphics &, const std::string &, bool, const std::string &, int = -1, double = 0,
              bool = true);
  void Chevron(IGraphics &, const IRECT &, const IColor &);
  void Field(IGraphics &, const std::string &, const IRECT &, int, const std::string &,
             bool = true);
  void HitBox(IRECT r, std::string action, int id = -1, double value = 0);
  void Activate(const Hit &);
  void Set(int, double, bool gesture = true);
  double Value(int);
  void StepProgram(int);
  void SetProgram(int);
  void FilterPrograms();
  void Note(int, bool);
  void FinishEdit();
  void ProgramRow(IGraphics &);
  Json mData, mPrograms, mBrowser, mLCD;
  std::map<std::string, IBitmap> mImages;
  std::map<std::string, Font> mFonts;
  std::vector<Hit> mHits;
  std::vector<int> mFiltered;
  std::array<bool, 128> mHeld{}, mLit{};
  std::array<double, 29> mLastValues{};
  int mPage = 0, mEG = 0, mOctave = 0, mSlot = 0, mDrag = -1, mDragNote = -1, mEdit = -1,
      mScroll = 0, mGroup = -1, mCategory = -1, mFocus = -1;
  float mDragY = 0, mMouseX = 0, mMouseY = 0;
  double mDragValue = 0, mTempo = 120, mPitch = 0;
  bool mHost = false, mFold = false, mSustain = false, mBrowsing = false, mSelectAll = false;
  std::string mEditText, mSearch, mHover;
  std::vector<std::string> mChoices;
  std::vector<int> mChoiceValues;
  Hit mPopupTarget;
  int mPopupScroll = 0, mPopupFocus = 0;
  bool mKeyboardFocus = false;
  double mFoldFrom = 0;
  std::chrono::steady_clock::time_point mFoldStarted{};
};
} // namespace krose::ui
