#pragma once
// stb_image's documented allocator hooks. Large decode scratch buffers return
// to macOS immediately after upload; persistent GPU textures are unaffected.
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifdef __APPLE__
#include <sys/mman.h>
#endif
typedef union KroseImageAllocation {
  struct { size_t bytes, mapped; } size;
  max_align_t alignment;
} KroseImageAllocation;
static inline void *KroseImageAllocate(size_t bytes) {
  if (bytes > SIZE_MAX - sizeof(KroseImageAllocation)) return NULL;
  const size_t total = bytes + sizeof(KroseImageAllocation);
  KroseImageAllocation *allocation;
#ifdef __APPLE__
  if (total >= 256u * 1024) {
    void *memory = mmap(NULL, total, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (memory == MAP_FAILED) return NULL;
    allocation = (KroseImageAllocation *)memory;
    allocation->size.mapped = total;
  } else
#endif
  {
    allocation = (KroseImageAllocation *)malloc(total);
    if (!allocation) return NULL;
    allocation->size.mapped = 0;
  }
  allocation->size.bytes = bytes;
  return allocation + 1;
}
static inline void KroseImageFree(void *memory) {
  if (!memory) return;
  KroseImageAllocation *allocation = (KroseImageAllocation *)memory - 1;
#ifdef __APPLE__
  if (allocation->size.mapped) {
    munmap(allocation, allocation->size.mapped);
    return;
  }
#endif
  free(allocation);
}
static inline void *KroseImageReallocate(void *memory, size_t bytes) {
  if (!bytes) { KroseImageFree(memory); return NULL; }
  void *replacement = KroseImageAllocate(bytes);
  if (replacement && memory) {
    size_t oldBytes = ((KroseImageAllocation *)memory - 1)->size.bytes;
    memcpy(replacement, memory, oldBytes < bytes ? oldBytes : bytes);
    KroseImageFree(memory);
  }
  return replacement;
}
#define STBI_MALLOC(bytes) KroseImageAllocate(bytes)
#define STBI_REALLOC(memory, bytes) KroseImageReallocate(memory, bytes)
#define STBI_FREE(memory) KroseImageFree(memory)
