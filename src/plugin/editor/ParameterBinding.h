#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace krose::ui {
// One binding path for knobs, fields, menus and keyboard edits. Values remain
// owned by the delegate, so automation/state restoration cannot leave a stale
// UI copy. Only the redraw comparison and active host gesture are cached here.
template <size_t Count> class ParameterBinding {
public:
  ParameterBinding() { mSeen.fill(std::numeric_limits<double>::quiet_NaN()); }
  template <class Delegate> void Begin(Delegate &delegate, int id) {
    if (id < 0 || id >= int(Count) || id == mGesture)
      return;
    End(delegate);
    mGesture = id;
    delegate.BeginInformHostOfParamChangeFromUI(id);
  }
  template <class Delegate> void End(Delegate &delegate) {
    if (mGesture >= 0)
      delegate.EndInformHostOfParamChangeFromUI(mGesture);
    mGesture = -1;
  }
  template <class Delegate> bool Set(Delegate &delegate, int id, double value, bool gesture = true) {
    if (id < 0 || id >= int(Count) || !std::isfinite(value))
      return false;
    auto *parameter = delegate.GetParam(id);
    const double low = parameter->GetMin(), high = parameter->GetMax(), step = parameter->GetStep();
    value = std::clamp(value, low, high);
    if (step > 0)
      value = std::clamp(low + std::round((value - low) / step) * step, low, high);
    const double normalized = parameter->ToNormalized(value);
    if (std::abs(normalized - parameter->ToNormalized(parameter->Value())) < 1e-12)
      return false;
    const bool discrete = gesture && mGesture != id;
    if (discrete)
      Begin(delegate, id);
    delegate.SendParameterValueFromUI(id, normalized);
    if (discrete)
      End(delegate);
    return true;
  }
  template <class Delegate> bool Changed(Delegate &delegate) {
    bool changed = false;
    for (size_t id = 0; id < Count; ++id) {
      const double value = delegate.GetParam(int(id))->Value();
      if (value != mSeen[id]) {
        mSeen[id] = value;
        changed = true;
      }
    }
    return changed;
  }

private:
  std::array<double, Count> mSeen;
  int mGesture = -1;
};
} // namespace krose::ui
