#include "concert_effects.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

int main(void) {
    double b[40]={0};
    for (int i=0;i<8;i++) b[i*5]=1;
    assert(!concert_effects_create(0,b,1,1.8,0.15,0.18,0));
    assert(!concert_effects_create(48000,b,1,NAN,0.15,0.18,0));
    ConcertEffects *e=concert_effects_create(48000,b,1,1.8,0.15,0.18,0);
    assert(e);
    float block[514+32];
    for (int k=0;k<546;k++) block[k]=123;
    for (int k=16;k<530;k++) block[k]=0;
    block[16]=0.5;
    for (int j=0;j<1000;j++) {
        concert_effects_process(e,block+16,257);
        for (int k=0;k<16;k++) assert(block[k]==123 && block[530+k]==123);
        for (int k=16;k<530;k++) { assert(isfinite(block[k])); block[k]=0; }
    }
    concert_effects_process(e,block+16,0);
    concert_effects_reset(e);
    concert_effects_destroy(e);
    puts("PASS address/undefined-behavior sanitizers, odd block size and buffer guards");
    return 0;
}
