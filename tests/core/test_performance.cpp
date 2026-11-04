#include "engine/InstrumentEngine.h"
#include "midi/Performance.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <new>
#include <vector>

static bool audioThread = false;
static unsigned allocations = 0;
void* operator new(std::size_t size) {
  if (audioThread) ++allocations;
  if (auto* p = std::malloc(size)) return p;
  throw std::bad_alloc();
}
void* operator new[](std::size_t n) { return ::operator new(n); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

using namespace segrand;
struct Audio {
  std::vector<float> left, right;
  explicit Audio(int frames) : left(frames), right(frames) {}
};
template<class Engine> Audio render(Engine& engine, int frames, int block = 127) {
  Audio result(frames);
  for (int at = 0; at < frames; at += block) {
    audioThread = true;
    engine.Process(result.left.data() + at, result.right.data() + at, std::min(block, frames - at));
    audioThread = false;
  }
  for (int i = 0; i < frames; ++i)
    assert(std::isfinite(result.left[i]) && std::isfinite(result.right[i]));
  return result;
}
double difference(const Audio& a, const Audio& b) {
  double sum = 0;
  for (size_t i = 0; i < a.left.size(); ++i)
    sum += std::abs(a.left[i] - b.left[i]) + std::abs(a.right[i] - b.right[i]);
  return sum;
}
void originalObservations(const std::string& folder) {
  MonoKeys keys;
  std::ifstream file(folder + "/keys.tsv");
  assert(file);
  int priority, note, velocity, expected, count, cached;
  std::string operation;
  unsigned cases = 0;
  while (file >> priority >> operation >> note >> velocity >> expected >> count >> cached) {
    if (operation == "reset") keys.Reset();
    else if (operation == "on") keys.On(note, velocity, priority);
    else keys.Off(note);
    assert(keys.Note() == expected && int(keys.Count()) == count && keys.Velocity() == cached);
    ++cases;
  }
  assert(cases == 72);
  std::ifstream coefficients(folder + "/coefficients.tsv");
  for (auto value : kPortamentoCoefficients) { int original; assert(coefficients >> original); assert(original == value); }
  std::ifstream visits(folder + "/glide.tsv");
  PitchGlide glide;
  int amount, interval, visit, pitch, step;
  unsigned visitsChecked = 0;
  while (visits >> amount >> interval >> visit >> pitch >> step) {
    if (!visit) glide.Start(60 * 65536, 60 + interval, amount);
    assert(glide.Pitch() == pitch && glide.Step() == step);
    glide.Tick();
    ++visitsChecked;
  }
  assert(visitsChecked > 40);
  for (int speed = 0; speed < 128; ++speed) {
    for (int target : {0, 60, 127}) {
      glide.Start(60 * 65536, target, speed);
      int last = glide.Pitch();
      for (int i = 0; i < 4000 && glide.Step(); ++i) {
        glide.Tick();
        assert(target >= 60 ? glide.Pitch() >= last : glide.Pitch() <= last);
        last = glide.Pitch();
      }
      assert(glide.Pitch() == target * 65536 && !glide.Step());
    }
  }
}
template<class Engine> void performance(Engine& engine) {
  Controls controls;
  controls.space = 0;
  controls.releaseSeconds = .05;
  for (int mode : {1, 2}) {
    controls.voiceMode = mode;
    controls.glide = 64;
    engine.SetControls(controls);
    for (double rate : {44100., 48000., 96000.}) {
      auto sequence = [&] {
        engine.Queue({17, 0x90, 60, 40});
        engine.Queue({257, 0x90, 72, 120});
        engine.Queue({503, 0x90, 65, 90});
        engine.Queue({1000, 0x80, 65, 0});
        engine.Queue({4096, 0x80, 72, 0});
        engine.Queue({8192, 0x80, 60, 0});
      };
      engine.Prepare(rate); sequence();
      const auto one = render(engine, 16000, 16000);
      engine.Prepare(rate); sequence();
      const auto split = render(engine, 16000, 31);
      assert(one.left == split.left && one.right == split.right);
      assert(std::all_of(one.left.begin(), one.left.begin() + 17, [](float v) {return v == 0;}));
      render(engine, int(rate)); assert(!engine.ActiveVoices());
    }
    engine.Prepare(48000);
    engine.Queue({0, 0x90, 60, 100}); render(engine, 256);
    const auto voices = engine.ActiveVoices(); assert(voices > 0);
    engine.Queue({0, 0x90, 60, 40}); render(engine, 256);
    assert(engine.ActiveVoices() == voices);
    engine.Queue({0, 0x80, 60, 0}); render(engine, 256);
    assert(engine.ActiveVoices() == voices);
    engine.Queue({0, 0xb0, 64, 127});
    engine.Queue({0, 0x90, 60, 0}); render(engine, 12000);
    assert(engine.ActiveVoices() == voices);
    engine.Queue({0, 0xb0, 64, 0}); render(engine, 48000);
    assert(!engine.ActiveVoices());
    // Independent channels, including panic/all-notes-off and controller reset.
    engine.Panic();
    engine.Queue({0, 0x90, 60, 100});engine.Queue({0, 0x91, 60, 100});render(engine, 256);
    assert(engine.ActiveVoices() == 2 * voices);
    engine.Queue({0, 0xb0, 120, 0});render(engine, 256);
    assert(engine.ActiveVoices() == voices);
    engine.Queue({0, 0xb1, 64, 127});engine.Queue({0, 0xb1, 123, 0});render(engine, 256);
    assert(engine.ActiveVoices() == voices);
    engine.Queue({0, 0xb1, 121, 0});render(engine, 48000);assert(!engine.ActiveVoices());
    // Full ten-note stack evicts the oldest; missing note-offs do not revive it.
    engine.Panic();
    for (int i = 0; i < 11; ++i) engine.Queue({i, 0x90, uint8_t(60 + i), 100});
    for (int i = 10; i >= 1; --i) engine.Queue({100 + 10 - i, 0x80, uint8_t(60 + i), 0});
    render(engine, 48000);assert(!engine.ActiveVoices());
  }
  // Repeated same-note legato keeps the first sample/velocity and envelopes.
  controls.voiceMode = 2; controls.glide = 0; engine.SetControls(controls);
  engine.Prepare(48000);engine.Queue({0, 0x90, 60, 40});const auto held = render(engine, 12000);
  engine.Prepare(48000);engine.Queue({0, 0x90, 60, 40});engine.Queue({4000, 0x90, 60, 127});
  const auto reused = render(engine, 12000);
  assert(difference(held, reused) < .0001);
  controls.voiceMode = 1;engine.SetControls(controls);engine.Prepare(48000);
  engine.Queue({0, 0x90, 60, 40});engine.Queue({4000, 0x90, 60, 127});
  assert(difference(held, render(engine, 12000)) > .01);
  // Glide is audible, and switching modes cannot leave keys in a stale list.
  auto phrase = [&](int glide) {
    controls.voiceMode = 2; controls.glide = glide; engine.SetControls(controls);engine.Prepare(48000);
    engine.Queue({0, 0x90, 60, 100});engine.Queue({4000, 0x90, 72, 100});return render(engine, 20000);
  };
  assert(difference(phrase(0), phrase(64)) > .01);
  controls.voiceMode = 0;engine.SetControls(controls);render(engine, 1000);assert(!engine.ActiveVoices());
  engine.Queue({0, 0x80, 72, 0});engine.Queue({0, 0x80, 60, 0});render(engine, 1000);assert(!engine.ActiveVoices());
}
int main(int argc, char** argv) {
  assert(argc == 4);
  originalObservations(argv[3]);
  auto bank = SampleBank::Load(argv[1]);
  auto library = ProgramLibrary::Load(argv[2]);
  PianoEngine concert(bank);performance(concert);
  ProgramEngine factory(library);performance(factory);
  NativeVoice amplitude;
  const auto* program=library->programs[0].controls.data();
  amplitude.StartProgram(program,60,40,0,127);
  for(int i=0;i<5;++i)amplitude.Tick();
  NativeFilter filter;filter.StartProgram(program,amplitude,0,40,48000);
  const int ampLevel=amplitude.Level(),ampStage=amplitude.Stage(),filterLevel=filter.Level(),filterStage=filter.Stage();
  const auto ampDuration=amplitude.Duration(),filterDuration=filter.Duration();
  const auto velocityFactor=amplitude.VelocityFactor();
  amplitude.Retune(84);filter.Retune(amplitude);
  assert(amplitude.Source(13)!=0&&amplitude.VelocityFactor()==velocityFactor);
  assert(amplitude.Level()==ampLevel&&amplitude.Stage()==ampStage&&amplitude.Duration()==ampDuration);
  assert(filter.Level()==filterLevel&&filter.Stage()==filterStage&&filter.Duration()==filterDuration);
  InstrumentEngine instrument(bank,library);Controls mono;mono.voiceMode=2;mono.program=1;
  instrument.SetControls(mono);instrument.Prepare(48000);
  instrument.Queue({0,0x90,60,100});instrument.Queue({10,0x90,72,100});render(instrument,1000);
  assert(instrument.ActiveVoices());
  mono.program=2;instrument.SetControls(mono);instrument.Queue({0,0x80,72,0});render(instrument,1000);
  assert(!instrument.ActiveVoices());
  instrument.Queue({0,0x90,60,100});render(instrument,256);assert(instrument.ActiveVoices());
  instrument.Panic();render(instrument,256);assert(!instrument.ActiveVoices());
  assert(!allocations);
  std::cout << "PASS original mono/glide observations; both engines; repeated keys; channel-local pedals; fallback; mode changes; three rates; block invariance; zero audio allocations\n";
}
