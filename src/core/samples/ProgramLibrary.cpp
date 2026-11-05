#include "samples/ProgramLibrary.h"
#include "samples/NativeSampleCodec.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>
#include <stdexcept>
namespace segrand {
namespace {
class Reader {
public:
  std::ifstream file;
  explicit Reader(const std::string &path) : file(std::filesystem::u8path(path), std::ios::binary) {
    if (!file)
      throw std::runtime_error("Factory sample library is missing");
  }
  void Bytes(void *target, size_t size) {
    if (!file.read(static_cast<char *>(target), std::streamsize(size)))
      throw std::runtime_error("Truncated factory library");
  }
  uint32_t U32() {
    uint8_t p[4];
    Bytes(p, 4);
    return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
  }
  int16_t I16() {
    uint8_t p[2];
    Bytes(p, 2);
    const uint16_t bits = uint16_t(p[0]) | (uint16_t(p[1]) << 8);
    int16_t v;
    std::memcpy(&v, &bits, 2);
    return v;
  }
  int32_t I32() {
    const auto bits = U32();
    int32_t v;
    std::memcpy(&v, &bits, 4);
    return v;
  }
  uint64_t U64() {
    const auto lo = U32();
    return uint64_t(lo) | (uint64_t(U32()) << 32);
  }
  float Float() {
    const auto bits = U32();
    float v;
    std::memcpy(&v, &bits, 4);
    return v;
  }
};
void Require(bool value) {
  if (!value)
    throw std::runtime_error("Invalid factory library");
}
} // namespace
std::shared_ptr<const ProgramLibrary> ProgramLibrary::Load(const std::string &path, bool preload) {
  static std::mutex mutex;
  static std::map<std::string, std::weak_ptr<const ProgramLibrary>> cache;
  const std::string key =
      std::filesystem::absolute(std::filesystem::u8path(path)).lexically_normal().u8string();
  std::lock_guard<std::mutex> lock(mutex); // Loading only, never called by audio processing.
  const auto cacheKey = key + (preload ? "#full" : "#metadata");
  if (auto existing = cache[cacheKey].lock())
    return existing;
  for (auto it = cache.begin(); it != cache.end();)
    if (it->second.expired())
      it = cache.erase(it);
    else
      ++it;
  Reader in(key);
  char magic[8];
  in.Bytes(magic, 8);
  const auto version = in.U32();
  Require((!std::memcmp(magic, "KRPRG002", 8) && version == 2) ||
          (!std::memcmp(magic, "KRPRG003", 8) && version == 3));
  const auto sampleCount = in.U32(), regionCount = in.U32(), programCount = in.U32();
  Require(sampleCount > 0 && sampleCount <= 8192 && regionCount > 0 && regionCount <= 262144 &&
          programCount > 0 && programCount <= 2048);
  const auto fileSize = std::filesystem::file_size(std::filesystem::u8path(key));
  Require(fileSize <= 512ull * 1024 * 1024);
  auto bank = std::make_shared<ProgramLibrary>();
  bank->mPath = key;
  bank->mPreload = preload;
  bank->mSampleCache.resize(sampleCount);
  for (auto &v : bank->mPhaseBase)
    v = in.U32();
  for (auto &v : bank->mPhaseFraction) {
    uint8_t p[2];
    in.Bytes(p, 2);
    v = uint16_t(p[0]) | (uint16_t(p[1]) << 8);
  }
  for (auto &v : bank->mCrossfade) {
    uint8_t p[2];
    in.Bytes(p, 2);
    v = uint16_t(p[0]) | (uint16_t(p[1]) << 8);
  }
  if (version == 3)
    for (auto &v : bank->mSampleLut)
      v = in.I16();
  bank->samples.resize(sampleCount);
  uint64_t expected = 24 + 224 * 4 + 256 * 2 + 129 * 2 + (version == 3 ? 512 : 0) +
                      uint64_t(sampleCount) * (version == 3 ? 40 : 32) +
                      uint64_t(regionCount) * 96 + uint64_t(programCount) * 2232;
  for (auto &sample : bank->samples) {
    sample.id = in.U32();
    const auto frames = in.U32();
    sample.loopStart = in.U32();
    sample.loopEnd = in.U32();
    sample.flags = in.U32();
    sample.pitch = in.I32();
    const auto offset = in.U64();
    Require(sample.id < 65536 && sample.pitch >= -32768 && sample.pitch <= 32767 && frames > 0 &&
            frames <= 48000 * 60 && sample.loopStart < frames && sample.loopEnd < frames &&
            sample.loopStart <= sample.loopEnd && offset == expected);
    sample.frames = frames;
    sample.offset = offset;
    if (version == 3) {
      sample.a1 = in.I16();
      sample.a2 = in.I16();
      sample.codec = in.U32();
      Require(sample.codec <= 2);
    }
    expected += uint64_t(frames) * (sample.codec == 1 ? 1 : sample.codec == 2 ? 2 : 3);
    Require(expected <= fileSize);
  }
  Require(expected == fileSize);
  bank->regions.resize(regionCount);
  for (auto &r : bank->regions) {
    r.sample[0] = in.U32();
    r.sample[1] = in.U32();
    r.noteLow = int(in.U32());
    r.noteHigh = int(in.U32());
    r.velocityLow = int(in.U32());
    r.velocityHigh = int(in.U32());
    r.root[0] = int(in.U32());
    r.fine[0] = in.I32();
    r.root[1] = int(in.U32());
    r.fine[1] = in.I32();
    r.oscillator = int(in.U32());
    r.slotLevel = int(in.U32());
    r.pan = int(in.U32());
    r.exclusive = int(in.U32());
    r.flags = int(in.U32());
    r.gain = in.Float();
    r.coarse = in.I32();
    r.drumFine = in.I32();
    r.slot = in.I32();
    r.fadeInWidth = in.I32();
    r.fadeInCurve = in.I32();
    r.fadeOutBottom = in.I32();
    r.fadeOutWidth = in.I32();
    r.fadeOutCurve = in.I32();
    Require(r.sample[0] < sampleCount && (r.sample[1] == UINT32_MAX || r.sample[1] < sampleCount) &&
            r.noteLow >= 0 && r.noteHigh <= 127 && r.noteLow <= r.noteHigh && r.velocityLow >= 1 &&
            r.velocityHigh <= 127 && r.velocityLow <= r.velocityHigh && r.root[0] >= 0 &&
            r.root[0] <= 127 && r.root[1] >= 0 && r.root[1] <= 127 &&
            std::abs(int64_t(r.fine[0])) <= 32768 && std::abs(int64_t(r.fine[1])) <= 32768 &&
            r.oscillator >= 0 && r.oscillator < 2 && r.slotLevel >= 0 && r.slotLevel <= 127 &&
            r.pan >= 0 && r.pan <= 127 && r.exclusive >= 0 && r.exclusive <= 127 && r.flags >= 0 &&
            r.flags < 16 && std::isfinite(r.gain) && r.gain >= 0 && r.gain <= 8 &&
            r.coarse >= -255 && r.coarse <= 255 && r.drumFine >= -199 && r.drumFine <= 199 &&
            r.slot >= 0 && r.slot < 4 && r.fadeInWidth >= 0 && r.fadeInWidth <= 127 &&
            r.fadeOutWidth >= 0 && r.fadeOutWidth <= 127 && r.fadeInCurve >= 0 &&
            r.fadeInCurve <= 3 && r.fadeOutCurve >= 0 && r.fadeOutCurve <= 3 &&
            r.fadeOutBottom >= 0 && r.fadeOutBottom <= 127);
  }
  bank->programs.resize(programCount);
  bank->mProgramWindows.resize(programCount);
  for (auto &p : bank->programs) {
    in.Bytes(p.id.data(), p.id.size());
    in.Bytes(p.name.data(), p.name.size());
    const auto kind = in.U32();
    p.drum = kind != 0;
    p.firstRegion = in.U32();
    p.regionCount = in.U32();
    in.Bytes(p.controls.data(), p.controls.size());
    Require(kind <= 1 && p.id.back() == 0 && p.name.back() == 0 && p.regionCount > 0 &&
            uint64_t(p.firstRegion) + p.regionCount <= regionCount);
    if (!p.drum)
      for (unsigned phase=0;phase<4;++phase)
        Require(p.controls[0x520+8+phase]<=10);
    for (auto &osc : p.lookup)
      for (auto &note : osc)
        note.fill(-1);
    for (unsigned o = 0; o < 2; ++o) {
      const auto *base = p.controls.data() + 0x564 + 380 * o;
      for (unsigned stage = 0; stage < 4; ++stage)
        Require(base[0x118 + stage * 2 + 1] < 100 && base[0x118 + 8 + stage] <= 10 &&
                base[0xd8 + 5 + stage * 2] < 100 && base[0xd8 + stage] <= 10);
    }
    for (uint32_t i = p.firstRegion; i < p.firstRegion + p.regionCount; ++i) {
      const auto &r = bank->regions[i];
      Require(p.drum == bool(r.flags & 8));
      for (int n = r.noteLow; n <= r.noteHigh; ++n) {
        Require(p.lookup[r.oscillator][n][r.slot] == -1);
        p.lookup[r.oscillator][n][r.slot] = int32_t(i);
      }
    }
  }
  if (preload)
    for (auto &sample : bank->samples) {
      Require(uint64_t(in.file.tellg()) == sample.offset);
      ReadSamplePCM(in.file, sample.codec, sample.a1, sample.a2, bank->mSampleLut, sample.frames,
                    sample.pcm);
    }
  cache[cacheKey] = bank;
  return bank;
}
std::shared_ptr<const SampleWindow> ProgramLibrary::LoadProgram(unsigned program) const {
  if (program >= programs.size())
    throw std::out_of_range("Program index");
  std::lock_guard<std::mutex> lock(mCacheMutex);
  auto &cached = mProgramWindows[program];
  if (auto window = cached.lock())
    return window;
  std::vector<uint32_t> indices;
  const auto &p = programs[program];
  for (uint32_t r = p.firstRegion; r < p.firstRegion + p.regionCount; ++r)
    for (auto index : regions[r].sample)
      if (index != UINT32_MAX)
        indices.push_back(index);
  auto window = std::make_shared<const SampleWindow>(LoadSamplesLocked(indices, true));
  cached = window;
  return window;
}
SampleWindow ProgramLibrary::LoadSamples(const std::vector<uint32_t> &indices, bool retainRecent) const {
  std::lock_guard<std::mutex> lock(mCacheMutex);
  return LoadSamplesLocked(indices, retainRecent);
}
SampleWindow ProgramLibrary::LoadSamplesLocked(const std::vector<uint32_t> &indices,
                                                bool retainRecent) const {
  SampleWindow result(samples.size());
  std::ifstream file(std::filesystem::u8path(mPath), std::ios::binary);
  if (!file)
    throw std::runtime_error("Factory samples unavailable");
  for (auto index : indices) {
    if (index >= samples.size())
      throw std::out_of_range("Sample index");
    if (result[index])
      continue;
    auto pcm = mSampleCache[index].lock();
    if (!pcm) {
      const auto &sample = samples[index];
      auto loaded = std::make_shared<PCM24>();
      file.seekg(std::streamoff(sample.offset));
      ReadSamplePCM(file, sample.codec, sample.a1, sample.a2, mSampleLut, sample.frames, *loaded);
      pcm = std::move(loaded);
      mSampleCache[index] = pcm;
    }
    result[index] = pcm;
    if (!retainRecent)
      continue; // Concert interleaves into its own buffer; do not retain a second copy.
    auto recent = std::find_if(mRecent.begin(), mRecent.end(),
                               [&](const auto &entry) { return entry.get() == pcm.get(); });
    if (recent != mRecent.end())
      mRecent.splice(mRecent.end(), mRecent, recent);
    else {
      mRecent.push_back(pcm);
      mRecentBytes += pcm->storageBytes();
    }
    // Active voices/snapshots keep their own pins. Only unneeded cache references go away.
    while (mRecentBytes > 32u * 1024 * 1024 && !mRecent.empty()) {
      mRecentBytes -= mRecent.front()->storageBytes();
      mRecent.pop_front();
    }
  }
  return result;
}
size_t ProgramLibrary::ResidentBytes() const {
  std::lock_guard<std::mutex> lock(mCacheMutex);
  size_t bytes = PCMBytes();
  for (const auto &weak : mSampleCache)
    if (auto pcm = weak.lock())
      bytes += pcm->storageBytes();
  return bytes;
}
uint32_t ProgramLibrary::Phase(int exponent) const noexcept {
  const auto index = unsigned(std::clamp(exponent, -32768, 24575) + 32768);
  const uint32_t base = mPhaseBase[index >> 8];
  return base + uint32_t((uint64_t(base) * mPhaseFraction[index & 255]) >> 16);
}
double ProgramLibrary::Step(const InstrumentProgram &p, const ProgramRegion &r, int channel,
                            int note, double rate, int modulation) const noexcept {
  const auto &s = samples[r.sample[channel]];
  if (r.flags & 8)
    return 48000.0 * Phase(s.pitch * 2) / 8192 / rate *
           std::pow(2, (r.coarse + r.drumFine / 100.0) / 12);
  const int fine = (std::abs(r.fine[channel]) * 1311 / 1024) * (r.fine[channel] < 0 ? -1 : 1);
  const int pitch = SelectionPitch(p, r.oscillator, note);
  // Oscillator Tune affects playback in cents. Sample selection uses the coarse pitch.
  const auto *osc = p.controls.data() + 0x564 + 380 * r.oscillator;
  const int tuneBits = osc[0x7a] | (osc[0x7b] << 8);
  const int tuneCents = tuneBits < 32768 ? tuneBits : tuneBits - 65536;
  const int tune = (tuneCents * 256 + (tuneCents < 0 ? -50 : 50)) / 100;
  int state = int(int16_t(r.root[channel] * 256 - fine - s.pitch * 2));
  if (r.flags & (2 << channel))
    state += pitch - r.root[channel] * 256;
  const int exponent = int(int16_t(pitch - state + tune + modulation));
  uint32_t limit = (s.flags & 1) ? 32768 : 2097151;
  if (!(s.flags & 33)) {
    const auto length = s.loopEnd - s.loopStart;
    if (length <= 255)
      limit = length <= 15    ? 65536
              : length <= 31  ? 131072
              : length <= 63  ? 262144
              : length <= 127 ? 524288
                              : 1048576;
  }
  return 48000.0 * std::min(Phase(exponent), limit) / 8192 / rate;
}
int ProgramLibrary::SelectionPitch(const InstrumentProgram &p, int oscillator, int note) noexcept {
  const auto *b = p.controls.data() + 0x564 + 380 * oscillator;
  const auto signedByte = [](uint8_t x) { return x < 128 ? int(x) : int(x) - 256; };
  const int slope = signedByte(b[0x7c]),
            transpose = signedByte(uint8_t(12 * signedByte(b[0x78]) + b[0x79]));
  int value = slope == 0     ? 60 * 256
              : slope == 10  ? note * 256
              : slope == -10 ? (120 - note) * 256
              : slope == 20  ? std::clamp(512 * note - 60 * 256, 0, 32767)
                             : std::clamp(60 * 256 + ((820 * note - 49200) * slope >> 5), 0, 32767);
  int folded = transpose + (value >> 8);
  while (folded < 0)
    folded += 12;
  while (folded > 127)
    folded -= 12;
  return (folded << 8) | (value & 255);
}
int ProgramLibrary::LayerWeight(const ProgramRegion &r, int velocity) const noexcept {
  if (velocity < r.velocityLow || velocity > r.velocityHigh)
    return 0;
  auto shape = [&](int value, int curve) {
    if (curve == 2)
      return 32768;
    if (curve != 1 || value >= 32768)
      return value;
    const int index = value >> 8, fraction = value & 255;
    return int(mCrossfade[index]) +
           ((int(mCrossfade[index + 1]) - mCrossfade[index]) * fraction >> 8);
  };
  if (r.fadeOutWidth && velocity >= r.fadeOutBottom)
    return shape(
        std::clamp(32768 - (velocity - r.fadeOutBottom) * 32768 / r.fadeOutWidth, 0, 32768),
        r.fadeOutCurve);
  if (r.fadeInWidth && velocity < r.velocityLow + r.fadeInWidth)
    return shape(std::clamp((velocity - r.velocityLow) * 32768 / r.fadeInWidth, 0, 32768),
                 r.fadeInCurve);
  return 32768;
}
size_t ProgramLibrary::PCMBytes() const noexcept {
  size_t n = 0;
  for (const auto &s : samples)
    n += s.pcm.storageBytes();
  return n;
}
} // namespace segrand
