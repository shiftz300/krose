#pragma once
#include <array>
#include <cstdint>
namespace segrand {
inline constexpr int kArpPatternCount = 1285;
struct ArpStep {
  int pitch=0, gate=0, velocity=128, flam=0;
  unsigned tones=0;
};
struct ArpPattern {
  const unsigned char *bytes = nullptr;
  int Length() const noexcept;
  unsigned Flags() const noexcept { return bytes ? bytes[24] : 0; }
  unsigned SwingGrid() const noexcept { return bytes ? bytes[26] : 0; }
  int Note(unsigned tone) const noexcept { return bytes ? bytes[28+tone%12]&127 : 0; }
  ArpStep Step(unsigned index) const noexcept;
};
ArpPattern Pattern(int index) noexcept;
std::array<char,25> ArpPatternName(int index) noexcept;
} // namespace segrand
