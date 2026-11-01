#include "ProgramEngine.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <vector>
using namespace segrand;
int main(int argc,char** argv){
 if(argc!=2)return 1;const auto start=std::chrono::steady_clock::now();auto bank=ProgramLibrary::Load(argv[1]);const double load=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
 std::cout<<"{\"load_ms\":"<<load<<",\"shared_PCM_bytes\":"<<bank->PCMBytes()<<",\"programs\":[";
 for(unsigned p=0;p<bank->programs.size();++p){ProgramEngine engine(bank);Controls c;c.space=.2;engine.SetControls(c);engine.SetProgram(p);engine.Prepare(48000);std::array<float,128> l{},r{};for(int i=0;i<64;++i)engine.Queue({0,0x90,uint8_t(36+i),100});std::vector<double> times;times.reserve(1000);for(int i=0;i<1000;++i){auto before=std::chrono::steady_clock::now();engine.Process(l.data(),r.data(),128);times.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-before).count());}std::sort(times.begin(),times.end());if(p)std::cout<<',';std::cout<<"{\"id\":\""<<bank->programs[p].id.data()<<"\",\"median_us\":"<<times[500]<<",\"p99_us\":"<<times[990]<<",\"max_us\":"<<times.back()<<",\"end_OSC_voices\":"<<engine.ActiveVoices()<<'}';}
 std::cout<<"]}\n";
}
