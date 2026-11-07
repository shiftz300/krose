#include "engine/InstrumentEngine.h"
#include "voice/ProgramLevels.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <memory>
using namespace segrand;
int main(int argc,char**argv) {
  assert(argc==3);auto bank=ProgramLibrary::Load(argv[1]);auto concert=SampleBank::Load(argv[2]);
  auto find=[&](const char *id){for(unsigned i=0;i<bank->programs.size();++i)if(std::strcmp(bank->programs[i].id.data(),id)==0)return i;std::abort();};
  auto fx=ProgramEffects::Decode(bank->programs[find("A000")].controls.data());
  assert((fx.sourceIDs==std::array<int,4>{7,5,0,105}));
  assert(fx.slots[0].type==2&&fx.slots[1].type==4&&!fx.slots[2].enabled&&fx.slots[3].type==4);
  assert(fx.sourceSlots[0]==0&&fx.sourceSlots[1]==1);
  assert(std::abs(fx.slots[3].detail[kDecay]-1.8)<1e-12);
  assert(fx.slots[3].amount>0&&fx.slots[3].amount<10);
  // A native Graphic7EQ can occupy MFX, with all seven signed gains intact.
  auto raw=bank->programs[find("A000")].controls;
  auto *payload=raw.data()+0x194;
  const auto bits=[&](int byte,int shift,int width,int value) {
    for(int bit=0;bit<width;++bit) {
      const int offset=8*byte+shift+bit;
      payload[offset/8]=uint8_t((payload[offset/8]&~(1u<<(offset%8)))|(((unsigned(value)>>bit)&1u)<<(offset%8)));
    }
  };
  payload[64]=8;payload[65]=64;
  bits(0,1,7,100);bits(2,6,7,85);bits(3,5,4,5);
  const int offsets[]={4,5,5,6,7,8,9}, shifts[]={1,0,7,6,5,4,3};
  for(int i=0;i<7;++i)bits(offsets[i],shifts[i],7,-36+12*i);
  const auto graphic=ProgramEffects::Decode(raw.data()).slots[2];
  assert(graphic.type==11 && graphic.enabled && graphic.detail[kGraphicType]==5 && graphic.detail[kFxTrim]==85);
  for(int i=0;i<7;++i)assert(graphic.detail[kGraphicGain+i]==-18+6*i);
  unsigned missing=0;
  for(const auto &program:bank->programs) {
    const auto effects=ProgramEffects::Decode(program.controls.data());
    for(unsigned i=0;i<4;++i) {
      const auto &slot=effects.slots[i];
      if(effects.sourceIDs[i] && slot.type==1)++missing;
      assert(slot.type>=1&&slot.type<int(i<2?kInsertTypes.size():kSendTypes.size()));
      assert(slot.amount>=0&&slot.amount<=100);
      for(int d=0;d<kFxDetailCount;++d)assert(std::isfinite(slot.detail[d])&&slot.detail[d]>=kFxValues[d].min&&slot.detail[d]<=kFxValues[d].max);
    }
    const auto arp=ProgramArpeggiator(program.controls.data());
    assert(arp.pattern>=0&&arp.pattern<kArpPatternCount&&arp.gate>=1&&arp.gate<=101);
    const double gain=ProgramLevelGain(program.id.data());assert(gain>=std::pow(10.,-36./20)&&gain<=std::pow(10.,18./20));
  }
  std::cout<<"Unsupported selected native slots: "<<missing<<'\n';
  for(const char *id:{"D105","G078","F033","g7-126","g1-123","g5-125"}) {
    const auto index=find(id);
    auto engine=std::make_unique<InstrumentEngine>(concert,bank);
    Controls c;c.program=int(index)+1;c.fx=engine->FactoryEffects(c.program).slots;
    engine->Prepare(48000);assert(engine->SetControls(c,true));
    for(int note:{48,60,72})engine->Queue({0,0x90,uint8_t(note),110});
    float l[128],r[128];double energy=0,peak=0;
    for(int at=0;at<48000*8;at+=128) {
      engine->Process(l,r,128);
      for(int n=0;n<128;++n){assert(std::isfinite(l[n])&&std::isfinite(r[n]));peak=std::max({peak,std::abs(double(l[n])),std::abs(double(r[n]))});energy+=l[n]*l[n]+r[n]*r[n];}
    }
    assert(peak<=1. && energy>1e-5);
    std::cout<<id<<" peak="<<peak<<" energy="<<energy<<'\n';
  }
  // The original cymbal/snare tail continues beyond its PCM file through the
  // loop, then follows the kit's envelope instead of dropping at file EOF.
  auto drum=std::make_unique<ProgramEngine>(bank);Controls dry;dry.fxBypass=true;drum->SetControls(dry);
  drum->SetProgram(find("F033"));drum->Prepare(48000);drum->Queue({0,0x90,95,127});
  float l[128],r[128];double late=0;
  for(int at=0;at<48000*4;at+=128){drum->Process(l,r,128);if(at>48000*3)for(int i=0;i<128;++i)late+=l[i]*l[i]+r[i]*r[i];}
  assert(late>1e-7);
  std::cout<<"PASS complete Program FX/ARP/range coverage; six reported patches, bounded output and drum tail beyond EOF\n";
}
