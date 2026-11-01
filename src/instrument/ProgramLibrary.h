#pragma once
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
namespace segrand {
struct SharedSample {
  uint32_t id=0,loopStart=0,loopEnd=0,flags=0;
  int pitch=0;
  std::vector<float> pcm; // Mono, stored once and shared by all regions/instances.
};
struct ProgramRegion {
  std::array<uint32_t,2> sample{};
  int noteLow=0,noteHigh=127,velocityLow=1,velocityHigh=127;
  std::array<int,2> root{},fine{};
  int oscillator=0,slotLevel=127,pan=64,exclusive=0,flags=0,coarse=0,drumFine=0;
  double gain=1;
};
struct InstrumentProgram {
  std::array<char,16> id{};
  std::array<char,64> name{};
  bool drum=false;
  uint32_t firstRegion=0,regionCount=0;
  std::array<uint8_t,2140> controls{};
  // Precompiled note/velocity selection: no searching/allocating in Process.
  std::array<std::array<std::array<int32_t,128>,128>,2> lookup{};
};
class ProgramLibrary {
public:
  // The returned bank is immutable; loading/caching is a non-audio-thread operation.
  static std::shared_ptr<const ProgramLibrary> Load(const std::string& path);
  std::vector<SharedSample> samples;
  std::vector<ProgramRegion> regions;
  std::vector<InstrumentProgram> programs;
  double Step(const ProgramRegion& region,int channel,int note,double sampleRate) const noexcept;
  size_t PCMBytes() const noexcept;
private:
  std::array<uint32_t,224> mPhaseBase{};
  std::array<uint16_t,256> mPhaseFraction{};
  uint32_t Phase(int exponent) const noexcept;
};
}
