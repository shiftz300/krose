#include "NativePanel.h"
#include "../../KrosePlugin.h"
#include "PanelDrawing.h"
#include <complex>

namespace krose::ui {
using namespace detail;
bool NativePanel::UpdateFxVisuals() {
  const auto now = std::chrono::steady_clock::now();
  const double dt = std::chrono::duration<double>(now - mFxTick).count();
  if (dt < 1. / 30) return false;
  mFxTick = now;
  auto *plugin = static_cast<KrosePlugin *>(GetDelegate());
  std::array<segrand::FxVisualSample, segrand::FxMonitor::kCapacity> samples;
  bool changed = false;
  for (unsigned slot = 0; slot < mFxAnalysis.size(); ++slot) {
    const unsigned count = plugin->ReadFxVisual(slot, samples.data(), unsigned(samples.size()));
    if (count) mFxAnalysis[slot].Feed(samples.data(), count);
    else {
      samples.fill({});
      mFxAnalysis[slot].Feed(samples.data(), FxAnalysis::kWindow);
    }
    changed |= mFxAnalysis[slot].Analyze(plugin->VisualRate(), std::min(.2,dt));
    const double peak = mFxAnalysis[slot].peak;
    mMeterLevels[slot] = std::max(peak, mMeterLevels[slot] * std::exp(-std::min(.2,dt) / .25));
    if (mMeterLevels[slot] < .0001) mMeterLevels[slot] = 0;
  }
  const float old = mOutputReduction;
  mOutputLevel = plugin->TakeOutputPeak();
  mOutputReduction = std::max(plugin->TakeOutputReduction(), float(mOutputReduction * std::exp(-std::min(.2,dt)/.35)));
  const double seconds = std::chrono::duration<double>(now.time_since_epoch()).count();
  if (mOutputLevel > .95f) mOverloadUntil = seconds + 1.5;
  const bool safetyShown = seconds < mOverloadUntil;
  if (safetyShown != mSafetyShown) SetDirty(false);
  mSafetyShown = safetyShown;
  if (mOutputReduction < .0001f) mOutputReduction = 0;
  changed |= old != mOutputReduction;
  return changed;
}
void NativePanel::DrawFxSignal(IGraphics &g, const IRECT &r, int slot, int type) {
  const auto &data = mFxAnalysis[slot];
  const int algorithm = segrand::FxAlgorithm(type,slot);
  const IColor grid(50,159,180,169), line(235,180,231,217), quiet(105,174,191,183);
  g.FillRect(IColor(255,32,51,45),r);
  g.PathClipRegion(r);
  for (int i=1;i<4;++i) {
    g.DrawLine(grid,r.L+i*r.W()/4,r.T,r.L+i*r.W()/4,r.B,nullptr,.5);
    g.DrawLine(grid,r.L,r.T+i*r.H()/4,r.R,r.T+i*r.H()/4,nullptr,.5);
  }
  auto bandY = [&](float value) {
    const double db = 20 * std::log10(std::max(1e-5f,value));
    return float(r.B - 3 - std::clamp((db + 72) / 72,0.,1.)*(r.H()-6));
  };
  auto spectrum = [&](const auto &bands, const IColor &color) {
    for (unsigned i=1;i<bands.size();++i)
      g.DrawLine(color,r.L+3+(i-1)*(r.W()-6)/(bands.size()-1),bandY(bands[i-1]),
          r.L+3+i*(r.W()-6)/(bands.size()-1),bandY(bands[i]),nullptr,.7);
  };
  if (algorithm == 2 || algorithm == 7) {
    spectrum(data.bands,quiet);
    if (slot == 0 && Value(kFxType1) == 0) {
      // AUTO uses the recovered Concert EQ, rather than the manual four bands.
      // Plot the measured transfer only where the input has useful energy.
      for (unsigned i = 1; i < data.bands.size(); ++i) {
        if (data.inputBands[i-1] < 1e-4f || data.inputBands[i] < 1e-4f) continue;
        const auto y = [&](unsigned j) {
          const double db = 20 * std::log10(std::max(1e-6f,data.bands[j]) / data.inputBands[j]);
          return float(r.MH() - std::clamp(db,-24.,24.) * r.H()/48);
        };
        g.DrawLine(line,r.L+(i-1)*r.W()/31,y(i-1),r.L+i*r.W()/31,y(i),nullptr,1);
      }
      g.PathClipRegion();
      return;
    }
    // Manual response uses the same peaking biquads and wet mix as the DSP.
    const double rate = static_cast<KrosePlugin *>(GetDelegate())->AudioRate();
    auto response = [&](double f) {
      std::complex<double> transfer(1,0);
      const auto z = std::polar(1.,-6.283185307179586*f/std::max(32000.,rate));
      const bool graphic = algorithm == 7;
      const int layout = std::clamp(int(Value(FxDetailParameter(slot,segrand::kGraphicType))),0,11);
      for (int b=0;b<(graphic?7:4);++b) {
        const double hz=std::min(graphic ? segrand::kGraphicFrequencies[layout][b] : Value(FxDetailParameter(slot,b*3)),rate*.45);
        const double gain=std::pow(10.,Value(FxDetailParameter(slot,graphic?segrand::kGraphicGain+b:b*3+1))/40);
        const double q=graphic ? 1.4 : Value(FxDetailParameter(slot,b*3+2));
        const double w=6.283185307179586*hz/rate, a=std::sin(w)/(2*q), mid=-2*std::cos(w);
        transfer *= ((1+a*gain)+mid*z+(1-a*gain)*z*z) /
                    ((1+a/gain)+mid*z+(1-a/gain)*z*z);
      }
      transfer *= Value(FxDetailParameter(slot,segrand::kFxTrim))/100;
      const double wet = slot<2 ? Value(kFxAmount1+slot)/100 : 1;
      return 20*std::log10(std::max(1e-6,std::abs(1.+wet*(transfer-1.))));
    };
    for (int i=1;i<48;++i) {
      const auto y = [&](int j) { return float(r.MH()-std::clamp(response(30*std::pow(500.,j/47.)),-24.,24.)*r.H()/48); };
      g.DrawLine(line,r.L+(i-1)*r.W()/47,y(i-1),r.L+i*r.W()/47,y(i),nullptr,1);
    }
  } else if (algorithm <= 10) {
    spectrum(data.inputBands,quiet);
    spectrum(data.bands,line);
    // Live input/output transfer points expose drive and exciter saturation.
    for (unsigned i=0;i<data.input.size();++i) {
      const float x=r.MW()+std::clamp(data.input[i]*2,-1.f,1.f)*(r.W()/2-3);
      const float y=r.MH()-std::clamp((data.left[i]+data.right[i]),-1.f,1.f)*(r.H()/2-3);
      g.FillCircle(IColor(105,226,204,164),x,y,.65f);
    }
  } else if (type == 2) {
    // Stereo L/R vectorscope, driven only by the chorus return.
    for (unsigned i=1;i<data.left.size();++i) {
      const auto x=[&](unsigned j){return r.MW()+std::clamp(data.left[j]*4,-1.f,1.f)*(r.W()/2-3);};
      const auto y=[&](unsigned j){return r.MH()-std::clamp(data.right[j]*4,-1.f,1.f)*(r.H()/2-3);};
      g.DrawLine(line,x(i-1),y(i-1),x(i),y(i),nullptr,.65);
    }
  } else if (type == 3) {
    for (unsigned i=0;i<data.history.size();++i) {
      const float h=std::clamp(data.history[i]*5,0.f,1.f)*(r.H()-8);
      g.FillRect(IColor(180,199,181,155),R(r.L+3+i*2,r.B-4-h,1.25f,h));
    }
    spectrum(data.bands,quiet);
  } else {
    // CT-like depth slices. Each contour is the actual return spectrum;
    // depth and brightness follow successive RMS measurements, including tails.
    for (int slice=7;slice>=0;--slice) {
      const float depth=slice/7.f;
      const float energy=std::clamp(data.history[23-slice*2]*6,0.f,1.f);
      const IColor color(int(35+170*energy),type==5?222:184,type==5?177:171,235);
      for (unsigned i=1;i<data.bands.size();++i) {
        const auto point=[&](unsigned j) {
          const double angle=6.283185307179586*j/(data.bands.size()-1);
          const double amplitude=.55+.45*std::clamp((20.*std::log10(double(std::max(1e-5f,data.bands[j])))+72)/72,0.,1.);
          return std::pair<float,float>{float(r.MW()+(r.W()*.34)*amplitude*std::cos(angle)+depth*5-2.5),
            float(r.MH()+(r.H()*.17)*amplitude*std::sin(angle)-depth*17+8)};
        };
        const auto a=point(i-1),b=point(i);
        g.DrawLine(color,a.first,a.second,b.first,b.second,nullptr,.7);
      }
    }
  }
  g.PathClipRegion();
}
}
