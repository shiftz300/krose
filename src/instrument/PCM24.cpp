#include "PCM24.h"
#include <limits>
#include <new>
#include <utility>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <sys/mman.h>
#endif
namespace segrand {
PCM24::~PCM24() { clear(); }
void PCM24::clear() noexcept {
  if (mMappedBytes) {
#ifdef _WIN32
    VirtualFree(mData, 0, MEM_RELEASE);
#else
    munmap(mData, mMappedBytes);
#endif
  }
  mData = nullptr;
  mSize = mMappedBytes = 0;
  std::vector<uint8_t>().swap(mSmall);
}
PCM24::PCM24(PCM24 &&other) noexcept { *this = std::move(other); }
PCM24 &PCM24::operator=(PCM24 &&other) noexcept {
  if (this == &other)
    return *this;
  clear();
  mSmall = std::move(other.mSmall);
  mData = other.mData;
  mSize = other.mSize;
  mMappedBytes = other.mMappedBytes;
  other.mData = nullptr;
  other.mSize = other.mMappedBytes = 0;
  return *this;
}
void PCM24::resize(std::size_t samples) {
  if (samples > (std::numeric_limits<std::size_t>::max() - 1) / 3)
    throw std::bad_alloc();
  clear();
  if (!samples)
    return;
  const auto bytes = samples * 3 + 1;
  // Anonymous memory, not file-backed streaming. The worker reads/touches the
  // whole PCM before publication. Large blocks return to the OS on retirement
  // instead of accumulating in the host process's general-purpose heap cache.
  if (bytes >= 256u * 1024) {
#ifdef _WIN32
    auto *memory = VirtualAlloc(nullptr, bytes, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (!memory)
      throw std::bad_alloc();
#else
    auto *memory = mmap(nullptr, bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (memory == MAP_FAILED)
      throw std::bad_alloc();
#endif
    mData = static_cast<uint8_t *>(memory);
    mMappedBytes = bytes;
    mData[bytes - 1] = 0; // Prefault the decoder's guard byte as well.
  } else {
    mSmall.resize(bytes);
    mData = mSmall.data();
  }
  mSize = samples;
}
} // namespace segrand
