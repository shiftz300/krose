#include "midi/EventQueue.h"
#include <cassert>
#include <iostream>
using namespace segrand;
int main() {
  EventQueue<4> queue;
  queue.Push({128, 0x90, 60, 255});
  queue.Push({-1, 0x90, 61, 100});
  queue.Push({128, 0x80, 60, 0});
  queue.Push({256, 0x90, 62, 99});
  assert(queue.Size() == 4 && queue[0].data1 == 61 && queue[0].offset == 0);
  assert(queue[1].status == 0x90 && queue[1].data2 == 127 && queue[2].status == 0x80);
  assert(queue.ReadyCount(128) == 1);
  queue.Advance(1, 128);
  assert(queue.Size() == 3 && queue[0].offset == 0 && queue[1].offset == 0 &&
         queue[2].offset == 128);
  assert(queue.ReadyCount(128) == 2);
  queue.Push({128, 0x90, 255, 255}, false);
  assert(queue[3].data1 == 255 && queue[3].data2 == 255);
  queue.Push({0, 0x90, 1, 1});
  assert(queue.Overflowed() && queue.Size() == 4);
  queue.Discard();
  assert(queue.Size() == 0 && queue.Overflowed());
  queue.Clear();
  assert(queue.Size() == 0 && !queue.Overflowed());
  std::cout << "PASS stable MIDI ordering, sample boundaries, carry, normalization and overflow\n";
}
