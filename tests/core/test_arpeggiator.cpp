#include "midi/Arpeggiator.h"
#include "engine/InstrumentEngine.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <new>
#include <vector>

static bool audioThread=false;
static unsigned allocations=0;
void* operator new(std::size_t n){if(audioThread)++allocations;if(auto* p=std::malloc(n))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
using namespace segrand;
struct Recorder {
  int base=0;
  std::vector<MidiEvent> events;
  static void Emit(void* context,MidiEvent e){
    auto& self=*static_cast<Recorder*>(context);e.offset+=self.base;
    if((e.status&240)==0x90||(e.status&240)==0x80)self.events.push_back(e);
  }
};
void process(Arpeggiator& arp,Recorder& out,int frames,const std::vector<MidiEvent>& input={},int block=256){
  const int origin=out.base;
  for(int at=0;at<frames;at+=block){
    const int size=std::min(block,frames-at);
    std::array<MidiEvent,2048> events{};unsigned count=0;
    for(auto event:input)if(event.offset>=at&&event.offset<at+size){event.offset-=at;events[count++]=event;}
    out.base=origin+at;arp.Process(size,events.data(),count,&out,Recorder::Emit);
  }
  out.base=origin+frames;
}
bool same(const Recorder& a,const Recorder& b){
  if(a.events.size()!=b.events.size())return false;
  for(size_t i=0;i<a.events.size();++i){auto x=a.events[i],y=b.events[i];if(x.offset!=y.offset||x.status!=y.status||x.data1!=y.data1||x.data2!=y.data2)return false;}
  return true;
}
std::vector<MidiEvent> ons(const Recorder& out){std::vector<MidiEvent> result;for(auto e:out.events)if((e.status&240)==0x90)result.push_back(e);return result;}
void balanced(const Recorder& out){
  int counts[16][128]{};
  for(auto e:out.events){auto& n=counts[e.status&15][e.data1];n+=(e.status&240)==0x90?1:-1;assert(n>=0);}
  for(auto& channel:counts)for(auto n:channel)assert(n==0);
}
void originals(const std::string& folder){
  std::ifstream cases(folder+"/presets.tsv");assert(cases);
  int pattern,octaves,sort,n,steps;unsigned checked=0;
  while(cases>>pattern>>octaves>>sort>>n>>steps){
    std::vector<int> keys(n);for(auto& key:keys)cases>>key;
    auto ordered=keys;if(sort)std::sort(ordered.begin(),ordered.end());uint16_t seed=1;
    for(int i=0;i<steps;++i){
      int note,velocity;cases>>note>>velocity;
      auto position=Arpeggiator::Position(pattern,n*octaves,i,seed);
      int source=ordered[position%n],actual=source+12*int(position/n);while(actual>127)actual-=12;
      assert(actual==note&&velocity==40+std::find(keys.begin(),keys.end(),source)-keys.begin());++checked;
    }
  }
  assert(checked==9600);
  uint16_t random=1;unsigned period=0;
  do{random=Arpeggiator::RandomNext(random);++period;}while(random!=1&&period<65536);
  assert(period==65535&&Arpeggiator::RandomNext(0)==0);
  std::array<Recorder,5> recordings;
  for(int kind=0;kind<5;++kind){
    Arpeggiator arp;ArpControls c;c.enabled=true;c.pattern=kind;c.octaves=2;c.gate=50;c.hostSync=false;
    arp.SetControls(c);arp.Prepare(48000);
    process(arp,recordings[kind],24*6000,{{0,0x90,60,90},{0,0x90,64,90},{0,0x90,67,90}},31);
    balanced(recordings[kind]);
  }
  std::array<unsigned,5> cursor{};std::ifstream events(folder+"/events.tsv");assert(events);
  int kind,tick,on,note,velocity;
  while(events>>kind>>tick>>on>>note>>velocity){
    const auto e=recordings[kind].events.at(cursor[kind]++);
    assert(e.offset==tick*50&&e.data1==note&&((e.status&240)==0x90)==bool(on));
    if(on)assert(e.data2==velocity);
  }
  for(int i=0;i<5;++i)assert(cursor[i]==recordings[i].events.size());
}
void timing(){
  for(double rate:{44100.,48000.,96000.})for(int resolution=0;resolution<8;++resolution){
    ArpControls c;c.enabled=true;c.hostSync=false;c.tempo=137.3;c.resolution=resolution;c.gate=resolution%2?100:1;
    const std::vector<MidiEvent> input{{17,0x90,67,100},{17,0x90,60,40},{30000,0x80,67,0},{31000,0x80,60,0}};
    Arpeggiator arp;arp.SetControls(c);arp.Prepare(rate);Recorder one;process(arp,one,40000,input,40000);
    arp.Prepare(rate);Recorder split;process(arp,split,40000,input,31);
    assert(same(one,split));balanced(one);
    assert(ons(one).front().offset==17);
  }
  // Valid host beat: wait for the next grid when Key Sync is off, and preserve
  // the musical step/gate through a tempo change between audio callbacks.
  Arpeggiator arp;ArpControls c;c.enabled=true;c.keySync=false;c.gate=50;
  arp.SetControls(c);arp.Prepare(48000);Recorder out;
  arp.SetTransport({true,false,120,.1});process(arp,out,512,{{0,0x90,60,100}});assert(out.events.empty());
  arp.SetTransport({true,true,120,.1});process(arp,out,4000);
  assert(ons(out).size()==1&&ons(out)[0].offset==512+3600);
  arp.SetTransport({true,false,120,.1+4000./24000});process(arp,out,1000);balanced(out);
  // Seek and loop reset the sequence without retaining an old sounding note.
  arp.SetTransport({true,true,120,0});process(arp,out,1000);assert(ons(out).back().data1==60);
  arp.SetTransport({true,true,120,0});process(arp,out,1000);
  arp.SetTransport({true,false,120,0});process(arp,out,1);balanced(out);
  arp.Prepare(48000);out={};c.keySync=true;c.gate=80;arp.SetControls(c);
  arp.SetTransport({true,true,120,0});process(arp,out,3000,{{0,0x90,60,100}});
  arp.SetTransport({true,true,240,.125});process(arp,out,1600);
  assert(ons(out).size()==2&&ons(out)[1].offset==4500);
  assert(out.events[1].offset==3900);
  arp.SetTransport({true,false,240,.125+1600./12000});process(arp,out,1);balanced(out);
  // A missing host clock uses the saved internal tempo, including standalone.
  arp.Prepare(48000);out={};c.tempo=60;arp.SetControls(c);arp.SetTransport({});
  process(arp,out,24001,{{0,0x90,60,100}});assert(ons(out).size()==3&&ons(out)[1].offset==12000);

  // MIDI pulse jitter is phase error, while an explicit song-position
  // revision is a seek. Only the latter interrupts the held pattern.
  arp.Prepare(48000);
  out = {};
  arp.SetTransport({true, true, 120, 0, true, 1});
  process(arp, out, 1000, {{0, 0x90, 60, 100}});
  arp.SetTransport({true, true, 120, 1020. / 24000, true, 1});
  process(arp, out, 1000);
  assert(out.events.size() == 1);
  arp.SetTransport({true, true, 120, 4, true, 2});
  process(arp, out, 1);
  assert(ons(out).size() == 2 && ons(out).back().offset == 2000);
}
void keysAndStops(){
  Arpeggiator arp;ArpControls c;c.enabled=true;c.hostSync=false;c.latch=true;
  arp.SetControls(c);arp.Prepare(48000);Recorder out;
  process(arp,out,14000,{{0,0x90,60,40},{100,0x80,60,0},{7000,0x90,64,80},{7100,0x90,64,110}});
  auto notes=ons(out);assert(notes.size()==4&&notes[0].data1==60&&notes[1].data1==60&&notes[2].data1==64&&notes[2].offset==7000&&notes[3].data2==110);
  process(arp,out,1000,{{0,0x80,64,0}});c.latch=false;arp.SetControls(c);process(arp,out,1000);balanced(out);
  arp.Prepare(48000);out={};
  process(arp,out,9000,{{0,0xb0,64,127},{0,0x90,60,90},{0,0x91,72,80},{100,0x80,60,0},{100,0x81,72,0},{8000,0xb0,64,0}});
  notes=ons(out);assert(notes.size()==3&&notes.back().offset==6000&&notes.back().data1==60);balanced(out);
  // Panic and all-notes-off clear latch/physical keys; no resurrection later.
  for(int cc:{120,123,121}){
    arp.Prepare(48000);out={};process(arp,out,9000,{{0,0xb0,64,127},{0,0x90,60,90},{100,0x80,60,0},{8000,0xb0,uint8_t(cc),0}});
    process(arp,out,24000);assert(ons(out).size()==2);balanced(out);
  }
  arp.Prepare(48000);out={};process(arp,out,1000,{{0,0x90,60,100}});
  c.enabled=false;arp.SetControls(c);process(arp,out,30000); // CC120 terminates routing; record note-off separately below.
  assert(ons(out).size()==1);
  c.enabled=true;arp.SetControls(c);process(arp,out,30000);assert(ons(out).size()==1);
  // All 128 keys, repeated keys, and per-channel input stay within fixed storage.
  arp.Prepare(48000);out={};std::vector<MidiEvent> input;
  for(int n=0;n<128;++n){input.push_back({0,0x90,uint8_t(n),90});input.push_back({0,0x90,uint8_t(n),100});}
  input.push_back({31000,0xb0,123,0});process(arp,out,40000,input);balanced(out);
}
void audio(const char* concert,const char* factory){
  auto bank=SampleBank::Load(concert);auto programs=ProgramLibrary::Load(factory);
  InstrumentEngine engine(bank,programs);Controls controls;controls.space=0;controls.releaseSeconds=.03;
  ArpControls arp;arp.enabled=true;arp.hostSync=false;arp.tempo=137.3;arp.gate=50;
  for(int program:{0,1})for(int mode:{0,2}){
    controls.program=program;controls.voiceMode=mode;engine.SetControls(controls);engine.SetArpeggiator(arp);
    auto render=[&](int block){
      engine.Prepare(48000);engine.Queue({17,0x90,60,100});engine.Queue({17,0x90,64,100});engine.Queue({100000,0xb0,120,0});
      std::vector<float> left(110000),right(110000);
      for(int at=0;at<110000;at+=block){audioThread=true;engine.Process(left.data()+at,right.data()+at,std::min(block,110000-at));audioThread=false;}
      assert(!engine.ActiveVoices());double energy=0;for(float x:left){assert(std::isfinite(x));energy+=x*x;}assert(energy>.01);
      return left;
    };
    assert(render(110000)==render(31));
    engine.Queue({0,0x90,60,100});float l[256],r[256];engine.Process(l,r,256);engine.Panic();engine.Process(l,r,256);assert(!engine.ActiveVoices());
  }
  assert(!allocations);
}
int main(int argc,char** argv){assert(argc==4);originals(argv[3]);timing();keysAndStops();audio(argv[1],argv[2]);std::cout<<"PASS 9600 original notes, five event traces, timing/transport, latch/pedal, both engines, block invariance and zero audio allocations\n";}
