#pragma once
#include "samples/PCM24.h"
#include <array>
#include <cstdint>
#include <list>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
namespace segrand {
using SampleWindow = std::vector<std::shared_ptr<const PCM24>>;
struct SharedSample {
  uint32_t id = 0, loopStart = 0, loopEnd = 0, flags = 0;
  int pitch = 0;
  uint32_t frames = 0;
  uint64_t offset = 0;
  int16_t a1 = 0, a2 = 0;
  uint32_t codec = 0;
  PCM24 pcm; // Mono, stored once and shared by all regions/instances.
};
struct ProgramRegion {
  std::array<uint32_t, 2> sample{};
  int noteLow = 0, noteHigh = 127, velocityLow = 1, velocityHigh = 127;
  std::array<int, 2> root{}, fine{};
  int oscillator = 0, slotLevel = 127, pan = 64, exclusive = 0, flags = 0, coarse = 0, drumFine = 0;
  double gain = 1;
  int slot = 0, fadeInWidth = 0, fadeInCurve = 0, fadeOutBottom = 0, fadeOutWidth = 0,
      fadeOutCurve = 0;
};
struct InstrumentProgram {
  std::array<char, 16> id{};
  std::array<char, 64> name{};
  bool drum = false;
  uint32_t firstRegion = 0, regionCount = 0;
  std::array<uint8_t, 2140> controls{};
  // Precompiled OSC/key/slot selection: four bounded slots, no allocation.
  std::array<std::array<std::array<int32_t, 4>, 128>, 2> lookup{};
};
class ProgramLibrary {
public:
  // The returned bank is immutable; loading/caching is a non-audio-thread operation.
  static std::shared_ptr<const ProgramLibrary> Load(const std::string &path, bool preload = true);
  bool OnDemand() const noexcept { return !mPreload; }
  // Worker/lifecycle thread only. Cache is shared by plugin instances.
  std::shared_ptr<const SampleWindow> LoadProgram(unsigned program) const;
  SampleWindow LoadSamples(const std::vector<uint32_t> &indices, bool retainRecent = true) const;
  size_t ResidentBytes() const;
  std::vector<SharedSample> samples;
  std::vector<ProgramRegion> regions;
  std::vector<InstrumentProgram> programs;
  double Step(const InstrumentProgram &program, const ProgramRegion &region, int channel, int note,
              double sampleRate, int modulation = 0) const noexcept;
  size_t PCMBytes() const noexcept;
  int LayerWeight(const ProgramRegion &region, int velocity) const noexcept;
  static int SelectionPitch(const InstrumentProgram &program, int oscillator, int note) noexcept;

private:
  std::string mPath;
  bool mPreload = true;
  mutable std::mutex mCacheMutex;
  mutable std::vector<std::weak_ptr<const PCM24>> mSampleCache;
  mutable std::vector<std::weak_ptr<const SampleWindow>> mProgramWindows;
  mutable std::list<std::shared_ptr<const PCM24>> mRecent;
  mutable size_t mRecentBytes = 0;
  std::array<uint32_t, 224> mPhaseBase{};
  std::array<uint16_t, 256> mPhaseFraction{};
  std::array<uint16_t, 129> mCrossfade{};
  std::array<int16_t, 256> mSampleLut{};
  uint32_t Phase(int exponent) const noexcept;
  SampleWindow LoadSamplesLocked(const std::vector<uint32_t> &indices, bool retainRecent) const;
};
} // namespace segrand
