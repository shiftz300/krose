/* Offline research prototype, not installed firmware or a MIDI handler.
 * A caller must supply a validated reader, output transport and 256 KiB scratch.
 * No flash writer, allocator, device discovery or firmware patch is included.
 */
#include <stdint.h>
#include <stddef.h>

typedef struct {
  uint32_t abi_version;
  uint32_t source_kind; /* 0 unknown, 1 synthetic; not proof of authenticity */
  void *manager;
  void (*read_block)(void *, uint32_t, void *);
  int (*emit)(void *, const uint8_t *, uint32_t);
  void *sink;
  const uint8_t *firmware_sha256;
} K2RecoveryAPI;

static inline void put32(uint8_t *p, uint32_t n) {
  p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8);
  p[2]=(uint8_t)(n>>16); p[3]=(uint8_t)(n>>24);
}

int k2_export_block(const K2RecoveryAPI *api, uint32_t block,
                    uint8_t *scratch, uint32_t capacity) {
  uint8_t header[64];
  uint32_t crc=0xffffffffu;
  if (!api || api->abi_version!=1 || api->source_kind>1 || !api->manager ||
      !api->read_block || !api->emit || !api->firmware_sha256 || !scratch)
    return -1;
  if (block>=256 || capacity<0x40000u || ((uintptr_t)scratch & 1u)) return -2;
  api->read_block(api->manager, block, scratch);
  for (uint32_t i=0; i<0x40000u; ++i) {
    crc ^= scratch[i];
    for (uint32_t bit=0; bit<8; ++bit)
      crc=(crc>>1) ^ (0xedb88320u & (0u-(crc & 1u)));
  }
  for (uint32_t i=0; i<64; ++i) header[i]=0;
  header[0]='K'; header[1]='R'; header[2]='2'; header[3]='B';
  header[4]='L'; header[5]='K'; header[6]='0'; header[7]='1';
  put32(header+8,64); put32(header+12,0x4000000u);
  put32(header+16,0x40000u); put32(header+20,block);
  put32(header+24,crc^0xffffffffu); put32(header+28,api->source_kind);
  for (uint32_t i=0; i<32; ++i) header[32+i]=api->firmware_sha256[i];
  if (api->emit(api->sink,header,64)) return -3;
  if (api->emit(api->sink,scratch,0x40000u)) return -4;
  return 0;
}
