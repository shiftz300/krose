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
#include <vector>
using namespace Steinberg;
using namespace Steinberg::Vst;

void verifyEditor(IPlugView*,const std::function<double()>&,const std::function<double()>&,const std::function<double()>&,const std::function<double()>&,const std::function<double(const char*)>&);

int main(int argc,char** argv){
  const bool editorOnly=argc==3 && std::string(argv[2])=="--editor-only";
  const bool openEditor=editorOnly||(argc==3 && std::string(argv[2])=="--editor");
  assert(argc==2 || openEditor);
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
  // Actual VST3 musical context gates the arpeggiator when the host stops.
  {
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
    events.clear();changes.clearQueue();context.state|=ProcessContext::kPlaying;
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
  auto* view=controller->createView(ViewType::kEditor);assert(view);
  if(openEditor) verifyEditor(view,[&]{return controller->getParamNormalized(ids["Velocity"]);},[&]{return controller->getParamNormalized(ids["Program"]);},[&]{return controller->getParamNormalized(ids["Voice Mode"]);},[&]{return controller->getParamNormalized(ids["Glide"]);},[&](const char* name){return controller->getParamNormalized(ids.at(name));});
  view->release();
  if(editorOnly)std::cout<<"PASS editor-only: state/transport/UI checks; full-bank render skipped\n";
  else std::cout<<"PASS compiled VST3: self-contained sample bank, MIDI offsets/audio, three rates/tones, parameter state round-trip, sustain mapping and editor creation\n";
}
