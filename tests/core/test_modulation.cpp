#include "NativeVoiceData.h"
#include "voice/ModulationData.h"
#include "voice/NativeFilter.h"
#include "voice/NativeLFO.h"
#include "voice/NativeModulation.h"
#include "voice/PitchEnvelope.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <fstream>
#include <iostream>
using namespace segrand;
unsigned Read(std::ifstream &f, int n) {
  unsigned x = 0;
  for (int i = 0; i < n; ++i) {
    int c = f.get();
    assert(c >= 0);
    x |= unsigned(c) << (8 * i);
  }
  return x;
}
int main(int argc, char **argv) {
  assert(argc == 7);
  std::ifstream file(argv[1], std::ios::binary);
  assert(file);
  unsigned count = Read(file, 4);
  for (unsigned c = 0; c < count; ++c) {
    std::array<uint8_t, 28> p{};
    file.read(reinterpret_cast<char *>(p.data()), p.size());
    NativeLFO lfo;
    ModulationSources sources{};
    uint32_t seed = 0x12345678;
    lfo.Start(p.data(), 0, seed, sources);
    const unsigned clocks[] = {0, 1, 15, 60, 240, 480, 960, 1920};
    for (unsigned t : clocks) {
      const int expected = int32_t(Read(file, 4));
      const unsigned phase = Read(file, 2), fade = Read(file, 2);
      const int value = lfo.Wave(sources, seed);
      lfo.Advance(sources, t);
      if (value != expected || lfo.Phase() != phase || lfo.Fade() != fade) {
        std::cerr << "LFO case " << c << " clock " << t << ": " << value << '/' << expected
                  << " phase " << lfo.Phase() << '/' << phase << " fade " << lfo.Fade() << '/'
                  << fade << '\n';
        return 1;
      }
    }
  }
  assert(file.peek() == EOF);
  assert(count == 3072);
  assert(NativeLFO::Depth(50) == 131 && NativeLFO::Depth(60) == 256 &&
         NativeLFO::Depth(99) == 2254);
  std::cout << "PASS 24576 original ARM LFO updates\n";
  std::ifstream pitch(argv[2], std::ios::binary);
  assert(pitch);
  const unsigned cases = Read(pitch, 4);
  unsigned updates = 0;
  for (unsigned c = 0; c < cases; ++c) {
    std::array<uint8_t, 26> p{};
    pitch.read(reinterpret_cast<char *>(p.data()), p.size());
    const unsigned steps = Read(pitch, 4);
    PitchEnvelope eg;
    ModulationSources sources{};
    eg.Start(p.data(), sources);
    for (unsigned i = 0; i < steps; ++i) {
      const bool release = Read(pitch, 1);
      const int level = int32_t(Read(pitch, 4)), stage = int32_t(Read(pitch, 4));
      if (release)
        eg.Release(sources);
      eg.Tick(sources);
      if (eg.Level() != level || eg.Stage() != stage) {
        std::cerr << "Pitch case " << c << " update " << i << ": " << eg.Level() << '/' << level
                  << " stage " << eg.Stage() << '/' << stage << '\n';
        return 1;
      }
      ++updates;
    }
  }
  assert(pitch.peek() == EOF);
  std::cout << "PASS " << updates << " original ARM Pitch EG updates\n";
  std::ifstream mixer(argv[3], std::ios::binary);
  assert(mixer);
  unsigned mixerCases = Read(mixer, 4), mixed = 0;
  for (unsigned c = 0; c < mixerCases; ++c) {
    std::array<uint8_t, 2140> program{};
    mixer.read(reinterpret_cast<char *>(program.data() + 0x564 + 0x14c), 24);
    const unsigned steps = Read(mixer, 4);
    NativeModulation mod;
    for (unsigned i = 0; i < steps; ++i) {
      const unsigned initialize = Read(mixer, 1);
      ModulationSources s{};
      for (int j = 9; j <= 11; ++j)
        s[j] = int32_t(Read(mixer, 4));
      const int expected = int32_t(Read(mixer, 4));
      if (initialize)
        mod.Start(program.data(), 0, s, 1);
      else
        mod.Tick(s, 20 * i);
      if (initialize != 2 && mod.sources[1] != expected) {
        std::cerr << "Mixer case " << c << " update " << i << ": " << mod.sources[1] << '/'
                  << expected << '\n';
        return 1;
      }
      ++mixed;
    }
  }
  assert(mixer.peek() == EOF);
  std::cout << "PASS " << mixed << " original ARM mixer updates\n";
  std::array<uint8_t, 2140> program{};
  for (int i = 0; i < 2; ++i) {
    auto p = program.data() + 0x564 + 0x30 + 28 * i;
    p[0] = i ? 3 : 0;
    p[1] = 50;
    p[8] = uint8_t(7 - i);
    p[9] = 35;
    p[12] = 6;
    p[13] = 1;
    p[16] = uint8_t(7 - i);
    p[17] = 45;
  }
  NativeModulation feedback;
  feedback.Start(program.data(), 0, {}, 1);
  std::ifstream trace(argv[4], std::ios::binary);
  assert(trace);
  for (unsigned i = 0; i < 128; ++i) {
    feedback.Tick({}, i);
    const int a = int32_t(Read(trace, 4)), b = int32_t(Read(trace, 4));
    const unsigned pa = Read(trace, 4), pb = Read(trace, 4);
    assert(feedback.lfo[0].Value() == a && feedback.lfo[1].Value() == b);
    assert(feedback.lfo[0].Phase() == pa && feedback.lfo[1].Phase() == pb);
  }
  assert(trace.peek() == EOF);
  std::ifstream targets(argv[5], std::ios::binary);
  assert(targets);
  const unsigned targetCases = Read(targets, 4);
  for (unsigned i = 0; i < targetCases; ++i) {
    const int amount = int8_t(Read(targets, 1));
    const unsigned routing = Read(targets, 1);
    const int values[] = {int16_t(Read(targets, 2)), int16_t(Read(targets, 2))};
    const unsigned fades[] = {Read(targets, 2), Read(targets, 2)};
    const int offset = int16_t(Read(targets, 2));
    program = {};
    program[0x564 + 0x88] = uint8_t(routing);
    program[0x564 + 0x7e] = program[0x564 + 0x7f] = uint8_t(amount);
    for (unsigned branch = 0; branch < 2; ++branch) {
      auto p = program.data() + 0x564 + 0x90 + 36 * branch;
      p[17] = p[18] = 99;
      p[19] = 50;
      p[20] = 10;
      p[25] = p[26] = uint8_t(amount);
    }
    NativeModulation mod;
    mod.Start(program.data(), 0, {}, 1);
    std::array<std::array<uint8_t, 28>, 2> params{};
    uint32_t seed = 1;
    for (unsigned slot = 0; slot < 2; ++slot) {
      auto &p = params[slot];
      p[0] = values[slot] > 0 ? 1 : values[slot] < 0 ? 2 : 0;
      p[3] = values[slot] < 0 ? 36 : 0;
      p[7] = fades[slot] ? 0 : 99;
      mod.lfo[slot].Start(p.data(), 0, seed, {});
      if (mod.lfo[slot].Value() != values[slot] || mod.lfo[slot].Fade() != fades[slot]) {
        std::cerr << "Target LFO " << i << " slot " << slot << ": " << mod.lfo[slot].Value() << '/'
                  << values[slot] << " fade " << mod.lfo[slot].Fade() << '/' << fades[slot] << '\n';
        return 1;
      }
    }
    assert(mod.PitchOffset() == offset);
    NativeVoice amplitude;
    amplitude.StartProgram(program.data(), 60, 100, 0, 127);
    NativeFilter filter;
    filter.StartProgram(program.data(), amplitude, 0, 100, 48000);
    filter.SetModulation({}, mod.lfo);
    for (unsigned branch = 0; branch < 2; ++branch)
      for (unsigned field = 0; field < 4; ++field)
        assert(filter.Word(branch, field) == Read(targets, 2));
  }
  for (int amount = -99; amount <= 99; ++amount)
    assert(NativeLFO::Depth(amount) == int16_t(Read(targets, 2)));
  assert(targets.peek() == EOF);
  std::cout << "PASS " << targetCases << " original ARM LFO pitch/filter targets and 199 depths\n";
  std::copy_n(native_data::kProgram, program.size(), program.data());
  auto *osc = program.data() + 0x564;
  osc[0x68] = 19;
  osc[0x69] = 50;
  osc[0x7d] = osc[0x7e] = osc[0x7f] = 0;
  ModulationSources sources{};
  NativeModulation mod;
  mod.Start(program.data(), 0, sources, 1);
  assert(mod.PitchOffset() == 0);
  sources[19] = 4096;
  mod.Tick(sources, 20);
  assert(mod.PitchOffset() == 131);
  std::array<uint8_t, 128> cc;
  cc.fill(255);
  sources = {};
  NativeModulation::Controllers(sources, cc, 0, 0, 0);
  assert(sources[19] == 0 && sources[16] == 0);
  cc[1] = 127;
  cc[16] = 0;
  NativeModulation::Controllers(sources, cc, 127, 64, -8192);
  assert(sources[19] == 4096 && sources[24] == -4096 && sources[16] == 4096 &&
         sources[17] == 2064 && sources[18] == -4096);
  sources = {};
  osc[0x108] = 19;
  osc[0x109] = 206;
  NativeVoice amplitude;
  amplitude.StartProgram(program.data(), 60, 100, 0, 127);
  std::array<NativeLFO, 2> lfo{};
  amplitude.SetModulation(sources, lfo);
  const auto gain = amplitude.Gain();
  sources[19] = 4096;
  amplitude.SetModulation(sources, lfo);
  assert(amplitude.Gain() < gain);
  osc[0x98] = 19;
  osc[0x99] = 226;
  NativeFilter filter;
  filter.StartProgram(program.data(), amplitude, 0, 100, 48000);
  sources = {};
  filter.SetModulation(sources, lfo);
  const auto cutoff = filter.Word(0, 1);
  sources[19] = 4096;
  filter.SetModulation(sources, lfo);
  assert(filter.Word(0, 1) < cutoff);
  // Audio topology follows the documented routing, independently of the
  // approximate control-word -> Hz/Q transfer law.
  for (unsigned route = 0; route < 4; ++route) {
    auto a = program, b = program;
    a[0x564 + 0x88] = b[0x564 + 0x88] = 0;
    std::copy_n(program.data() + 0x564 + 0xb4, 36, b.data() + 0x564 + 0x90);
    program[0x564 + 0x88] = uint8_t(route);
    NativeFilter actual, first, second;
    actual.StartProgram(program.data(), amplitude, 0, 100, 48000);
    first.StartProgram(a.data(), amplitude, 0, 100, 48000);
    second.StartProgram(b.data(), amplitude, 0, 100, 48000);
    if (route == 3) {
      assert(actual.Word(1, 0) == 32767 && actual.Word(0, 3) == 32767);
      assert(actual.Word(1, 1) == actual.Word(0, 1));
      assert(actual.Word(1, 2) == (unsigned(actual.Word(0, 2)) * 115 >> 8));
    }
    for (unsigned i = 0; i < 1000; ++i) {
      double l = i == 0 ? 1 : 0, r = l, x = l, y = r, z = l, w = r;
      actual.Process(l, r);
      first.Process(x, y);
      if (route == 1) {
        second.Process(x, y);
      } else if (route == 2) {
        second.Process(z, w);
        x += z;
        y += w;
      }
      if (route < 3) {
        assert(l == x && r == y);
      }
      assert(std::isfinite(l) && std::isfinite(r));
    }
  }
  std::cout << "PASS dynamic pitch/amplitude/filter AMS, controllers and four filter routes\n";
  program = {};
  program[0x564 + 0x31] = 50;
  program[0x564 + 0x36] = 50;
  cc.fill(255);
  cc[76] = 127;
  cc[78] = 0;
  NativeModulation fast;
  fast.Start(program.data(), 0, {}, 1, &cc);
  fast.Tick({}, 0, &cc);
  assert(fast.lfo[0].Phase() == std::min<unsigned>(modulation_data::kRate[99], 27525));
  cc[78] = 127;
  NativeModulation delayed;
  delayed.Start(program.data(), 0, {}, 1, &cc);
  delayed.Tick({}, 0, &cc);
  assert(delayed.lfo[0].Phase() == 0 && delayed.lfo[0].Fade() == 0);
  std::ifstream retriggers(argv[6], std::ios::binary);
  assert(retriggers);
  const unsigned traces = Read(retriggers, 4);
  for (unsigned c = 0; c < traces; ++c) {
    const int threshold = int32_t(Read(retriggers, 4)), initial = int32_t(Read(retriggers, 4));
    program = {};
    auto pitch = program.data() + 0x520;
    auto filterParams = program.data() + 0x564 + 0xd8;
    auto amp = program.data() + 0x564 + 0x118;
    const uint8_t curves[] = {0, 3, 7, 10};
    const uint8_t pitchParams[] = {236, 50, 70, 50, 216, 50, 50, 246, 0, 3, 7, 10};
    std::copy_n(pitchParams, 12, pitch);
    pitch[24] = 19;
    pitch[25] = uint8_t(threshold);
    std::copy_n(curves, 4, filterParams);
    filterParams[4] = 236;
    filterParams[5] = 50;
    filterParams[6] = 70;
    filterParams[7] = 50;
    filterParams[8] = 216;
    filterParams[9] = 50;
    filterParams[10] = 10;
    filterParams[11] = 50;
    filterParams[12] = 246;
    filterParams[32] = 19;
    filterParams[33] = uint8_t(threshold);
    const uint8_t ampParams[] = {0, 50, 99, 50, 70, 50, 40, 50, 0, 3, 7, 10};
    std::copy_n(ampParams, 12, amp);
    amp[31] = 19;
    amp[32] = uint8_t(threshold);
    sources = {};
    sources[19] = initial;
    PitchEnvelope pitchEG;
    pitchEG.Start(pitch, sources);
    NativeVoice ampEG;
    ampEG.StartProgram(program.data(), 60, 100, 0, 127, &sources);
    NativeFilter filterEG;
    filterEG.StartProgram(program.data(), ampEG, 0, 100, 48000);
    for (unsigned i = 0; i < 16; ++i) {
      sources[19] = int32_t(Read(retriggers, 4));
      int levels[3], stages[3];
      for (auto &v : levels)
        v = int32_t(Read(retriggers, 4));
      for (auto &v : stages)
        v = int32_t(Read(retriggers, 4));
      if (i == 8) {
        pitchEG.Release(sources);
        ampEG.ReleaseProgram();
        filterEG.Release();
      }
      pitchEG.Tick(sources);
      ampEG.Tick();
      filterEG.Tick();
      ampEG.SetModulation(sources, lfo);
      filterEG.SetModulation(sources, lfo);
      assert(pitchEG.Level() == levels[0] && ampEG.Level() == levels[2] &&
             filterEG.Level() == levels[1]);
      assert(pitchEG.Stage() == stages[0] && ampEG.Stage() == stages[2] &&
             filterEG.Stage() == stages[1]);
    }
  }
  assert(retriggers.peek() == EOF);
  std::cout << "PASS 80 original ARM three-envelope retrigger updates\n";
}
