#include "engine/InstrumentEngine.h"
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <new>
#include <memory>
#include <thread>
using namespace segrand;
static thread_local bool realtime = false;
static thread_local unsigned allocations = 0, frees = 0;
void *operator new(std::size_t n) {
  if (realtime)
    ++allocations;
  if (auto p = std::malloc(n))
    return p;
  throw std::bad_alloc();
}
void *operator new[](std::size_t n) { return ::operator new(n); }
void operator delete(void *p) noexcept {
  if (realtime && p)
    ++frees;
  std::free(p);
}
void operator delete[](void *p) noexcept { ::operator delete(p); }
void operator delete(void *p, std::size_t) noexcept { ::operator delete(p); }
void operator delete[](void *p, std::size_t) noexcept { ::operator delete(p); }
struct Block {
  std::array<float, 128> l{}, r{};
};
void render(InstrumentEngine &engine, Block &b) {
  realtime = true;
  engine.Process(b.l.data(), b.r.data(), 128);
  realtime = false;
  for (int i = 0; i < 128; ++i)
    assert(std::isfinite(b.l[i]) && std::isfinite(b.r[i]));
}
void same(InstrumentEngine &a, InstrumentEngine &b) {
  Block x, y;
  render(a, x);
  render(b, y);
  assert(x.l == y.l && x.r == y.r);
}
int main(int argc, char **argv) {
  assert(argc == 3);
  // Exercise both heap and independently mapped storage, including the final
  // unaligned decode, ownership transfer and resizing between allocation modes.
  for (size_t count : {size_t(17), size_t(262144), size_t(262143)}) {
    PCM24 samples;
    samples.resize(count);
    assert(samples.size() == count && samples[count - 1] == 0);
    auto *last = samples.data() + (count - 1) * 3;
    last[0] = 0xff;
    last[1] = 0xff;
    last[2] = 0x7f;
    const float expected = 8388607.f / 8388608.f;
    PCM24 moved(std::move(samples));
    assert(samples.size() == 0 && samples.data() == nullptr);
    assert(moved[count - 1] == expected);
    samples.resize(300000);
    samples = std::move(moved);
    assert(samples[count - 1] == expected && moved.data() == nullptr);
    samples.resize(9);
    assert(samples[8] == 0);
    samples.resize(0);
    assert(samples.size() == 0 && samples.data() == nullptr);
  }
  auto metadata = ProgramLibrary::Load(argv[1], false);
  auto concert = SampleBank::Load(argv[2], false);
  assert(metadata->PCMBytes() == 0 && !concert->preloaded);
  for (const auto &layer : concert->layers)
    for (const auto &sample : layer)
      assert(sample.stereo.size() == 0 && sample.frames() > 0);
  {
    auto first = metadata->LoadProgram(0), second = metadata->LoadProgram(0);
    assert(first == second);
    assert(std::any_of(first->begin(), first->end(), [](const auto &pcm) { return bool(pcm); }));
    std::weak_ptr<const SampleWindow> window = first;
    first.reset();
    assert(!window.expired());
    second.reset();
    assert(window.expired());
  }
  auto full = ProgramLibrary::Load(argv[1]);
  auto fullConcert = SampleBank::Load(argv[2]);
  {
    // Large engine fixtures must not consume the default Windows thread stack.
    auto lazyStorage=std::make_unique<InstrumentEngine>(concert,metadata);
    auto referenceStorage=std::make_unique<InstrumentEngine>(fullConcert,full);
    auto& lazy=*lazyStorage;auto& reference=*referenceStorage;
    Controls controls;
    controls.space = .3;
    // Multiple rates, overlapping voices across both engines, repeated programs,
    // reverse/loop/stereo regions and large expansion sets.
    for (double rate : {44100., 48000., 96000.}) {
      lazy.Prepare(rate);
      reference.Prepare(rate);
      for (int program : {1, 2, 5, 40, 128, 256, 512, 900, 1100, 1161, 0, 1}) {
        controls.program = program;
        lazy.SetControls(controls, true);
        reference.SetControls(controls);
        assert(lazy.CurrentProgram() == program);
        for (int note : {36, 60, 84}) {
          lazy.Queue({37, 0x90, uint8_t(note), 113});
          reference.Queue({37, 0x90, uint8_t(note), 113});
        }
        for (int n = 0; n < 24; ++n)
          same(lazy, reference);
        for (int note : {36, 60, 84}) {
          lazy.Queue({17, 0x80, uint8_t(note), 0});
          reference.Queue({17, 0x80, uint8_t(note), 0});
        }
        for (int n = 0; n < 8; ++n)
          same(lazy, reference);
      }
    }
    // Real-time cold selection continues the held old voice until the new set is
    // ready. New program publication has no effect on the old voice's PCM.
    lazy.Panic();
    reference.Panic();
    controls.program = 1;
    lazy.SetControls(controls, true);
    reference.SetControls(controls);
    lazy.Queue({0, 0x90, 60, 110});
    reference.Queue({0, 0x90, 60, 110});
    same(lazy, reference);
    controls.program = 700;
    auto begin = std::chrono::steady_clock::now();
    do {
      realtime = true;
      const bool published = lazy.SetControls(controls);
      realtime = false;
      // Commit FX and calibrated level on the same block in both engines.
      // Their held voices continue reading their original immutable PCM.
      if (published) reference.SetControls(controls);
      same(lazy, reference);
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
      assert(std::chrono::steady_clock::now() - begin < std::chrono::seconds(5));
    } while (lazy.CurrentProgram() != 700);
    reference.SetControls(controls);
    lazy.Queue({0, 0x90, 72, 110});
    reference.Queue({0, 0x90, 72, 110});
    for (int n = 0; n < 30; ++n)
      same(lazy, reference);
    std::cout << "Cold switch ms "
              << std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begin)
                     .count()
              << '\n';
    // Rapid changes are coalesced; a late worker result cannot replace the final selection.
    Block audio;
    for (int p = 2; p < 180; ++p) {
      controls.program = p;
      realtime = true;
      lazy.SetControls(controls);
      realtime = false;
      render(lazy, audio);
    }
    controls.program = 1161;
    begin = std::chrono::steady_clock::now();
    do {
      realtime = true;
      lazy.SetControls(controls);
      realtime = false;
      render(lazy, audio);
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
      assert(std::chrono::steady_clock::now() - begin < std::chrono::seconds(5));
    } while (lazy.CurrentProgram() != 1161);
    for (int n = 0; n < 50; ++n) {
      lazy.SetControls(controls);
      render(lazy, audio);
      assert(lazy.CurrentProgram() == 1161);
    }
    // Release retired snapshots. Small final patch + bounded recent cache, not the full bank.
    lazy.Panic();
    render(lazy, audio);
    std::this_thread::sleep_for(std::chrono::milliseconds(40));
    assert(metadata->ResidentBytes() < 40u * 1024 * 1024);
  }
  // Suspended host: nobody acquires completed results. Browsing beyond the slot
  // count must recycle cancelled Ready results and keep the cache bounded.
  {
    SampleLoader idle(argv[2], metadata);
    for (int program = 100; program < 370; ++program) {
      idle.Request(program);
      const auto begin = std::chrono::steady_clock::now();
      while (!idle.ReadyFor(program)) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
        assert(std::chrono::steady_clock::now() - begin < std::chrono::seconds(5));
      }
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    assert(idle.ResidentBytes() < 64u * 1024 * 1024);
  }
  // A failed cold load keeps the old playable Program and reports failure.
  auto temporary = std::filesystem::temp_directory_path() /
                   std::filesystem::path(
                       "krose-load-failure-" +
                       std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::create_directory(temporary);
  auto link = temporary / "Factory.samples";
  std::error_code linkError;
  std::filesystem::create_hard_link(std::filesystem::absolute(argv[1]), link, linkError);
  if (linkError)
    std::filesystem::copy_file(argv[1], link);
  {
    auto broken = ProgramLibrary::Load(link.string(), false);
    auto engineStorage=std::make_unique<InstrumentEngine>(concert,broken);auto& engine=*engineStorage;
    std::filesystem::remove(link);
    Controls c;
    c.program = 2;
    Block audio;
    auto begin = std::chrono::steady_clock::now();
    while (engine.FailedProgram() != 2) {
      realtime = true;
      engine.SetControls(c);
      realtime = false;
      render(engine, audio);
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
      assert(std::chrono::steady_clock::now() - begin < std::chrono::seconds(5));
    }
    assert(engine.CurrentProgram() == 0);
    engine.Queue({0, 0x90, 60, 110});
    double energy = 0;
    for (int n = 0; n < 50; ++n) {
      render(engine, audio);
      for (float x : audio.l)
        energy += x * x;
    }
    assert(energy > 1e-6);
    engine.SetControls(c, true);
    render(engine, audio);
    for (float value : audio.l)
      assert(value == 0);
  }
  std::filesystem::remove_all(temporary);
  assert(allocations == 0 && frees == 0);
  std::cout << "PASS on-demand PCM equivalence, live tails, cancellation, failure fallback, "
               "bounded cache; zero RT new/delete\n";
}
