// Fixtures come from original ARM runs, not from the C++ implementation.
#include "NativeVoice.h"
#include <cassert>
#include <cstring>
#include <fstream>
#include <iostream>
using namespace segrand;
uint32_t U32(std::ifstream& f){unsigned char b[4];assert(f.read(reinterpret_cast<char*>(b),4));return uint32_t(b[0])|uint32_t(b[1])<<8|uint32_t(b[2])<<16|uint32_t(b[3])<<24;}
uint16_t U16(std::ifstream& f){unsigned char b[2];assert(f.read(reinterpret_cast<char*>(b),2));return uint16_t(b[0]|unsigned(b[1])<<8);}
void Magic(std::ifstream& f,const char* s){char b[8];assert(f.read(b,8));assert(!std::memcmp(b,s,8));}
int main(int argc,char** argv){
  assert(argc==4);std::ifstream map(argv[1],std::ios::binary);Magic(map,"K2CTR01");
  assert(U32(map)==2&&U32(map)==128&&U32(map)==127&&U32(map)==20);
  NativeVoice voice;
  for(int osc=0;osc<2;++osc)for(int note=0;note<128;++note)for(int velocity=1;velocity<128;++velocity){
    const auto gain=U16(map),level=U16(map),factor=U16(map),slot=U16(map);
    const int mixer1=int16_t(U16(map)),mixer2=int16_t(U16(map));
    const auto attack=U32(map),release=U32(map);
    voice.Start(note,velocity,osc,velocity<107?119:127);
    if(voice.Gain()!=gain||voice.Level()!=level||voice.Duration()!=attack||voice.VelocityFactor()!=factor||voice.SlotFactor()!=slot||voice.Mixer(0)!=mixer1||voice.Mixer(1)!=mixer2){
      std::cerr<<"Mismatch osc="<<osc<<" note="<<note<<" vel="<<velocity<<" gain="<<voice.Gain()<<'/'<<gain<<" level="<<voice.Level()<<'/'<<level<<" time="<<voice.Duration()<<'/'<<attack<<'\n';return 1;
    }
    voice.Release();assert(voice.Duration()==release);
  }
  assert(map.peek()==EOF);
  std::ifstream traces(argv[2],std::ios::binary);Magic(traces,"K2TRACE1");const auto count=U32(traces);
  int previous=-1,nextTick=0;
  for(unsigned i=0;i<count;++i){
    int note=U32(traces),velocity=U32(traces),tick=U32(traces),off=U32(traces),stage=U32(traces),level=U32(traces),gain=U32(traces);auto duration=U32(traces);
    if(note!=previous){voice.Start(note,velocity,0,velocity<107?119:127);previous=note;nextTick=0;}
    while(nextTick<=tick){if(nextTick==off)voice.Release();voice.Tick();++nextTick;}
    if(voice.Stage()!=stage||voice.Level()!=level||voice.Gain()!=gain||voice.Duration()!=duration){
      std::cerr<<"Trace mismatch note="<<note<<" tick="<<tick<<" stage="<<voice.Stage()<<'/'<<stage<<" level="<<voice.Level()<<'/'<<level<<" gain="<<voice.Gain()<<'/'<<gain<<'\n';return 1;
    }
  }
  std::ifstream commands(argv[3],std::ios::binary);Magic(commands,"K2TGSLW1");unsigned n=U32(commands);
  for(unsigned i=0;i<n;++i){int duration=U32(commands),from=U32(commands),target=U32(commands),step=int32_t(U32(commands));uint32_t word=U32(commands);
    assert(NativeSlew::CommandStep(from,target,duration)==step);
    assert((uint32_t(uint16_t(step))<<16|unsigned(target))==word);
    NativeSlew slew;slew.Reset(uint16_t(from));slew.SetTarget(uint16_t(target),duration);
    for(int frame=0;frame<32768&&slew.Current()!=target;++frame){int last=slew.Current();slew.Advance();assert(target>from?slew.Current()>=last&&slew.Current()<=target:slew.Current()<=last&&slew.Current()>=target);}
    assert(slew.Current()==target);
  }
  std::cout<<"PASS 32512 ARM initial/release contexts, "<<count<<" multi-stage ARM trace states, "<<n<<" TG commands and bounded host slew\n";
}
