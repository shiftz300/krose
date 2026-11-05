// Device-free, real-time-paced VST3/UI measurements on macOS.
#include "pluginterfaces/gui/iplugview.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "public.sdk/source/vst/hosting/eventlist.h"
#include "public.sdk/source/vst/hosting/hostclasses.h"
#include "public.sdk/source/vst/hosting/module.h"
#include "public.sdk/source/vst/hosting/parameterchanges.h"
#include "public.sdk/source/vst/hosting/plugprovider.h"
#import <Cocoa/Cocoa.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <libproc.h>
#include <map>
#include <string>
#include <sys/resource.h>
#include <thread>
#include <time.h>
#include <unistd.h>
#include <vector>
using namespace Steinberg;
using namespace Steinberg::Vst;
using Clock = std::chrono::steady_clock;
static void pump(double seconds) {
  const auto end = Clock::now() + std::chrono::duration<double>(seconds);
  while (Clock::now() < end)
    @autoreleasepool {
      auto event = [NSApp nextEventMatchingMask:NSEventMaskAny
                                      untilDate:[NSDate dateWithTimeIntervalSinceNow:.003]
                                         inMode:NSDefaultRunLoopMode
                                        dequeue:YES];
      if (event)
        [NSApp sendEvent:event];
      [NSApp updateWindows];
    }
}
static rusage_info_v4 usage() {
  rusage_info_v4 r{};
  assert(proc_pid_rusage(getpid(), RUSAGE_INFO_V4, reinterpret_cast<rusage_info_t *>(&r)) == 0);
  return r;
}
static NSView *native(NSView *view) {
  if ([NSStringFromClass(view.class) containsString:@"IGraphics"])
    return view;
  for (NSView *child in view.subviews)
    if (auto result = native(child))
      return result;
  return nil;
}
static void fold(NSView *view) {
  auto point =
      [view convertPoint:NSMakePoint(71, view.isFlipped ? 85 : view.bounds.size.height - 85)
                  toView:nil];
  for (auto type : {NSEventTypeLeftMouseDown, NSEventTypeLeftMouseUp}) {
    auto event = [NSEvent mouseEventWithType:type
                                    location:point
                               modifierFlags:0
                                   timestamp:0
                                windowNumber:view.window.windowNumber
                                     context:nil
                                 eventNumber:0
                                  clickCount:1
                                    pressure:1];
    if (type == NSEventTypeLeftMouseDown)
      [view mouseDown:event];
    else
      [view mouseUp:event];
  }
}
static double cpuSeconds() {
  rusage value{};
  assert(getrusage(RUSAGE_SELF, &value) == 0);
  return value.ru_utime.tv_sec + value.ru_stime.tv_sec +
         (value.ru_utime.tv_usec + value.ru_stime.tv_usec) / 1e6;
}
struct Metrics {
  std::vector<double> cpu, footprint, rss;
  double previousCpu = cpuSeconds();
  Clock::time_point last = Clock::now();
  void sample() {
    auto now = Clock::now();
    const auto r = usage();
    const double seconds = std::chrono::duration<double>(now - last).count();
    const double currentCpu = cpuSeconds();
    cpu.push_back((currentCpu - previousCpu) / seconds * 100);
    previousCpu = currentCpu;
    footprint.push_back(r.ri_phys_footprint / 1048576.);
    rss.push_back(r.ri_resident_size / 1048576.);
    last = now;
  }
};
static double quantile(std::vector<double> data, double p) {
  if (data.empty())
    return 0;
  std::sort(data.begin(), data.end());
  return data[std::min(data.size() - 1, size_t(p * data.size()))];
}
static double average(const std::vector<double> &v) {
  double total = 0;
  for (auto n : v)
    total += n;
  return v.empty() ? 0 : total / v.size();
}
struct Audio {
  IAudioProcessor *processor;
  std::map<std::string, ParamID> &ids;
  int program, notes;
  bool arp, switching;
  std::atomic<bool> stop{false}, measure{false};
  std::thread worker;
  std::vector<double> callbacks, callbackCpu;
  double maximumCpu = 0, maximumWall = 0;
  double energy = 0, peak = 0;
  unsigned overBudget = 0;
  int expansion;
  Audio(IAudioProcessor *p, std::map<std::string, ParamID> &params, int selected, int count,
        bool useArp, bool switches, int ex)
      : processor(p), ids(params), program(selected), notes(count), arp(useArp),
        switching(switches), expansion(ex) {
    callbacks.reserve(20000);
    callbackCpu.reserve(20000);
    worker = std::thread([this] { run(); });
  }
  ~Audio() { finish(); }
  void finish() {
    stop = true;
    if (worker.joinable())
      worker.join();
  }
  void run() {
    EventList events;
    ParameterChanges changes;
    int index = 0, point = 0;
    auto parameter = [&](const char *name, double v) {
      if (ids.count(name))
        changes.addParameterData(ids.at(name), index)->addPoint(0, v, point);
    };
    parameter("Program", program / 1161.);
    parameter("Arp", arp ? 1 : 0);
    parameter("Arp Host Sync", 0);
    parameter("FX Bypass", 0);
    parameter("MIDI Input Channel", 0);
    float left[128]{}, right[128]{};
    float *channels[] = {left, right};
    AudioBusBuffers bus{};
    bus.numChannels = 2;
    bus.channelBuffers32 = channels;
    ProcessData data{};
    data.processMode = kRealtime;
    data.symbolicSampleSize = kSample32;
    data.numSamples = 128;
    data.numOutputs = 1;
    data.outputs = &bus;
    data.inputEvents = &events;
    data.inputParameterChanges = &changes;
    ProcessContext context{};
    context.sampleRate = 48000;
    context.tempo = 120;
    context.state = ProcessContext::kPlaying | ProcessContext::kProjectTimeMusicValid |
                    ProcessContext::kTempoValid;
    data.processContext = &context;
    unsigned block = 0;
    const auto origin = Clock::now();
    while (!stop.load()) {
      if (block % 375 == 0)
        for (int n = 0; n < notes; ++n) {
          Event event{};
          event.type = Event::kNoteOffEvent;
          event.noteOff.pitch = 40 + n;
          events.addEvent(event);
          event = {};
          event.type = Event::kNoteOnEvent;
          event.noteOn.pitch = 40 + n;
          event.noteOn.velocity = 100.f / 127;
          event.noteOn.noteId = n;
          events.addEvent(event);
        }
      if (switching && block % 375 == 0) {
        const int programs[] = {1, 2, 400, 700, 1161, expansion, 0};
        parameter("Program", programs[(block / 375) % 7] / 1161.);
      }
      context.projectTimeSamples = uint64_t(block) * 128;
      context.projectTimeMusic = context.projectTimeSamples * 120. / (60 * 48000);
      const bool recording = measure.load();
      timespec cpuBegin{}, cpuEnd{};
      clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpuBegin);
      const auto begin = Clock::now();
      assert(processor->process(data) == kResultOk);
      clock_gettime(CLOCK_THREAD_CPUTIME_ID, &cpuEnd);
      const double cpuMicros =
          (cpuEnd.tv_sec - cpuBegin.tv_sec) * 1e6 + (cpuEnd.tv_nsec - cpuBegin.tv_nsec) / 1000.;
      const double micros = std::chrono::duration<double, std::micro>(Clock::now() - begin).count();
      if (recording) {
        callbacks.push_back(micros);
        callbackCpu.push_back(cpuMicros);
        if (micros > maximumWall) {
          maximumWall = micros;
          maximumCpu = cpuMicros;
        }
        if (micros > 128. / 48000 * 1e6)
          ++overBudget;
        for (int i = 0; i < 128; ++i) {
          assert(std::isfinite(left[i]) && std::isfinite(right[i]));
          energy += left[i] * left[i] + right[i] * right[i];
          peak = std::max({peak, std::abs(double(left[i])), std::abs(double(right[i]))});
        }
      }
      events.clear();
      changes.clearQueue();
      ++block;
      std::this_thread::sleep_until(origin +
                                    std::chrono::duration_cast<Clock::duration>(
                                        std::chrono::duration<double>(block * 128. / 48000)));
    }
  }
};
static void report(const std::string &name, const Metrics &m, const Audio *a = nullptr) {
  std::cout << "{\"case\":\"" << name << "\",\"cpu_mean_percent\":" << average(m.cpu)
            << ",\"cpu_p95_percent\":" << quantile(m.cpu, .95)
            << ",\"footprint_mean_mib\":" << average(m.footprint)
            << ",\"footprint_peak_mib\":" << quantile(m.footprint, 1)
            << ",\"rss_mean_mib\":" << average(m.rss);
  if (a)
    std::cout << ",\"callback_median_us\":" << quantile(a->callbacks, .5)
              << ",\"callback_p95_us\":" << quantile(a->callbacks, .95)
              << ",\"callback_max_us\":" << quantile(a->callbacks, 1)
              << ",\"callback_cpu_p95_us\":" << quantile(a->callbackCpu, .95)
              << ",\"worst_wall_callback_cpu_us\":" << a->maximumCpu
              << ",\"callback_budget_overruns\":" << a->overBudget << ",\"energy\":" << a->energy
              << ",\"peak\":" << a->peak;
  std::cout << "}" << std::endl;
}
int main(int argc, char **argv) {
  if (argc < 2 || argc > 3)
    return 2;
  const double seconds = argc == 3 ? std::max(3., std::atof(argv[2])) : 6.;
  const auto config = "/tmp/krose-benchmark-midi-" + std::to_string(getpid()) + ".json";
  setenv("KROSE_MIDI_MAP_FILE", config.c_str(), 1);
  @autoreleasepool {
    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
    auto window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1472, 648)
                                              styleMask:NSWindowStyleMaskBorderless
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    [window orderFront:nil];
    pump(.5);
    auto observe = [&](const char *name, Audio *audio, NSView *animation) {
      Metrics m;
      if (audio)
        audio->measure = true;
      auto start = Clock::now(), next = start;
      unsigned n = 0;
      while (std::chrono::duration<double>(Clock::now() - start).count() < seconds) {
        pump(.2);
        m.sample();
        if (animation && Clock::now() >= next) {
          fold(animation);
          next = Clock::now() + std::chrono::milliseconds(450);
        }
        ++n;
      }
      if (audio) {
        audio->measure = false;
        audio->finish();
      }
      report(name, m, audio);
    };
    observe("empty_host", nullptr, nil);
    const auto loading = Clock::now();
    std::string error;
    auto module = VST3::Hosting::Module::create(argv[1], error);
    assert(module);
    auto host = owned(new HostApplication);
    PluginContextFactory::instance().setPluginContext(host.get());
    const auto classes = module->getFactory().classInfos();
    const auto info = std::find_if(classes.begin(), classes.end(), [](const auto &c) {
      return c.category() == kVstAudioEffectClass;
    });
    assert(info != classes.end());
    PlugProvider provider(module->getFactory(), *info, true);
    assert(provider.initialize());
    auto component = provider.getComponentPtr();
    auto controller = provider.getControllerPtr();
    FUnknownPtr<IAudioProcessor> processor(component);
    assert(processor && controller);
    std::map<std::string, ParamID> ids;
    for (int i = 0; i < controller->getParameterCount(); ++i) {
      ParameterInfo p{};
      controller->getParameterInfo(i, p);
      if (p.id >= 39)
        continue;
      std::string name;
      for (auto c : p.title) {
        if (!c)
          break;
        name += char(c);
      }
      ids[name] = p.id;
    }
    ProcessSetup setup{};
    setup.processMode = kRealtime;
    setup.symbolicSampleSize = kSample32;
    setup.maxSamplesPerBlock = 128;
    setup.sampleRate = 48000;
    assert(processor->setupProcessing(setup) == kResultOk);
    SpeakerArrangement stereo = SpeakerArr::kStereo;
    assert(processor->setBusArrangements(nullptr, 0, &stereo, 1) == kResultOk);
    component->activateBus(kAudio, kOutput, 0, true);
    component->activateBus(kEvent, kInput, 0, true);
    component->setActive(true);
    std::cout << "{\"startup_ms\":"
              << std::chrono::duration<double, std::milli>(Clock::now() - loading).count()
              << ",\"scope\":\"48kHz/128 frames, whole test host, 100 percent = one CPU core, "
                 "real-time paced, no device\"}"
              << std::endl;
    int expansion = 1161;
    for (int i = 0; i <= 1161; ++i) {
      String128 text{};
      controller->getParamStringByValue(ids.at("Program"), i / 1161., text);
      std::string name;
      for (auto c : text) {
        if (!c)
          break;
        name += char(c);
      }
      if (name.find("EXPCM001:000") != std::string::npos) {
        expansion = i;
        break;
      }
    }
    auto view = owned(controller->createView(ViewType::kEditor));
    assert(view);
    NSView *panel = nil;
    auto phase = [&](const char *name, int program, int notes, bool arp = false,
                     bool switching = false, bool animate = false) {
      if (const char *only = std::getenv("KROSE_BENCH_CASE"))
        if (name != std::string(only))
          return;
      processor->setProcessing(true);
      {
        Audio audio(processor, ids, program, notes, arp, switching, expansion);
        pump(1.2);
        observe(name, &audio, animate ? panel : nil);
        if (notes)
          assert(audio.energy > 1e-6);
      }
      processor->setProcessing(false);
    };
    phase("audio_idle_editor_closed", 0, 0);
    assert(view->attached((__bridge void *)window.contentView, kPlatformTypeNSView) == kResultOk);
    pump(2);
    panel = native(window.contentView);
    assert(panel);
    phase("editor_idle", 0, 0);
    phase("fx_animation", 0, 0, false, false, true);
    phase("concert_8_notes", 0, 8);
    phase("concert_32_notes", 0, 32);
    phase("factory_8_notes", 1, 8);
    phase("factory_32_notes", 1, 32);
    phase("expansion_piano_8_notes", expansion, 8);
    phase("arp_8_keys", 1, 8, true);
    phase("program_switching_8_notes", 1, 8, false, true);
    view->removed();
    pump(1);
    phase("editor_closed_after_browsing", 0, 0);
    component->setActive(false);
    [window orderOut:nil];
  }
}
