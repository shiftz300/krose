#pragma once
#include "../Parameters.h"
#include <array>

namespace krose::midi::essential {
struct ParameterControl { int parameter; const char *label; };
// Software's left 2x3 matrix, followed by its right-side Volume knob.
// The last two hardware encoders have no matching software knob.
inline constexpr std::array<ParameterControl, 9> kKnobControls{{
    {kGlide,"Glide"}, {kParamProgram,"Value"}, {kParamPan,"Pan"},
    {kParamCutoff,"Cutoff"}, {kParamResonance,"Resonance"}, {kParamVelocity,"Velocity"},
    {kParamOutput,"Volume"}, {-1,"Unassigned"}, {-1,"Unassigned"}}};
inline constexpr std::array<int, 9> kFaderParameters{{
    kAmpAttack,kAmpDecay,kAmpSustain,kAmpRelease,
    kFilterAttack,kFilterDecay,kFilterSustain,kFilterRelease,kParamOutput}};
inline constexpr int FaderParameter(unsigned index, bool filter) {
  return index < 8 ? kFaderParameters[index ^ (filter ? 4u : 0u)] :
         index == 8 ? kParamOutput : -1;
}
inline constexpr std::array<int, 8> kPadParameters{{
    kArpEnabled,kArpLatch,kFxOn1,kFxOn2,kFxOn3,kFxOn4,kSW1State,kSW2State}};
} // namespace krose::midi::essential
