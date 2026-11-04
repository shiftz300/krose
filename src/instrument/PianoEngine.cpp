#include "PianoEngine.h"
#include "SampleResidency.h"
#include "ConcertEqData.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <mutex>
#include <map>
#include <stdexcept>

namespace segrand {
namespace {
uint32_t U32(const unsigned char* p) {return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
uint64_t U64(const unsigned char* p) {return uint64_t(U32(p))|uint64_t(U32(p+4))<<32;}
double Interpolate(const Sample& sample,double position,int channel) {
  const auto base=static_cast<int64_t>(position);
  const double f=position-base;
  auto at=[&](int64_t i){return double(sample.stereo[static_cast<size_t>(std::clamp<int64_t>(i,0,sample.frames()-1))*2+channel]);};
  const double a=at(base-1),b=at(base),c=at(base+1),d=at(base+2);
  return b+0.5*f*(c-a+f*(2*a-5*b+4*c-d+f*(3*(b-c)+d-a)));
}
}

std::shared_ptr<const SampleBank> SampleBank::Load(const std::string& path,bool preload) {
  // Construction only. Instances share immutable samples; no audio-thread locks.
  static std::mutex mutex;
  static std::map<std::string,std::weak_ptr<const SampleBank>> cache;
  std::lock_guard<std::mutex> lock(mutex);
  const auto key=path+(preload?"#full":"#metadata");
  if(auto existing=cache[key].lock())return existing;
  for(auto it=cache.begin();it!=cache.end();)if(it->second.expired())it=cache.erase(it);else ++it;
  std::ifstream file(std::filesystem::u8path(path),std::ios::binary|std::ios::ate);
  if(!file)throw std::runtime_error("Sample library is missing");
  const auto fileSize=file.tellg();
  if(fileSize<32 || fileSize>268435456)throw std::runtime_error("Invalid sample library size");
  file.seekg(0);
  unsigned char header[32];
  if(!file.read(reinterpret_cast<char*>(header),32)||std::memcmp(header,"SEGRAND1",8)||U32(header+8)!=1||U32(header+12)!=84||U32(header+24)!=32)
    throw std::runtime_error("Invalid sample library header");
  auto bank=std::make_shared<SampleBank>();bank->path=path;bank->preloaded=preload;
  uint64_t rateBits=U64(header+16);
  std::memcpy(&bank->rootRate,&rateBits,8);
  if(bank->rootRate!=42017.578125)throw std::runtime_error("Unsupported source playback rate");
  std::array<unsigned char,84*32> descriptors;
  if(!file.read(reinterpret_cast<char*>(descriptors.data()),descriptors.size()))throw std::runtime_error("Incomplete sample table");
  uint64_t expectedOffset=32+descriptors.size();
  unsigned previousLayer=0, previousTop=0;
  for(unsigned i=0;i<84;++i) {
    const unsigned char* d=descriptors.data()+i*32;
    const unsigned layer=U32(d),root=U32(d+4),top=U32(d+8),frames=U32(d+12),start=U32(d+16),end=U32(d+20);
    const uint64_t offset=U64(d+24),bytes=uint64_t(frames)*6;
    if(layer>2||layer!=i/28||root>127||top>127||root>top||frames<4||frames>48000*60||start>=end||end>=frames||offset!=expectedOffset||offset+bytes>uint64_t(fileSize)
       ||(i>0&&layer==previousLayer&&top<=previousTop))throw std::runtime_error("Invalid sample region");
    previousTop=top; previousLayer=layer; expectedOffset+=bytes;
    Sample sample;sample.root=root;sample.top=top;sample.loopStart=start;sample.loopEnd=end;
    sample.frameCount=frames;
    if(preload){sample.stereo.resize(static_cast<size_t>(frames)*2);
    file.seekg(static_cast<std::streamoff>(offset));
    if(!file.read(reinterpret_cast<char*>(sample.stereo.data()),bytes))throw std::runtime_error("Incomplete sample payload");}
    bank->layers[layer].push_back(std::move(sample));
  }
  if(expectedOffset!=uint64_t(fileSize))throw std::runtime_error("Trailing sample payload data");
  cache[key]=bank;
  return bank;
}

const Sample& SampleBank::Select(unsigned layer,unsigned note) const {
  const auto& regions=layers.at(layer);
  for(const auto& sample:regions)if(note<=sample.top)return sample;
  return regions.back();
}

PianoEngine::PianoEngine(std::shared_ptr<const SampleBank> bank):mBank(std::move(bank)) {
  if(!mBank)throw std::invalid_argument("Missing sample bank");
  mPlaybackBank=mBank.get();
  Prepare(48000);
}
void PianoEngine::SetSamples(const SampleResidency* samples) noexcept {
 mResidency=samples;mPlaybackBank=samples?samples->concert.get():mBank.get();
}
void PianoEngine::MarkSamples(bool* used) const noexcept {
 for(const auto& v:mVoices)if(v.sample&&v.residency)used[v.residency->slot]=true;
 for(const auto& v:mTails)if(v.sample&&v.residency)used[v.residency->slot]=true;
}
void PianoEngine::Deactivate() noexcept {
 mMono.Reset();mSustain.fill(false);for(auto& v:mVoices)if(v.sample)Release(v);
}
PianoEngine::~PianoEngine()=default;
void PianoEngine::Prepare(double rate) {
  if(!std::isfinite(rate)||rate<32000||rate>192000)throw std::invalid_argument("Sample rate must be 32..192 kHz");
  std::array<std::unique_ptr<ConcertEffects,EffectDeleter>,3> effects;
  const double times[3]={1.8,1.5,2.6},wet[3]={0.15,0.12,0.23},chorus[3]={0,0,0.18},tone[3]={0,8500,0};
  for(int i=0;i<3;++i){
    effects[i].reset(concert_effects_create(rate,kConcertEq,kConcertTrim,times[i],wet[i]*mControls.space,chorus[i],tone[i]));
    if(!effects[i])throw std::runtime_error("Could not prepare effects");
  }
  mEffects=std::move(effects);mRate=rate;
  mControlIncrement=kNativeControlHz/rate;mNativeAudioIncrement=kNativeAudioHz/rate;
  mSmoothing=1-std::exp(-1/(rate*0.02));
  mOutputTarget=std::pow(10,mControls.outputDb/20);mOutput=mOutputTarget;
  mWeights={{0,0,0}};mWeights[static_cast<size_t>(mControls.preset)]=1;
  Panic();
}
void PianoEngine::Panic() noexcept {
  mMono.Reset();mVoices={};mTails={};mSustain.fill(false);mBend.fill(1);mVolume.fill(1);mExpression.fill(1);mSoft.fill(1);
  mEventCount=0;mOverflow=false;
  for(auto& effect:mEffects)concert_effects_reset(effect.get());
}
unsigned PianoEngine::ActiveVoices() const noexcept {unsigned n=0;for(const auto& v:mVoices)if(v.sample)++n;return n;}
void PianoEngine::SetControls(const Controls& incoming) {
  Controls c=incoming;
  if(!std::isfinite(c.outputDb)||!std::isfinite(c.space)||!std::isfinite(c.releaseSeconds)||!std::isfinite(c.velocityCurve))return;
  c.preset=std::clamp(c.preset,0,2);c.outputDb=std::clamp(c.outputDb,-60.0,6.0);c.space=std::clamp(c.space,0.0,2.0);
  c.releaseSeconds=std::clamp(c.releaseSeconds,0.03,2.0);c.velocityCurve=std::clamp(c.velocityCurve,0.5,3.0);
  mOutputTarget=std::pow(10,c.outputDb/20);
  const double wet[3]={0.15,0.12,0.23},chorus[3]={0,0,0.18};
  for(int i=0;i<3;++i)concert_effects_set_wet(mEffects[i].get(),wet[i]*c.space,chorus[i]);
  c.voiceMode=std::clamp(c.voiceMode,0,2);c.glide=std::clamp(c.glide,0,127);
  if(c.voiceMode!=mControls.voiceMode){mMono.Reset();for(auto& voice:mVoices)if(voice.sample)Tail(voice);}
  mControls=c;
}
void PianoEngine::Queue(MidiEvent event) noexcept {
  event.offset=std::max(0,event.offset);event.data1&=127;event.data2&=127;
  if(mEventCount==kEvents){mOverflow=true;return;}
  unsigned index=mEventCount++;
  while(index&&mEvents[index-1].offset>event.offset){mEvents[index]=mEvents[index-1];--index;}
  mEvents[index]=event;
}
void PianoEngine::Release(Voice& voice) noexcept {
  voice.keyDown=false;voice.released=true;
  for(auto& native:voice.native)native.Release(mControls.releaseSeconds);
  for(auto& filter:voice.filter)filter.Release();
}
void PianoEngine::Tail(Voice& voice) noexcept {
  auto tail=std::find_if(mTails.begin(),mTails.end(),[](const Voice& v){return !v.sample;});
  if(tail==mTails.end())tail=mTails.begin();
  *tail=voice;tail->forcedRemaining=96;voice={};
}
void PianoEngine::SelectMono(int note,int velocity,int channel,bool connected) noexcept {
  int previous=-1;
  bool reused=false;
  for(auto& voice:mVoices)if(voice.sample&&voice.channel==channel){
    if(connected&&voice.keyDown&&!voice.released){
      previous=voice.glide.CurrentPitch();
      if(mControls.voiceMode==2){
        if(voice.note==note){reused=true;continue;}
        voice.note=note;
        voice.step=mBank->rootRate/mRate*std::exp2((note-int(voice.sample->root))/12.);
        voice.glide.Start(previous,note,mControls.glide);voice.glideRatio=voice.glide.Ratio();
        for(int osc=0;osc<2;++osc){voice.native[osc].Retune(note);voice.filter[osc].Retune(voice.native[osc]);voice.slew[osc].SetTarget(voice.native[osc].Gain());}
        reused=true;continue;
      }
    }
    Tail(voice);
  }
  if(!reused)NoteOn(note,velocity,channel,previous);
}
void PianoEngine::NoteOn(int note,int velocity,int channel,int previousPitch) noexcept {
  auto it=std::find_if(mVoices.begin(),mVoices.end(),[](const Voice& v){return !v.sample;});
  if(it==mVoices.end()){
    it=std::min_element(mVoices.begin(),mVoices.end(),[](const Voice& a,const Voice& b){
      if(a.released!=b.released)return a.released;
      return a.age<b.age;
    });
    auto tail=std::find_if(mTails.begin(),mTails.end(),[](const Voice& v){return !v.sample;});
    if(tail==mTails.end())tail=mTails.begin();
    *tail=*it;tail->forcedRemaining=96;tail->released=false;
  }
  const int layer=VelocityLayer(velocity);
  const int selection=mControls.glide&&previousPitch>=0?std::max(note,previousPitch/65536):note;
  const Sample& sample=mPlaybackBank->Select(layer,selection);
  *it={};it->residency=mResidency;it->sample=&sample;it->note=note;it->channel=channel;it->keyDown=true;it->age=++mAge;
  it->step=mBank->rootRate/mRate*std::pow(2,(note-int(sample.root))/12.0);
  it->glide.Start(previousPitch,note,mControls.glide);it->glideRatio=it->glide.Ratio();
  // Native velocity/slot/AMS/keyboard response is the baseline. This optional
  // host trim changes loudness response, leaving the verified layer edges fixed.
  it->velocityTrim=std::pow(velocity/127.0,mControls.velocityCurve-1);
  for(int osc=0;osc<2;++osc){
    it->native[osc].SetOffsets(mControls.ampEg);
    it->filter[osc].SetOffsets(mControls.filterEg,mControls.cutoff,mControls.resonance);
    it->native[osc].Start(note,velocity,osc,layer==2?127:119);
    it->slew[osc].Reset(it->native[osc].InitialGain());
    it->slew[osc].SetTarget(it->native[osc].Gain());
    it->filter[osc].Start(it->native[osc],osc,velocity,mRate);
  }
}
void PianoEngine::Midi(const MidiEvent& event) noexcept {
  const int ch=event.status&15,type=event.status&240,note=event.data1,value=event.data2;
  if(mControls.voiceMode&&mMono.Handle(event,2,
      [this](int n,int v,int c,bool held){SelectMono(n,v,c,held);},
      [this](int c){for(auto& v:mVoices)if(v.sample&&v.channel==c&&v.keyDown){v.keyDown=false;if(!mSustain[c])Release(v);}}))return;
  if(type==0x90&&value){NoteOn(note,value,ch);return;}
  if(type==0x80||(type==0x90&&!value)){
    Voice* selected=nullptr;
    for(auto& v:mVoices)if(v.sample&&v.note==note&&v.channel==ch&&v.keyDown&&(!selected||v.age<selected->age))selected=&v;
    if(selected){selected->keyDown=false;if(!mSustain[ch])Release(*selected);}
  }else if(type==0xE0){mBend[ch]=std::pow(2,(((value*128+note)-8192)/8192.0)*2/12);}
  else if(type==0xB0){
    if(note==64){
      mSustain[ch]=value>=64;
      if(!mSustain[ch])for(auto& v:mVoices)if(v.sample&&v.channel==ch&&!v.keyDown&&!v.released)Release(v);
    }else if(note==7)mVolume[ch]=value/127.0;
    else if(note==11)mExpression[ch]=value/127.0;
    else if(note==67)mSoft[ch]=value>=64?0.75:1;
    else if(note==123){for(auto& v:mVoices)if(v.sample&&v.channel==ch){v.keyDown=false;if(!mSustain[ch])Release(v);}}
    else if(note==120){for(auto& v:mVoices)if(v.channel==ch)v={};for(auto& v:mTails)if(v.channel==ch)v={};}
    else if(note==121){mSustain[ch]=false;mBend[ch]=mVolume[ch]=mExpression[ch]=mSoft[ch]=1;
      for(auto& v:mVoices)if(v.sample&&v.channel==ch&&!v.keyDown)Release(v);}
  }
}
void PianoEngine::RenderVoice(Voice& voice,double& left,double& right) noexcept {
  if(!voice.sample)return;
  const Sample& sample=*voice.sample;
  const double end=double(sample.loopEnd)+1;
  const double cross=std::min(210.0,(end-sample.loopStart)/8);
  const double restart=sample.loopStart+cross;
  if(voice.position>=end)voice.position=restart+std::fmod(voice.position-end,end-restart);
  double l=Interpolate(sample,voice.position,0),r=Interpolate(sample,voice.position,1);
  if(voice.position>end-cross){
    const double blend=(voice.position-(end-cross))/cross;
    const double start=sample.loopStart+voice.position-(end-cross);
    l+=(Interpolate(sample,start,0)-l)*blend;r+=(Interpolate(sample,start,1)-r)*blend;
  }
  // Share the sample read, but filter each OSC before applying its native gain.
  // Retain the prototype's explicit mean-OSC/0.4 headroom convention. Absolute
  // TG transfer, mixing/pan and fixed-point arithmetic remain unverified.
  double filteredL=0,filteredR=0;
  for(int osc=0;osc<2;++osc){
    double oscL=l,oscR=r;
    if(mControls.filterEnabled)voice.filter[osc].Process(oscL,oscR);
    filteredL+=oscL*voice.slew[osc].Current()/65536.0;
    filteredR+=oscR*voice.slew[osc].Current()/65536.0;
  }
  double level=0.4*voice.velocityTrim*mVolume[voice.channel]*mExpression[voice.channel]*mSoft[voice.channel];
  if(voice.forcedRemaining){level*=voice.forcedRemaining/96.0;if(!--voice.forcedRemaining)voice.sample=nullptr;}
  left+=filteredL*level;right+=filteredR*level;
  voice.position+=voice.step*mBend[voice.channel]*voice.glideRatio;
  voice.glideRatio=voice.glide.Advance(mRate);
  // Continuous per-voice clocks make the result independent of host block
  // partitioning. TG slew advances on a nominal 48 kHz grid at every host rate.
  voice.nativeAudioPhase+=mNativeAudioIncrement;
  while(voice.nativeAudioPhase>=1){for(auto& slew:voice.slew)slew.Advance();voice.nativeAudioPhase-=1;}
  voice.controlPhase+=mControlIncrement;
  if(voice.controlPhase>=1){
    voice.controlPhase-=1;
    for(int osc=0;osc<2;++osc){voice.native[osc].SetOffsets(mControls.ampEg);voice.filter[osc].SetOffsets(mControls.filterEg,mControls.cutoff,mControls.resonance);voice.native[osc].Tick();voice.slew[osc].SetTarget(voice.native[osc].Gain());voice.filter[osc].Tick();}
  }
  if(voice.native[0].Finished()&&voice.native[1].Finished()&&voice.slew[0].Silent()&&voice.slew[1].Silent())voice.sample=nullptr;
}
void PianoEngine::Render(float* left,float* right,int frames) noexcept {
  for(int start=0;start<frames;start+=kChunk){
    const int count=std::min<int>(kChunk,frames-start);
    std::array<float,kChunk*2> dry{};
    std::array<std::array<float,kChunk*2>,3> audio;
    for(int n=0;n<count;++n){double l=0,r=0;for(auto& v:mVoices)RenderVoice(v,l,r);for(auto& v:mTails)RenderVoice(v,l,r);dry[n*2]=float(l);dry[n*2+1]=float(r);}
    std::array<double,kChunk*2> equalized;
    concert_effects_equalize(mEffects[0].get(),dry.data(),equalized.data(),count);
    for(int p=0;p<3;++p)concert_effects_process_equalized(mEffects[p].get(),equalized.data(),audio[p].data(),count);
    for(int n=0;n<count;++n){
      double l=0,r=0;mOutput+=mSmoothing*(mOutputTarget-mOutput);
      for(int p=0;p<3;++p){mWeights[p]+=mSmoothing*((p==mControls.preset?1:0)-mWeights[p]);l+=audio[p][n*2]*mWeights[p];r+=audio[p][n*2+1]*mWeights[p];}
      left[start+n]=float(l*mOutput);right[start+n]=float(r*mOutput);
    }
  }
}
void PianoEngine::Process(float* left,float* right,int frames) noexcept {
  if(frames<=0||!left||!right)return;
  if(mOverflow){Panic();}
  unsigned consumed=0;int position=0;
  while(consumed<mEventCount&&mEvents[consumed].offset<frames){
    const int target=mEvents[consumed].offset;
    if(target>position)Render(left+position,right+position,target-position);
    position=target;Midi(mEvents[consumed++]);
  }
  if(position<frames)Render(left+position,right+position,frames-position);
  for(unsigned i=consumed;i<mEventCount;++i){mEvents[i-consumed]=mEvents[i];mEvents[i-consumed].offset-=frames;}
  mEventCount-=consumed;
}
}
