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

void verifyEditor(IPlugView*,const std::function<double()>&);

int main(int argc,char** argv){
  const bool openEditor=argc==3 && std::string(argv[2])=="--editor";
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
  for(int i=0;i<controller->getParameterCount();++i){ParameterInfo p{};assert(controller->getParameterInfo(i,p)==kResultOk);std::string name;for(auto c:p.title){if(!c)break;name+=char(c);}ids[name]=p.id;}
  for(const char* name:{"Tone","Output","Space","Release","Velocity","Program"})assert(ids.count(name));
  assert(component->getBusCount(kAudio,kInput)==0&&component->getBusCount(kAudio,kOutput)==1);
  SpeakerArrangement stereo=SpeakerArr::kStereo;
  assert(processor->setBusArrangements(nullptr,0,&stereo,1)==kResultOk);
  component->activateBus(kAudio,kOutput,0,true);component->activateBus(kEvent,kInput,0,true);
  std::vector<double> signatures;
  for(double rate:{44100.,48000.,96000.}){
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
  assert(std::abs(signatures[0]-signatures[1])>0.001&&std::abs(signatures[1]-signatures[2])>0.001);
  // Exercise every newly packaged factory Program through the compiled plugin.
  for(int program=1;program<=6;++program){
    ProcessSetup setup{};setup.processMode=kOffline;setup.symbolicSampleSize=kSample32;setup.maxSamplesPerBlock=512;setup.sampleRate=48000;
    assert(processor->setupProcessing(setup)==kResultOk);assert(component->setActive(true)==kResultOk);processor->setProcessing(true);
    std::vector<float> l(512),r(512);float* channels[2]={l.data(),r.data()};AudioBusBuffers bus{};bus.numChannels=2;bus.channelBuffers32=channels;
    EventList events;ParameterChanges changes;int index=0,point=0;changes.addParameterData(ids["Program"],index)->addPoint(0,program/6.,point);
    changes.addParameterData(ids["Space"],index)->addPoint(0,0,point);
    Event on{};on.type=Event::kNoteOnEvent;on.busIndex=0;on.sampleOffset=37;on.noteOn.channel=program>=5?9:0;on.noteOn.pitch=program>=5?36:60;on.noteOn.velocity=.9f;events.addEvent(on);
    ProcessData data{};data.processMode=kOffline;data.symbolicSampleSize=kSample32;data.numOutputs=1;data.outputs=&bus;data.inputEvents=&events;data.inputParameterChanges=&changes;data.numSamples=512;
    double energy=0;for(int block=0;block<100;++block){assert(processor->process(data)==kResultOk);for(int i=0;i<512;++i){assert(std::isfinite(l[i])&&std::isfinite(r[i]));energy+=l[i]*l[i]+r[i]*r[i];}events.clear();changes.clearQueue();}
    assert(energy>1e-6);MemoryStream state;assert(component->getState(&state)==kResultOk);state.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&state)==kResultOk);assert(std::abs(controller->getParamNormalized(ids["Program"])-program/6.)<1e-6);
    processor->setProcessing(false);component->setActive(false);std::cout<<"Factory Program "<<program<<" energy "<<energy<<'\n';
  }
  controller->setParamNormalized(ids["Tone"],0.5);controller->setParamNormalized(ids["Release"],0.7);
  MemoryStream saved;assert(component->getState(&saved)==kResultOk&&saved.getSize()>0);
  controller->setParamNormalized(ids["Tone"],1);controller->setParamNormalized(ids["Release"],0);
  saved.seek(0,IBStream::kIBSeekSet,nullptr);assert(component->setState(&saved)==kResultOk);
  assert(std::abs(controller->getParamNormalized(ids["Tone"])-0.5)<1e-6);
  assert(std::abs(controller->getParamNormalized(ids["Release"])-0.7)<1e-6);
  FUnknownPtr<IMidiMapping> mapping(controller);assert(mapping);ParamID sustain=0;
  assert(mapping->getMidiControllerAssignment(0,0,kCtrlSustainOnOff,sustain)==kResultOk);
  auto* view=controller->createView(ViewType::kEditor);assert(view);
  if(openEditor) verifyEditor(view,[&]{return controller->getParamNormalized(ids["Velocity"]);});
  view->release();
  std::cout<<"PASS compiled VST3: self-contained sample bank, MIDI offsets/audio, three rates/tones, parameter state round-trip, sustain mapping and editor creation\n";
}
