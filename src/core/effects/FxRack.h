#pragma once
#include "effects/concert_effects.h"
#include "effects/FxMonitor.h"
#include <array>
#include <cstddef>
#include <memory>

namespace segrand {
inline constexpr std::array<const char *, 11> kInsertTypes{
    "AUTO", "OFF", "EQ", "COMPRESSOR", "LIMITER", "DRIVE", "EXCITER",
    "GRAPHIC 7 EQ", "PHASER", "TREMOLO", "AUTO PAN"};
inline constexpr std::array<const char *, 15> kSendTypes{
    "AUTO", "OFF", "CHORUS", "STEREO DELAY", "HALL", "PLATE", "EQ",
    "COMPRESSOR", "LIMITER", "DRIVE", "EXCITER", "GRAPHIC 7 EQ", "PHASER", "TREMOLO", "AUTO PAN"};
// Shared algorithms in either native IFX/MFX position. Existing enum values stay fixed.
int FxAlgorithm(int type, int slot) noexcept;

enum FxDetail {
  kEqFreq, kEqGain, kEqQ, kThreshold = 12, kRatio, kAttack, kRelease, kCeiling, kDrive, kBlend,
  kDepth, kLfoRate, kDelayLeft, kDelayRight, kFeedback, kDecay, kHiDamp,
  kGraphicGain, kGraphicType = kGraphicGain + 7, kFxTrim, kFxDetailCount
};
inline constexpr int kInsertDetailCount = kDepth;
inline constexpr int kSendDetailCount = kGraphicGain - kDepth; // Frozen legacy parameter layout.

struct FxValueSpec {
  const char *label, *unit;
  double initial, min, max, step;
};
constexpr std::array<FxValueSpec, kFxDetailCount> kFxValues{{
    {"Freq", " Hz", 80, 20, 20000, 1}, {"Gain", " dB", 6, -18, 24, .5}, {"Q", "", .5, .5, 16, .1},
    {"Freq", " Hz", 630, 20, 20000, 1}, {"Gain", " dB", 1.5, -18, 24, .5}, {"Q", "", 2.1, .5, 16, .1},
    {"Freq", " Hz", 1800, 20, 20000, 1}, {"Gain", " dB", 4, -18, 24, .5}, {"Q", "", .8, .5, 16, .1},
    {"Freq", " Hz", 4500, 20, 20000, 1}, {"Gain", " dB", 3, -18, 24, .5}, {"Q", "", .7, .5, 16, .1},
    {"Threshold", " dB", -21.4, -40, 0, .1}, {"Ratio", ":1", 4, 1, 40, .1},
    {"Attack", " ms", 1, 0, 250, 1}, {"Release", " ms", 75, 1, 5000, 1},
    {"Ceiling", " dB", -9.1, -30, 0, .1}, {"Drive", "", 60, 1, 200, 1}, {"Blend", "%", 30, 0, 100, 1},
    {"Depth", "%", 70, 0, 100, 1}, {"LFO Rate", " Hz", .5, .05, 5, .05},
    {"L Delay", " ms", 244, 1, 2000, 1}, {"R Delay", " ms", 326, 1, 2000, 1},
    {"Feedback", "%", 28, 0, 95, 1}, {"Decay", " s", 1.8, .3, 20, .1},
    {"Hi Damp", "%", 62, 0, 100, 1},
    {"Band 1", " dB", 0, -18, 18, .5}, {"Band 2", " dB", 0, -18, 18, .5},
    {"Band 3", " dB", 0, -18, 18, .5}, {"Band 4", " dB", 0, -18, 18, .5},
    {"Band 5", " dB", 0, -18, 18, .5}, {"Band 6", " dB", 0, -18, 18, .5},
    {"Band 7", " dB", 0, -18, 18, .5},
    {"Layout", "", 0, 0, 11, 1}, {"Trim", "%", 100, 0, 100, 1},
}};
// Original v1.2.4 display table at 0x37cb30, all twelve native layouts.
inline constexpr std::array<std::array<double,7>,12> kGraphicFrequencies{{
    {{80,220,500,1000,2500,6300,16000}}, {{120,320,630,1200,3200,8000,18000}},
    {{63,180,550,1200,3200,7500,18000}}, {{80,120,420,1500,3000,6500,10000}},
    {{160,320,750,1500,3000,6000,12000}}, {{120,250,500,1000,2000,4000,8000}},
    {{80,120,160,250,320,500,630}}, {{63,120,250,500,1000,2000,4000}},
    {{800,1000,1200,1600,2500,3200,4000}}, {{320,500,800,1200,2000,3200,5000}},
    {{5000,6300,8000,10000,12500,16000,18000}}, {{1000,2000,4000,6300,8000,12500,16000}},
}};
inline constexpr std::array<const char *,12> kGraphicLayouts{{
    "Wide 1", "Wide 2", "Wide 3", "Half Wide 1", "Half Wide 2", "Half Wide 3",
    "Low", "Wide Low", "Mid", "Wide Mid", "High", "Wide High"
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
    std::array<EqBand, 7> eq{};
    std::array<double, kFxDetailCount> configured{};
    std::array<std::array<double, 6>, 2> allpass{};
    double phase = 0, rate = .5, depth = .7, trim = 1;
  };
  struct SendSlot {
    std::unique_ptr<ConcertEffects, RoomDeleter> room;
    std::unique_ptr<std::array<float, 2>[]> delay;
    std::size_t delaySize = 0, cursor = 0, valid = 0;
    int type = 1, target = 1;
    double amount = 0, targetAmount = 0;
    double delayLeft = 0, delayRight = 0, targetLeft = 0, targetRight = 0, feedback = .28;
    std::array<double, kSendDetailCount> configured{};
    InsertSlot processor;
  };
  void ConfigureInsert(InsertSlot &, const FxSlot &) noexcept;
  void ProcessInsert(InsertSlot &, double &, double &) noexcept;
  void ConfigureSend(SendSlot &, const FxSlot &) noexcept;
  void ConfigureRoom(SendSlot &) noexcept;
  void RenderSend(SendSlot &, const double *input, double *wet, int count) noexcept;
  std::array<InsertSlot, 2> mInserts{};
  std::array<float, 2> mPeaks{};
  std::array<SendSlot, 2> mSends{};
  double mRate = 48000, mEq = 1, mEqTarget = 1, mSmoothing = 1, mExciterAlpha = 1;
};
} // namespace segrand
