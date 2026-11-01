#include "PianoEngine.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <new>
#include <vector>

// A real-time regression gate: every test Process call must perform zero new.
static bool gAudio=false;
static unsigned gAllocations=0;
void* operator new(std::size_t n){if(gAudio)++gAllocations;if(void* p=std::malloc(n))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}

using namespace segrand;
struct Audio {std::vector<float> l,r; explicit Audio(size_t n):l(n),r(n){};};
void Process(PianoEngine& e,Audio& audio,int block){
  for(size_t i=0;i<audio.l.size();i+=block){const int n=std::min<size_t>(block,audio.l.size()-i);gAudio=true;e.Process(audio.l.data()+i,audio.r.data()+i,n);gAudio=false;}
  for(size_t i=0;i<audio.l.size();++i)assert(std::isfinite(audio.l[i])&&std::isfinite(audio.r[i]));
}
double Energy(const Audio& a){double sum=0;for(size_t i=0;i<a.l.size();++i)sum+=a.l[i]*a.l[i]+a.r[i]*a.r[i];return sum;}
int main(int argc,char** argv){
  assert(argc==2);
  auto bank=SampleBank::Load(argv[1]);
  assert(SampleBank::Load(argv[1]).get()==bank.get());
  for(const auto& layer:bank->layers)assert(layer.size()==28);
  assert(PianoEngine::VelocityLayer(1)==0&&PianoEngine::VelocityLayer(85)==0);
  assert(PianoEngine::VelocityLayer(86)==1&&PianoEngine::VelocityLayer(106)==1);
  assert(PianoEngine::VelocityLayer(107)==2&&PianoEngine::VelocityLayer(127)==2);
  PianoEngine e(bank);
  Controls controls;controls.space=0;controls.releaseSeconds=0.05;e.SetControls(controls);
  for(double rate:{44100.,48000.,96000.,192000.}){
    e.Prepare(rate);
    Audio audio(static_cast<size_t>(rate/4));
    e.Queue({37,0x90,62,110});
    Process(e,audio,257);
    assert(std::all_of(audio.l.begin(),audio.l.begin()+37,[](float x){return x==0;}));
    assert(Energy(audio)>0.1&&e.ActiveVoices()==1);
    e.Queue({0,0x80,62,0});
    Audio release(static_cast<size_t>(rate/4));Process(e,release,63);assert(e.ActiveVoices()==0);
  }
  // A held pedal survives note-off, then releases when CC64 is lifted.
  e.Prepare(48000);e.Queue({0,0xB0,64,127});e.Queue({0,0x90,62,100});e.Queue({100,0x80,62,0});
  Audio held(24000);Process(e,held,128);assert(e.ActiveVoices()==1);
  e.Queue({0,0xB0,64,0});Audio lift(12000);Process(e,lift,128);assert(e.ActiveVoices()==0);
  // Sustain is channel-local, and repeated note-ons require separate note-offs.
  e.Panic();e.Queue({0,0x90,62,100});e.Queue({1,0x90,62,100});e.Queue({2,0x80,62,0});
  Audio repeated(12000);Process(e,repeated,256);assert(e.ActiveVoices()==1);
  e.Queue({0,0x90,62,0});Audio zeroOff(12000);Process(e,zeroOff,256);assert(e.ActiveVoices()==0);
  // Exact block partition independence including an event on a block boundary.
  e.Panic();Controls wide;wide.preset=2;e.SetControls(wide);e.Prepare(48000);
  auto queue=[&](){e.Queue({0,0x90,48,85});e.Queue({256,0x90,62,86});e.Queue({259,0x90,77,107});e.Queue({1000,0x80,48,0});};
  queue();Audio one(12000);Process(e,one,12000);
  e.Prepare(48000);queue();Audio many(12000);Process(e,many,31);
  assert(one.l==many.l&&one.r==many.r);
  // Timing acceptance at the player boundary: a 288 ms *base* release is
  // modulated by the factory EG. MIDI60/vel100 takes roughly 24 control ticks,
  // rather than the old fixed exponential or a mistakenly doubled control Hz.
  double minimumRelease=10,maximumRelease=0;
  for(double rate:{44100.,48000.,96000.,192000.}){
    Controls native;native.space=0;e.SetControls(native);e.Prepare(rate);
    e.Queue({0,0x90,60,100});Audio before(static_cast<size_t>(rate/2));Process(e,before,127);
    e.Queue({0,0x80,60,0});int samples=0;float l=0,r=0;
    while(e.ActiveVoices()&&samples<int(rate)){
      gAudio=true;e.Process(&l,&r,1);gAudio=false;++samples;
      assert(std::isfinite(l)&&std::isfinite(r));
    }
    const double seconds=samples/rate;
    assert(seconds>0.35&&seconds<0.43);
    minimumRelease=std::min(minimumRelease,seconds);maximumRelease=std::max(maximumRelease,seconds);
  }
  assert(maximumRelease-minimumRelease<0.001);
  // Exercise the connected filter path, not just its standalone math. Weak
  // factory notes must differ from the same sample/MIDI with filter bypassed.
  Controls comparison;comparison.space=0;e.SetControls(comparison);e.Prepare(48000);
  e.Queue({0,0x90,60,40});Audio filtered(12000);Process(e,filtered,127);
  comparison.filterEnabled=false;e.SetControls(comparison);e.Prepare(48000);
  e.Queue({0,0x90,60,40});Audio bypass(12000);Process(e,bypass,127);
  double difference=0;for(size_t i=0;i<filtered.l.size();++i)difference+=std::pow(filtered.l[i]-bypass.l[i],2)+std::pow(filtered.r[i]-bypass.r[i],2);
  assert(Energy(filtered)>0&&difference>Energy(bypass)*0.001);
  comparison.filterEnabled=true;e.SetControls(comparison);
  // Long held note crosses the actual end/loop boundary of a high sample.
  e.Panic();e.Queue({0,0x90,107,127});Audio loop(48000*5);Process(e,loop,127);assert(Energy(loop)>0.1);
  // Dense retriggers exercise bounded voice stealing, soft transition tails,
  // preset changes and wet-amount automation with no new in Process.
  e.Panic();for(int i=0;i<100;++i)e.Queue({i,0x90,uint8_t(24+i%84),127});
  Audio dense(4096);Process(e,dense,65);assert(e.ActiveVoices()==64);
  for(int i=0;i<3;++i){wide.preset=i;wide.space=i;e.SetControls(wide);Process(e,dense,257);}
  e.Queue({0,0xB0,120,0});Process(e,dense,128);assert(e.ActiveVoices()==0);
  e.Panic();for(unsigned i=0;i<PianoEngine::kEvents+1;++i)e.Queue({0,0x90,62,100});
  Process(e,dense,128);assert(e.ActiveVoices()==0);
  assert(gAllocations==0);
  std::cout<<"PASS bank sharing; velocity edges; four sample rates; MIDI offsets; pedal; repeated notes; block partitions; native release timing "<<minimumRelease<<".."<<maximumRelease<<" s; filter connected/bypass difference; loops; voice stealing; overflow recovery; zero audio-thread new\n";
}
