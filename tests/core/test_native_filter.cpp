// Independent fixtures are original ARM outputs. Audio checks validate only the
// explicitly approximate host filter, not a physical KROSS2 transfer function.
#include "voice/NativeFilter.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
using namespace segrand;
uint32_t U32(std::ifstream& f){unsigned char b[4];assert(f.read(reinterpret_cast<char*>(b),4));return uint32_t(b[0])|uint32_t(b[1])<<8|uint32_t(b[2])<<16|uint32_t(b[3])<<24;}
uint16_t U16(std::ifstream& f){unsigned char b[2];assert(f.read(reinterpret_cast<char*>(b),2));return uint16_t(b[0]|unsigned(b[1])<<8);}
void Magic(std::ifstream& f,const char* s){char b[8];assert(f.read(b,8));assert(!std::memcmp(b,s,8));}
void State(std::ifstream& stream,const NativeFilter& filter,const NativeVoice& amp,int note,int velocity){
  for(int branch=0;branch<2;++branch)for(int field=0;field<4;++field){int expected=U16(stream);
    if(filter.Word(branch,field)!=expected){std::cerr<<"Filter mismatch "<<note<<' '<<velocity<<" branch "<<branch<<" field "<<field<<' '<<filter.Word(branch,field)<<'/'<<expected<<'\n';std::abort();}}
  assert(filter.Level()==int16_t(U16(stream)));assert(filter.Stage()==U16(stream));assert(filter.Duration()==U32(stream));
  assert(amp.Mixer(0)==int16_t(U16(stream)));assert(amp.Mixer(1)==int16_t(U16(stream)));
}
int main(int argc,char** argv){
  assert(argc==3);std::ifstream map(argv[1],std::ios::binary);Magic(map,"K2FILT01");
  assert(U32(map)==2&&U32(map)==128&&U32(map)==127&&U32(map)==28);
  NativeVoice amp;NativeFilter filter;
  for(int osc=0;osc<2;++osc)for(int note=0;note<128;++note)for(int velocity=1;velocity<128;++velocity){
    amp.Start(note,velocity,osc,velocity<107?119:127);filter.Start(amp,osc,velocity,48000);
    State(map,filter,amp,note,velocity);
  }
  assert(map.peek()==EOF);
  std::ifstream traces(argv[2],std::ios::binary);Magic(traces,"K2FLTRC1");const auto count=U32(traces);
  int previous=-1,nextTick=0;
  for(unsigned i=0;i<count;++i){
    int osc=U32(traces),note=U32(traces),velocity=U32(traces),tick=U32(traces),off=U32(traces);assert(U32(traces)==0);
    if(previous!=osc*128+note){amp.Start(note,velocity,osc,velocity<107?119:127);filter.Start(amp,osc,velocity,48000);previous=osc*128+note;nextTick=0;}
    while(nextTick<=tick){if(nextTick==off)filter.Release();filter.Tick();++nextTick;}
    State(traces,filter,amp,note,velocity);
  }
  assert(traces.peek()==EOF);
  // Fixed weak-note low-pass, B output zero: measurable high-frequency rejection
  // at every supported endpoint/test rate, with a silent independent right side.
  double attenuationMin=1;
  for(double rate:{32000.,44100.,48000.,96000.,192000.}){
    double energy[2]={};
    for(int tone=0;tone<2;++tone){
      amp.Start(60,40,0,119);filter.Start(amp,0,40,rate);assert(filter.Word(1,3)==0);
      for(int frame=0;frame<int(rate);++frame){double l=std::sin(6.283185307179586*(tone?8000:100)*frame/rate),r=0;filter.Process(l,r);assert(std::isfinite(l)&&r==0);if(frame>rate/2)energy[tone]+=l*l;}
    }
    const double ratio=energy[1]/energy[0];assert(ratio<0.01);attenuationMin=std::min(attenuationMin,ratio);
    // Worst factory boundaries plus changing EG/release, impulse/tail stability.
    for(int note:{0,24,60,108,127})for(int velocity:{1,85,86,100,106,107,127}){
      amp.Start(note,velocity,0,velocity<107?119:127);filter.Start(amp,0,velocity,rate);
      double sum=0;
      for(int frame=0;frame<int(rate/2);++frame){
        if(frame==int(rate/4))filter.Release();
        if(frame%int(rate/62.5)==0)filter.Tick();
        double l=frame<1024?0.1*std::sin(frame*0.19):0,r=l;filter.Process(l,r);
        assert(std::isfinite(l)&&std::abs(l)<2&&l==r);sum+=l*l;
      }
      assert(sum>=0);
    }
  }
  std::cout<<"PASS 32512 ARM filter contexts, "<<count<<" ARM trace states; host filter five-rate rejection/stability/stereo checks (approximate Hz/Q only)\n";
}
