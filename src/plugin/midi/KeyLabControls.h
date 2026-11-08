#pragma once
#include <array>
#include <algorithm>
#include <cmath>
namespace krose::midi::essential {
enum class Kind { None, Knob, Fader, Pad, Program, FxEdit };
struct Control { Kind kind = Kind::None; unsigned index = 0; };
inline int ProgramKnobDelta(unsigned value, int previous) noexcept {
  const int delta = int(value) - previous;
  return value < 128 && previous >= 0 && previous < 128 ? delta : 0;
}
// mk3 DAW map: CC on MIDI channel 1, pads on channel 11. Leave notes,
// pitch, Mod, pedal and every transport button to the normal MIDI/DAW path.
inline Control Decode(unsigned status, unsigned number) noexcept {
  if (status == 0xb0) {
    if (number >= 44 && number <= 47) return {Kind::FxEdit, number - 44};
    if (number >= 96 && number <= 104) return {Kind::Knob, number - 96};
    if (number >= 105 && number <= 113) return {Kind::Fader, number - 105};
    if (number == 116) return {Kind::Program, 0};
  }
  if ((status == 0x9a || status == 0x8a) && number >= 36 && number <= 43)
    return {Kind::Pad, (number - 36) ^ 4u};
  return {};
}
enum class FxPressAction { None, Edit, Toggle };
class FxButtonPresses {
public:
  static constexpr double kHoldSeconds = .6;
  void Reset() noexcept { mButtons = {}; }
  FxPressAction Input(unsigned index, bool down, double now) noexcept {
    if (index >= mButtons.size() || !std::isfinite(now)) return FxPressAction::None;
    auto &button=mButtons[index];
    if (down) {
      if (!button.down) button={true,false,now};
      return FxPressAction::None;
    }
    if (!button.down) return FxPressAction::None;
    const bool fired=button.fired;
    const double elapsed=now-button.started;
    button={};
    return fired || elapsed<0 ? FxPressAction::None :
           elapsed>=kHoldSeconds ? FxPressAction::Toggle : FxPressAction::Edit;
  }
  unsigned Tick(double now) noexcept {
    unsigned result=0;
    for (unsigned i=0;i<mButtons.size();++i) {
      auto &button=mButtons[i];
      if (button.down && !button.fired && now-button.started>=kHoldSeconds) {
        button.fired=true;result|=1u<<i;
      }
    }
    return result;
  }
private:
  struct Button { bool down=false, fired=false; double started=0; };
  std::array<Button,4> mButtons{};
};
// Soft takeover for non-motorized faders, rearmed on sound/automation changes.
class Pickup {
public:
  void Reset() noexcept { mSeen.fill(false); mCaught.fill(false); }
  void Reset(unsigned first, unsigned count) noexcept {
    for (unsigned i = first; i < mSeen.size() && i - first < count; ++i) {
      mSeen[i] = false; mCaught[i] = false;
    }
  }
  bool Accept(unsigned index, double value, double target) noexcept {
    if (index >= 9 || !std::isfinite(value) || !std::isfinite(target)) return false;
    if (mSeen[index] && std::abs(target - mTarget[index]) > 1e-6) mCaught[index] = false;
    mCaught[index] = mCaught[index] || std::abs(value - target) < .04 ||
                     (mSeen[index] && (mPrevious[index] - target) * (value - target) <= 0);
    mPrevious[index] = value;
    mTarget[index] = mCaught[index] ? value : target;
    mSeen[index] = true;
    return mCaught[index];
  }
  // Remember the parameter's actual value after snapping/normalization. The
  // next hardware event must not mistake our own rounding for automation.
  void Applied(unsigned index, double target) noexcept {
    if (index < 9 && std::isfinite(target)) mTarget[index] = target;
  }
private:
  std::array<bool, 9> mSeen{}, mCaught{};
  std::array<double, 9> mPrevious{}, mTarget{};
};
} // namespace krose::midi::essential
