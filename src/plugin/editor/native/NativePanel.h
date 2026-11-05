#pragma once
#include "../../Parameters.h"
#include "../ParameterBinding.h"
#include "FXMotion.h"
#include "IControl.h"
#include "json.hpp"
#include <array>
#include <chrono>
#include <map>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

namespace krose::ui {
using namespace iplug;
using namespace iplug::igraphics;
class NativePanel final : public IControl {
public:
  NativePanel();
  ~NativePanel() override;
  void OnInit() override;
  void Draw(IGraphics &) override;
  bool IsDirty() override;
  bool IsParameterHit(float x, float y) const;
  void OnMouseDown(float, float, const IMouseMod &) override;
  void OnMouseDrag(float, float, float, float, const IMouseMod &) override;
  void OnMouseUp(float, float, const IMouseMod &) override;
  void OnMouseDblClick(float, float, const IMouseMod &) override;
  void OnMouseWheel(float, float, const IMouseMod &, float) override;
  bool OnKeyDown(float, float, const IKeyPress &) override;
  bool OnKeyUp(float, float, const IKeyPress &) override;
  void OnMouseOver(float, float, const IMouseMod &) override;
  void OnMouseOut() override;
  void Refresh(double tempo, bool host, bool loading, bool loadFailed);
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
    std::vector<std::array<float, 6>> glyphs;
    std::unordered_map<std::string, size_t> indices;
    int size;
  };
  void Render(IGraphics &);
  double FoldProgress() const;
  void LCD(IGraphics &);
  int FxType(int slot);
  bool FxEnabled(int slot);
  std::string FxName(int slot);
  void FxPage(IGraphics &);
  void DrawFxFace(IGraphics &, const IRECT &, int slot);
  void DrawEmptyFxSlot(IGraphics &, const IRECT &, bool vertical);
  void Browser(IGraphics &);
  void Popup(IGraphics &);
  void OpenPopup(const Hit &);
  void PresetMenu(IGraphics &);
  void PresetCategory(int category);
  void LoadFavorites();
  void ToggleFavorite(int program);
  void Heart(IGraphics &, const IRECT &, int program);
  void Text(IGraphics &, const std::string &, const std::string &, const IRECT &, int align = 0);
  double TextWidth(const std::string &, const std::string &) const;
  void Bitmap(IGraphics &, const std::string &, float, float);
  const IBitmap &Image(const std::string &);
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
  void Controllers(IGraphics &);
  bool ControllerAction(const Hit &);
  void ControllerMenu(const Hit &);
  void ControllerChoice(int, int);
  void BeginLearn(int target);
  void ReleaseSwitches();
  uint64_t ControllerHash();
  void ControllerCell(IGraphics &, const std::string &, IRECT, const std::string &, int = -1,
                      double = 0, bool = false);
  const Json &mData, &mPrograms, &mBrowser, &mLCD;
  const std::vector<int> &mProgramOrder;
  std::map<std::string, IBitmap> mImages;
  std::string mResourceRoot;
  std::map<std::string, Font> mFonts;
  std::vector<Hit> mHits;
  std::vector<int> mFiltered;
  std::array<bool, 128> mHeld{}, mLit{};
  ParameterBinding<kNumParams> mParameters;
  int mPage = 0, mEG = 0, mOctave = 0, mSlot = 0, mFxBand = 0, mDrag = -1, mDragNote = -1, mEdit = -1,
      mScroll = 0, mGroup = -1, mCategory = -1, mFocus = -1;
  float mDragY = 0, mMouseX = 0, mMouseY = 0;
  double mDragValue = 0, mTempo = 120, mPitch = 0;
  bool mLoading = false, mLoadFailed = false;
  bool mHost = false, mFold = false, mSustain = false, mBrowsing = false, mSelectAll = false;
  std::string mEditText, mSearch, mHover;
  std::vector<std::string> mChoices;
  std::vector<int> mChoiceValues;
  Hit mPopupTarget;
  int mPopupScroll = 0, mPopupFocus = 0, mPopupRows = 12;
  bool mPresetOpen = false, mFavoriteSaveFailed = false;
  int mPresetCategory = -2, mPresetRootFocus = 0, mPresetFocus = 0, mPresetScroll = 0,
      mPresetColumn = 0;
  std::vector<int> mPresetItems;
  std::set<std::string> mFavorites;
  bool mKeyboardFocus = false;
  FXMotion mFXMotion;
  double mRenderedFold = 0;
  ILayerPtr mFXLayer;
  std::vector<double> mDrawTimes, mFrameGaps;
  std::chrono::steady_clock::time_point mPreviousFrame{};
  bool mPreviousAnimating = false;
  bool mControllers = false;
  int mControllerPage = 0, mMapSlot = 0, mMapEdit = -1, mConfirmProfile = -1;
  unsigned mMapRevision = 0;
  uint32_t mLastMidi = 0;
  uint64_t mStoredMapping = 0;
  std::array<bool, 2> mHeldSwitch{};
  std::string mControllerStatus;
};
} // namespace krose::ui
