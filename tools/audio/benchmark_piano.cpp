// Local engine timing only; excludes DAW, GUI, audio driver and plugin wrapper.
#include "engine/PianoEngine.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <iostream>
#include <vector>
int main(int argc,char** argv){
  if(argc!=2)return 2;
  auto bank=segrand::SampleBank::Load(argv[1]);
  segrand::PianoEngine engine(bank);
  std::array<float,128> left{},right{};
  std::cout<<"{\"scope\":\"local engine, 64 held voices, three running effect cores, 128 frames; no DAW\",\"measurements\":[";
  bool first=true;
  for(double rate:{44100.,48000.,96000.}){
    engine.Prepare(rate);
    for(int note=36;note<100;++note)engine.Queue({0,0x90,static_cast<uint8_t>(note),110});
    for(int i=0;i<100;++i)engine.Process(left.data(),right.data(),128);
    if(engine.ActiveVoices()!=64){std::cerr<<"Expected 64 active voices after warmup\n";return 3;}
    std::vector<double> timings;timings.reserve(1000);
    for(int i=0;i<1000;++i){
      auto start=std::chrono::steady_clock::now();
      engine.Process(left.data(),right.data(),128);
      timings.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count());
    }
    if(engine.ActiveVoices()!=64){std::cerr<<"Benchmark lost active voices\n";return 3;}
    std::sort(timings.begin(),timings.end());
    if(!first)std::cout<<',';first=false;
    std::cout<<"{\"rate_hz\":"<<rate<<",\"active_voices_at_start_and_end\":64,\"median_us\":"<<timings[500]<<",\"p99_us\":"<<timings[990]
      <<",\"max_us\":"<<timings.back()<<",\"block_budget_us\":"<<128e6/rate<<'}';
  }
  std::cout<<"]}\n";
}
