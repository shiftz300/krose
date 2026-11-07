#pragma once
#include "effects/FxMonitor.h"
#include <algorithm>
#include <array>
#include <cmath>

namespace krose::ui {
class FxAnalysis {
public:
  static constexpr unsigned kWindow = 1024, kBands = 32, kScope = 64;
  FxAnalysis() {
    for (unsigned i = 0; i < kWindow; ++i)
      mWindow[i] = .5 - .5 * std::cos(6.283185307179586 * i / (kWindow - 1));
  }
  void Feed(const segrand::FxVisualSample *samples, unsigned count) noexcept {
    for (unsigned i = 0; i < count; ++i) {
      mSamples[mPosition] = samples[i];
      mPosition = (mPosition + 1) % kWindow;
    }
  }
  bool Analyze(double rate, double seconds) noexcept {
    const auto previous = bands;
    const float oldPeak = peak, oldReduction = reduction;
    peak = 0; reduction = 0;
    double energy = 0, inputEnergy = 0;
    for (unsigned i = 0; i < kScope; ++i) {
      const auto &s = mSamples[(mPosition + i * kWindow / kScope) % kWindow];
      left[i] = s.left; right[i] = s.right; input[i] = s.input;
    }
    for (const auto &s : mSamples) {
      peak = std::max({peak, std::abs(s.left), std::abs(s.right)});
      reduction = std::max(reduction, s.reduction);
      energy += double(s.left) * s.left + double(s.right) * s.right;
      inputEnergy += double(s.input) * s.input;
    }
    std::move(history.begin() + 1, history.end(), history.begin());
    history.back() = float(std::sqrt(energy / (2 * kWindow)));
    const double release = std::exp(-seconds / .16);
    for (unsigned band = 0; band < kBands; ++band) {
      const double frequency = 30 * std::pow(std::min(11000., rate * .45) / 30, double(band) / (kBands - 1));
      const double coefficient = 2 * std::cos(6.283185307179586 * frequency / rate);
      double a = 0, b = 0, ia = 0, ib = 0;
      for (unsigned i = 0; energy + inputEnergy > 1e-20 && i < kWindow; ++i) {
        const auto &s = mSamples[(mPosition + i) % kWindow];
        const double window = mWindow[i];
        const double v = (s.left + s.right) * .5 * window + coefficient * a - b;
        b = a; a = v;
        const double iv = s.input * window + coefficient * ia - ib;
        ib = ia; ia = iv;
      }
      const float magnitude = float(std::sqrt(std::max(0., a*a + b*b - coefficient*a*b)) * 4 / kWindow);
      const float inMagnitude = float(std::sqrt(std::max(0., ia*ia + ib*ib - coefficient*ia*ib)) * 4 / kWindow);
      bands[band] = std::max(magnitude, float(bands[band] * release));
      inputBands[band] = std::max(inMagnitude, float(inputBands[band] * release));
      if (bands[band] < 1e-5) bands[band] = 0;
      if (inputBands[band] < 1e-5) inputBands[band] = 0;
    }
    return previous != bands || oldPeak != peak || oldReduction != reduction ||
        std::any_of(history.begin(), history.end(), [](float level) { return level > 1e-5f; });
  }
  std::array<float, kBands> bands{}, inputBands{};
  std::array<float, kScope> left{}, right{}, input{};
  std::array<float, 24> history{};
  float peak = 0, reduction = 0;
private:
  std::array<segrand::FxVisualSample, kWindow> mSamples{};
  std::array<double, kWindow> mWindow{};
  unsigned mPosition = 0;
};
}
