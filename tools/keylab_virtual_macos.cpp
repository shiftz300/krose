// Software-only MIDI acceptance device. Build on macOS with:
// clang++ -std=c++17 tools/keylab_virtual_macos.cpp -framework CoreMIDI
//   -framework CoreFoundation -o /tmp/krose-keylab-virtual
// Enter hexadecimal MIDI bytes on stdin; q disposes both temporary endpoints.
#include <CoreMIDI/CoreMIDI.h>
#include <CoreFoundation/CoreFoundation.h>
#include <array>
#include <iostream>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <thread>
#include <vector>
namespace {
MIDIEndpointRef source = 0;
std::mutex logMutex;
void send(const std::vector<unsigned char> &bytes) {
  if (bytes.empty() || bytes.size() > 1024) return;
  alignas(MIDIPacketList) std::array<unsigned char, 2048> storage{};
  auto *list = reinterpret_cast<MIDIPacketList *>(storage.data());
  auto *packet = MIDIPacketListInit(list);
  if (MIDIPacketListAdd(list, storage.size(), packet, 0, bytes.size(), bytes.data()))
    MIDIReceived(source, list);
}
void receive(const MIDIPacketList *packets, void *, void *) {
  const auto *packet = &packets->packet[0];
  for (unsigned i = 0; i < packets->numPackets; ++i) {
    {
      std::lock_guard<std::mutex> lock(logMutex);
      std::cout << "RX";
      for (unsigned j = 0; j < packet->length; ++j)
        std::cout << ' ' << std::hex << std::setw(2) << std::setfill('0') << unsigned(packet->data[j]);
      std::cout << std::dec << std::endl;
    }
    if (packet->length >= 6 && packet->data[0] == 0xf0 && packet->data[1] == 0x7e && packet->data[3] == 6 && packet->data[4] == 1)
      send({0xf0,0x7e,0x7f,6,2,0,0x20,0x6b,2,0,5,0,1,0,0,0,0xf7});
    if (packet->length >= 11 && packet->data[0] == 0xf0 && packet->data[6] == 0x21)
      send({0xf0,0,0x20,0x6b,0x7f,0x42,0x21,0x11,0x40,2,0,1,0xf7});
    packet = MIDIPacketNext(packet);
  }
}
}
int main() {
  MIDIClientRef client = 0;
  MIDIEndpointRef destination = 0;
  const auto name = CFSTR("KL Essential 49 mk3 Test (MIDI)");
  if (MIDIClientCreate(CFSTR("Krose software controller test"), nullptr, nullptr, &client) ||
      MIDISourceCreate(client, name, &source) ||
      MIDIDestinationCreate(client, name, receive, nullptr, &destination)) return 1;
  auto loop = CFRunLoopGetCurrent();
  std::cout << "READY" << std::endl;
  std::thread commands([loop] {
    std::string line;
    while (std::getline(std::cin, line) && line != "q") {
      std::istringstream input(line);
      unsigned value;
      std::vector<unsigned char> bytes;
      while (input >> std::hex >> value) {
        if (value > 255) { bytes.clear(); break; }
        bytes.push_back(static_cast<unsigned char>(value));
      }
      send(bytes);
    }
    CFRunLoopStop(loop);
  });
  CFRunLoopRun();
  commands.join();
  MIDIEndpointDispose(destination);
  MIDIEndpointDispose(source);
  MIDIClientDispose(client);
}
