#include "ProgramEngine.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace segrand {
namespace {
double Read(const SharedSample& sample,double position){
 const auto last=sample.pcm.size()-1;
 const auto i=std::min(last,size_t(std::max(0.0,position)));
 return sample.pcm[i]+(sample.pcm[std::min(last,i+1)]-sample.pcm[i])*(position-std::floor(position));
}
}
ProgramEngine::ProgramEngine(std::shared_ptr<const ProgramLibrary> library):mLibrary(std::move(library)){
 if(!mLibrary||mLibrary->programs.empty())throw std::invalid_argument("Missing factory Programs");
 Prepare(48000);
}
ProgramEngine::~ProgramEngine()=default;
void ProgramEngine::Prepare(double rate){
 if(!std::isfinite(rate)||rate<32000||rate>192000)throw std::invalid_argument("Sample rate must be 32..192 kHz");
 double identity[40]{};for(int i=0;i<8;++i)identity[i*5]=1;
 std::unique_ptr<ConcertEffects,DeleteEffect> room(concert_effects_create(rate,identity,1,1.8,.12*mControls.space,0,0));
 if(!room)throw std::runtime_error("Could not prepare room effect");
 mRoom=std::move(room);mRate=rate;mSmooth=1-std::exp(-1/(rate*.02));mOutput=mTarget;Panic();
}
void ProgramEngine::Panic() noexcept{
 mVoices={};mTails={};mEventCount=0;mOverflow=false;mSustain.fill(false);mBend.fill(1);mVolume.fill(1);mExpression.fill(1);mSoft.fill(1);
 concert_effects_reset(mRoom.get());
}
void ProgramEngine::SetProgram(unsigned index) noexcept{if(index<mLibrary->programs.size())mProgram=index;}
void ProgramEngine::SetControls(const Controls& c) noexcept{
 if(!std::isfinite(c.outputDb)||!std::isfinite(c.space)||!std::isfinite(c.velocityCurve)||!std::isfinite(c.releaseSeconds))return;
 mControls=c;mControls.space=std::clamp(c.space,0.,2.);mControls.velocityCurve=std::clamp(c.velocityCurve,.5,3.);mControls.releaseSeconds=std::clamp(c.releaseSeconds,.03,2.);
 mTarget=std::pow(10,std::clamp(c.outputDb,-60.,6.)/20);concert_effects_set_wet(mRoom.get(),.12*mControls.space,0);
}
unsigned ProgramEngine::ActiveVoices() const noexcept{unsigned n=0;for(const auto& v:mVoices)if(v.region)++n;return n;}
void ProgramEngine::Tail(Voice& voice) noexcept{
 auto it=std::find_if(mTails.begin(),mTails.end(),[](const Voice& v){return !v.region;});if(it==mTails.end())it=mTails.begin();
 *it=voice;it->forced=96;voice={};
}
void ProgramEngine::Release(Voice& voice) noexcept{
 voice.down=false;if(!voice.region||voice.program->drum||voice.released)return;
 voice.released=true;voice.amplitude.ReleaseProgram(mControls.releaseSeconds/kNativeReleaseBaseSeconds);voice.filter.Release();
}
void ProgramEngine::NoteOn(int note,int velocity,int channel) noexcept{
 const auto& p=mLibrary->programs[mProgram];
 std::array<int32_t,8> indices;indices.fill(-1);unsigned selected=0;
 for(int osc=0;osc<2;++osc)for(int slot=0;slot<4;++slot){
  const auto* b=p.controls.data()+0x564+380*osc;
  if(velocity<std::min(b[0x2d],b[0x2e])||velocity>std::max(b[0x2d],b[0x2e]))continue;
  const auto index=p.lookup[osc][note][slot];
  if(index>=0&&mLibrary->LayerWeight(mLibrary->regions[unsigned(index)],velocity)>0)indices[selected++]=index;
 }
 unsigned needed=0;for(auto i:indices)if(i>=0)++needed;if(!needed)return;
 if(p.drum){const int group=mLibrary->regions[unsigned(indices[0])].exclusive;if(group)for(auto& v:mVoices)if(v.region&&v.channel==channel&&v.program==&p&&v.region->exclusive==group)Tail(v);}
 while(kVoices-ActiveVoices()<needed){
  const Voice* oldest=nullptr;for(const auto& v:mVoices)if(v.region&&(!oldest||(v.released&&!oldest->released)||(v.released==oldest->released&&v.age<oldest->age)))oldest=&v;
  if(!oldest)break;const auto age=oldest->age;for(auto& v:mVoices)if(v.region&&v.age==age)Tail(v);
 }
 const uint64_t age=++mAge;
 for(auto index:indices){
  if(index<0)continue;const auto& r=mLibrary->regions[unsigned(index)];
  auto it=std::find_if(mVoices.begin(),mVoices.end(),[](const Voice& v){return !v.region;});if(it==mVoices.end())return;
  auto& v=*it;v={};v.region=&r;v.program=&p;v.note=note;v.channel=channel;v.down=true;v.age=age;
  const int weight=mLibrary->LayerWeight(r,velocity);
  v.velocityTrim=p.drum?std::pow(velocity/127.,1.4)*weight/32768.:std::pow(velocity/127.,mControls.velocityCurve-1);
  const double pan=std::clamp((r.pan-64)/63.,-1.,1.);
  if(r.sample[1]==UINT32_MAX){v.panL=std::cos((pan+1)*.7853981633974483);v.panR=std::sin((pan+1)*.7853981633974483);}
  else {v.panL=pan>0?1-pan:1;v.panR=pan<0?1+pan:1;}
  for(int ch=0;ch<2;++ch)if(r.sample[ch]!=UINT32_MAX){v.step[ch]=mLibrary->Step(p,r,ch,note,mRate);if(r.flags&1)v.position[ch]=mLibrary->samples[r.sample[ch]].pcm.size()-1;}
  if(!p.drum){v.amplitude.SetOffsets(mControls.ampEg);v.filter.SetOffsets(mControls.filterEg,mControls.cutoff,mControls.resonance);v.amplitude.StartProgram(p.controls.data(),note,velocity,r.oscillator,r.slotLevel*weight/32768);v.slew.Reset(v.amplitude.InitialGain());v.slew.SetTarget(v.amplitude.Gain());v.filter.StartProgram(p.controls.data(),v.amplitude,r.oscillator,velocity,mRate);}
 }
}
void ProgramEngine::Queue(MidiEvent event) noexcept{
 event.offset=std::max(0,event.offset);event.data1&=127;event.data2&=127;
 if(mEventCount==kEvents){mOverflow=true;return;}unsigned index=mEventCount++;
 while(index&&mEvents[index-1].offset>event.offset){mEvents[index]=mEvents[index-1];--index;}mEvents[index]=event;
}
void ProgramEngine::Midi(const MidiEvent& e) noexcept{
 const int ch=e.status&15,type=e.status&240,note=e.data1,value=e.data2;
 if(type==0x90&&value){NoteOn(note,value,ch);return;}
 if(type==0x80||(type==0x90&&!value)){
  uint64_t age=UINT64_MAX;for(const auto& v:mVoices)if(v.region&&v.note==note&&v.channel==ch&&v.down)age=std::min(age,v.age);
  for(auto& v:mVoices)if(v.region&&v.age==age){v.down=false;if(!mSustain[ch])Release(v);}
 }else if(type==0xe0)mBend[ch]=std::pow(2,((value*128+note-8192)/8192.)*2/12);
 else if(type==0xb0){
  if(note==64){mSustain[ch]=value>=64;if(!mSustain[ch])for(auto& v:mVoices)if(v.region&&v.channel==ch&&!v.down)Release(v);}
  else if(note==7)mVolume[ch]=value/127.;else if(note==11)mExpression[ch]=value/127.;else if(note==67)mSoft[ch]=value>=64?.75:1;
  else if(note==120){for(auto& v:mVoices)if(v.channel==ch)v={};for(auto& v:mTails)if(v.channel==ch)v={};}
  else if(note==123){for(auto& v:mVoices)if(v.region&&v.channel==ch){v.down=false;if(!mSustain[ch])Release(v);}}
  else if(note==121){mSustain[ch]=false;mBend[ch]=mVolume[ch]=mExpression[ch]=mSoft[ch]=1;for(auto& v:mVoices)if(v.region&&v.channel==ch&&!v.down)Release(v);}
 }
}
void ProgramEngine::RenderVoice(Voice& v,double& left,double& right) noexcept{
 if(!v.region)return;const auto& r=*v.region;std::array<double,2> audio{};
 for(int ch=0;ch<2;++ch){
  if(r.sample[ch]==UINT32_MAX)continue;const auto& sample=mLibrary->samples[r.sample[ch]];
  const bool reverse=r.flags&1,loop=!v.program->drum&&(sample.flags&16)&&sample.loopEnd-sample.loopStart>=8;
  auto& pos=v.position[ch];
  const double cross=loop?std::min(32.,double(sample.loopEnd-sample.loopStart)/8):0;
  if(!reverse&&pos>=sample.loopEnd&&loop){const double restart=sample.loopStart+cross;pos=restart+std::fmod(pos-sample.loopEnd,sample.loopEnd-restart);}
  if(pos<0||pos>=sample.pcm.size()){v.region=nullptr;return;}
  audio[ch]=Read(sample,pos);
  if(loop&&pos>sample.loopEnd-cross){const double blend=(pos-(sample.loopEnd-cross))/cross;const double from=sample.loopStart+pos-(sample.loopEnd-cross);audio[ch]+=(Read(sample,from)-audio[ch])*blend;}
  pos+=(reverse?-1:1)*v.step[ch]*mBend[v.channel];
 }
 double l=audio[0],rr=r.sample[1]==UINT32_MAX?audio[0]:audio[1];
 double level=v.program->drum?.75:v.slew.Current()/65536.;
 if(!v.program->drum&&mControls.filterEnabled)v.filter.Process(l,rr);
 level*=r.gain*v.velocityTrim*mVolume[v.channel]*mExpression[v.channel]*mSoft[v.channel];
 level*=std::min(1.,v.ageSeconds/.002);v.ageSeconds+=1/mRate;
 if(!v.program->drum)level*=.4;
 if(v.forced){level*=v.forced/96.;if(!--v.forced)v.region=nullptr;}
 left+=l*level*v.panL;right+=rr*level*v.panR;
 if(!v.program->drum){
  v.audioPhase+=kNativeAudioHz/mRate;while(v.audioPhase>=1){v.slew.Advance();v.audioPhase-=1;}
  v.phase+=kNativeControlHz/mRate;if(v.phase>=1){v.phase-=1;v.amplitude.SetOffsets(mControls.ampEg);v.filter.SetOffsets(mControls.filterEg,mControls.cutoff,mControls.resonance);v.amplitude.Tick();v.slew.SetTarget(v.amplitude.Gain());v.filter.Tick();}
  if(v.amplitude.Finished()&&v.slew.Silent())v.region=nullptr;
 }
}
void ProgramEngine::Render(float* left,float* right,int frames) noexcept{
 for(int start=0;start<frames;start+=128){
  const int count=std::min(128,frames-start);std::array<float,256> bus{};
  for(int i=0;i<count;++i){double l=0,r=0;for(auto& v:mVoices)RenderVoice(v,l,r);for(auto& v:mTails)RenderVoice(v,l,r);bus[i*2]=float(l);bus[i*2+1]=float(r);}
  // One shared return bus, not a separate reverb per voice or per Program.
  concert_effects_process(mRoom.get(),bus.data(),count);
  for(int i=0;i<count;++i){mOutput+=mSmooth*(mTarget-mOutput);left[start+i]=float(bus[i*2]*mOutput);right[start+i]=float(bus[i*2+1]*mOutput);}
 }
}
void ProgramEngine::Process(float* left,float* right,int frames) noexcept{
 if(frames<=0||!left||!right)return;if(mOverflow)Panic();unsigned consumed=0;int position=0;
 while(consumed<mEventCount&&mEvents[consumed].offset<frames){const int target=mEvents[consumed].offset;if(target>position)Render(left+position,right+position,target-position);position=target;Midi(mEvents[consumed++]);}
 if(position<frames)Render(left+position,right+position,frames-position);
 for(unsigned i=consumed;i<mEventCount;++i){mEvents[i-consumed]=mEvents[i];mEvents[i-consumed].offset-=frames;}mEventCount-=consumed;
}
}
