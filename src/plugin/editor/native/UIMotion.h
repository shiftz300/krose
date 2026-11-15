#pragma once
#include <algorithm>
#include <cmath>

namespace krose::ui {
// Visual values only. Absolute time keeps the same path at any refresh rate;
// repeated targets do not restart it and interrupted transitions keep position.
class UIMotion {
public:
  enum class Curve { EaseOut, Linear };
  void Snap(double value) noexcept { mFrom = mTarget = value; mReady = true; }
  double At(double now) const noexcept {
    const double t = std::clamp((now - mStart) / mDuration, 0., 1.);
    if (t >= 1 || mFrom == mTarget) return mTarget;
    const double progress = mCurve == Curve::Linear ? t :
                            (1 - std::exp(-6 * t)) / (1 - std::exp(-6.));
    return mFrom + (mTarget - mFrom) * progress;
  }
  void Target(double value, double now, double seconds = .12,
              Curve curve = Curve::EaseOut) noexcept {
    if (!mReady) { Snap(value); return; }
    if (value == mTarget) return;
    mFrom = At(now); mTarget = value; mStart = now;
    mDuration = std::max(.001, seconds);
    mCurve = curve;
  }
  bool Active(double now) const noexcept { return At(now) != mTarget; }
private:
  double mFrom = 0, mTarget = 0, mStart = 0, mDuration = .12;
  Curve mCurve = Curve::EaseOut;
  bool mReady = false;
};
} // namespace krose::ui
