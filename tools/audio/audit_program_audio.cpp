#include "engine/ProgramEngine.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

// Offline diagnostic, deliberately before OutputSafety so a limiter cannot
// conceal a defective voice. Pitch snippets retain actual gain and timing.
int main(int argc, char **argv) {
  if (argc < 3) {
    std::fprintf(stderr, "usage: audit-program-audio Factory.samples output-prefix [first] [last] [dry|wet|drums|chord|keys] [rate]\n");
    return 2;
  }
  using namespace segrand;
  const auto bank = ProgramLibrary::Load(argv[1]);
  const unsigned first = argc > 3 ? unsigned(std::stoul(argv[3])) : 0;
  const unsigned last = std::min<unsigned>(bank->programs.size(), argc > 4 ? unsigned(std::stoul(argv[4])) : bank->programs.size());
  const std::string mode = argc > 5 ? argv[5] : "wet";
  const bool drums = mode == "drums";
  const std::string prefix = argv[2];
  std::ofstream report(prefix + ".tsv"), snippets(prefix + ".f32", std::ios::binary);
  if (!report || !snippets) return 2;
  report << "program\tid\tname\tdrum\tnote\tvelocity\tpeak\trms\tjump\tjump_frame\tisolated\tisolated_frame\tend_jump\tend_frame\tactive\tsnippet\n";
  auto engine = std::make_unique<ProgramEngine>(bank);
  Controls controls; controls.space = 1; controls.fxBypass = mode == "dry" || mode == "drums";
  const int rate = argc>6 ? std::stoi(argv[6]) : 48000;
  if(rate<32000 || rate>192000)return 2;
  const int length=rate*(mode=="keys"?4:2), hold=mode=="keys"?rate*3:rate*3/2;
  engine->Prepare(rate);
  std::vector<float> l(length), r(length);
  unsigned record = 0;
  for (unsigned p = first; p < last; ++p) {
    const auto &program = bank->programs[p];
    if (drums && !program.drum) continue;
    controls.fx = engine->FactoryEffects(p).slots;
    engine->SetControls(controls); engine->SetProgram(p);
    std::vector<int> notes;
    if (drums || mode=="keys") { for (int n = 0; n < 128; ++n) notes.push_back(n); }
    else if (mode == "chord") notes = {60};
    else if (program.drum) notes = {36, 38, 42, 46, 49, 60, 76};
    else notes = {36, 48, 57, 60, 69, 72, 84};
    for (int note : notes) for (int velocity : mode == "chord" ? std::vector<int>{127} : std::vector<int>{48,100,127}) {
      engine->Panic();
      engine->Queue({0, 0x90, uint8_t(note), uint8_t(velocity)});
      engine->Queue({hold, 0x80, uint8_t(note), 0});
      if(mode=="chord") {
        for(int key:{36,43,48,55,64,67,72,76,79,84,88,91}) {
          engine->Queue({17,0x91,uint8_t(key),127});
          engine->Queue({hold,0x81,uint8_t(key),0});
        }
        engine->Queue({rate/2,0xe1,127,127});
        engine->Queue({rate*3/4,0xe1,0,64});
        engine->Queue({hold+17,0xb1,120,0});
      }
      for (int at = 0; at < length; at += 257)
        engine->Process(l.data() + at, r.data() + at, std::min(257, length - at));
      double peak = 0, energy = 0, jump = 0, isolated = 0, endJump = 0;
      int jumpFrame = 0, isolatedFrame = 0, endFrame = 0, silentRun = 0;
      unsigned active = 0;
      for (int i = 0; i < length; ++i) {
        const double a = l[i], b = r[i];
        if (!std::isfinite(a) || !std::isfinite(b)) {
          std::fprintf(stderr,"non-finite: %s note %d velocity %d at %d\n", program.id.data(), note, velocity, i);
          return 1;
        }
        peak = std::max({peak, std::abs(a), std::abs(b)});
        energy += (a*a+b*b)*.5;
        active += std::max(std::abs(a), std::abs(b)) > 1e-6;
        if (i == 0) continue;
        const double d = std::max(std::abs(a-l[i-1]), std::abs(b-r[i-1]));
        if (d > jump) { jump = d; jumpFrame = i; }
        if (i >= 33 && i + 32 < length && d > .001) {
          double neighborhood = 0;
          for (int j = -32; j <= 32; ++j) if (j < -2 || j > 2)
            neighborhood += std::max(std::abs(l[i+j]-l[i+j-1]), std::abs(r[i+j]-r[i+j-1]));
          const double excess = d - 6 * neighborhood / 60;
          if (excess > isolated) { isolated = excess; isolatedFrame = i; }
        }
        // A single zero PCM sample is a normal zero crossing, especially
        // for drums. Require sustained silence before calling it a cut.
        silentRun = std::abs(a)+std::abs(b)<1e-10 ? silentRun+1 : 0;
        if (silentRun==32 && i>=32) {
          const double cut=std::max(std::abs(l[i-32]),std::abs(r[i-32]));
          if(cut>endJump) {endJump=cut;endFrame=i-31;}
        }
      }
      report << p << '\t' << program.id.data() << '\t' << program.name.data() << '\t' << program.drum << '\t'
             << note << '\t' << velocity << '\t' << peak << '\t' << std::sqrt(energy/length) << '\t'
             << jump << '\t' << jumpFrame << '\t' << isolated << '\t' << isolatedFrame << '\t'
             << endJump << '\t' << endFrame << '\t' << active << '\t' << record++ << '\n';
      // Two 4096-frame windows at 12 kHz, summed channels. Keep short attacks
      // and held pitch separate; percussion/noise is never automatically tuned.
      if (!drums) for (int start : {rate/10, rate}) for (int j = 0; j < 4096; ++j) {
        float value = 0;
        for (int k = 0; k < 4; ++k) value += (l[start+j*rate/12000+k]+r[start+j*rate/12000+k])*.125f;
        snippets.write(reinterpret_cast<const char *>(&value), sizeof(value));
      }
    }
    report.flush();
    if (p % 32 == 0) std::fprintf(stderr, "%u/%u\n", p, last);
  }
  return !report || !snippets;
}
