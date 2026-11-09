#include "standalone/CoreMidiPacket.h"
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>

int main() {
  using krose::standalone::CoreMidiPacket;
  CoreMidiPacket builder;
  const unsigned char byte = 0;
  assert(!builder.Build(nullptr, 3, 0));
  assert(!builder.Build(&byte, 0, 0));
  assert(!builder.Build(&byte, std::size_t(std::numeric_limits<unsigned int>::max()) + 1, 0));
  assert(!CoreMidiPacket::RequiredBytes(std::numeric_limits<std::size_t>::max()));
  // Exercise the inline/heap boundary and per-packet alignment, including
  // fragmented SysEx beyond CoreMIDI's 16-bit individual packet length.
  for (std::size_t size : {1u, 3u, 52u, 480u, 500u, 512u, 65534u, 65535u, 65536u, 131070u, 1048576u, 52u}) {
    std::vector<unsigned char> message(size);
    for (std::size_t i = 0; i < size; ++i) message[i] = (i * 7) % 128;
    auto* list = builder.Build(message.data(), size, 12345);
    assert(list && std::uintptr_t(list) % alignof(MIDIPacketList) == 0);
    auto* packet = &list->packet[0];
    std::size_t offset = 0;
    for (unsigned i = 0; i < list->numPackets; ++i) {
      if (packet->timeStamp != 12345 || packet->length == 0)
        std::cerr << "size=" << size << " packets=" << list->numPackets << " index=" << i
                  << " offset=" << offset << " length=" << packet->length << " timestamp=" << packet->timeStamp << '\n';
      assert(packet->timeStamp == 12345 && packet->length > 0);
      assert(offset + packet->length <= size);
      assert(std::equal(packet->data, packet->data + packet->length, message.data() + offset));
      offset += packet->length;
      packet = MIDIPacketNext(packet);
    }
    assert(offset == size);
  }
  std::cout << "CoreMIDI inline, long SysEx, alignment and size boundaries passed\n";
}
