#include "InstrumentEngine.h"
#include <algorithm>
namespace segrand {
InstrumentEngine::InstrumentEngine(std::shared_ptr<const SampleBank> concert,std::shared_ptr<const ProgramLibrary> factory):mConcert(std::move(concert)),mFactory(factory),mProgramCount(unsigned(factory->programs.size())+1){}
void InstrumentEngine::Prepare(double rate){mConcert.Prepare(rate);mFactory.Prepare(rate);Panic();}
void InstrumentEngine::SetControls(const Controls& controls){
 const int program=std::clamp(controls.program,0,int(mProgramCount)-1);
 if(program!=mProgram){
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
void InstrumentEngine::Panic() noexcept{mConcert.Panic();mFactory.Panic();mEventCount=0;mOverflow=false;mFade=0;mLast={};}
unsigned InstrumentEngine::ActiveVoices() const noexcept{return mProgram?mFactory.ActiveVoices():mConcert.ActiveVoices();}
void InstrumentEngine::Process(float* left,float* right,int frames) noexcept{
 if(frames<=0||!left||!right)return;if(mOverflow)Panic();
 unsigned consumed=0;while(consumed<mEventCount&&mEvents[consumed].offset<frames){if(mProgram)mFactory.Queue(mEvents[consumed]);else mConcert.Queue(mEvents[consumed]);++consumed;}
 for(unsigned i=consumed;i<mEventCount;++i){mEvents[i-consumed]=mEvents[i];mEvents[i-consumed].offset-=frames;}mEventCount-=consumed;
 if(mProgram)mFactory.Process(left,right,frames);else mConcert.Process(left,right,frames);
 for(int i=0;i<frames;++i){if(mFade){const float t=1-float(mFade)/96;left[i]=left[i]*t+mFrom[0]*(1-t);right[i]=right[i]*t+mFrom[1]*(1-t);--mFade;}mLast={{left[i],right[i]}};}
}
}
