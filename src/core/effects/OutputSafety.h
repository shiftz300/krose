#pragma once
#include <algorithm>
#include <cmath>

namespace segrand {
// Zero-latency stereo-linked soft knee. Unity below -0.45 dBFS, bounded below
// full scale above it. Only overload changes the signal; quiet audio is exact.
class OutputSafety {
public:
  void Reset() noexcept { mPeak = 0; mReduction = 0; }
  void ClearMeters() noexcept { mPeak = 0; mReduction = 0; }
  void Process(float &left, float &right) noexcept {
    if (!std::isfinite(left) || !std::isfinite(right)) {
      left = right = 0;
      mReduction = 1;
      return;
    }
    const double peak = std::max(std::abs(double(left)), std::abs(double(right)));
    mPeak = std::max(mPeak, float(peak));
    constexpr double knee = .95, ceiling = .999;
    if (peak <= knee) return;
    const double limited = knee + (ceiling - knee) *
        std::tanh((peak - knee) / (ceiling - knee));
    const double gain = limited / peak;
    left = float(left * gain);
    right = float(right * gain);
    mReduction = std::max(mReduction, float(1 - gain));
  }
  void MergeMeters(float peak, float reduction) noexcept {
    mPeak = std::max(mPeak, peak);
    mReduction = std::max(mReduction, reduction);
  }
  float Peak() const noexcept { return mPeak; }
  float Reduction() const noexcept { return mReduction; }
private:
  float mPeak = 0, mReduction = 0;
};
}
