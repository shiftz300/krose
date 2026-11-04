#include "../../src/plugin/editor/native/ImageMemory.h"
#include <cassert>
#include <cstdint>
#include <iostream>
int main() {
  KroseImageFree(nullptr);
  auto *p = static_cast<unsigned char *>(KroseImageAllocate(31));
  assert(p && uintptr_t(p) % alignof(max_align_t) == 0);
  for (size_t i=0;i<31;++i) p[i]=static_cast<unsigned char>(i);
  for (size_t size : {size_t(524289),size_t(1048577),size_t(67),size_t(31)}) {
    auto *next=static_cast<unsigned char *>(KroseImageReallocate(p,size));
    assert(next && uintptr_t(next) % alignof(max_align_t) == 0);
    for (size_t i=0;i<31;++i) assert(next[i]==i);
    next[size-1]=0x5a; // touch both ends of mapped and heap allocations
    next[30]=30;
    p=next;
  }
  assert(KroseImageReallocate(p,SIZE_MAX)==nullptr);
  assert(p[30]==30); // allocation failure preserves the old buffer
  KroseImageFree(p);
  assert(KroseImageReallocate(KroseImageAllocate(300000),0)==nullptr);
  auto *fresh=KroseImageReallocate(nullptr,512);
  assert(fresh);KroseImageFree(fresh);
  std::cout << "PASS image scratch alignment, growth/shrink, preserved bytes and overflow\n";
}
