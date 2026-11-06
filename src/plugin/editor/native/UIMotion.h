#pragma once
#include <algorithm>
#include <cmath>

namespace krose::ui {
// Visual values only. Absolute time keeps the same path at any refresh rate;
// repeated targets do not restart it and interrupted transitions keep position.
class UIMotion {
public:
  void Snap(double value) noexcept { mFrom = mTarget = value; mReady = true; }
  double At(double now) const noexcept {
    const double t = std::clamp((now - mStart) / mDuration, 0., 1.);
    if (t >= 1 || mFrom == mTarget) return mTarget;
    const double eased = (1 - std::exp(-6 * t)) / (1 - std::exp(-6.));
    return mFrom + (mTarget - mFrom) * eased;
  }
  void Target(double value, double now, double seconds = .12) noexcept {
    if (!mReady) { Snap(value); return; }
    if (value == mTarget) return;
    mFrom = At(now); mTarget = value; mStart = now;
    mDuration = std::max(.001, seconds);
  }
  bool Active(double now) const noexcept { return At(now) != mTarget; }
private:
  double mFrom = 0, mTarget = 0, mStart = 0, mDuration = .12;
  bool mReady = false;
};
} // namespace krose::ui
