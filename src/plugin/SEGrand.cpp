#include "SEGrand.h"
#include "IPlug_include_in_plug_src.h"
#include "IPlugPaths.h"
#include "FactoryPrograms.h"
#include <algorithm>
#include <array>
#if IPLUG_EDITOR
#include "IControls.h"
#include "IWebViewControl.h"
#include "json.hpp"
#include <fstream>
#include <iterator>

namespace {
class KroseEditor final : public IWebViewControl {
public:
  using IWebViewControl::IWebViewControl;
  void OnWebContentLoaded() override {
    IWebViewControl::OnWebContentLoaded();
    EvaluateJavaScript("window.IPlugSendMsg({type:'ready'})");
  }
};
}
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
    g->AttachPanelBackground(IColor(255,16,18,22));
    g->AttachControl(new KroseEditor(g->GetBounds(),true,
      [this](IWebViewControl* web) {
        WDL_String path;
        BundleResourcePath(path,GetBundleID());
        path.Append("/editor.html");
        std::ifstream input(path.Get(),std::ios::binary);
        std::string html((std::istreambuf_iterator<char>(input)),{});
        web->LoadHTML(html.empty()?"<p>Krose editor resource unavailable</p>":html.c_str());
      },
      [this](IWebViewControl*,const char* json) { HandleEditorMessage(json); }), kEditorTag);
  };
#endif
}
#if IPLUG_EDITOR
void SEGrand::OnParamChangeUI(int id,EParamSource) {
  if(!GetUI() || id<0 || id>=kNumParams) return;
  auto* web=static_cast<IWebViewControl*>(GetUI()->GetControlWithTag(kEditorTag));
  if(!web) return;
  nlohmann::json args={GetParam(id)->GetName(),id,GetParam(id)->Value()};
  auto js="window.kroseNative?.receive(..."+args.dump()+")";
  web->EvaluateJavaScript(js.c_str());
}

void SEGrand::OnUIClose() {
  for(int n=0;n<128;++n) if(mEditorNotes[n]) SendMidiMsgFromUI(IMidiMsg(0,0x80,n,0));
  mEditorNotes.fill(false);
  if(mEditorSustain) SendMidiMsgFromUI(IMidiMsg(0,0xb0,64,0));
  if(mEditorBend) SendMidiMsgFromUI(IMidiMsg(0,0xe0,0,64));
  mEditorSustain=mEditorBend=false;
  Plugin::OnUIClose();
}

void SEGrand::HandleEditorMessage(const char* text) {
  const auto msg=nlohmann::json::parse(text,nullptr,false);
  if(!msg.is_object()) return;
  const auto type=msg.find("type");
  if(type==msg.end() || !type->is_string()) return;
  if(*type=="ready"){
    for(int id=0;id<kNumParams;++id) OnParamChangeUI(id);
    return;
  }
  auto integer=[&](const char* key,int limit){
    auto p=msg.find(key);
    return p!=msg.end() && p->is_number_integer() && *p>=0 && *p<=limit ? p->get<int>() : -1;
  };
  if(*type=="midi"){
    const int status=integer("status",239),a=integer("data1",127),b=integer("data2",127);
    if(status<128 || a<0 || b<0) return;
    if(status==0x90 || status==0x80) mEditorNotes[a]=status==0x90 && b>0;
    if(status==0xb0 && a==64) mEditorSustain=b>=64;
    if(status==0xe0) mEditorBend=a!=0 || b!=64;
    SendMidiMsgFromUI(IMidiMsg(0,status,a,b));
    return;
  }
  const int id=integer("id",kNumParams-1);
  if(id<0) return;
  if(*type=="begin") BeginInformHostOfParamChangeFromUI(id);
  if(*type=="end") EndInformHostOfParamChangeFromUI(id);
  if(*type=="set" && msg.contains("value") && msg["value"].is_number()){
    const double value=msg["value"];
    auto* param=GetParam(id);
    if(std::isfinite(value)) SendParameterValueFromUI(id,param->ToNormalized(std::clamp(value,param->GetMin(),param->GetMax())));
  }
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
