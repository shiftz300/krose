#pragma once
#include <algorithm>
#include <cmath>

namespace krose::ui {
// Analytic critically damped motion: independent of frame rate, with continuous
// position and velocity when the user reverses direction during a transition.
class FXMotion {
public:
  struct State {
    double position, velocity;
  };
  State At(double now) const noexcept {
    const double t = std::max(0., now - mStarted);
    const double distance = mPosition - mTarget;
    const double c = mVelocity + kOmega * distance;
    const double decay = std::exp(-kOmega * t);
    const double offset = (distance + c * t) * decay;
    const double velocity = (mVelocity - kOmega * c * t) * decay;
    // Below 0.28 px at the largest mask radius; stop invalidating idle frames.
    if (std::abs(offset) < .0005 && std::abs(velocity) < .01)
      return {mTarget, 0};
    return {std::clamp(mTarget + offset, 0., 1.), velocity};
  }
  void Target(bool folded, double now) noexcept {
    const auto current = At(now);
    mPosition = current.position;
    mVelocity = current.velocity;
    mTarget = folded ? 1. : 0.;
    mStarted = now;
  }

private:
  static constexpr double kOmega = 24.;
  double mPosition = 0, mVelocity = 0, mTarget = 0, mStarted = 0;
};
} // namespace krose::ui
