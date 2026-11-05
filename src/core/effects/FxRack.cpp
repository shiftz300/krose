#include "effects/FxRack.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace segrand {
namespace {
constexpr double kPi = 3.141592653589793;
double Amount(const FxSlot &slot) noexcept {
  return std::isfinite(slot.amount) ? std::clamp(slot.amount / 100, 0., 1.) : .5;
}
double Detail(const FxSlot &slot, int id) noexcept {
  const auto &spec = kFxValues[id];
  const auto value = slot.detail[id];
  return std::isfinite(value) ? std::clamp(value, spec.min, spec.max) : spec.initial;
}
double Gain(double db) noexcept { return std::pow(10, db / 20); }
double Smooth(double rate, double ms) noexcept {
  return ms <= 0 ? 1 : 1 - std::exp(-1000 / (rate * ms));
}
} // namespace

int ResolveFxType(int type, int slot, bool concert, bool wide) noexcept {
  if (type != 0)
    return type;
  const int defaults[] = {concert ? 2 : 1, 1, wide ? 2 : 1, 4};
  return defaults[slot];
}

FxSends ResolveFxSends(const FxSettings &settings, double hall, double chorus, double space) noexcept {
  // AUTO uses the legacy tone's wet levels. Explicit MFX run in the two independent returns.
  const auto factor = [&](int slot) {
    const auto &s = settings[slot];
    return s.enabled && s.type == 0 ? Amount(s) * 2 : 0;
  };
  return {std::min(.5, hall * space * factor(3)), std::min(.5, chorus * factor(2))};
}

void FxRack::Prepare(double rate) {
  mRate = rate;
  mSmoothing = Smooth(rate, 7);
  mExciterAlpha = 1 - std::exp(-2 * kPi * 2400 / rate);
  for (auto &insert : mInserts)
    insert.configured.fill(std::numeric_limits<double>::quiet_NaN());
  double identity[40]{};
  for (int i = 0; i < 8; ++i)
    identity[i * 5] = 1;
  for (auto &slot : mSends) {
    slot.room.reset(concert_effects_create(rate, identity, 1, 1.8, 0, 0, 0));
    if (!slot.room)
      throw std::runtime_error("Could not prepare FX return");
    slot.delaySize = size_t(std::ceil(rate * .55)) + 2;
    // valid prevents reads of unwritten cells. Keep unused delay pages untouched.
    slot.delay.reset(new std::array<float, 2>[slot.delaySize]);
    slot.configured.fill(std::numeric_limits<double>::quiet_NaN());
  }
  Reset();
}

void FxRack::Reset() noexcept {
  for (auto &slot : mInserts) {
    slot.type = slot.target;
    slot.amount = slot.targetAmount;
    slot.gain = 1;
    slot.low = {};
    for (auto &band : slot.eq) {
      band.coefficient = band.target;
      band.history = {};
    }
  }
  for (auto &slot : mSends) {
    slot.type = slot.target;
    slot.amount = slot.targetAmount;
    slot.cursor = slot.valid = 0;
    slot.delayLeft = slot.targetLeft;
    slot.delayRight = slot.targetRight;
    ConfigureRoom(slot);
    concert_effects_reset(slot.room.get());
  }
  mEq = mEqTarget;
}

void FxRack::ConfigureInsert(InsertSlot &slot, const FxSlot &setting) noexcept {
  std::array<double, kInsertDetailCount> detail;
  for (int i = 0; i < kInsertDetailCount; ++i)
    detail[i] = Detail(setting, i);
  if (detail == slot.configured)
    return;
  slot.configured = detail;
  for (int i = 0; i < 4; ++i) {
    const double f = std::min(detail[3 * i], mRate * .45);
    const double a = std::sqrt(Gain(detail[3 * i + 1]));
    const double w = 2 * kPi * f / mRate;
    const double alpha = std::sin(w) / (2 * detail[3 * i + 2]);
    const double mid = -2 * std::cos(w), norm = 1 + alpha / a;
    slot.eq[i].target = {(1 + alpha * a) / norm, mid / norm, (1 - alpha * a) / norm,
                         -mid / norm, -(1 - alpha / a) / norm};
  }
  slot.threshold = Gain(detail[kThreshold]);
  slot.ceiling = Gain(detail[kCeiling]);
  slot.reciprocalRatio = 1 / detail[kRatio];
  slot.attack = Smooth(mRate, detail[kAttack]);
  slot.release = Smooth(mRate, detail[kRelease]);
  slot.drive = detail[kDrive];
  slot.blend = .035 * (detail[kBlend] / 30);
}

void FxRack::SetInserts(const FxSettings &settings, bool concert) noexcept {
  mEqTarget = concert && settings[0].enabled && settings[0].type == 0 ? Amount(settings[0]) * 2 : 0;
  for (size_t i = 0; i < mInserts.size(); ++i) {
    const auto &setting = settings[i];
    auto &slot = mInserts[i];
    const int type = setting.type;
    slot.target = setting.enabled && type >= 2 && type < int(kInsertTypes.size()) ? type : 1;
    slot.targetAmount = slot.target == 1 ? 0 : Amount(setting);
    if (slot.target != 1)
      ConfigureInsert(slot, setting);
  }
}

double FxRack::ConcertEqMix() noexcept {
  mEq += mSmoothing * (mEqTarget - mEq);
  return mEq;
}

void FxRack::Insert(double &left, double &right) noexcept {
  for (auto &slot : mInserts) {
    if (slot.type == 1 && slot.target == 1)
      continue;
    const double target = slot.type == slot.target ? slot.targetAmount : 0;
    slot.amount += mSmoothing * (target - slot.amount);
    if (slot.amount < 1e-5 && slot.type != slot.target) {
      slot.type = slot.target;
      slot.gain = 1;
      slot.low = {};
      for (auto &band : slot.eq) {
        band.coefficient = band.target;
        band.history = {};
      }
    }
    if (slot.amount < 1e-5)
      continue;
    if (slot.type == 2) {
      std::array<double, 2> signal{left, right};
      for (auto &band : slot.eq) {
        auto &b = band.coefficient;
        for (size_t i = 0; i < b.size(); ++i)
          b[i] += mSmoothing * (band.target[i] - b[i]);
        for (size_t ch = 0; ch < 2; ++ch) {
          auto &z = band.history[ch];
          const double in = signal[ch], out = b[0] * in + z[0];
          z[0] = b[1] * in + b[3] * out + z[1];
          z[1] = b[2] * in + b[4] * out;
          signal[ch] = out;
        }
      }
      left += slot.amount * (signal[0] - left);
      right += slot.amount * (signal[1] - right);
    } else if (slot.type == 3 || slot.type == 4) {
      const bool compressor = slot.type == 3;
      const double peak = std::max(std::abs(left), std::abs(right));
      const double threshold = compressor ? slot.threshold : slot.ceiling;
      const double ratio = threshold / std::max(peak, threshold);
      const double wanted = compressor ? slot.reciprocalRatio + (1 - slot.reciprocalRatio) * ratio : ratio;
      const double attack = compressor ? slot.attack : 1;
      slot.gain += (wanted < slot.gain ? attack : slot.release) * (wanted - slot.gain);
      const double gain = 1 + slot.amount * ((compressor ? 1.6 : 1) * slot.gain - 1);
      left *= gain;
      right *= gain;
    } else if (slot.type == 5) {
      left += slot.amount * (std::tanh(slot.drive * left) / 27 - left);
      right += slot.amount * (std::tanh(slot.drive * right) / 27 - right);
    } else if (slot.type == 6) {
      slot.low[0] += mExciterAlpha * (left - slot.low[0]);
      slot.low[1] += mExciterAlpha * (right - slot.low[1]);
      left += slot.amount * slot.blend * std::tanh(30 * (left - slot.low[0]));
      right += slot.amount * slot.blend * std::tanh(30 * (right - slot.low[1]));
    }
  }
}

void FxRack::ConfigureSend(SendSlot &slot, const FxSlot &setting) noexcept {
  std::array<double, kSendDetailCount> detail;
  for (int i = 0; i < kSendDetailCount; ++i)
    detail[i] = Detail(setting, kDepth + i);
  if (detail == slot.configured)
    return;
  slot.configured = detail;
  slot.targetLeft = mRate * Detail(setting, kDelayLeft) / 1000;
  slot.targetRight = mRate * Detail(setting, kDelayRight) / 1000;
  slot.feedback = Detail(setting, kFeedback) / 100;
  if (slot.type == slot.target)
    ConfigureRoom(slot);
}

void FxRack::ConfigureRoom(SendSlot &slot) noexcept {
  const auto value = [&](int id) {
    const double cached = slot.configured[id - kDepth];
    return std::isfinite(cached) ? cached : kFxValues[id].initial;
  };
  const bool reverb = slot.type == 4 || slot.type == 5;
  concert_effects_set_wet(slot.room.get(), reverb ? .5 : 0, slot.type == 2 ? .5 : 0);
  if (reverb)
    concert_effects_set_room(slot.room.get(), mRate, value(kDecay), value(kHiDamp) / 100,
                             slot.type == 5);
  if (slot.type == 2)
    concert_effects_set_chorus(slot.room.get(), mRate, value(kDepth) / 100, value(kLfoRate));
}

void FxRack::SetReturns(const FxSettings &settings, double space) noexcept {
  for (size_t i = 0; i < mSends.size(); ++i) {
    const auto &setting = settings[i + 2];
    auto &slot = mSends[i];
    const int type = setting.type;
    slot.target = setting.enabled && type >= 2 && type < int(kSendTypes.size()) ? type : 1;
    const double level = std::clamp(Amount(setting) * space, 0., 1.);
    slot.targetAmount = slot.target == 1 ? 0 : level * (slot.target == 2 ? .64 : slot.target == 3 ? .5 : .9);
    if (slot.target != 1)
      ConfigureSend(slot, setting);
  }
}

void FxRack::RenderSend(SendSlot &slot, const double *input, double *wet, int count) noexcept {
  if (slot.amount < 1e-5 && slot.type != slot.target) {
    slot.type = slot.target;
    slot.cursor = slot.valid = 0;
    slot.delayLeft = slot.targetLeft;
    slot.delayRight = slot.targetRight;
    if (slot.type == 2 || slot.type >= 4) {
      ConfigureRoom(slot);
      concert_effects_reset(slot.room.get());
    }
  }
  const double target = slot.type == slot.target ? slot.targetAmount : 0;
  if (slot.type == 1 || (target == 0 && slot.amount < 1e-5))
    return;

  if (slot.type == 3) {
    const auto size = slot.delaySize;
    const auto read = [&](double delay, size_t channel) {
      const auto frames = size_t(delay);
      const double frac = delay - frames;
      const auto pos = (slot.cursor + size - frames) % size;
      const double a = slot.valid >= frames ? slot.delay[pos][channel] : 0;
      const double b = slot.valid > frames ? slot.delay[(pos + size - 1) % size][channel] : 0;
      return a + (b - a) * frac;
    };
    for (int n = 0; n < count; ++n) {
      slot.amount += mSmoothing * (target - slot.amount);
      slot.delayLeft += mSmoothing * (slot.targetLeft - slot.delayLeft);
      slot.delayRight += mSmoothing * (slot.targetRight - slot.delayRight);
      const double l = read(slot.delayLeft, 0), r = read(slot.delayRight, 1);
      slot.delay[slot.cursor] = {float(input[n * 2] + slot.feedback * r),
                                 float(input[n * 2 + 1] + slot.feedback * l)};
      wet[n * 2] += l * slot.amount;
      wet[n * 2 + 1] += r * slot.amount;
      slot.cursor = (slot.cursor + 1) % size;
      if (slot.valid < size)
        ++slot.valid;
    }
    return;
  }
  std::array<float, 256> returned;
  concert_effects_process_equalized(slot.room.get(), input, returned.data(), count);
  for (int n = 0; n < count; ++n) {
    slot.amount += mSmoothing * (target - slot.amount);
    for (int ch = 0; ch < 2; ++ch) {
      const int i = n * 2 + ch;
      wet[i] += (returned[i] - float(input[i])) * slot.amount;
    }
  }
}

void FxRack::Returns(const double *input, double *wet, int count) noexcept {
  assert(count >= 0 && count <= 128);
  std::fill(wet, wet + count * 2, 0.);
  for (auto &slot : mSends)
    RenderSend(slot, input, wet, count);
}
} // namespace segrand
