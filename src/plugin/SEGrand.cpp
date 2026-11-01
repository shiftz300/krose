#include "SEGrand.h"
#include "IPlug_include_in_plug_src.h"
#include "IPlugPaths.h"
#include "FactoryPrograms.h"
#include <algorithm>
#include <array>
#if IPLUG_EDITOR
#include "IControls.h"
#include "IVKeyboardControl.h"
#endif

SEGrand::SEGrand(const InstanceInfo& info):Plugin(info,MakeConfig(kNumParams,segrand::kInstrumentProgramCount+2)) {
  GetParam(kParamTone)->InitEnum("Tone",0,3,"",IParam::kFlagsNone,"","Concert","Warm","Wide");
  GetParam(kParamOutput)->InitDouble("Output",-6,-60,6,0.1,"dB");
  GetParam(kParamSpace)->InitDouble("Space",100,0,200,1,"%");
  GetParam(kParamRelease)->InitDouble("Release",288,30,2000,1,"ms");
  GetParam(kParamVelocity)->InitDouble("Velocity",1.,0.5,3,0.01,"");
  GetParam(kParamProgram)->InitEnum("Program",0,segrand::kInstrumentProgramCount);
  for(int i=0;i<segrand::kInstrumentProgramCount;++i)GetParam(kParamProgram)->SetDisplayText(i,segrand::kInstrumentProgramNames[i]);
  MakePreset("Concert",0.,-6.,100.,288.,1.,0.);
  MakePreset("Warm",1.,-6.,100.,288.,1.,0.);
  MakePreset("Wide",2.,-6.,100.,288.,1.,0.);
  for(int i=1;i<segrand::kInstrumentProgramCount;++i)MakePreset(segrand::kInstrumentProgramNames[i],0.,-6.,20.,288.,1.,double(i));
  try {
    WDL_String path;BundleResourcePath(path,GetBundleID());path.Append("/SEGrand.samples");
    auto concert=segrand::SampleBank::Load(path.Get());
    BundleResourcePath(path,GetBundleID());path.Append("/Factory.samples");
    mEngine=std::make_unique<segrand::InstrumentEngine>(std::move(concert),segrand::ProgramLibrary::Load(path.Get()));
  } catch(const std::exception& error) { mError=error.what(); }
#if IPLUG_EDITOR
  mMakeGraphicsFunc=[this](){return MakeGraphics(*this,PLUG_WIDTH,PLUG_HEIGHT,PLUG_FPS,GetScaleForScreen(PLUG_WIDTH,PLUG_HEIGHT));};
  mLayoutFunc=[this](IGraphics* g){
    g->LoadFont("Roboto-Regular",ROBOTO_FN);
    g->EnableMouseOver(true);
    g->AttachPopupMenuControl();
    g->AttachTextEntryControl();
    g->AttachPanelBackground(IColor(255,244,241,233));
    IText title(32,IColor(255,35,50,45),"Roboto-Regular",EAlign::Near);
    IText caption(13,IColor(255,90,103,95),"Roboto-Regular",EAlign::Near);
    g->AttachControl(new ITextControl(IRECT(28,12,350,50),"Krose",title));
    g->AttachControl(new ITextControl(IRECT(30,45,630,62),mError.empty()?"":mError.c_str(),caption));
    const IVStyle style=DEFAULT_STYLE.WithColor(kFG,IColor(255,50,94,76))
      .WithColor(kPR,IColor(255,50,94,76)).WithColor(kFR,IColor(255,150,164,149))
      .WithColor(kBG,IColor(255,244,241,233)).WithDrawShadows(false);
    const IVStyle tabs=style.WithColor(kFG,IColor(255,234,232,222)).WithColor(kPR,IColor(255,173,198,177));
    g->AttachControl(new IVMenuButtonControl(IRECT(28,65,652,98),kParamProgram,"",style.WithShowLabel(false)));
    g->AttachControl(new IVTabSwitchControl(IRECT(28,100,652,140),kParamTone,{"Concert","Warm","Wide"},"",tabs));
    g->DisableControl(kParamTone,GetParam(kParamProgram)->Int()!=0);
    const char* names[4]={"Output","Space","Release","Velocity"};
    for(int i=0;i<4;++i)g->AttachControl(new IVKnobControl(IRECT(30+i*156,155,180+i*156,260),i+1,names[i],style));
    g->AttachControl(new IVKeyboardControl(IRECT(28,280,652,338),36,84));
  };
#endif
}
#if IPLUG_EDITOR
void SEGrand::OnParamChangeUI(int,EParamSource) {
  if(auto* ui=GetUI())ui->DisableControl(kParamTone,GetParam(kParamProgram)->Int()!=0);
}
#endif
#if IPLUG_DSP
void SEGrand::OnReset() {
  if(mEngine)try {mEngine->Prepare(GetSampleRate());mPrepared=true;}
  catch(const std::exception&){mPrepared=false;mEngine->Panic();}
}
void SEGrand::ProcessMidiMsg(const IMidiMsg& msg) {
  if(mEngine&&mPrepared)mEngine->Queue({msg.mOffset,msg.mStatus,msg.mData1,msg.mData2});
}
void SEGrand::ProcessBlock(sample**,sample** outputs,int nFrames) {
  const int channels=NOutChansConnected();
  if(!mEngine||!mPrepared){for(int ch=0;ch<channels;++ch)std::fill(outputs[ch],outputs[ch]+nFrames,sample(0));return;}
  segrand::Controls c;c.program=GetParam(kParamProgram)->Int();c.preset=GetParam(kParamTone)->Int();c.outputDb=GetParam(kParamOutput)->Value();
  c.space=GetParam(kParamSpace)->Value()/100;c.releaseSeconds=GetParam(kParamRelease)->Value()/1000;c.velocityCurve=GetParam(kParamVelocity)->Value();
  mEngine->SetControls(c);
  // Fixed stack buffers support arbitrary host block lengths without allocation.
  std::array<float,256> left,right;
  for(int start=0;start<nFrames;start+=256){
    const int count=std::min(256,nFrames-start);mEngine->Process(left.data(),right.data(),count);
    if(channels>0)for(int n=0;n<count;++n)outputs[0][start+n]=sample(left[n]);
    if(channels>1)for(int n=0;n<count;++n)outputs[1][start+n]=sample(right[n]);
    for(int ch=2;ch<channels;++ch)std::fill(outputs[ch]+start,outputs[ch]+start+count,sample(0));
  }
}
#endif
