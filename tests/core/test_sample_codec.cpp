#include "samples/NativeSampleCodec.h"
#include "engine/PianoEngine.h"
#include "samples/ProgramLibrary.h"
#include <cassert>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>

using namespace segrand;
template<class F> void Reject(F action) {
  bool rejected=false;
  try { action(); } catch(const std::exception&) { rejected=true; }
  assert(rejected);
}
void CheckInvalidBanks(const std::filesystem::path& source){
  const auto temporary=std::filesystem::temp_directory_path()/
    ("krose-codec-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::create_directory(temporary);
  const auto factory=temporary/"Factory.samples";
  {
    std::ifstream input(source/"Factory.samples",std::ios::binary);
    std::array<char,4096> header{};input.read(header.data(),header.size());assert(input);
    const bool native=std::memcmp(header.data(),"KRPRG003",8)==0;
    if(native){
      constexpr size_t codec=24+224*4+256*2+129*2+512+36;
      header[codec]=3;
      std::ofstream output(factory,std::ios::binary);output.write(header.data(),header.size());output.close();
      // Preserve the declared payload size without allocating/copying a full bank.
      std::filesystem::resize_file(factory,std::filesystem::file_size(source/"Factory.samples"));
      Reject([&]{ProgramLibrary::Load(factory.string(),false);});
      std::filesystem::resize_file(factory,100);
      Reject([&]{ProgramLibrary::Load(factory.string(),false);});
      std::filesystem::remove(factory);
    }
  }
  {
    std::ifstream input(source/"SEGrand.samples",std::ios::binary);
    std::array<char,2720> view{};input.read(view.data(),view.size());assert(input);
    if(uint8_t(view[8])==2){
      std::error_code error;
      std::filesystem::create_hard_link(std::filesystem::absolute(source/"Factory.samples"),factory,error);
      if(error)std::filesystem::copy_file(source/"Factory.samples",factory);
      const auto concert=temporary/"SEGrand.samples";
      // Invalid channel index, mismatched frame count and trailing view data.
      const auto original=view;
      for(int mutation=0;mutation<3;++mutation){
        view=original;
        if(mutation==0)std::memset(view.data()+32+24,0xff,4);
        if(mutation==1)view[32+12]^=1;
        std::ofstream output(concert,std::ios::binary);output.write(view.data(),view.size());
        if(mutation==2)output.put('x');output.close();
        Reject([&]{SampleBank::Load(concert.string(),false);});
      }
    }
  }
  std::filesystem::remove_all(temporary);
}
int main(int argc,char** argv) {
  std::array<int16_t,256> lut{};
  // Feedback includes low 8 bits, truncates negative division towards zero,
  // and saturates symmetrically at both the predictor and reconstruction.
  lut[128]=32767;lut[129]=-32768;lut[130]=1;
  const std::string codes{"\0\0\1\1\2\1\0\2",8};
  const std::array<uint32_t,8> expected{{0x7fff00,0x7fffff,0xffffff,0x800000,0x800100,0x800000,0xffff00,0x40017f}};
  // This constant vector is independently fixed by the research C decoder below;
  // it exercises overflow before adding an opposite-sign residual.
  std::istringstream stream(codes);
  PCM24 decoded;
  ReadSamplePCM(stream,1,24577,-8193,lut,8,decoded);
  for(size_t i=0;i<expected.size();++i){
    const auto* p=decoded.data()+i*3;
    const auto value=uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16);
    if(value!=expected[i]){std::cerr<<"vector "<<i<<": "<<std::hex<<value<<'\n';return 1;}
  }
  std::istringstream raw(std::string{"\0\x80\xff\x7f\xff\xff",6});
  ReadSamplePCM(raw,2,0,0,lut,3,decoded);
  assert(decoded[0]==-1&&decoded[1]==32767.f/32768.f&&decoded[2]==-1.f/32768.f);
  Reject([&]{std::istringstream shortFile("x");ReadSamplePCM(shortFile,1,0,0,lut,2,decoded);});
  Reject([&]{std::istringstream shortFile("x");ReadSamplePCM(shortFile,2,0,0,lut,1,decoded);});
  Reject([&]{std::istringstream input;ReadSamplePCM(input,3,0,0,lut,1,decoded);});
  if(argc==3){
    // Optional full migration acceptance: old PCM banks and staged native banks.
    const auto start=std::chrono::steady_clock::now();
    auto old=ProgramLibrary::Load((std::filesystem::path(argv[1])/"Factory.samples").string());
    auto native=ProgramLibrary::Load((std::filesystem::path(argv[2])/"Factory.samples").string(),false);
    assert(native->samples.size()==old->samples.size());
    for(uint32_t i=0;i<old->samples.size();++i){
      const auto pcm=native->LoadSamples({i},false);
      assert(pcm[i]->size()==old->samples[i].pcm.size());
      assert(std::memcmp(pcm[i]->data(),old->samples[i].pcm.data(),pcm[i]->size()*3)==0);
    }
    auto concertOld=SampleBank::Load((std::filesystem::path(argv[1])/"SEGrand.samples").string());
    auto concertNative=SampleBank::Load((std::filesystem::path(argv[2])/"SEGrand.samples").string());
    for(size_t l=0;l<3;++l)for(size_t i=0;i<28;++i){
      const auto& a=concertOld->layers[l][i];const auto& b=concertNative->layers[l][i];
      assert(a.frames()==b.frames()&&a.loopStart==b.loopStart&&a.loopEnd==b.loopEnd);
      assert(std::memcmp(a.stereo.data(),b.stereo.data(),a.stereo.size()*3)==0);
    }
    std::cout<<"Bit-exact C++ decoding: "<<old->samples.size()<<" mono + 84 stereo, "
      <<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()<<" s\n";
  }else {assert(argc==1||argc==2);if(argc==2)CheckInvalidBanks(argv[1]);}
  std::cout<<"PASS native disk codecs, saturation, truncation and format rejection\n";
}
