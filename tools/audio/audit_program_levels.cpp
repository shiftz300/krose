#include "engine/ProgramEngine.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <vector>

// Repeatable, offline activity-gated stereo RMS measurement. This is not a
// LUFS meter: short percussion tails must not be averaged against long silence.
// Use --raw when regenerating compensation, otherwise report audible output.
int main(int argc, char **argv) {
  if (argc < 2) { std::fprintf(stderr,"usage: audit-program-levels Factory.samples [--raw]\n"); return 2; }
  using namespace segrand;
  auto bank = ProgramLibrary::Load(argv[1]);
  auto engine = std::make_unique<ProgramEngine>(bank);
  Controls controls;
  controls.fxBypass = true;
  controls.space = 0;
  controls.balancePrograms = !(argc > 2 && std::strcmp(argv[2],"--raw") == 0);
  engine->SetControls(controls);
  std::puts("id\tname\tdrum\tpeak_db\tactive_rms_db\tlate_rms_db\tmin_rms_db\tvalid_notes");
  for (unsigned p=0; p<bank->programs.size(); ++p) {
    const auto &program = bank->programs[p];
    controls.fxBypass = false;
    controls.space = 1;
    controls.fx = engine->FactoryEffects(p).slots;
    engine->SetControls(controls);
    double peak = 0, lateSum = 0;
    std::vector<double> levels;
    unsigned lateCount = 0;
    for (int note : program.drum ? std::array<int,4>{36,38,42,49} : std::array<int,4>{45,57,69,81}) {
      engine->SetProgram(p); engine->Panic();
      engine->Queue({0,0x90,uint8_t(note),100});
      std::vector<double> windows;
      constexpr int window = 2400, frames = 48000*3;
      double sum = 0, notePeak = 0;
      std::array<float,256> l{},r{};
      for (int at=0; at<frames; at+=256) {
        const int n=std::min(256,frames-at);
        engine->Process(l.data(),r.data(),n);
        for (int i=0;i<n;++i) {
          if (!std::isfinite(l[i]) || !std::isfinite(r[i])) return 1;
          notePeak=std::max({notePeak,std::abs(double(l[i])),std::abs(double(r[i]))});
          const double v=(double(l[i])*l[i]+double(r[i])*r[i])*.5;
          sum+=v;
          if (at+i>=frames-48000) { lateSum+=v; ++lateCount; }
          if ((at+i+1)%window==0) { windows.push_back(sum/window); sum=0; }
        }
      }
      peak=std::max(peak,notePeak);
      const auto maximum=*std::max_element(windows.begin(),windows.end());
      if (maximum < 1e-15) continue; // Unmapped / effectively silent note; flagged below.
      double activity=0; unsigned count=0;
      for (double energy:windows) if (energy>=maximum*.01) { activity+=energy; ++count; }
      levels.push_back(10*std::log10(activity/std::max(1u,count)));
    }
    std::sort(levels.begin(),levels.end());
    const double rms=levels.empty() ? -400 : levels[levels.size()/2];
    std::printf("%s\t%s\t%d\t%.3f\t%.3f\t%.3f\t%.3f\t%zu\n",program.id.data(),program.name.data(),program.drum,
       20*std::log10(std::max(1e-20,peak)),rms,10*std::log10(std::max(1e-40,lateSum/std::max(1u,lateCount))),
       levels.empty() ? -400 : levels.front(),levels.size());
    std::fflush(stdout);
  }
}
