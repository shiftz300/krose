// Default-preset, idle memory comparison. No audio device or user state writes.
#import <Cocoa/Cocoa.h>
#include "public.sdk/source/vst/hosting/hostclasses.h"
#include "public.sdk/source/vst/hosting/module.h"
#include "public.sdk/source/vst/hosting/plugprovider.h"
#include "public.sdk/source/vst/hosting/processdata.h"
#include "public.sdk/source/vst/hosting/eventlist.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/gui/iplugview.h"
#include <mach/mach.h>
#include <unistd.h>
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <cmath>
#include <vector>
using namespace Steinberg;
using namespace Steinberg::Vst;
static void pump(double seconds) {
  auto end = std::chrono::steady_clock::now() + std::chrono::duration<double>(seconds);
  while (std::chrono::steady_clock::now() < end) {
    @autoreleasepool {
      NSEvent *e = [NSApp nextEventMatchingMask:NSEventMaskAny
          untilDate:[NSDate dateWithTimeIntervalSinceNow:.005]
          inMode:NSDefaultRunLoopMode dequeue:YES];
      if (e) [NSApp sendEvent:e];
      [NSApp updateWindows];
    }
  }
}
static void memory(const char *stage) {
  task_vm_info_data_t info{};
  mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
  if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) == KERN_SUCCESS)
    std::cout << "MEMORY " << stage << " footprint=" << info.phys_footprint
              << " resident=" << info.resident_size << std::endl;
}
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  @autoreleasepool {
    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
    NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,800,600)
        styleMask:NSWindowStyleMaskBorderless backing:NSBackingStoreBuffered defer:NO];
    [window orderFront:nil];
    pump(.2);
    std::cout << "PID " << getpid() << std::endl;
    memory("host");
    std::string error;
    auto module = VST3::Hosting::Module::create(argv[1], error);
    if (!module) { std::cerr << error << '\n'; return 3; }
    auto host = owned(new HostApplication);
    PluginContextFactory::instance().setPluginContext(host.get());
    auto classes = module->getFactory().classInfos();
    auto info = std::find_if(classes.begin(), classes.end(), [](const auto &c) {
      return c.category() == kVstAudioEffectClass;
    });
    if (info == classes.end()) return 4;
    std::cout << "PLUGIN " << info->name() << " VERSION " << info->version() << std::endl;
    PlugProvider provider(module->getFactory(), *info, true);
    if (!provider.initialize()) return 5;
    auto component = provider.getComponentPtr();
    auto controller = provider.getControllerPtr();
    FUnknownPtr<IAudioProcessor> processor(component);
    if (!processor || !controller) return 6;
    ProcessSetup setup{};
    setup.processMode=kRealtime; setup.symbolicSampleSize=kSample32;
    setup.maxSamplesPerBlock=128; setup.sampleRate=48000;
    if (processor->setupProcessing(setup) != kResultOk) return 7;
    for (auto dir : {kInput,kOutput})
      for (int bus=0;bus<component->getBusCount(kAudio,dir);++bus)
        component->activateBus(kAudio,dir,bus,true);
    HostProcessData data;
    data.prepare(*component,128,kSample32);
    data.processMode=kRealtime;data.numSamples=128;
    for (int bus=0;bus<data.numInputs;++bus) {
      data.inputs[bus].silenceFlags=HostProcessData::kAllChannelsSilent;
      for (int ch=0;ch<data.inputs[bus].numChannels;++ch)
        std::fill_n(data.inputs[bus].channelBuffers32[ch],128,0.f);
    }
    component->setActive(true);processor->setProcessing(true);
    for(int n=0;n<128;++n) processor->process(data);
    processor->setProcessing(false); // no concurrent audio work in the GUI measurement
    pump(2);
    memory("engine");
    auto view=owned(controller->createView(ViewType::kEditor));
    if (!view) return 8;
    ViewRect rect{};view->getSize(&rect);
    std::cout << "VIEW " << rect.getWidth() << 'x' << rect.getHeight() << std::endl;
    [window setContentSize:NSMakeSize(rect.getWidth(),rect.getHeight())];
    @autoreleasepool {
      if (view->attached((__bridge void*)window.contentView,kPlatformTypeNSView)!=kResultOk) return 9;
      pump(3);
    }
    memory("editor");
    if (std::getenv("KROSE_BENCH_PLAY")) {
      if (component->getBusCount(kEvent,kInput)>0)
        component->activateBus(kEvent,kInput,0,true);
      EventList events;data.inputEvents=&events;
      for (int note : {48,55,60,64,67,72,76,79}) {
        Event e{};e.type=Event::kNoteOnEvent;e.busIndex=0;
        e.noteOn.pitch=note;e.noteOn.velocity=.8f;e.noteOn.noteId=note;
        events.addEvent(e);
      }
      double energy=0,peak=0;std::vector<double> times;
      processor->setProcessing(true);
      for (int block=0;block<1125;++block) {
        if (block==750)
          for (int note : {48,55,60,64,67,72,76,79}) {
            Event e{};e.type=Event::kNoteOffEvent;e.busIndex=0;
            e.noteOff.pitch=note;e.noteOff.noteId=note;events.addEvent(e);
          }
        const auto begin=std::chrono::steady_clock::now();
        if (processor->process(data)!=kResultOk) return 10;
        times.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-begin).count());
        events.clear();
        for (int b=0;b<data.numOutputs;++b)
          for (int c=0;c<data.outputs[b].numChannels;++c)
            for (int n=0;n<128;++n) {
              const double value=data.outputs[b].channelBuffers32[c][n];
              if (!std::isfinite(value)) return 11;
              energy+=value*value;peak=std::max(peak,std::abs(value));
            }
        pump(.002667);
      }
      processor->setProcessing(false);data.inputEvents=nullptr;
      std::sort(times.begin(),times.end());
      std::cout << "AUDIO eight notes, 48kHz/128 frames, 2s held+1s release: energy=" << energy
                << " peak=" << peak << " median_us=" << times[times.size()/2]
                << " p95_us=" << times[size_t(times.size()*.95)] << std::endl;
      memory("played");
    }
    if (const char* hold=std::getenv("KROSE_BENCH_HOLD_SECONDS")) pump(std::atoi(hold));
    view->removed();pump(1);memory("closed");
    component->setActive(false);
    [window orderOut:nil];
    std::cout << "PASS default-preset idle memory measurement\n";
  }
}
