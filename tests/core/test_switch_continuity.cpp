#include "engine/InstrumentEngine.h"
#include "FactoryPrograms.h"
#include <cassert>
#include <cmath>
#include <iostream>
#include <memory>
#include <cstring>
#include <new>
#include <cstdlib>
static bool audioThread=false;
static unsigned allocations=0;
void *operator new(size_t size) {
  if(audioThread) ++allocations;
  if(auto p=std::malloc(size)) return p;
  throw std::bad_alloc();
}
void *operator new[](size_t size) {return ::operator new(size);}
void operator delete(void *p) noexcept {std::free(p);}
void operator delete[](void *p) noexcept {std::free(p);}
void operator delete(void *p,size_t) noexcept {std::free(p);}
void operator delete[](void *p,size_t) noexcept {std::free(p);}
using namespace segrand;
int main(int argc,char **argv) {
  assert(argc==3);
  auto library=ProgramLibrary::Load(argv[1]);auto concert=SampleBank::Load(argv[2]);
  int synth=-1;
  for(int i=1;i<kInstrumentProgramCount;++i)
    if(std::strcmp(kInstrumentProgramNames[i],"GM Simple Sawtooth")==0)synth=i;
  assert(synth>0);
  for(double rate:{32000.,48000.,96000.,192000.})for(int voices:{32,33,36,64,128}) {
    auto a=std::make_unique<InstrumentEngine>(concert,library);
    auto b=std::make_unique<InstrumentEngine>(concert,library);
    Controls c;c.program=synth;c.space=0;c.fxBypass=true;c.outputDb=-24;
    for(auto *e:{a.get(),b.get()}) {
      e->Prepare(rate);e->SetControls(c);
      for(int i=0;i<voices;++i)e->Queue({0,0x90,uint8_t(24+i%84),100});
    }
    float left[128]{},right[128]{},refL[128]{},refR[128]{};
    for(int i=0;i<int(rate*.6)/128;++i) {
      a->Process(left,right,128);b->Process(refL,refR,128);
    }
    c.voiceMode=1;
    audioThread=true;
    a->SetControls(c);a->Process(left,right,128);b->Process(refL,refR,128);
    audioThread=false;
    assert(std::abs(left[0]-refL[0])<1e-6 && std::abs(right[0]-refR[0])<1e-6);
    // Overfill the tail bank repeatedly within one audio block.
    audioThread=true;
    for(int burst=0;burst<8;++burst) {
      c.voiceMode=0;a->SetControls(c);
      for(int i=0;i<128;++i)a->Queue({0,0x90,uint8_t(24+i%84),100});
      a->Process(left,right,1);
      c.voiceMode=1;a->SetControls(c);
    }
    a->Process(left,right,128);
    audioThread=false;
    for(int i=0;i<128;++i)assert(std::isfinite(left[i])&&std::abs(left[i])<=1);
  }
  assert(allocations==0);
  std::cout<<"PASS dense mode switches and oversubscribed fade tails, four rates, no RT allocations\n";
}
