#include "InstrumentEngine.h"
#include <algorithm>
#include <cmath>
namespace segrand {
InstrumentEngine::InstrumentEngine(std::shared_ptr<const SampleBank> concert,std::shared_ptr<const ProgramLibrary> factory):mConcert(std::move(concert)),mFactory(factory),mProgramCount(unsigned(factory->programs.size())+1){}
void InstrumentEngine::Prepare(double rate){mArp.Prepare(rate);mConcert.Prepare(rate);mFactory.Prepare(rate);mPanSmooth=1-std::exp(-1/(rate*.01));mPan=mPanTarget;Panic();}
void InstrumentEngine::SetControls(const Controls& controls){
 mPanTarget=std::clamp(controls.pan,-64,63)/(controls.pan<0?64.0:63.0);
 const int program=std::clamp(controls.program,0,int(mProgramCount)-1);
 if(program!=mProgram){
  if(mArp.Controls().enabled){mArp.Reset();mConcert.Panic();mFactory.Panic();}
  if(!mProgram||!program){mFrom=mLast;mFade=96;mConcert.Panic();mFactory.Panic();}
  mProgram=program;if(program)mFactory.SetProgram(unsigned(program-1));
 }
 mConcert.SetControls(controls);mFactory.SetControls(controls);
}
void InstrumentEngine::Queue(MidiEvent event) noexcept{
 if(mEventCount==mEvents.size()){mOverflow=true;return;}
 event.offset=std::max(0,event.offset);unsigned index=mEventCount++;
 while(index&&mEvents[index-1].offset>event.offset){mEvents[index]=mEvents[index-1];--index;}mEvents[index]=event;
}
void InstrumentEngine::Panic() noexcept{mArp.Reset();mConcert.Panic();mFactory.Panic();mEventCount=0;mOverflow=false;mFade=0;mLast={};}
unsigned InstrumentEngine::ActiveVoices() const noexcept{return mProgram?mFactory.ActiveVoices():mConcert.ActiveVoices();}
void InstrumentEngine::Process(float* left,float* right,int frames) noexcept{
 if(frames<=0||!left||!right)return;
 // Bound generated MIDI per engine call even for very large offline blocks.
 if(frames>256){for(int at=0;at<frames;at+=256)Process(left+at,right+at,std::min(256,frames-at));return;}
 if(mOverflow)Panic();
 unsigned consumed=0;while(consumed<mEventCount&&mEvents[consumed].offset<frames)++consumed;
 mArp.Process(frames,mEvents.data(),consumed,this,[](void* context,MidiEvent event){
  auto& self=*static_cast<InstrumentEngine*>(context);
  if(self.mProgram)self.mFactory.Queue(event);else self.mConcert.Queue(event);
 });
 for(unsigned i=consumed;i<mEventCount;++i){mEvents[i-consumed]=mEvents[i];mEvents[i-consumed].offset-=frames;}mEventCount-=consumed;
 if(mProgram)mFactory.Process(left,right,frames);else mConcert.Process(left,right,frames);
 for(int i=0;i<frames;++i){if(mFade){const float t=1-float(mFade)/96;left[i]=left[i]*t+mFrom[0]*(1-t);right[i]=right[i]*t+mFrom[1]*(1-t);--mFade;}mLast={{left[i],right[i]}};
  mPan+=mPanSmooth*(mPanTarget-mPan);
  left[i]*=1-std::max(mPan,0.0);right[i]*=1+std::min(mPan,0.0);
 }
}
}
