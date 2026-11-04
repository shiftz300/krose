#include "samples/SampleBank.h"
#include "samples/ProgramLibrary.h"
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>
#include <stdexcept>
namespace segrand {
namespace {
uint32_t U32(const unsigned char *p) {
  return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
uint64_t U64(const unsigned char *p) { return uint64_t(U32(p)) | uint64_t(U32(p + 4)) << 32; }
} // namespace
std::shared_ptr<const SampleBank> SampleBank::Load(const std::string &path, bool preload) {
  // Construction only. Instances share immutable samples; no audio-thread locks.
  static std::mutex mutex;
  static std::map<std::string, std::weak_ptr<const SampleBank>> cache;
  std::lock_guard<std::mutex> lock(mutex);
  const auto key = path + (preload ? "#full" : "#metadata");
  if (auto existing = cache[key].lock())
    return existing;
  for (auto it = cache.begin(); it != cache.end();)
    if (it->second.expired())
      it = cache.erase(it);
    else
      ++it;
  std::ifstream file(std::filesystem::u8path(path), std::ios::binary | std::ios::ate);
  if (!file)
    throw std::runtime_error("Sample library is missing");
  const auto fileSize = file.tellg();
  if (fileSize < 32 || fileSize > 268435456)
    throw std::runtime_error("Invalid sample library size");
  file.seekg(0);
  unsigned char header[32];
  if (!file.read(reinterpret_cast<char *>(header), 32) || std::memcmp(header, "SEGRAND1", 8) ||
      (U32(header + 8) != 1 && U32(header + 8) != 2) || U32(header + 12) != 84 ||
      U32(header + 24) != 32)
    throw std::runtime_error("Invalid sample library header");
  const bool view = U32(header + 8) == 2;
  auto bank = std::make_shared<SampleBank>();
  bank->path = path;
  bank->preloaded = preload;
  uint64_t rateBits = U64(header + 16);
  std::memcpy(&bank->rootRate, &rateBits, 8);
  if (bank->rootRate != 42017.578125)
    throw std::runtime_error("Unsupported source playback rate");
  std::array<unsigned char, 84 * 32> descriptors;
  if (!file.read(reinterpret_cast<char *>(descriptors.data()), descriptors.size()))
    throw std::runtime_error("Incomplete sample table");
  uint64_t expectedOffset = 32 + descriptors.size();
  std::shared_ptr<const ProgramLibrary> factory;
  if (view) {
    if (uint64_t(fileSize) != expectedOffset)
      throw std::runtime_error("Invalid Concert reference size");
    const auto directory = std::filesystem::u8path(path).parent_path();
    auto factoryPath = directory / "Factory.samples";
    if (!std::filesystem::exists(factoryPath))
      factoryPath = directory.parent_path() / "program-library" / "Factory.samples";
    factory = ProgramLibrary::Load(factoryPath.u8string(), false);
  }
  unsigned previousLayer = 0, previousTop = 0;
  for (unsigned i = 0; i < 84; ++i) {
    const unsigned char *d = descriptors.data() + i * 32;
    const unsigned layer = U32(d), root = U32(d + 4), top = U32(d + 8), frames = U32(d + 12),
                   start = U32(d + 16), end = U32(d + 20);
    const uint64_t offset = U64(d + 24), bytes = uint64_t(frames) * 6;
    if (layer > 2 || layer != i / 28 || root > 127 || top > 127 || root > top || frames < 4 ||
        frames > 48000 * 60 || start >= end || end >= frames ||
        (!view && (offset != expectedOffset || offset + bytes > uint64_t(fileSize))) ||
        (i > 0 && layer == previousLayer && top <= previousTop))
      throw std::runtime_error("Invalid sample region");
    previousTop = top;
    previousLayer = layer;
    if (!view)
      expectedOffset += bytes;
    const std::array<uint32_t, 2> indices{{U32(d + 24), U32(d + 28)}};
    if (view)
      for (auto index : indices)
        if (index >= factory->samples.size() || factory->samples[index].frames != frames)
          throw std::runtime_error("Invalid Concert sample reference");
    Sample sample;
    sample.root = root;
    sample.top = top;
    sample.loopStart = start;
    sample.loopEnd = end;
    sample.frameCount = frames;
    if (preload) {
      sample.stereo.resize(static_cast<size_t>(frames) * 2);
      if (view) {
        const auto channels = factory->LoadSamples({indices[0], indices[1]}, false);
        for (size_t frame = 0; frame < frames; ++frame)
          for (size_t channel = 0; channel < 2; ++channel)
            std::memcpy(sample.stereo.data() + (frame * 2 + channel) * 3,
                        channels[indices[channel]]->data() + frame * 3, 3);
      } else {
        file.seekg(static_cast<std::streamoff>(offset));
        if (!file.read(reinterpret_cast<char *>(sample.stereo.data()), bytes))
          throw std::runtime_error("Incomplete sample payload");
      }
    }
    bank->layers[layer].push_back(std::move(sample));
  }
  if (expectedOffset != uint64_t(fileSize))
    throw std::runtime_error("Trailing sample payload data");
  cache[key] = bank;
  return bank;
}

const Sample &SampleBank::Select(unsigned layer, unsigned note) const {
  const auto &regions = layers.at(layer);
  for (const auto &sample : regions)
    if (note <= sample.top)
      return sample;
  return regions.back();
}

} // namespace segrand
