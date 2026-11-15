#include "ExpansionLoader.h"
#include "KepDecodeContext.h"
#include "zlib.h"

#include <algorithm>
#include <fstream>
#include <random>
#include <stdexcept>
#include <string_view>
#include <utility>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <bcrypt.h>
#include <vector>
#else
#include <CommonCrypto/CommonDigest.h>
#endif

namespace krose::storage {
namespace fs = std::filesystem;
namespace {
using Bytes = std::vector<unsigned char>;

std::string SHA256(const Bytes &data) {
  std::array<unsigned char, 32> hash{};
#ifdef _WIN32
  struct Digest {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    std::vector<unsigned char> state;
    ~Digest() {
      if (hash) BCryptDestroyHash(hash);
      if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    }
  } digest;
  ULONG stateSize = 0, written = 0;
  if (BCryptOpenAlgorithmProvider(&digest.algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0 ||
      BCryptGetProperty(digest.algorithm, BCRYPT_OBJECT_LENGTH,
                       reinterpret_cast<PUCHAR>(&stateSize), sizeof(stateSize), &written, 0) < 0)
    throw std::runtime_error("SHA256 UNAVAILABLE");
  digest.state.resize(stateSize);
  if (BCryptCreateHash(digest.algorithm, &digest.hash, digest.state.data(), stateSize, nullptr, 0, 0) < 0 ||
      BCryptHashData(digest.hash, const_cast<PUCHAR>(data.data()), ULONG(data.size()), 0) < 0 ||
      BCryptFinishHash(digest.hash, hash.data(), ULONG(hash.size()), 0) < 0)
    throw std::runtime_error("SHA256 UNAVAILABLE");
#else
  CC_SHA256(data.data(), static_cast<CC_LONG>(data.size()), hash.data());
#endif
  constexpr char digits[] = "0123456789abcdef";
  std::string hex;
  hex.reserve(64);
  for (auto byte : hash) {
    hex.push_back(digits[byte >> 4]);
    hex.push_back(digits[byte & 15]);
  }
  return hex;
}

uint32_t ReadLE(const unsigned char *p) {
  return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
uint32_t ReadLE16(const unsigned char *p) {
  return uint32_t(p[0]) | uint32_t(p[1]) << 8;
}

Bytes ReadZipKep(Bytes &archive) {
  // Official KORG ZIPs store ordinary local entries with explicit lengths.
  // Only a supported KEP member is read into memory. Filenames are never used as paths.
  for (size_t position = 0; archive.size() - position >= 30;) {
    auto *entry = archive.data() + position;
    if (ReadLE(entry) != 0x04034b50) break;
    const auto flags = ReadLE16(entry + 6), method = ReadLE16(entry + 8);
    const auto compressed = ReadLE(entry + 18), expanded = ReadLE(entry + 22);
    const auto length = ReadLE16(entry + 26), extras = ReadLE16(entry + 28);
    const size_t header = 30 + length + extras;
    const auto remaining = archive.size() - position;
    if ((flags & 9) || header > remaining || compressed > remaining - header)
      throw std::runtime_error("UNSUPPORTED OR DAMAGED ZIP");
    const std::string_view path(reinterpret_cast<const char *>(entry + 30), length);
    const auto separator = path.find_last_of("/\\");
    const auto name = separator == std::string_view::npos ? path : path.substr(separator + 1);
    for (const auto &pack : kExpansions) {
      if (name != std::string(pack.file, 8) + ".KEP") continue;
      if (expanded != pack.kepSize) throw std::runtime_error("UNSUPPORTED .KEP FILE");
      auto *source = entry + header;
      if (method == 0 && compressed == expanded) return Bytes(source, source + compressed);
      if (method != 8) throw std::runtime_error("UNSUPPORTED ZIP COMPRESSION");
      Bytes kep(expanded);
      z_stream stream{};
      stream.next_in = source;
      stream.avail_in = compressed;
      stream.next_out = kep.data();
      stream.avail_out = expanded;
      if (inflateInit2(&stream, -MAX_WBITS) != Z_OK)
        throw std::runtime_error("CANNOT OPEN EXPANSION ZIP");
      const int result = inflate(&stream, Z_FINISH);
      inflateEnd(&stream);
      if (result != Z_STREAM_END || stream.total_in != compressed || stream.total_out != expanded)
        throw std::runtime_error("DAMAGED EXPANSION ZIP");
      return kep;
    }
    position += header + compressed;
  }
  throw std::runtime_error("NO SUPPORTED .KEP IN ZIP");
}
void WriteLE(unsigned char *p, uint32_t v) {
  for (unsigned i = 0; i < 4; ++i) p[i] = static_cast<unsigned char>(v >> (i * 8));
}
uint32_t Round(uint32_t x) {
  const auto *s = kKepDecodeContext.data() + 18;
  return ((s[x & 255] + s[256 + ((x >> 8) & 255)]) ^ s[512 + ((x >> 16) & 255)]) +
         s[768 + (x >> 24)];
}
void Decode(Bytes &bytes) {
  for (size_t offset = 0; offset < bytes.size(); offset += 8) {
    auto *block = bytes.data() + offset;
    uint32_t left = ReadLE(block), right = ReadLE(block + 4);
    for (int round = 17; round >= 2; --round) {
      left ^= kKepDecodeContext[round];
      right ^= Round(left);
      std::swap(left, right);
    }
    WriteLE(block, right ^ kKepDecodeContext[0]);
    WriteLE(block + 4, left ^ kKepDecodeContext[1]);
  }
}

bool HasSize(const fs::path &file, uint64_t size) {
  std::error_code error;
  return !file.empty() && fs::is_regular_file(file, error) && fs::file_size(file, error) == size &&
         !error;
}

std::string TemporarySuffix() {
  std::random_device random;
  return std::to_string(random()) + "-" + std::to_string(random());
}
void WriteAtomically(const fs::path &path, const Bytes &data) {
  auto directory = path.parent_path();
  fs::create_directories(directory);
  directory /= ".install-" + TemporarySuffix();
  if (!fs::create_directory(directory)) throw std::runtime_error("EXPANSION STORAGE BUSY");
  struct Cleanup {
    fs::path folder;
    ~Cleanup() { std::error_code error; fs::remove_all(folder, error); }
  } cleanup{directory};
  auto temporary = directory / "payload";
  std::ofstream file(temporary, std::ios::binary);
  if (!data.empty()) file.write(reinterpret_cast<const char *>(data.data()), data.size());
  file.close();
  if (!file) throw std::runtime_error("CANNOT WRITE EXPANSION");
  fs::rename(temporary, path);
}

void RemoveInstalledPayload(const fs::path &file) {
#ifdef _WIN32
  // Renaming first frees the stable name for a reinstall even while a host
  // owns a read handle. Windows releases the removed payload when that handle closes.
  if (fs::exists(file)) {
    auto removed = file;
    removed += ".unload-" + TemporarySuffix();
    if (!MoveFileExW(file.c_str(), removed.c_str(), 0))
      throw std::runtime_error("CANNOT UNLOAD EXPANSION");
    if (!DeleteFileW(removed.c_str())) {
      MoveFileExW(removed.c_str(), file.c_str(), 0);
      throw std::runtime_error("CANNOT REMOVE EXPANSION");
    }
  }
#else
  fs::remove(file);
#endif
}
} // namespace

ExpansionLoader::ExpansionLoader(fs::path userDirectory, fs::path defaultOasys)
    : mUserDirectory(std::move(userDirectory)), mDefaultOasys(std::move(defaultOasys)) {}

fs::path ExpansionLoader::Source(const ExpansionInfo &pack) const {
  const auto installed = mUserDirectory / pack.file;
  if (HasSize(installed, pack.pcmSize))
    return installed;
  if (pack.number == 1 && HasSize(mDefaultOasys, pack.pcmSize))
    return mDefaultOasys;
  return {};
}

bool ExpansionLoader::Installed(const ExpansionInfo &pack) const {
  return !Source(pack).empty();
}
segrand::ExpansionPaths ExpansionLoader::Sources() const {
  segrand::ExpansionPaths paths;
  for (const auto &pack : kExpansions)
    paths[pack.number] = Source(pack).u8string();
  return paths;
}

unsigned ExpansionLoader::Install(const fs::path &file, const segrand::ProgramLibrary &library) {
  if (!library.Split()) throw std::runtime_error("EXPANSION LOADER UNAVAILABLE");
  if (!fs::is_regular_file(file)) throw std::runtime_error("SELECT AN EXPCM .KEP OR ZIP");
  const auto size = fs::file_size(file);
  if (size < 4 || size > 64u * 1024 * 1024) throw std::runtime_error("UNSUPPORTED EXPANSION FILE");
  Bytes original(static_cast<size_t>(size));
  std::ifstream input(file, std::ios::binary);
  if (!input.read(reinterpret_cast<char *>(original.data()), original.size()) ||
      input.peek() != std::char_traits<char>::eof())
    throw std::runtime_error("CANNOT READ EXPANSION FILE");
  if (ReadLE(original.data()) == 0x04034b50) original = ReadZipKep(original);
  const auto pack = std::find_if(kExpansions.begin(), kExpansions.end(),
                                [&](const auto &entry) { return original.size() == entry.kepSize; });
  if (pack == kExpansions.end()) throw std::runtime_error("UNSUPPORTED .KEP FILE");
  if (SHA256(original) != pack->kepHash)
    throw std::runtime_error("UNRECOGNIZED OR DAMAGED .KEP");
  if (Installed(*pack)) return pack->number;

  Decode(original);
  // The three allowlisted inputs have identical EXP1 layout. Keep only the
  // waveform bytes referenced by this build, in native descriptor order.
  constexpr size_t prmStart = 208;
  const size_t sampleCount = ReadLE(original.data() + 0x9c);
  const size_t prmSize = ReadLE(original.data() + 200);
  const size_t pcmStart = prmStart + prmSize + 16;
  if (ReadLE(original.data()) != 0x47524f4b || pcmStart > original.size() ||
      sampleCount > prmSize / 64)
    throw std::runtime_error("INVALID EXPANSION TABLE");
  const size_t pcmSize = ReadLE(original.data() + pcmStart - 8);
  if (pcmSize > original.size() - pcmStart)
    throw std::runtime_error("INVALID EXPANSION PCM");
  Bytes native(pack->pcmSize);
  size_t written = 0;
  for (const auto &sample : library.samples) {
    if (sample.id / 10000 != pack->number) continue;
    const size_t index = sample.id % 10000;
    if (index >= sampleCount || sample.offset != written || sample.frames > native.size() - written)
      throw std::runtime_error("EXPANSION DOES NOT MATCH THIS BUILD");
    const auto *descriptor = original.data() + prmStart + index * 64;
    const size_t start = ReadLE(descriptor + 12);
    const size_t end = ReadLE(descriptor + 24);
    if (start > end || end >= pcmSize || end - start + 1 != sample.frames)
      throw std::runtime_error("INVALID EXPANSION WAVEFORM");
    std::copy_n(original.data() + pcmStart + start, sample.frames, native.data() + written);
    written += sample.frames;
  }
  if (written != native.size()) throw std::runtime_error("EXPANSION DOES NOT MATCH THIS BUILD");

  WriteAtomically(mUserDirectory / pack->file, native);
  return pack->number;
}

void ExpansionLoader::Uninstall(const ExpansionInfo &pack) {
  // The installer grants deletion of the shared file itself. The parent
  // directory remains protected, so this path needs no rename or directory write.
  if (pack.number == 1 && !mDefaultOasys.empty())
    fs::remove(mDefaultOasys);
  RemoveInstalledPayload(mUserDirectory / pack.file);
}
} // namespace krose::storage
