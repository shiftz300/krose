#pragma once
#include "effects/concert_effects.h"
#include "effects/FxMonitor.h"
#include <array>
#include <cstddef>
#include <memory>

namespace segrand {
inline constexpr std::array<const char *, 7> kInsertTypes{
    "AUTO", "OFF", "EQ", "COMPRESSOR", "LIMITER", "DRIVE", "EXCITER"};
inline constexpr std::array<const char *, 6> kSendTypes{
    "AUTO", "OFF", "CHORUS", "STEREO DELAY", "HALL", "PLATE"};

enum FxDetail {
  kEqFreq, kEqGain, kEqQ, kThreshold = 12, kRatio, kAttack, kRelease, kCeiling, kDrive, kBlend,
  kDepth, kLfoRate, kDelayLeft, kDelayRight, kFeedback, kDecay, kHiDamp, kFxDetailCount
};
inline constexpr int kInsertDetailCount = kDepth;
inline constexpr int kSendDetailCount = kFxDetailCount - kDepth;

struct FxValueSpec {
  const char *label, *unit;
  double initial, min, max, step;
};
constexpr std::array<FxValueSpec, kFxDetailCount> kFxValues{{
    {"Freq", " Hz", 80, 20, 20000, 1}, {"Gain", " dB", 6, -18, 18, .5}, {"Q", "", .5, .5, 10, .1},
    {"Freq", " Hz", 630, 20, 20000, 1}, {"Gain", " dB", 1.5, -18, 18, .5}, {"Q", "", 2.1, .5, 10, .1},
    {"Freq", " Hz", 1800, 20, 20000, 1}, {"Gain", " dB", 4, -18, 18, .5}, {"Q", "", .8, .5, 10, .1},
    {"Freq", " Hz", 4500, 20, 20000, 1}, {"Gain", " dB", 3, -18, 18, .5}, {"Q", "", .7, .5, 10, .1},
    {"Threshold", " dB", -21.4, -40, 0, .1}, {"Ratio", ":1", 4, 1, 20, .1},
    {"Attack", " ms", 1, 0, 100, 1}, {"Release", " ms", 75, 1, 500, 1},
    {"Ceiling", " dB", -9.1, -30, 0, .1}, {"Drive", "", 60, 1, 100, 1}, {"Blend", "%", 30, 0, 100, 1},
    {"Depth", "%", 70, 0, 100, 1}, {"LFO Rate", " Hz", .5, .05, 5, .05},
    {"L Delay", " ms", 244, 1, 550, 1}, {"R Delay", " ms", 326, 1, 550, 1},
    {"Feedback", "%", 28, 0, 90, 1}, {"Decay", " s", 1.8, .3, 6, .1},
    {"Hi Damp", "%", 62, 0, 100, 1},
}};

struct FxSlot {
  int type = 0;
  double amount = 50;
  bool enabled = true;
  std::array<double, kFxDetailCount> detail = [] {
    std::array<double, kFxDetailCount> values{};
    for (int i = 0; i < kFxDetailCount; ++i)
      values[i] = kFxValues[i].initial;
    return values;
  }();
};

struct FxSends {
  double hall = 0, chorus = 0;
};

using FxSettings = std::array<FxSlot, 4>;
int ResolveFxType(int type, int slot, bool concert, bool wide) noexcept;
FxSends ResolveFxSends(const FxSettings &settings, double hall, double chorus, double space) noexcept;

class FxRack {
public:
  void Prepare(double rate);
  void Reset() noexcept;
  void SetInserts(const FxSettings &settings, bool concert) noexcept;
  void Insert(double &left, double &right, const double *autoEqInput = nullptr) noexcept;
  void SetReturns(const FxSettings &settings, double space) noexcept;
  // Interleaved stereo, up to 128 frames. Returns contain effect signal only.
  void Returns(const double *input, double *wet, int count) noexcept;
  double ConcertEqMix() noexcept;
  FxMonitor &Monitor() noexcept { return mMonitor; }
  void ClearMeters() noexcept { mPeaks.fill(0); }
  const std::array<float, 2> &Peaks() const noexcept { return mPeaks; }

private:
  FxMonitor mMonitor;
  struct RoomDeleter {
    void operator()(ConcertEffects *p) const noexcept { concert_effects_destroy(p); }
  };
  struct EqBand {
    std::array<double, 5> coefficient{}, target{};
    std::array<std::array<double, 2>, 2> history{};
  };
  struct InsertSlot {
    int type = 1, target = 1;
    double amount = 0, targetAmount = 0, gain = 1;
    double threshold = .085, ceiling = .35, reciprocalRatio = .25, attack = 1, release = 1;
    double drive = 60, blend = .035;
    std::array<double, 2> low{};
    std::array<EqBand, 4> eq{};
    std::array<double, kInsertDetailCount> configured{};
  };
  struct SendSlot {
    std::unique_ptr<ConcertEffects, RoomDeleter> room;
    std::unique_ptr<std::array<float, 2>[]> delay;
    std::size_t delaySize = 0, cursor = 0, valid = 0;
    int type = 1, target = 1;
    double amount = 0, targetAmount = 0;
    double delayLeft = 0, delayRight = 0, targetLeft = 0, targetRight = 0, feedback = .28;
    std::array<double, kSendDetailCount> configured{};
  };
  void ConfigureInsert(InsertSlot &, const FxSlot &) noexcept;
  void ConfigureSend(SendSlot &, const FxSlot &) noexcept;
  void ConfigureRoom(SendSlot &) noexcept;
  void RenderSend(SendSlot &, const double *input, double *wet, int count) noexcept;
  std::array<InsertSlot, 2> mInserts{};
  std::array<float, 2> mPeaks{};
  std::array<SendSlot, 2> mSends{};
  double mRate = 48000, mEq = 1, mEqTarget = 1, mSmoothing = 1, mExciterAlpha = 1;
};
} // namespace segrand
