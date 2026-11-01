#include "PianoEngine.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
using namespace segrand;
static void U32(std::ofstream& f,uint32_t v){for(int i=0;i<4;++i)f.put(char((v>>(i*8))&255));}
static void U16(std::ofstream& f,uint16_t v){f.put(char(v&255));f.put(char(v>>8));}
int main(int argc,char** argv){
  if(argc<3||argc>5){std::cerr<<"render-piano sample-pack output.wav [--dry] [--no-filter]\n";return 1;}
  auto bank=SampleBank::Load(argv[1]);PianoEngine engine(bank);
  Controls controls;
  for(int i=3;i<argc;++i){const std::string flag=argv[i];if(flag=="--dry")controls.space=0;else if(flag=="--no-filter")controls.filterEnabled=false;else return 1;}
  engine.SetControls(controls);engine.Prepare(48000);
  constexpr int rate=48000,frames=rate*14;
  std::vector<float> left(frames),right(frames);
  for(int i=0;i<8;++i){const int notes[]={48,55,60,64,67,72,76,79};int when=i*rate/2;
    engine.Queue({when,0x90,uint8_t(notes[i]),uint8_t(i<3?65:i<6?96:120)});
    engine.Queue({when+rate/3,0x80,uint8_t(notes[i]),0});}
  engine.Queue({rate*5,0xB0,64,127});
  for(int note:{48,55,60,64,67}){engine.Queue({rate*5,0x90,uint8_t(note),110});engine.Queue({rate*6,0x80,uint8_t(note),0});}
  engine.Queue({rate*8,0xB0,64,0});
  double peak=0;
  for(int start=0;start<frames;start+=256){int n=std::min(256,frames-start);engine.Process(left.data()+start,right.data()+start,n);}
  for(int i=0;i<frames;++i){if(!std::isfinite(left[i])||!std::isfinite(right[i]))return 2;peak=std::max({peak,std::abs(double(left[i])),std::abs(double(right[i]))});}
  double gain=std::min(1.0,0.89/std::max(peak,1e-20));
  std::ofstream f(argv[2],std::ios::binary);f.write("RIFF",4);U32(f,36+frames*4);f.write("WAVEfmt ",8);U32(f,16);U16(f,1);U16(f,2);U32(f,rate);U32(f,rate*4);U16(f,4);U16(f,16);f.write("data",4);U32(f,frames*4);
  for(int i=0;i<frames;++i)for(float x:{left[i],right[i]})U16(f,uint16_t(int16_t(std::lround(x*gain*32767))));
  std::cout<<"Rendered native velocity/EG/filter controls, host filter approximation, chord and sustain pedal; "<<(controls.space==0?"dry-space":"Concert-space")<<"; filter "<<controls.filterEnabled<<"; peak "<<peak<<", listening gain "<<gain<<"\n";
  return !f;
}
