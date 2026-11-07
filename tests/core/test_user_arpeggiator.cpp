#include "midi/Arpeggiator.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <fstream>
#include <iostream>
#include <tuple>
#include <vector>
using namespace segrand;
struct Event {int at,on,note,velocity;auto Key()const{return std::tie(at,on,note,velocity);} };
struct Output {
  int base=0;std::vector<Event> events;
  static void Emit(void *p,MidiEvent e) {auto &o=*static_cast<Output*>(p);const int type=e.status&240;
    if(type==0x90||type==0x80)o.events.push_back({o.base+e.offset,type==0x90,e.data1,type==0x90?e.data2:0});}
};
Output Render(int pattern,int ticks,double rate,int block) {
  Arpeggiator arp;ArpControls c;c.enabled=true;c.hostSync=false;c.pattern=pattern;c.gate=101;c.velocity=129;
  arp.SetControls(c);arp.Prepare(rate);Output out;out.events.reserve(8192);
  const int end=int(std::ceil(ticks*rate/960.));
  MidiEvent keys[]={{0,0x90,60,90},{0,0x90,64,90},{0,0x90,67,90}};
  arp.Process(1,keys,3,&out,Output::Emit);out.base=1;
  while(out.base<end){const int n=std::min(block,end-out.base);arp.Process(n,nullptr,0,&out,Output::Emit);out.base+=n;}
  const MidiEvent stop{0,0xb0,120,0};arp.Process(1,&stop,1,&out,Output::Emit);
  std::array<int,128> count{};
  for(auto e:out.events){assert(e.note>=0&&e.note<=127);if(e.on){assert(e.velocity>=1&&e.velocity<=127);++count[e.note];}else{assert(count[e.note]>0);--count[e.note];}}
  for(auto n:count)assert(n==0);
  return out;
}
int main(int argc,char**argv) {
  assert(argc==2);std::ifstream cases(std::string(argv[1])+"/user-cases.tsv"),events(std::string(argv[1])+"/user-events.tsv");assert(cases&&events);
  std::vector<std::vector<Event>> expected(12);int c,t,on,n,v;
  while(events>>c>>t>>on>>n>>v)expected.at(c).push_back({t*50,on,n,v});
  int pattern,ticks,gate,velocity,octaves;unsigned row=0,total=0;
  while(cases>>pattern>>ticks>>gate>>velocity>>octaves) {
    assert(gate==101&&velocity==129&&octaves==1);
    auto reference=expected.at(row++);
    for(double rate:{32000.,44100.,48000.,96000.,192000.}) {
      auto scaled=reference;
      for(auto &e:scaled)e.at=int(std::ceil(e.at*rate/48000.));
      std::sort(scaled.begin(),scaled.end(),[](auto a,auto b){return a.Key()<b.Key();});
      for(int block:{31,257,1024}) {
        auto actual=Render(pattern,ticks,rate,block).events;
        std::sort(actual.begin(),actual.end(),[](auto a,auto b){return a.Key()<b.Key();});
        assert(actual.size()==scaled.size());
        for(unsigned i=0;i<actual.size();++i) {
          if(std::abs(actual[i].at-scaled[i].at)>1||actual[i].on!=scaled[i].on||actual[i].note!=scaled[i].note||actual[i].velocity!=scaled[i].velocity){
            std::cerr<<"Pattern "<<pattern<<" rate "<<rate<<" event "<<i<<" at "<<actual[i].at<<" / "<<scaled[i].at<<'\n';return 1;}
        }
      }
    }
    total+=reference.size();
  }
  assert(row==12);
  for(int i=5;i<kArpPatternCount;++i) {
    auto p=Pattern(i);assert(p.Length()>=1&&p.Length()<=64);assert(ArpPatternName(i)[24]==0);
    Render(i,std::min(4,p.Length())*120,48000,257);
  }
  std::cout<<"PASS "<<total<<" original ARM events, twelve patterns, five rates, three block sizes; all 1280 patterns balance note ownership\n";
}
