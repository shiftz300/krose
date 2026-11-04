#include "ProgramLibrary.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <mutex>
#include <stdexcept>
namespace segrand {
namespace {
class Reader {
public:
 std::ifstream file;
 explicit Reader(const std::string& path):file(std::filesystem::u8path(path),std::ios::binary){if(!file)throw std::runtime_error("Factory sample library is missing");}
 void Bytes(void* target,size_t size){if(!file.read(static_cast<char*>(target),std::streamsize(size)))throw std::runtime_error("Truncated factory library");}
 uint32_t U32(){uint8_t p[4];Bytes(p,4);return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
 int32_t I32(){const auto bits=U32();int32_t v;std::memcpy(&v,&bits,4);return v;}
 uint64_t U64(){const auto lo=U32();return uint64_t(lo)|(uint64_t(U32())<<32);}
 float Float(){const auto bits=U32();float v;std::memcpy(&v,&bits,4);return v;}
};
void Require(bool value){if(!value)throw std::runtime_error("Invalid factory library");}
}
std::shared_ptr<const ProgramLibrary> ProgramLibrary::Load(const std::string& path){
 static std::mutex mutex;
 static std::map<std::string,std::weak_ptr<const ProgramLibrary>> cache;
 const std::string key=std::filesystem::absolute(std::filesystem::u8path(path)).lexically_normal().string();
 std::lock_guard<std::mutex> lock(mutex); // Loading only, never called by audio processing.
 if(auto existing=cache[key].lock())return existing;
 for(auto it=cache.begin();it!=cache.end();)if(it->second.expired())it=cache.erase(it);else ++it;
 Reader in(key);char magic[8];in.Bytes(magic,8);Require(!std::memcmp(magic,"KRPRG002",8)&&in.U32()==2);
 const auto sampleCount=in.U32(),regionCount=in.U32(),programCount=in.U32();
 Require(sampleCount>0&&sampleCount<=8192&&regionCount>0&&regionCount<=262144&&programCount>0&&programCount<=2048);
 const auto fileSize=std::filesystem::file_size(key);Require(fileSize<=512ull*1024*1024);
 auto bank=std::make_shared<ProgramLibrary>();
 for(auto& v:bank->mPhaseBase)v=in.U32();
 for(auto& v:bank->mPhaseFraction){uint8_t p[2];in.Bytes(p,2);v=uint16_t(p[0])|(uint16_t(p[1])<<8);}
 for(auto& v:bank->mCrossfade){uint8_t p[2];in.Bytes(p,2);v=uint16_t(p[0])|(uint16_t(p[1])<<8);}
 struct Payload{uint32_t frames;uint64_t offset;};std::vector<Payload> payloads;
 bank->samples.resize(sampleCount);payloads.reserve(sampleCount);
 uint64_t expected=24+224*4+256*2+129*2+uint64_t(sampleCount)*32+uint64_t(regionCount)*96+uint64_t(programCount)*2232;
 for(auto& sample:bank->samples){
  sample.id=in.U32();const auto frames=in.U32();sample.loopStart=in.U32();sample.loopEnd=in.U32();sample.flags=in.U32();sample.pitch=in.I32();const auto offset=in.U64();
  Require(sample.id<65536&&sample.pitch>=-32768&&sample.pitch<=32767&&frames>0&&frames<=48000*60&&sample.loopStart<frames&&sample.loopEnd<frames&&sample.loopStart<=sample.loopEnd&&offset==expected);
  expected+=uint64_t(frames)*3;Require(expected<=fileSize);payloads.push_back({frames,offset});
 }
 Require(expected==fileSize);bank->regions.resize(regionCount);
 for(auto& r:bank->regions){
  r.sample[0]=in.U32();r.sample[1]=in.U32();r.noteLow=int(in.U32());r.noteHigh=int(in.U32());r.velocityLow=int(in.U32());r.velocityHigh=int(in.U32());
  r.root[0]=int(in.U32());r.fine[0]=in.I32();r.root[1]=int(in.U32());r.fine[1]=in.I32();r.oscillator=int(in.U32());r.slotLevel=int(in.U32());r.pan=int(in.U32());r.exclusive=int(in.U32());r.flags=int(in.U32());r.gain=in.Float();r.coarse=in.I32();r.drumFine=in.I32();r.slot=in.I32();r.fadeInWidth=in.I32();r.fadeInCurve=in.I32();r.fadeOutBottom=in.I32();r.fadeOutWidth=in.I32();r.fadeOutCurve=in.I32();
  Require(r.sample[0]<sampleCount&&(r.sample[1]==UINT32_MAX||r.sample[1]<sampleCount)&&r.noteLow>=0&&r.noteHigh<=127&&r.noteLow<=r.noteHigh&&r.velocityLow>=1&&r.velocityHigh<=127&&r.velocityLow<=r.velocityHigh&&r.root[0]>=0&&r.root[0]<=127&&r.root[1]>=0&&r.root[1]<=127&&std::abs(int64_t(r.fine[0]))<=32768&&std::abs(int64_t(r.fine[1]))<=32768&&r.oscillator>=0&&r.oscillator<2&&r.slotLevel>=0&&r.slotLevel<=127&&r.pan>=0&&r.pan<=127&&r.exclusive>=0&&r.exclusive<=127&&r.flags>=0&&r.flags<16&&std::isfinite(r.gain)&&r.gain>=0&&r.gain<=8&&r.coarse>=-255&&r.coarse<=255&&r.drumFine>=-199&&r.drumFine<=199&&r.slot>=0&&r.slot<4&&r.fadeInWidth>=0&&r.fadeInWidth<=127&&r.fadeOutWidth>=0&&r.fadeOutWidth<=127&&r.fadeInCurve>=0&&r.fadeInCurve<=3&&r.fadeOutCurve>=0&&r.fadeOutCurve<=3&&r.fadeOutBottom>=0&&r.fadeOutBottom<=127);
 }
 bank->programs.resize(programCount);
 for(auto& p:bank->programs){
  in.Bytes(p.id.data(),p.id.size());in.Bytes(p.name.data(),p.name.size());const auto kind=in.U32();p.drum=kind!=0;p.firstRegion=in.U32();p.regionCount=in.U32();in.Bytes(p.controls.data(),p.controls.size());
  Require(kind<=1&&p.id.back()==0&&p.name.back()==0&&p.regionCount>0&&uint64_t(p.firstRegion)+p.regionCount<=regionCount);
  for(auto& osc:p.lookup)for(auto& note:osc)note.fill(-1);
  for(unsigned o=0;o<2;++o){const auto* base=p.controls.data()+0x564+380*o;for(unsigned stage=0;stage<4;++stage)Require(base[0x118+stage*2+1]<100&&base[0x118+8+stage]<=10&&base[0xd8+5+stage*2]<100&&base[0xd8+stage]<=10);}
  for(uint32_t i=p.firstRegion;i<p.firstRegion+p.regionCount;++i){const auto& r=bank->regions[i];Require(p.drum==bool(r.flags&8));for(int n=r.noteLow;n<=r.noteHigh;++n){Require(p.lookup[r.oscillator][n][r.slot]==-1);p.lookup[r.oscillator][n][r.slot]=int32_t(i);}}
 }
 for(size_t i=0;i<bank->samples.size();++i){auto& sample=bank->samples[i];const auto& info=payloads[i];Require(uint64_t(in.file.tellg())==info.offset);std::vector<uint8_t> pcm(size_t(info.frames)*3);in.Bytes(pcm.data(),pcm.size());sample.pcm.resize(info.frames);for(size_t f=0;f<info.frames;++f){const auto* p=pcm.data()+f*3;int32_t v=int32_t(uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16));if(v&0x800000)v-=16777216;sample.pcm[f]=float(v/8388608.0);}}
 cache[key]=bank;return bank;
}
uint32_t ProgramLibrary::Phase(int exponent) const noexcept{
 const auto index=unsigned(std::clamp(exponent,-32768,24575)+32768);const uint32_t base=mPhaseBase[index>>8];return base+((base*uint32_t(mPhaseFraction[index&255]))>>16);
}
double ProgramLibrary::Step(const InstrumentProgram& p,const ProgramRegion& r,int channel,int note,double rate) const noexcept{
 const auto& s=samples[r.sample[channel]];
 if(r.flags&8)return 48000.0*Phase(s.pitch*2)/8192/rate*std::pow(2,(r.coarse+r.drumFine/100.0)/12);
 const int fine=(std::abs(r.fine[channel])*1311/1024)*(r.fine[channel]<0?-1:1);
 const int pitch=SelectionPitch(p,r.oscillator,note);
 int state=int(int16_t(r.root[channel]*256-fine-s.pitch*2));if(r.flags&(2<<channel))state+=pitch-r.root[channel]*256;
 const int exponent=int(int16_t(pitch-state));uint32_t limit=(s.flags&1)?32768:2097151;
 if(!(s.flags&33)){const auto length=s.loopEnd-s.loopStart;if(length<=255)limit=length<=15?65536:length<=31?131072:length<=63?262144:length<=127?524288:1048576;}
 return 48000.0*std::min(Phase(exponent),limit)/8192/rate;
}
int ProgramLibrary::SelectionPitch(const InstrumentProgram& p,int oscillator,int note) noexcept{
 const auto* b=p.controls.data()+0x564+380*oscillator;
 const auto signedByte=[](uint8_t x){return x<128?int(x):int(x)-256;};
 const int slope=signedByte(b[0x7c]),transpose=signedByte(uint8_t(12*signedByte(b[0x78])+b[0x79]));
 int value=slope==0?60*256:slope==10?note*256:slope==-10?(120-note)*256:slope==20?std::clamp(512*note-60*256,0,32767):std::clamp(60*256+((820*note-49200)*slope>>5),0,32767);
 int folded=transpose+(value>>8);while(folded<0)folded+=12;while(folded>127)folded-=12;
 return (folded<<8)|(value&255);
}
int ProgramLibrary::LayerWeight(const ProgramRegion& r,int velocity) const noexcept{
 if(velocity<r.velocityLow||velocity>r.velocityHigh)return 0;
 auto shape=[&](int value,int curve){
  if(curve==2)return 32768;
  if(curve!=1||value>=32768)return value;
  const int index=value>>8,fraction=value&255;
  return int(mCrossfade[index])+((int(mCrossfade[index+1])-mCrossfade[index])*fraction>>8);
 };
 if(r.fadeOutWidth&&velocity>=r.fadeOutBottom)
  return shape(std::clamp(32768-(velocity-r.fadeOutBottom)*32768/r.fadeOutWidth,0,32768),r.fadeOutCurve);
 if(r.fadeInWidth&&velocity<r.velocityLow+r.fadeInWidth)
  return shape(std::clamp((velocity-r.velocityLow)*32768/r.fadeInWidth,0,32768),r.fadeInCurve);
 return 32768;
}
size_t ProgramLibrary::PCMBytes() const noexcept{size_t n=0;for(const auto& s:samples)n+=s.pcm.size()*sizeof(float);return n;}
}
