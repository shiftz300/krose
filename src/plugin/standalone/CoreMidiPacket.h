#pragma once
#include <CoreMIDI/CoreMIDI.h>
#include <array>
#include <cstddef>
#include <cstring>
#include <limits>
#include <new>
#include <vector>

namespace krose::standalone {
// CoreMIDI aligns every packet separately. Reserve its header and alignment
// padding for every 65535-byte fragment, not just for the first fragment.
class CoreMidiPacket {
public:
  static constexpr std::size_t kInlineBytes = 512;
  static std::size_t RequiredBytes(std::size_t size) noexcept {
    if (!size) return 0;
    constexpr auto limit = std::numeric_limits<std::size_t>::max();
    constexpr auto header = offsetof(MIDIPacket, data) + alignof(MIDIPacket) - 1;
    const auto packets = 1 + (size - 1) / 65535;
    const auto prefix = offsetof(MIDIPacketList, packet);
    if (packets > (limit - prefix) / header) return 0;
    const auto overhead = prefix + packets * header;
    if (size > limit - overhead) return 0;
    return size + overhead;
  }

  MIDIPacketList* Build(const unsigned char* message, std::size_t size,
                       MIDITimeStamp timestamp) noexcept {
    const auto capacity = RequiredBytes(size);
    if (!message || !capacity || size > std::numeric_limits<unsigned int>::max()) return nullptr;
    void* storage = mInline.data();
    if (capacity > mInline.size()) {
      const auto words = 1 + (capacity - 1) / sizeof(std::max_align_t);
      if (words > mHeap.max_size()) return nullptr;
      try { mHeap.resize(words); }
      catch (const std::bad_alloc&) { return nullptr; }
      storage = mHeap.data();
    }
    auto* list = static_cast<MIDIPacketList*>(storage);
    list->numPackets = 0;
    auto* packet = &list->packet[0];
    std::size_t offset = 0;
    while (offset < size) {
      const auto count = size - offset > 65535 ? 65535 : size - offset;
      // MIDIPacketListAdd may coalesce equal timestamps and wrap a UInt16
      // length at 65536 bytes. Construct separate aligned fragments explicitly.
      packet->timeStamp = timestamp;
      packet->length = static_cast<UInt16>(count);
      std::memcpy(packet->data, message + offset, count);
      ++list->numPackets;
      offset += count;
      packet = MIDIPacketNext(packet);
    }
    return list;
  }
private:
  alignas(MIDIPacketList) std::array<unsigned char, kInlineBytes> mInline{};
  std::vector<std::max_align_t> mHeap;
};
} // namespace krose::standalone
