#include "engine/ProgramEngine.h"
#include "NativeVoiceData.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <memory>
using namespace segrand;
int main(int argc,char **argv) {
  assert(argc==2);
  const auto bank=ProgramLibrary::Load(argv[1]);
  auto a=std::make_unique<ProgramEngine>(bank), b=std::make_unique<ProgramEngine>(bank);
  Controls controls; controls.fxBypass=true; controls.space=0;
  unsigned program=0;
  while(program<bank->programs.size() && std::strcmp(bank->programs[program].id.data(),"B019")) ++program;
  assert(program<bank->programs.size());
  // Percussion organ disables pitch bend in the original program. A global
  // +/-2-semitone multiplier previously retuned it despite this setting.
  for(double rate:{32000.,48000.,192000.}) {
    for(auto *engine:{a.get(),b.get()}) {
      engine->SetControls(controls); engine->SetProgram(program); engine->Prepare(rate);
      engine->Queue({0,0x90,69,110});
    }
    float l[128],r[128],x[128],y[128];
    for(int block=0;block<300;++block) {
      if(block==100)a->Queue({17,0xe0,127,127});
      if(block==200)a->Queue({31,0xe0,0,0});
      a->Process(l,r,128);b->Process(x,y,128);
      for(int i=0;i<128;++i)assert(l[i]==x[i] && r[i]==y[i]);
    }
    a->Queue({0,0xb0,120,0});
    a->Process(l,r,128); b->Process(x,y,128);
    assert(l[0]==x[0] && r[0]==y[0]); // No hard step on All Sound Off.
    for(int i=97;i<128;++i)assert(l[i]==0 && r[i]==0);
  }
  // Honor the native filter bypass bit without altering trim/output levels.
  std::array<uint8_t,sizeof(native_data::kProgram)> raw{};
  std::copy(std::begin(native_data::kProgram),std::end(native_data::kProgram),raw.begin());
  auto *osc=raw.data()+0x564;
  osc[0x88]=0; osc[0xa0]=128; osc[0xa1]=osc[0xa2]=99;
  NativeVoice amp; amp.StartProgram(raw.data(),60,100,0,127);
  NativeFilter filter;filter.StartProgram(raw.data(),amp,0,100,48000);
  const double gain=(filter.Word(0,0)/32768.)*(filter.Word(0,3)/32768.);
  for(int i=0;i<4096;++i) {
    const double input=std::sin(i*.731);double left=input,right=-input;
    filter.Process(left,right);
    assert(std::abs(left-input*gain)<1e-12 && right==-left);
  }
  std::cout<<"PASS native zero-bend organ, channel All Sound Off continuity at three rates, native filter bypass\n";
}
