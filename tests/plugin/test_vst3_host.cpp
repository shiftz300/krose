#include <limits>
// Headless integration test against the compiled VST3, using the SDK's host API.
#include "public.sdk/source/vst/hosting/hostclasses.h"
#include "public.sdk/source/vst/hosting/module.h"
#include "public.sdk/source/vst/hosting/plugprovider.h"
#include "public.sdk/source/vst/hosting/eventlist.h"
#include "public.sdk/source/vst/hosting/parameterchanges.h"
#include "public.sdk/source/common/memorystream.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "pluginterfaces/vst/ivstmidicontrollers.h"
#include "pluginterfaces/gui/iplugview.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <iostream>
#include <functional>
#include <map>
#include <chrono>
#include <thread>
#include <vector>
#include <cstring>
#include <filesystem>
#include <unistd.h>
#include "../../src/plugin/midi/ControllerMap.h"
using namespace Steinberg;
using namespace Steinberg::Vst;

void verifyEditor(IPlugView*,const std::function<double()>&,const std::function<double()>&,const std::function<double()>&,const std::function<double()>&,const std::function<double(const char*)>&,const std::function<void(const char*,double)>&);

class GestureHandler final : public IComponentHandler {
public:
  tresult PLUGIN_API queryInterface(const TUID iid, void** object) override {
    if(FUnknownPrivate::iidEqual(iid,IComponentHandler::iid)||FUnknownPrivate::iidEqual(iid,FUnknown::iid)) {
      *object=static_cast<IComponentHandler*>(this);addRef();return kResultOk;
    }
    *object=nullptr;return kNoInterface;
  }
  uint32 PLUGIN_API addRef() override { return ++references; }
  uint32 PLUGIN_API release() override { const auto n=--references;if(!n)delete this;return n; }
  tresult PLUGIN_API beginEdit(ParamID id) override { if(tracking){assert(depth[id]++==0);++begins;}return kResultOk; }
  tresult PLUGIN_API performEdit(ParamID id,ParamValue value) override {
    if(tracking){assert(depth[id]==1&&std::isfinite(value)&&value>=0&&value<=1);++edits;}return kResultOk;
  }
  tresult PLUGIN_API endEdit(ParamID id) override { if(tracking){assert(depth[id]--==1);++ends;}return kResultOk; }
  tresult PLUGIN_API restartComponent(int32) override { return kResultOk; }
  bool tracking=false;
  unsigned references=1,begins=0,edits=0,ends=0;
  std::map<ParamID,int> depth;
};

int main(int argc,char** argv){
  const bool editorOnly=argc==3 && std::string(argv[2])=="--editor-only";
  const bool openEditor=editorOnly||(argc==3 && std::string(argv[2])=="--editor");
  assert(argc==2 || openEditor);
  const std::string midiFile="/tmp/krose-midi-state-test-"+std::to_string(getpid())+".json";
  const bool ownMidi=!std::getenv("KROSE_MIDI_MAP_FILE");
  if(ownMidi)setenv("KROSE_MIDI_MAP_FILE",midiFile.c_str(),1);
  std::string error;
  auto module=VST3::Hosting::Module::create(argv[1],error);
  if(!module){std::cerr<<error<<'\n';return 1;}
  auto host=owned(new HostApplication);
  PluginContextFactory::instance().setPluginContext(host.get());
  auto classes=module->getFactory().classInfos();
  auto info=std::find_if(classes.begin(),classes.end(),[](const auto& x){return x.category()==kVstAudioEffectClass;});
  assert(info!=classes.end());
  PlugProvider provider(module->getFactory(),*info,true);assert(provider.initialize());
  auto component=provider.getComponentPtr();auto controller=provider.getControllerPtr();
  FUnknownPtr<IAudioProcessor> processor(component);assert(processor&&controller);
  auto gestures=owned(new GestureHandler);
  assert(controller->setComponentHandler(gestures.get())==kResultOk);
  std::map<std::string,ParamID> ids;
  for(int i=0;i<controller->getParameterCount();++i){ParameterInfo p{};assert(controller->getParameterInfo(i,p)==kResultOk);std::string name;for(auto c:p.title){if(!c)break;name+=char(c);}ids.emplace(name,p.id);}
  for(const char* name:{"Tone","Output","Space","Release","Velocity","Program"})assert(ids.count(name));
  assert(component->getBusCount(kAudio,kInput)==0&&component->getBusCount(kAudio,kOutput)==1);
  SpeakerArrangement stereo=SpeakerArr::kStereo;
  assert(processor->setBusArrangements(nullptr,0,&stereo,1)==kResultOk);
  component->activateBus(kAudio,kOutput,0,true);component->activateBus(kEvent,kInput,0,true);
  std::vector<double> signatures;
  for(double rate:{44100.,48000.,96000.})if(!editorOnly){
    for(int tone=0;tone<3;++tone){
      ProcessSetup setup{};setup.processMode=kOffline;setup.symbolicSampleSize=kSample32;setup.maxSamplesPerBlock=512;setup.sampleRate=rate;
      assert(processor->setupProcessing(setup)==kResultOk);
      assert(component->setActive(true)==kResultOk);processor->setProcessing(true);
      std::vector<float> left(512),right(512);float* channels[2]={left.data(),right.data()};
      AudioBusBuffers output{};output.numChannels=2;output.channelBuffers32=channels;
      EventList events;ParameterChanges changes;
      ProcessData data{};data.processMode=kOffline;data.symbolicSampleSize=kSample32;data.numOutputs=1;data.outputs=&output;data.inputEvents=&events;data.inputParameterChanges=&changes;
      int index=0,point=0;changes.addParameterData(ids["Tone"],index)->addPoint(0,tone/2.,point);
      changes.addParameterData(ids["Space"],index)->addPoint(0,0.5,point);
      Event on{};on.type=Event::kNoteOnEvent;on.busIndex=0;on.sampleOffset=37;on.noteOn.channel=0;on.noteOn.pitch=62;on.noteOn.velocity=0.9f;on.noteOn.noteId=17;events.addEvent(on);
      double energy=0,peak=0;int rendered=0;
      while(rendered<int(rate*2)){
        data.numSamples=std::min(512,int(rate*2)-rendered);
        assert(processor->process(data)==kResultOk);
        if(rendered==0)for(int n=0;n<37;++n)assert(left[n]==0&&right[n]==0);
        for(int n=0;n<data.numSamples;++n){assert(std::isfinite(left[n])&&std::isfinite(right[n]));energy+=left[n]*left[n]+right[n]*right[n];peak=std::max({peak,std::abs(double(left[n])),std::abs(double(right[n]))});}
        rendered+=data.numSamples;events.clear();changes.clearQueue();
        if(rendered>=int(rate/2)&&rendered-512<int(rate/2)){Event off{};off.type=Event::kNoteOffEvent;off.busIndex=0;off.sampleOffset=0;off.noteOff.channel=0;off.noteOff.pitch=62;off.noteOff.noteId=17;events.addEvent(off);}
      }
      assert(energy>0.1&&peak<1);
      // Processor automation and the controller's parameter cache are separate.
      // Reload the processor's serialized state to verify what the DSP received,
      // rather than incorrectly expecting process() to update the UI cache.
      MemoryStream automatedState;
      assert(component->getState(&automatedState)==kResultOk);
      automatedState.seek(0,IBStream::kIBSeekSet,nullptr);
      assert(component->setState(&automatedState)==kResultOk);
      assert(std::abs(controller->getParamNormalized(ids["Tone"])-tone/2.)<1e-6);
      signatures.push_back(energy);
      processor->setProcessing(false);component->setActive(false);
      std::cout<<"VST3 rendered "<<rate<<" Hz tone "<<tone<<", energy "<<energy<<", peak "<<peak<<'\n';
    }
  }
  if(!editorOnly)assert(std::abs(signatures[0]-signatures[1])>0.001&&std::abs(signatures[1]-signatures[2])>0.001);
  // Exercise every newly packaged factory Program through the compiled plugin.
  for(int program=1;!editorOnly&&program<=1161;++program){
    ProcessSetup setup{};setup.processMode=kOffline;setup.symbolicSampleSize=kSample32;setup.maxSamplesPerBlock=512;setup.sampleRate=48000;
    assert(processor->setupProcessing(setup)==kResultOk);assert(component->setActive(true)==kResultOk);processor->setProcessing(true);
    std::vector<float> l(512),r(512);float* channels[2]={l.data(),r.data()};AudioBusBuffers bus{};bus.numChannels=2;bus.channelBuffers32=channels;
    EventList events;ParameterChanges changes;int index=0,point=0;changes.addParameterData(ids["Program"],index)->addPoint(0,program/1161.,point);
    changes.addParameterData(ids["Space"],index)->addPoint(0,0,point);
    Event on{};on.type=Event::kNoteOnEvent;on.busIndex=0;on.sampleOffset=37;on.noteOn.channel=0;on.noteOn.velocity=110.f/127;for(int note:{36,48,60,72,84}){on.noteOn.pitch=note;events.addEvent(on);}
    ProcessData data{};data.processMode=kOffline;data.symbolicSampleSize=kSample32;data.numOutputs=1;data.outputs=&bus;data.inputEvents=&events;data.inputParameterChanges=&changes;data.numSamples=512;
    double energy=0;for(int block=0;block<100;++block){assert(processor->process(data)==kResultOk);for(int i=0;i<512;++i){assert(std::isfinite(l[i])&&std::isfinite(r[i]));energy+=l[i]*l[i]+r[i]*r[i];}events.clear();changes.clearQueue();}
    if(energy<=1e-9){std::cerr<<"Silent VST3 Program "<<program<<" energy "<<energy<<std::endl;std::abort();}MemoryStream state;assert(component->getState(&state)==kResultOk);state.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&state)==kResultOk);assert(std::abs(controller->getParamNormalized(ids["Program"])-program/1161.)<1e-6);
    processor->setProcessing(false);component->setActive(false);if(program%128==0||program==1161)std::cout<<"Verified VST3 Program "<<program<<'\n';
  }
  // The same parameter queue can hold several timed changes in one block.
  if (!editorOnly) {
    ProcessSetup setup{kOffline, kSample32, 512, 48000};
    assert(processor->setupProcessing(setup) == kResultOk);
    assert(component->setActive(true) == kResultOk);
    processor->setProcessing(true);
    float left[512]{}, right[512]{};
    float* channels[]{left, right};
    AudioBusBuffers bus{};
    bus.numChannels = 2;
    bus.channelBuffers32 = channels;
    EventList events;
    ParameterChanges changes;
    int index = 0, point = 0;
    changes.addParameterData(ids.at("Program"), index)->addPoint(0, 0., point);
    auto* filter = changes.addParameterData(ids.at("MIDI Input Channel"), index);
    filter->addPoint(256, 2. / 16, point);
    filter->addPoint(384, 0., point);
    for (int offset : {17, 272, 399}) {
      Event note{};
      note.type = Event::kNoteOnEvent;
      note.sampleOffset = offset;
      note.noteOn.channel = 0;
      note.noteOn.pitch = 60;
      note.noteOn.velocity = 1.;
      events.addEvent(note);
    }
    ProcessData data{};
    data.processMode = kOffline;
    data.symbolicSampleSize = kSample32;
    data.numSamples = 512;
    data.numOutputs = 1;
    data.outputs = &bus;
    data.inputEvents = &events;
    data.inputParameterChanges = &changes;
    assert(processor->process(data) == kResultOk);
    auto audible = [&](int first, int end) {
      return std::any_of(left + first, left + end, [](float x) { return x != 0; });
    };
    assert(!audible(0, 17) && audible(17, 256));
    assert(!audible(256, 399) && audible(399, 512));
    processor->setProcessing(false);
    component->setActive(false);
  }
  // Actual VST3 musical context gates the arpeggiator when the host stops.
  {
    FUnknownPtr<IProcessContextRequirements> requirements(component);
    assert(requirements);
    const auto needed = IProcessContextRequirements::kNeedProjectTimeMusic |
                        IProcessContextRequirements::kNeedTempo |
                        IProcessContextRequirements::kNeedTransportState;
    assert((requirements->getProcessContextRequirements() & needed) == needed);
    ProcessSetup setup{};setup.processMode=kOffline;setup.symbolicSampleSize=kSample32;setup.maxSamplesPerBlock=512;setup.sampleRate=48000;
    assert(processor->setupProcessing(setup)==kResultOk);assert(component->setActive(true)==kResultOk);processor->setProcessing(true);
    std::vector<float> left(512),right(512);float* channels[2]={left.data(),right.data()};AudioBusBuffers bus{};bus.numChannels=2;bus.channelBuffers32=channels;
    EventList events;ParameterChanges changes;int index=0,point=0;
    for(auto pair:{std::pair<const char*,double>{"Program",0.},{"Space",0.},{"Arp",1.},{"Arp Host Sync",1.}})
      changes.addParameterData(ids.at(pair.first),index)->addPoint(0,pair.second,point);
    Event on{};on.type=Event::kNoteOnEvent;on.noteOn.channel=0;on.noteOn.pitch=60;on.noteOn.velocity=.9;events.addEvent(on);
    ProcessContext context{};context.sampleRate=48000;context.tempo=150;context.state=ProcessContext::kProjectTimeMusicValid|ProcessContext::kTempoValid;
    ProcessData data{};data.processMode=kOffline;data.symbolicSampleSize=kSample32;data.numOutputs=1;data.outputs=&bus;data.inputEvents=&events;data.inputParameterChanges=&changes;data.processContext=&context;data.numSamples=512;
    assert(processor->process(data)==kResultOk);
    for(int i=0;i<512;++i)assert(left[i]==0&&right[i]==0);
    events.clear();changes.clearQueue();
    for (bool omitContext : {true, false}) {
      data.processContext = omitContext ? nullptr : &context;
      if (!omitContext)
        context.state &= ~ProcessContext::kTempoValid;
      assert(processor->process(data) == kResultOk);
      assert(std::any_of(left.begin(), left.end(), [](float x) { return x != 0; }));
    }
    data.processContext = &context;
    context.state |= ProcessContext::kPlaying | ProcessContext::kTempoValid;
    double energy=0;
    for(int block=0;block<16;++block){
      context.projectTimeSamples=block*512;context.projectTimeMusic=context.projectTimeSamples*150./(60*48000);
      assert(processor->process(data)==kResultOk);
      for(int i=0;i<512;++i)energy+=left[i]*left[i]+right[i]*right[i];
    }
    assert(energy>.01);
    processor->setProcessing(false);component->setActive(false);
    std::cout<<"Verified VST3 ARP host stop/start at 150 BPM\n";
  }
  controller->setParamNormalized(ids["Tone"],0.5);controller->setParamNormalized(ids["Release"],0.7);
  MemoryStream saved;assert(component->getState(&saved)==kResultOk&&saved.getSize()>0);
  controller->setParamNormalized(ids["Tone"],1);controller->setParamNormalized(ids["Release"],0);
  saved.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&saved)==kResultOk);
  assert(std::abs(controller->getParamNormalized(ids["Tone"])-0.5)<1e-6);
  assert(std::abs(controller->getParamNormalized(ids["Release"])-0.7)<1e-6);
  // State emitted by the six-parameter release ends immediately before bypass.
  MemoryStream legacy;
  double legacyValues[]={2.,-9.,45.,410.,1.25,3.};
  int32 bypass=0;
  assert(legacy.write(legacyValues,sizeof(legacyValues),nullptr)==kResultOk);
  assert(legacy.write(&bypass,sizeof(bypass),nullptr)==kResultOk);
  legacy.seek(0,IBStream::kIBSeekSet,nullptr);
  controller->setParamNormalized(ids.at("Pan"),1.);
  assert(component->setState(&legacy)==kResultOk);
  assert(std::abs(controller->getParamNormalized(ids.at("Program"))-3./1161.)<1e-8);
  assert(std::abs(controller->getParamNormalized(ids.at("Pan"))-64./127.)<1e-8);
  // Upgrade the immediately previous 17-parameter release as well as the
  // original six-parameter state. Appended controls must use their defaults.
  assert(ids.at("Voice Mode")==17&&ids.at("Glide")==18);
  MemoryStream previous;
  double previousValues[]={2.,-9.,45.,410.,1.25,3.,-17.,12.,4.,1.,2.,3.,4.,5.,6.,7.,8.};
  assert(previous.write(previousValues,sizeof(previousValues),nullptr)==kResultOk);
  assert(previous.write(&bypass,sizeof(bypass),nullptr)==kResultOk);
  controller->setParamNormalized(ids.at("Voice Mode"),1.);
  controller->setParamNormalized(ids.at("Glide"),.75);
  previous.seek(0,IBStream::kIBSeekSet,nullptr);
  assert(component->setState(&previous)==kResultOk);
  assert(controller->getParamNormalized(ids.at("Voice Mode"))==0.);
  assert(controller->getParamNormalized(ids.at("Glide"))==0.);
  assert(std::abs(controller->getParamNormalized(ids.at("Filter Release"))-107./198.)<1e-8);
  controller->setParamNormalized(ids.at("Voice Mode"),1.);
  controller->setParamNormalized(ids.at("Glide"),64./127.);
  MemoryStream performanceState;
  assert(component->getState(&performanceState)==kResultOk);
  controller->setParamNormalized(ids.at("Voice Mode"),0.);
  controller->setParamNormalized(ids.at("Glide"),0.);
  performanceState.seek(0,IBStream::kIBSeekSet,nullptr);
  assert(component->setState(&performanceState)==kResultOk);
  assert(controller->getParamNormalized(ids.at("Voice Mode"))==1.);
  assert(std::abs(controller->getParamNormalized(ids.at("Glide"))-64./127.)<1e-8);
  FUnknownPtr<IMidiMapping> mapping(controller);assert(mapping);ParamID sustain=0;
  assert(mapping->getMidiControllerAssignment(0,0,kCtrlSustainOnOff,sustain)==kResultOk);
  MemoryStream nineteen;
  double values19[]={2.,-9.,45.,410.,1.25,3.,-17.,12.,4.,1.,2.,3.,4.,5.,6.,7.,8.,2.,64.};
  assert(nineteen.write(values19,sizeof(values19),nullptr)==kResultOk);
  assert(nineteen.write(&bypass,sizeof(bypass),nullptr)==kResultOk);
  controller->setParamNormalized(ids.at("Arp"),1.);
  nineteen.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&nineteen)==kResultOk);
  assert(controller->getParamNormalized(ids.at("Arp"))==0.);
  assert(controller->getParamNormalized(ids.at("Glide"))==64./127.);
  assert(ids.at("Arp")==19&&ids.at("Arp Key Sync")==28);
  controller->setParamNormalized(ids.at("Arp Pattern"),.75);
  controller->setParamNormalized(ids.at("Arp Tempo"),123.25/280.);
  MemoryStream arpState;assert(component->getState(&arpState)==kResultOk);
  controller->setParamNormalized(ids.at("Arp Pattern"),0.);controller->setParamNormalized(ids.at("Arp Tempo"),0.);
  arpState.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&arpState)==kResultOk);
  assert(controller->getParamNormalized(ids.at("Arp Pattern"))==.75);
  assert(std::abs(controller->getParamNormalized(ids.at("Arp Tempo"))-123.25/280.)<1e-8);
  // The project state owns the complete controller map, independently of user profiles.
  assert(ids.at("SW1 Assign")==29 && ids.at("FX Bypass")==38);
  {
    using namespace krose::midi;
    constexpr int fxType = 39, fxAmount = 43, oldParams = 39, previewParams = 47;
    assert(ids.at("IFX 1 Type") == fxType && ids.at("IFX 1 Amount") == fxAmount);
    controller->setParamNormalized(fxType, 5. / 6);
    controller->setParamNormalized(fxAmount, .7);
    const auto drive = ids.at("IFX 1 Drive"), on = ids.at("IFX 1 On");
    controller->setParamNormalized(drive, 1.);
    controller->setParamNormalized(on, 0.);
    MemoryStream fxState;
    assert(component->getState(&fxState) == kResultOk);
    const int params = (fxState.getSize() - 16 - 64*8 - 4) / 8;
    assert(params > previewParams && drive >= previewParams && on == previewParams);
    controller->setParamNormalized(fxType, 0.);
    controller->setParamNormalized(fxAmount, 0.);
    fxState.seek(0, IBStream::kIBSeekSet, nullptr);
    assert(component->setState(&fxState) == kResultOk);
    assert(std::abs(controller->getParamNormalized(fxType) - 5. / 6) < 1e-8);
    assert(controller->getParamNormalized(fxAmount) == .7);
    assert(controller->getParamNormalized(drive) == 1.);
    assert(controller->getParamNormalized(on) == 0.);
    MemoryStream preview;
    preview.write(fxState.getData(), previewParams*8, nullptr);
    preview.write(fxState.getData()+params*8, fxState.getSize()-params*8, nullptr);
    preview.seek(0, IBStream::kIBSeekSet, nullptr);
    assert(component->setState(&preview) == kResultOk);
    assert(controller->getParamNormalized(on) == 1.);
    assert(controller->getParamNormalized(drive) < 1.);
    assert(controller->getParamNormalized(fxAmount) == .7);
    MemoryStream legacy;
    legacy.write(fxState.getData(), oldParams*8, nullptr);
    legacy.write(fxState.getData()+params*8, fxState.getSize()-params*8, nullptr);
    legacy.seek(0, IBStream::kIBSeekSet, nullptr);
    assert(component->setState(&legacy) == kResultOk);
    assert(controller->getParamNormalized(fxType) == 0.);
    assert(controller->getParamNormalized(fxAmount) == .5);
    MemoryStream original;assert(component->getState(&original)==kResultOk);
    auto at=[&](int slot){return params*8+16+slot*8;};
    Binding b;b.source=Source::CC;b.channel=2;b.number=20;b.target=ids.at("Output");b.pickup=false;
    uint64_t word=b.Encode();std::memcpy(original.getData()+at(0),&word,8);
    // Leave no default CC10 map to affect this isolated test.
    original.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&original)==kResultOk);
    ProcessSetup setup{};setup.processMode=kOffline;setup.symbolicSampleSize=kSample32;setup.maxSamplesPerBlock=512;setup.sampleRate=48000;
    assert(processor->setupProcessing(setup)==kResultOk);assert(component->setActive(true)==kResultOk);processor->setProcessing(true);
    float l[512]{},r[512]{};float* channels[]={l,r};AudioBusBuffers bus{};bus.numChannels=2;bus.channelBuffers32=channels;
    ParameterChanges changes;int index=0,point=0;ParamID cc=0;
    assert(mapping->getMidiControllerAssignment(0,1,20,cc)==kResultOk);
    changes.addParameterData(cc,index)->addPoint(37,1.,point);
    ProcessData data{};data.processMode=kOffline;data.symbolicSampleSize=kSample32;data.numOutputs=1;data.outputs=&bus;data.inputParameterChanges=&changes;data.numSamples=512;
    assert(processor->process(data)==kResultOk);
    MemoryStream mapped;assert(component->getState(&mapped)==kResultOk);double output=0;std::memcpy(&output,mapped.getData()+8,8);assert(output==6.);
    uint64_t restored=0;std::memcpy(&restored,mapped.getData()+at(0),8);assert(restored==word);
    // A wrong channel cannot change this binding.
    changes.clearQueue();assert(mapping->getMidiControllerAssignment(0,15,20,cc)==kResultOk);
    changes.addParameterData(cc,index)->addPoint(0,0.,point);assert(processor->process(data)==kResultOk);
    MemoryStream wrong;assert(component->getState(&wrong)==kResultOk);std::memcpy(&output,wrong.getData()+8,8);assert(output==6.);
    processor->setProcessing(false);component->setActive(false);
    // A learned gain controller keeps its sample offset inside an audio block.
    auto phrase=[&](bool move){
      original.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&original)==kResultOk);
      assert(processor->setupProcessing(setup)==kResultOk);assert(component->setActive(true)==kResultOk);processor->setProcessing(true);
      // Commit restored controls, then reset voices/smoothers to the same start.
      changes.clearQueue();data.inputEvents=nullptr;assert(processor->process(data)==kResultOk);processor->setProcessing(false);processor->setProcessing(true);
      EventList notes;Steinberg::Vst::Event on{};on.type=Steinberg::Vst::Event::kNoteOnEvent;on.noteOn.channel=0;on.noteOn.pitch=60;on.noteOn.velocity=.9;notes.addEvent(on);
      changes.clearQueue();if(move){assert(mapping->getMidiControllerAssignment(0,1,20,cc)==kResultOk);changes.addParameterData(cc,index)->addPoint(37,0.,point);}
      data.inputEvents=&notes;assert(processor->process(data)==kResultOk);
      std::vector<float> result(l,l+512);processor->setProcessing(false);component->setActive(false);data.inputEvents=nullptr;return result;
    };
    const auto steady=phrase(false),moved=phrase(true);
    assert(std::equal(steady.begin(),steady.begin()+37,moved.begin()));
    double delta=0;for(int i=37;i<512;++i)delta+=std::abs(steady[i]-moved[i]);assert(delta>1e-5);
    // Multiple relative steps in one VST3 CC queue must all arrive.
    MemoryStream relative;relative.write(original.getData(),original.getSize(),nullptr);
    b.target=ids.at("Pan");b.mode=Mode::Relative1;uint64_t relativeWord=b.Encode();std::memcpy(relative.getData()+at(0),&relativeWord,8);
    relative.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&relative)==kResultOk);
    assert(processor->setupProcessing(setup)==kResultOk);assert(component->setActive(true)==kResultOk);processor->setProcessing(true);
    changes.clearQueue();assert(mapping->getMidiControllerAssignment(0,1,20,cc)==kResultOk);
    auto* queue=changes.addParameterData(cc,index);for(int sample:{0,17,37})queue->addPoint(sample,1./127.,point);
    assert(processor->process(data)==kResultOk);MemoryStream stepped;assert(component->getState(&stepped)==kResultOk);
    double beforePan=0,afterPan=0;std::memcpy(&beforePan,original.getData()+6*8,8);std::memcpy(&afterPan,stepped.getData()+6*8,8);assert(afterPan==beforePan+3);
    processor->setProcessing(false);component->setActive(false);
    original.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&original)==kResultOk);
    // A newly appended FX target (>64) survives mapping state and CC dispatch.
    MemoryStream extended;extended.write(original.getData(),original.getSize(),nullptr);
    const auto fxDecay=ids.at("MFX 2 Decay");assert(fxDecay>64);
    auto fxBinding=b;fxBinding.mode=Mode::Absolute;fxBinding.target=fxDecay+3;
    uint64_t fxWord=fxBinding.Encode();std::memcpy(extended.getData()+at(0),&fxWord,8);
    extended.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&extended)==kResultOk);
    assert(processor->setupProcessing(setup)==kResultOk);assert(component->setActive(true)==kResultOk);processor->setProcessing(true);
    changes.clearQueue();assert(mapping->getMidiControllerAssignment(0,1,20,cc)==kResultOk);
    changes.addParameterData(cc,index)->addPoint(37,1.,point);assert(processor->process(data)==kResultOk);
    MemoryStream fxMapped;assert(component->getState(&fxMapped)==kResultOk);
    double decay=0;std::memcpy(&decay,fxMapped.getData()+fxDecay*8,8);assert(decay==6.);
    // Invalid floating-point MIDI/automation values must not reach SDK casts.
    for(double invalid : {std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity()}) {
      changes.clearQueue();changes.addParameterData(cc,index)->addPoint(0,invalid,point);
      changes.addParameterData(fxDecay,index)->addPoint(0,invalid,point);
      EventList malformedNotes;Steinberg::Vst::Event malformed{};
      malformed.type=Steinberg::Vst::Event::kNoteOnEvent;malformed.noteOn.pitch=60;malformed.noteOn.velocity=float(invalid);
      malformedNotes.addEvent(malformed);data.inputEvents=&malformedNotes;
      assert(processor->process(data)==kResultOk);data.inputEvents=nullptr;
      MemoryStream valid;assert(component->getState(&valid)==kResultOk);
      std::memcpy(&decay,valid.getData()+fxDecay*8,8);assert(decay==6.);
      for(int i=0;i<512;++i)assert(std::isfinite(l[i])&&std::isfinite(r[i]));
    }
    processor->setProcessing(false);component->setActive(false);
    original.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&original)==kResultOk);
    const auto validOutput=controller->getParamNormalized(ids.at("Output"));
    assert(controller->setParamNormalized(ids.at("Output"),std::numeric_limits<double>::quiet_NaN())!=kResultOk);
    assert(controller->getParamNormalized(ids.at("Output"))==validOutput);
    // Reject corrupt mapping metadata without partially restoring parameters.
    mapped.getData()[params*8]=0;mapped.seek(0,IBStream::kIBSeekSet,nullptr);component->setState(&mapped);
    MemoryStream afterCorrupt;assert(component->getState(&afterCorrupt)==kResultOk);
    std::memcpy(&restored,afterCorrupt.getData()+at(0),8);assert(restored==word);
    // Reject nonfinite/out-of-range state before mutating any valid prefix.
    MemoryStream intact; assert(component->getState(&intact)==kResultOk);
    for(double invalid : {std::numeric_limits<double>::quiet_NaN(),
                           std::numeric_limits<double>::infinity(), -1e100, 1e100}) {
      MemoryStream broken; broken.write(intact.getData(),intact.getSize(),nullptr);
      double prefix=1.; std::memcpy(broken.getData(),&prefix,8);
      std::memcpy(broken.getData()+(params-1)*8,&invalid,8);
      broken.seek(0,IBStream::kIBSeekSet,nullptr); component->setState(&broken);
      MemoryStream unchanged; assert(component->getState(&unchanged)==kResultOk);
      assert(unchanged.getSize()==intact.getSize());
      assert(std::memcmp(unchanged.getData(),intact.getData(),intact.getSize())==0);
    }
    // Restore an ordinary map and retain input configuration across legacy presets.
    b.source=Source::Off;word=b.Encode();std::memcpy(original.getData()+at(0),&word,8);
    double channel=3;std::memcpy(original.getData()+35*8,&channel,8);
    original.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&original)==kResultOk);
    MemoryStream old29;assert(old29.write(original.getData(),29*8,nullptr)==kResultOk);assert(old29.write(&bypass,4,nullptr)==kResultOk);
    old29.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&old29)==kResultOk);
    assert(controller->getParamNormalized(ids.at("MIDI Input Channel"))==3./16.);
    controller->setParamNormalized(ids.at("MIDI Input Channel"),0.);
    controller->setParamNormalized(ids.at("Output"),54./66.);
    std::cout<<"Verified FX and MIDI state, legacy preservation, channel-2 and channel-16 CC input, corrupt-state rejection\n";
  }
  controller->setParamNormalized(ids.at("SW1 Mode"),1.);controller->setParamNormalized(ids.at("SW1"),1.);
  MemoryStream heldSwitch;assert(component->getState(&heldSwitch)==kResultOk);double savedSwitch=1;std::memcpy(&savedSwitch,heldSwitch.getData()+31*8,8);assert(savedSwitch==0.);
  controller->setParamNormalized(ids.at("SW1 Mode"),0.);controller->setParamNormalized(ids.at("SW1"),0.);
  if(std::getenv("KROSE_UI_REFERENCE")){
    for(int i=0;i<controller->getParameterCount();++i){ParameterInfo p{};controller->getParameterInfo(i,p);controller->setParamNormalized(p.id,p.defaultNormalizedValue);}
    controller->setParamNormalized(ids.at("Program"),1./1161.);
    controller->setParamNormalized(ids.at("Arp Host Sync"),0.);
  }
  if(const char* selected=std::getenv("KROSE_UI_BENCH_PROGRAM")){
    const int program=std::atoi(selected);assert(program>=0&&program<=1161);
    ProcessSetup setup{};setup.processMode=kRealtime;setup.symbolicSampleSize=kSample32;setup.maxSamplesPerBlock=128;setup.sampleRate=48000;
    assert(processor->setupProcessing(setup)==kResultOk);assert(component->setActive(true)==kResultOk);processor->setProcessing(true);
    ParameterChanges changes;int index=0,point=0;
    for(int i=0;i<controller->getParameterCount();++i){ParameterInfo p{};controller->getParameterInfo(i,p);
      if(p.id>=29)continue;
      const auto value=p.id==ids.at("Program")?program/1161.:p.defaultNormalizedValue;
      controller->setParamNormalized(p.id,value);changes.addParameterData(p.id,index)->addPoint(0,value,point);
    }
    float l[128]{},r[128]{};float* channels[]={l,r};AudioBusBuffers bus{};bus.numChannels=2;bus.channelBuffers32=channels;
    ProcessData data{};data.processMode=kRealtime;data.symbolicSampleSize=kSample32;data.numOutputs=1;data.outputs=&bus;data.inputParameterChanges=&changes;data.numSamples=128;
    for(int n=0;n<256;++n){assert(processor->process(data)==kResultOk);changes.clearQueue();std::this_thread::sleep_for(std::chrono::milliseconds(3));}
    processor->setProcessing(false);component->setActive(false);
    std::cout<<"MEMORY selected Program "<<program<<std::endl;
  }
  auto* view=controller->createView(ViewType::kEditor);assert(view);
  if(openEditor) {
    gestures->tracking=true;
    verifyEditor(view,[&]{return controller->getParamNormalized(ids["Velocity"]);},[&]{return controller->getParamNormalized(ids["Program"]);},[&]{return controller->getParamNormalized(ids["Voice Mode"]);},[&]{return controller->getParamNormalized(ids["Glide"]);},[&](const char* name){return controller->getParamNormalized(ids.at(name));},[&](const char* name,double value){assert(controller->setParamNormalized(ids.at(name),value)==kResultOk);});
    gestures->tracking=false;
    for(const auto& entry:gestures->depth)assert(entry.second==0);
    if(!std::getenv("KROSE_UI_REFERENCE")&&!std::getenv("KROSE_UI_BENCH"))
      assert(gestures->begins>0&&gestures->edits>0&&gestures->begins==gestures->ends);
    std::cout<<"PASS host UI gestures: "<<gestures->begins<<" balanced edits, "<<gestures->edits<<" values\n";
  }
  view->release();
  if(ownMidi){std::filesystem::remove(midiFile);unsetenv("KROSE_MIDI_MAP_FILE");}
  if(editorOnly)std::cout<<"PASS editor-only: state/transport/UI checks; full-bank render skipped\n";
  else std::cout<<"PASS compiled VST3: self-contained sample bank, MIDI offsets/audio, three rates/tones, parameter state round-trip, sustain mapping and editor creation\n";
}
