#include "effects/OutputSafety.h"
#include "../../src/plugin/storage/ParameterTransaction.h"
#include "effects/FxMonitor.h"
#include "../../src/plugin/editor/native/FxAnalysis.h"
#include <cassert>
#include <cmath>
#include <iostream>
#include <memory>
#include <limits>
#include <thread>

int main() {
  std::atomic<uint64_t> generation{0};
  {
    krose::storage::ParameterTransaction outer(generation);
    assert(uint32_t(generation.load()) == 1);
    { krose::storage::ParameterTransaction nested(generation); assert(uint32_t(generation.load()) == 2); }
    assert(uint32_t(generation.load()) == 1);
  }
  assert(uint32_t(generation.load()) == 0 && (generation.load() >> 32) == 2);
  segrand::OutputSafety safety;
  for (int i=-950;i<=950;++i) {
    float left=i/1000.f, right=-left*.5f;
    const float expected=left, expectedRight=right;
    safety.Process(left,right);
    assert(left==expected && right==expectedRight);
  }
  for (double value:{.96,1.,2.,5.,100.,1e20}) {
    float left=float(value), right=float(-value*.3);
    safety.Process(left,right);
    assert(std::abs(left)<=.999001 && std::abs(right)<=.999001);
    assert(std::abs(right/left+.3)<1e-6);
  }
  assert(safety.Reduction()>.9);
  float invalid=std::numeric_limits<float>::infinity(), finite=1;
  safety.Process(invalid,finite);assert(invalid==0 && finite==0);
  auto monitor=std::make_unique<segrand::FxMonitor>();
  monitor->Prepare(48000); monitor->Enable(true);
  // A full-rate stream preserves frequency without aliasing.
  for (unsigned i=0;i<4096;++i) {
    double x=.25*std::sin(6.283185307179586*1500*i/48000);
    monitor->Push(0,x,x,-x*.5,.4);
  }
  monitor->Publish();
  std::array<segrand::FxVisualSample,segrand::FxMonitor::kCapacity> data;
  const auto count=monitor->Read(0,data.data(),unsigned(data.size()));
  assert(count==4096);
  krose::ui::FxAnalysis analysis;
  analysis.Feed(data.data(),count); analysis.Analyze(48000,1./30);
  assert(analysis.peak>.24 && analysis.reduction>.39);
  auto maximum=std::max_element(analysis.inputBands.begin(),analysis.inputBands.end());
  const unsigned band=unsigned(maximum-analysis.inputBands.begin());
  const double frequency=30*std::pow(11000./30,band/31.);
  assert(frequency>1200 && frequency<1800);
  // Fill and overflow the visual ring without a consumer. It must stay bounded.
  for(unsigned i=0;i<20000;++i) monitor->Push(1,.1,.2,.3);
  monitor->Publish();
  assert(monitor->Read(1,data.data(),unsigned(data.size()))==segrand::FxMonitor::kCapacity);
  assert(monitor->Read(1,data.data(),unsigned(data.size()))==0);
  monitor->Enable(false);
  monitor->Push(1,1,1,1);monitor->Publish();
  assert(monitor->Read(1,data.data(),unsigned(data.size()))==0);
  monitor->Enable(true);
  std::atomic<bool> done{false};
  std::thread producer([&] {
    for (unsigned i=1; i<=200000; ++i) {
      monitor->Push(2,i,i,-double(i),.25);
      if (i%128==0) monitor->Publish();
    }
    monitor->Publish();done.store(true,std::memory_order_release);
  });
  float previous=0;unsigned received=0;
  for (;;) {
    const auto n=monitor->Read(2,data.data(),unsigned(data.size()));
    for (unsigned i=0;i<n;++i) {
      assert(data[i].left>previous && data[i].input==data[i].left);
      assert(data[i].right==-data[i].left && data[i].reduction==.25f);
      previous=data[i].left;++received;
    }
    if (done.load(std::memory_order_acquire) && !n) break;
    std::this_thread::yield();
  }
  producer.join();assert(received>0);
  std::cout<<"PASS output headroom, linked safety, visual signal frequency and bounded ring\n";
}
