#include "ProgramEngine.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <vector>
using namespace segrand;
static void U32(std::ofstream& f,uint32_t v){for(int i=0;i<4;++i)f.put(char((v>>(i*8))&255));}
static void U16(std::ofstream& f,uint16_t v){f.put(char(v&255));f.put(char(v>>8));}
int main(int argc,char** argv){
 if(argc!=4){std::cerr<<"render-program Factory.samples ProgramID output.wav\n";return 1;}
 auto bank=ProgramLibrary::Load(argv[1]);auto it=std::find_if(bank->programs.begin(),bank->programs.end(),[&](const InstrumentProgram& p){return std::string(p.id.data())==argv[2];});
 if(it==bank->programs.end())return 2;ProgramEngine engine(bank);engine.SetProgram(unsigned(it-bank->programs.begin()));Controls c;c.space=.2;engine.SetControls(c);engine.Prepare(48000);
 constexpr int rate=48000,frames=rate*10;
 if(it->drum){for(int beat=0;beat<16;++beat){engine.Queue({beat*rate/4,0x99,uint8_t(beat%4==2?38:36),uint8_t(beat%2?80:115)});engine.Queue({beat*rate/4,0x99,uint8_t(beat==7||beat==15?58:54),90});}}
 else{int i=0;for(int note:{48,55,60,64,67,72,76,79}){engine.Queue({i*rate/3,0x90,uint8_t(note),uint8_t(60+i*9)});engine.Queue({i*rate/3+rate/4,0x80,uint8_t(note),0});++i;}engine.Queue({rate*3,0xb0,64,127});for(int note:{48,55,60,64,67}){engine.Queue({rate*3,0x90,uint8_t(note),100});engine.Queue({rate*4,0x80,uint8_t(note),0});}engine.Queue({rate*5,0xb0,64,0});}
 std::vector<float> l(frames),r(frames);for(int i=0;i<frames;i+=256)engine.Process(l.data()+i,r.data()+i,std::min(256,frames-i));
 double peak=0,energy=0;for(int i=0;i<frames;++i){if(!std::isfinite(l[i])||!std::isfinite(r[i]))return 3;peak=std::max({peak,std::abs(double(l[i])),std::abs(double(r[i]))});energy+=l[i]*l[i]+r[i]*r[i];}
 const double gain=std::min(1.,.95/std::max(peak,1e-20));std::ofstream f(argv[3],std::ios::binary);f.write("RIFF",4);U32(f,36+frames*4);f.write("WAVEfmt ",8);U32(f,16);U16(f,1);U16(f,2);U32(f,rate);U32(f,rate*4);U16(f,4);U16(f,16);f.write("data",4);U32(f,frames*4);for(int i=0;i<frames;++i)for(auto x:{l[i],r[i]})U16(f,uint16_t(int16_t(std::lround(x*gain*32767))));
 std::cout<<it->id.data()<<" "<<it->name.data()<<" peak="<<peak<<" energy="<<energy<<" gain="<<gain<<" PCM_bytes="<<bank->PCMBytes()<<'\n';return !f;
}
