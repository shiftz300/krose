#pragma once
#include "IControl.h"
#include <algorithm>
#include <cmath>
#include <utility>

namespace krose::ui {
using namespace iplug;
using namespace iplug::igraphics;

// Bounds include the captured shadow; hit bounds remain the original DOM bounds.
class Knob final : public IControl {
public:
  Knob(const IRECT& face, int parameter, IBitmap shell, IBitmap pointer)
      : IControl(face.GetPadded(8), parameter), mFace(face),
        mShell(shell), mPointer(pointer) { SetTargetRECT(face); }
  void Draw(IGraphics& g) override {
    g.DrawBitmap(mShell, mRECT);
    g.DrawRotatedBitmap(mPointer, mFace.MW(), mFace.MH(), -135. + 270. * GetValue());
  }
  void OnMouseDown(float, float y, const IMouseMod&) override {
    mStartY = y; mStart = GetValue();
  }
  void OnMouseDrag(float, float y, float, float, const IMouseMod& mod) override {
    SetQuantized(mStart + (mStartY-y)/160. * (mod.S ? .1 : 1.));
  }
  void OnMouseDblClick(float, float, const IMouseMod&) override {
    SetValueFromUserInput(GetParam()->GetDefault(true));
  }
  bool OnKeyDown(float, float, const IKeyPress& key) override {
    if(key.VK == kVK_HOME) { SetValueFromUserInput(GetParam()->GetDefault(true)); return true; }
    int sign = key.VK == kVK_UP || key.VK == kVK_RIGHT ? 1 : key.VK == kVK_DOWN || key.VK == kVK_LEFT ? -1 : 0;
    if(!sign) return false;
    SetQuantized(GetValue() + sign * GetParam()->GetStep()/GetParam()->GetRange());
    return true;
  }
private:
  void SetQuantized(double normalized) {
    const auto* p=GetParam();
    double value=p->FromNormalized(std::clamp(normalized,0.,1.));
    value=std::round(value/p->GetStep())*p->GetStep();
    SetValueFromUserInput(p->ToNormalized(std::clamp(value,p->GetMin(),p->GetMax())));
  }
  IRECT mFace;
  IBitmap mShell, mPointer;
  float mStartY=0;
  double mStart=0;
};

class Switch final : public IControl {
public:
  Switch(const IRECT& face, int parameter, IBitmap off, IBitmap on)
      : IControl(face.GetPadded(3), parameter), mOff(off), mOn(on) { SetTargetRECT(face); }
  void Draw(IGraphics& g) override { g.DrawBitmap(GetValue()>.5 ? mOn : mOff,mRECT); }
  void OnMouseDown(float, float, const IMouseMod&) override { SetValueFromUserInput(GetValue()>.5?0.:1.); }
  bool OnKeyDown(float, float, const IKeyPress& key) override {
    if(key.VK!=kVK_SPACE && key.VK!=kVK_RETURN) return false;
    SetValueFromUserInput(GetValue()>.5?0.:1.);return true;
  }
private:
  IBitmap mOff,mOn;
};
} // namespace krose::ui
