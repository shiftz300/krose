#include "InstrumentEngine.h"
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <new>
#include <vector>
static bool gAudio=false;static unsigned gNew=0;
void* operator new(std::size_t n){if(gAudio)++gNew;if(void* p=std::malloc(n))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept{std::free(p);}void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
using namespace segrand;
struct Audio{std::vector<float> l,r;explicit Audio(int n):l(n),r(n){}};
template<class Engine>void Process(Engine& engine,Audio& a,int block){for(size_t i=0;i<a.l.size();i+=block){gAudio=true;engine.Process(a.l.data()+i,a.r.data()+i,int(std::min(size_t(block),a.l.size()-i)));gAudio=false;}for(size_t i=0;i<a.l.size();++i)assert(std::isfinite(a.l[i])&&std::isfinite(a.r[i]));}
double Energy(const Audio& a){double n=0;for(size_t i=0;i<a.l.size();++i)n+=a.l[i]*a.l[i]+a.r[i]*a.r[i];return n;}
int main(int argc,char** argv){
 assert(argc==3);auto bank=ProgramLibrary::Load(argv[1]);assert(ProgramLibrary::Load(argv[1]).get()==bank.get());assert(bank->programs.size()==6&&bank->samples.size()==357);
 const auto& piano=bank->programs[0];assert(piano.lookup[0][60][112]!=piano.lookup[0][60][113]);assert(piano.lookup[1][60][1]>=0);
 const auto& kit=bank->programs[4];assert(kit.drum&&kit.lookup[0][36][99]!=kit.lookup[0][36][100]);assert(kit.lookup[0][36][100]!=kit.lookup[0][38][100]);
 // A second instance retains pointers into the same PCM, not a private decoded bank.
 ProgramEngine engine(bank),other(bank);Controls controls;controls.space=0;engine.SetControls(controls);
 for(unsigned p=0;p<bank->programs.size();++p){
  engine.SetProgram(p);engine.Prepare(48000);engine.Queue({37,0x90,uint8_t(p>=4?36:60),100});engine.Queue({24000,0x80,uint8_t(p>=4?36:60),0});Audio a(48000);Process(engine,a,257);
  assert(std::all_of(a.l.begin(),a.l.begin()+37,[](float x){return x==0;}));assert(Energy(a)>1e-6);std::cout<<bank->programs[p].id.data()<<" energy "<<Energy(a)<<'\n';
 }
 // Host block partitioning cannot change control clocks or MIDI timing.
 for(double rate:{44100.,48000.,96000.,192000.}){
  engine.SetProgram(2);engine.Prepare(rate);auto events=[&](){engine.Queue({0,0x90,60,70});engine.Queue({256,0x90,67,110});engine.Queue({1200,0x80,60,0});};
  events();Audio a(12000);Process(engine,a,12000);engine.Prepare(rate);events();Audio b(12000);Process(engine,b,31);assert(a.l==b.l&&a.r==b.r);
 }
 // Drum note-offs and the pedal do not truncate one-shots; all-sound-off does.
 engine.SetProgram(4);engine.Prepare(48000);engine.Queue({0,0x90,36,100});Audio one(12000);Process(engine,one,127);
 engine.Prepare(48000);engine.Queue({0,0x90,36,100});engine.Queue({1,0x80,36,0});engine.Queue({2,0xb0,64,0});Audio two(12000);Process(engine,two,127);assert(one.l==two.l&&one.r==two.r);
 engine.Queue({0,0xb0,120,0});Audio silence(128);Process(engine,silence,128);assert(Energy(silence)<1e-15);
 // The source kit's open/closed hats share a nonzero exclusive group.
 const auto hat=kit.lookup[0][54][100],open=kit.lookup[0][58][100];assert(hat>=0&&open>=0);assert(bank->regions[hat].exclusive&&bank->regions[hat].exclusive==bank->regions[open].exclusive);
 engine.Prepare(48000);engine.Queue({0,0x90,58,100});Audio begin(1000);Process(engine,begin,64);engine.Queue({0,0x90,54,100});Audio shut(128);Process(engine,shut,128);assert(engine.ActiveVoices()<=1);
 // Program changes preserve already-held factory voices; their original off still releases them.
 engine.SetProgram(3);engine.Prepare(48000);engine.Queue({0,0x90,60,100});Audio held(6000);Process(engine,held,127);const auto voices=engine.ActiveVoices();assert(voices>0);gAudio=true;engine.SetProgram(1);gAudio=false;assert(engine.ActiveVoices()==voices);
 engine.Queue({0,0x80,60,0});Audio release(48000*10);Process(engine,release,257);assert(engine.ActiveVoices()==0);
 // Accepted Concert route is sample-for-sample identical through the migration facade.
 auto concert=SampleBank::Load(argv[2]);PianoEngine baseline(concert);InstrumentEngine facade(concert,bank);baseline.SetControls(controls);facade.SetControls(controls);baseline.Prepare(48000);facade.Prepare(48000);
 for(auto* e:{&baseline}){e->Queue({0,0x90,60,100});e->Queue({1200,0x80,60,0});}
 facade.Queue({0,0x90,60,100});facade.Queue({1200,0x80,60,0});Audio old(12000),same(12000);Process(baseline,old,127);Process(facade,same,127);assert(old.l==same.l&&old.r==same.r);
 // Tone offsets affect both Concert and factory voices at neutral pan.
 for(int program : {0,1}){
   auto renderTone=[&](int cutoff,int attack,int pan){
     Controls c;c.space=0;c.program=program;c.cutoff=cutoff;c.ampEg.attack=attack;c.pan=pan;
     facade.SetControls(c);facade.Prepare(48000);facade.Queue({0,0x90,60,100});
     Audio a(8192);Process(facade,a,127);return a;
   };
   const auto neutral=renderTone(0,0,0),dark=renderTone(-80,0,0),slow=renderTone(0,90,0),right=renderTone(0,0,63);
   assert(Energy(dark)<Energy(neutral) && std::abs(Energy(slow)-Energy(neutral))>1e-4);
   assert(std::all_of(right.l.begin(),right.l.end(),[](float v){return v==0;}));
   assert(Energy(right)>0);
 }
 // Host automation and queued notes on the switching block are not lost.
 controls.program=5;gAudio=true;facade.SetControls(controls);facade.Queue({0,0x90,38,100});gAudio=false;Audio switched(12000);Process(facade,switched,257);assert(Energy(switched)>1e-6);
 // Overflow recovery and dense retriggers stay bounded and allocation-free.
 engine.SetProgram(2);engine.Prepare(48000);for(int i=0;i<512;++i)engine.Queue({i,0x90,uint8_t(30+i%70),100});Audio dense(24000);Process(engine,dense,128);assert(engine.ActiveVoices()<=ProgramEngine::kVoices);
 for(unsigned i=0;i<ProgramEngine::kEvents+2;++i)engine.Queue({0,0x90,60,100});Audio overflow(128);Process(engine,overflow,128);assert(engine.ActiveVoices()==0);
 // The bank reader rejects a truncated input before using it.
 const std::string truncated=std::string(argv[1])+".test-truncated";{std::ofstream f(truncated,std::ios::binary);f.write("KRPRG001",8);}bool rejected=false;try{ProgramLibrary::Load(truncated);}catch(const std::exception&){rejected=true;}std::remove(truncated.c_str());assert(rejected);
 assert(gNew==0);std::cout<<"PASS shared PCM, six Programs, velocity slots, MIDI, block invariance, one-shots/choke, Concert compatibility, no audio-thread new\n";
}
