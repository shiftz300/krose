/* KROSS little-endian Blowfish block decoder, independently transcribed from
 * the user's device format. The expanded P/S context is provided separately.
 * This utility reads files only and never communicates with an instrument. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static void put32(unsigned char *p, uint32_t v) {
    p[0]=v; p[1]=v>>8; p[2]=v>>16; p[3]=v>>24;
}
static uint32_t f(uint32_t x, const uint32_t *s) {
    return ((s[x&255]+s[256+((x>>8)&255)]) ^ s[512+((x>>16)&255)])+s[768+(x>>24)];
}
int main(int argc, char **argv) {
    if (argc!=4) { fprintf(stderr,"usage: kep_blowfish expanded-context input output\n"); return 2; }
    unsigned char raw[4168]; uint32_t ctx[1042];
    FILE *cf=fopen(argv[1],"rb");
    if(!cf) {perror(argv[1]);return 1;}
    size_t got=fread(raw,1,sizeof raw,cf); int extra=fgetc(cf);fclose(cf);
    if(got!=sizeof raw || extra!=EOF){fprintf(stderr,"Invalid context length\n");return 1;}
    for(int i=0;i<1042;i++) ctx[i]=le32(raw+4*i);
    FILE *in=fopen(argv[2],"rb");
    if(!in){perror(argv[2]);return 1;}
    FILE *out=fopen(argv[3],"wb");
    if(!out){perror(argv[3]);fclose(in);return 1;}
    unsigned char buf[65536];size_t n,total=0;
    while((n=fread(buf,1,sizeof buf,in))!=0){
        if(n%8){fprintf(stderr,"Input length is not divisible by 8\n");fclose(in);fclose(out);return 1;}
        for(size_t pos=0;pos<n;pos+=8){
            uint32_t l=le32(buf+pos),r=le32(buf+pos+4);
            for(int i=17;i>=2;i--){ l^=ctx[i];r^=f(l,ctx+18);uint32_t t=l;l=r;r=t; }
            uint32_t t=l;l=r;r=t;r^=ctx[1];l^=ctx[0];
            put32(buf+pos,l);put32(buf+pos+4,r);
        }
        if(fwrite(buf,1,n,out)!=n){perror("write");return 1;}total+=n;
    }
    if(ferror(in)){perror("read");return 1;}
    fclose(in);if(fclose(out)){perror("close");return 1;}
    printf("Decoded %zu bytes\n",total);return 0;
}
