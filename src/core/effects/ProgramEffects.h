#pragma once
#include "effects/FxRack.h"
#include <array>
#include <cstdint>
namespace segrand {
// Four editable host slots are retained. Native IDs and missing algorithms stay
// available to the editor; unsupported native algorithms are never mislabeled
// as bit-exact implementations or inherited from the previously selected sound.
struct ProgramEffects {
  FxSettings slots;
  std::array<int,4> sourceIDs{};
  std::array<int,4> sourceSlots{{-1,-1,5,6}};
  unsigned omittedInserts = 0;
  bool masterChain = false;
  static ProgramEffects Decode(const uint8_t *program) noexcept;
  static const char *Name(int effect) noexcept;
};
} // namespace segrand
