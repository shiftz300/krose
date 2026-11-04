#pragma once
#include "EngineTypes.h"
#include <algorithm>
#include <array>
#include <cstddef>

namespace segrand {
// Fixed storage and stable ordering for events at the same sample offset.
// Each engine owns a queue; no allocation or ownership crosses the audio thread.
template <size_t Capacity> class EventQueue {
public:
  void Push(MidiEvent event, bool normalizeData = true) noexcept {
    if (mSize == Capacity) {
      mOverflow = true;
      return;
    }
    event.offset = std::max(0, event.offset);
    if (normalizeData) {
      event.data1 &= 127;
      event.data2 &= 127;
    }
    unsigned at = mSize++;
    while (at && mEvents[at - 1].offset > event.offset) {
      mEvents[at] = mEvents[at - 1];
      --at;
    }
    mEvents[at] = event;
  }
  unsigned Size() const noexcept { return mSize; }
  bool Overflowed() const noexcept { return mOverflow; }
  const MidiEvent &operator[](unsigned index) const noexcept { return mEvents[index]; }
  const MidiEvent *Data() const noexcept { return mEvents.data(); }
  unsigned ReadyCount(int frames) const noexcept {
    unsigned count = 0;
    while (count < mSize && mEvents[count].offset < frames)
      ++count;
    return count;
  }
  void Advance(unsigned consumed, int frames) noexcept {
    for (unsigned i = consumed; i < mSize; ++i) {
      mEvents[i - consumed] = mEvents[i];
      mEvents[i - consumed].offset -= frames;
    }
    mSize -= consumed;
  }
  void Clear() noexcept {
    mSize = 0;
    mOverflow = false;
  }
  // Offline load failure discards queued notes while retaining overflow/Panic.
  void Discard() noexcept { mSize = 0; }

private:
  std::array<MidiEvent, Capacity> mEvents{};
  unsigned mSize = 0;
  bool mOverflow = false;
};
} // namespace segrand
