#include "voice/NativeFilter.h"
#include "NativeVoiceData.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <iostream>
using namespace segrand;
int main() {
  std::array<uint8_t,2140> program{};
  std::copy_n(native_data::kProgram, program.size(), program.begin());
  auto *amp = program.data() + 0x564 + 0x118;
  amp[0]=0; amp[1]=99; amp[2]=99; amp[3]=20; amp[4]=80; amp[5]=0; amp[6]=60; amp[7]=99;
  // Remove EG time/level modulation from this deterministic instrument.
  std::fill(amp+12,amp+33,0);
  NativeVoice voice;
  voice.StartProgram(program.data(),60,100,0,127);
  const auto longAttack=voice.Duration();
  for(int i=0;i<4;++i)voice.Tick();
  const int before=voice.Level();
  voice.SetOffsets({-99,0,0,0});
  assert(voice.Level()==before && voice.Duration()<longAttack);
  for(int i=0;i<2000&&voice.Stage()!=6;++i)voice.Tick();
  assert(voice.Stage()==6 && !voice.Finished());
  const int held=voice.Level();
  voice.SetOffsets({-99,0,-30,0});
  assert(voice.Level()==held); // No discontinuity or retrigger on an edit.
  for(int i=0;i<4;++i)voice.Tick();
  assert(voice.Stage()==6 && std::abs(voice.Level()-30*330)<4);
  const int sustain=voice.Level();
  voice.SetOffsets({-99,0,-30,-50});
  assert(voice.Stage()==6 && voice.Level()==sustain); // Future release only.
  voice.ReleaseProgram();
  const auto originalRelease=voice.Duration();
  voice.SetOffsets({-99,0,-30,-99});
  assert(voice.Level()==sustain && voice.Duration()<originalRelease);
  for(int i=0;i<100&&!voice.Finished();++i)voice.Tick();
  assert(voice.Finished());

  auto *eg=program.data()+0x564+0xd8;
  std::fill(eg+13,eg+34,0);
  eg[4]=0;eg[5]=99;eg[6]=99;eg[7]=0;eg[8]=70;eg[9]=0;eg[10]=50;eg[11]=99;eg[12]=0;
  voice.SetOffsets({});voice.StartProgram(program.data(),60,100,0,127);
  NativeFilter filter;filter.StartProgram(program.data(),voice,0,100,48000);
  const auto filterAttack=filter.Duration();
  const int initial=filter.Level();
  filter.SetOffsets({-99,0,0,0},0,0);
  assert(filter.Level()==initial && filter.Duration()<filterAttack);
  for(int i=0;i<32;++i)filter.Tick();
  assert(filter.Stage()==6);
  const int filterHeld=filter.Level();
  filter.SetOffsets({-99,0,-25,0},0,0);
  assert(filter.Level()==filterHeld);
  for(int i=0;i<4;++i)filter.Tick();
  assert(filter.Stage()==6 && std::abs(filter.Level()-25*330)<4);
  filter.Release();
  const auto filterRelease=filter.Duration();
  filter.SetOffsets({-99,0,-25,-99},0,0);
  assert(filter.Duration()<filterRelease);
  for(int i=0;i<32;++i)filter.Tick();
  assert(std::abs(filter.Level())<4);
  // EG intensity changes a held note's filter depth, without changing its envelope timing.
  auto *branch = program.data() + 0x564 + 0x90;
  branch[19] = 35; branch[22] = 0; branch[23] = 0; branch[24] = 0;
  NativeFilter depth;
  depth.SetOffsets({-99,0,0,0},0,0);
  depth.StartProgram(program.data(),voice,0,100,48000);
  for (int i=0;i<32;++i) depth.Tick();
  const auto duration = depth.Duration();
  const int level = depth.Level(), original = depth.Word(0,1);
  assert(level > 0);
  depth.SetOffsets({-99,0,0,0},0,0,99); depth.Tick();
  const int positive = depth.Word(0,1);
  depth.SetOffsets({-99,0,0,0},0,0,-99); depth.Tick();
  const int negative = depth.Word(0,1);
  assert(positive > original && original > negative);
  assert(depth.Level() == level && depth.Duration() == duration);
  depth.SetOffsets({-99,0,0,0},0,0,0); depth.Tick();
  assert(depth.Word(0,1) == original);
  std::cout<<"PASS held AMP/filter sustain, in-flight attack/release retiming, continuity and future-phase edits\n";
}
