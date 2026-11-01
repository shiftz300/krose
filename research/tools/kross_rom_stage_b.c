/* KROSS 2 v1.2.4 stage B. Research only: fixed original read APIs, never flash.
 * The two-word event ABI is mandatory. No heap, startup hook or arbitrary
 * address command. Each request reads at most one lower-64MiB TG block.
 */
#include <stdint.h>
#define SCRATCH ((uint8_t *)0xc0520000u)
#define BLOCK 0x40000u
#define RESERVED (BLOCK+512u)
#define CALL(address,type) ((type)(uintptr_t)(address))
typedef void (*VoidPtr)(void *);
typedef void (*ReadBlock)(void *,uint32_t,void *);
typedef void (*Send)(void *,const void *,uint32_t,uint32_t);

__asm__(".text\n.arm\n.balign 4\n.global k2_probe_entry\n"
        "k2_probe_entry:\nmov r0,r5\nmov r1,r7\nsub sp,fp,#0x20\n"
        "ldmia sp,{r4,r5,r6,r7,r8,fp,sp,lr}\nb k2_rom_handler\n");

static const uint8_t fingerprint[32]={
  0x30,0x05,0xf0,0xec,0xa3,0xf3,0x77,0x2b,0xcb,0x81,0x0c,0x52,0x6c,0xee,0xbb,0x15,
  0x56,0x27,0x47,0xd3,0xcd,0xcd,0xf5,0xd2,0x0f,0xaa,0xe4,0xa5,0x39,0x52,0x0c,0x54};

static void put32(uint8_t *p,uint32_t x) {
  p[0]=(uint8_t)x; p[1]=(uint8_t)(x>>8); p[2]=(uint8_t)(x>>16); p[3]=(uint8_t)(x>>24);
}
static uint32_t crc32(const uint8_t *p,uint32_t n) {
  uint32_t c=0xffffffffu;
  while(n--) { c^=*p++; for(uint32_t b=0;b<8;b++) c=(c>>1)^(0xedb88320u & (0u-(c&1u))); }
  return c^0xffffffffu;
}
static void prefix(uint8_t *p) {
  CALL(0xc0138c68u,VoidPtr)(p);
  p[6]=0x7d; p[7]='K'; p[8]='R'; p[9]='O'; p[10]='S'; p[11]='E'; p[12]=3;
}
/* Standard groups of one MSB mask then up to seven low-seven-bit bytes. */
static void frame(uint8_t kind,const uint8_t *a,uint32_t na,
                  const uint8_t *b,uint32_t nb,uint8_t *out) {
  uint32_t n=na+nb,used=14,i=0;
  if(n>272) return;
  prefix(out); out[13]=kind;
  while(i<n) {
    uint32_t mask=used++,bit=0; out[mask]=0;
    while(bit<7 && i<n) {
      uint8_t v=i<na ? a[i] : b[i-na];
      out[mask]|=(uint8_t)((v>>7)<<bit);
      out[used++]=(uint8_t)(v&127); bit++; i++;
    }
  }
  out[used++]=0xf7;
  /* Same per-message transmit mutex used by the original mode reply.
   * Never hold it during TG reads or between separate complete frames. */
  CALL(0xc0139748u,VoidPtr)((void *)0xc104790cu);
  CALL(0xc0138240u,Send)(0,out,used,2);
  CALL(0xc013978cu,VoidPtr)((void *)0xc104790cu);
}
static void status(uint32_t error) {
  uint8_t h[8],out[128];
  h[0]='K';h[1]='2';h[2]='X';h[3]='1';put32(h+4,error);
  frame(0x13,h,8,0,0,out);
}
static int untouched(void) {
  volatile uint32_t *p=(volatile uint32_t *)SCRATCH;
  for(uint32_t i=0;i<RESERVED/4;i++) if(p[i]!=0xffffffffu) return 0;
  return 1;
}
static void clear_scratch(void) {
  volatile uint32_t *p=(volatile uint32_t *)SCRATCH;
  for(uint32_t i=0;i<RESERVED/4;i++) p[i]=0xffffffffu;
}
void k2_rom_handler(const uint8_t *event,uint32_t port) {
  uint8_t h[64],out[128];
  uint32_t mode=event[4],block=event[5];
  if(port!=2 || event[0]!=0x72 || event[1]!=0x18) return;
  if(mode==0 && block==0) {
    prefix(out);out[13]=0xf7;CALL(0xc0138240u,Send)(0,out,14,2);return;
  }
  if(mode!=2 && block!=0) return;
  if(mode<1 || mode>3) return;
  if(mode==3) {
    if(!untouched()) { status(2);return; }
    volatile uint32_t *p=(volatile uint32_t *)SCRATCH;
    uint32_t ok=1;
    for(uint32_t i=0;i<RESERVED/4;i++) {
      uint32_t v=0xa55a0000u^i;p[i]=v;if(p[i]!=v) ok=0;p[i]=0xffffffffu;
    }
    h[0]='K';h[1]='2';h[2]='R';h[3]='1';put32(h+4,0xc0520000u);
    put32(h+8,RESERVED);put32(h+12,ok?0:3);frame(0x15,h,16,0,0,out);return;
  }
  void *manager=CALL(0xc011c860u,void *(*)(void))();
  if(!manager || *(volatile uint32_t *)manager!=0x60000000u) { status(1);return; }
  if(mode==1) {
    const uint8_t *tail=CALL(0xc011cd00u,const uint8_t *(*)(void *))(manager);
    h[0]='K';h[1]='2';h[2]='W';h[3]='1';put32(h+4,0x03fffff0u);
    put32(h+8,16);put32(h+12,crc32(tail,16));
    for(uint32_t i=0;i<16;i++) h[16+i]=tail[i];
    frame(0x14,h,32,0,0,out);return;
  }
  if(!untouched()) { status(2);return; }
  /* Original function enters TG read mode and restores it BEFORE returning.
   * No transport/CRC work occurs while TG is in read mode. */
  CALL(0xc011c90cu,ReadBlock)(manager,block,SCRATCH);
  uint32_t crc=crc32(SCRATCH,BLOCK);
  for(uint32_t i=0;i<64;i++) h[i]=0;
  h[0]='K';h[1]='R';h[2]='2';h[3]='B';h[4]='L';h[5]='K';h[6]='0';h[7]='1';
  put32(h+8,64);put32(h+12,0x4000000u);put32(h+16,BLOCK);put32(h+20,block);
  put32(h+24,crc); /* source kind=0: provenance is established separately. */
  for(uint32_t i=0;i<32;i++) h[32+i]=fingerprint[i];
  uint8_t *wire=SCRATCH+BLOCK;
  frame(0x10,h,64,0,0,wire);
  for(uint32_t offset=0;offset<BLOCK;offset+=256) {
    h[0]='K';h[1]='2';h[2]='D';h[3]='1';put32(h+4,offset);
    h[8]=0;h[9]=1;h[10]=0;h[11]=0;put32(h+12,crc32(SCRATCH+offset,256));
    frame(0x11,h,16,SCRATCH+offset,256,wire);
  }
  h[0]='K';h[1]='2';h[2]='E';h[3]='1';put32(h+4,block);put32(h+8,BLOCK);put32(h+12,crc);
  frame(0x12,h,16,0,0,wire);
  clear_scratch();
}
