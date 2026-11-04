#include "voice/NativeModulation.h"
#include "voice/ModulationData.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>
namespace segrand {
namespace {
int S8(uint8_t x) { return x < 128 ? x : int(x) - 256; }
int S16(const uint8_t *p) {
  int x = p[0] + 256 * p[1];
  return x < 32768 ? x : x - 65536;
}
int32_t S32(int64_t x) {
  uint32_t b = uint32_t(x);
  int32_t s;
  std::memcpy(&s, &b, 4);
  return s;
}
int Mod(int a, int x) { return std::clamp(int(int64_t(a) * x * 331 >> 15), -32768, 32767); }
int Scale(int a, int x) { return S32(int64_t(a) * x * 331) >> 15; }
int Velocity(int v) { return (129 * v + 1) >> 2; }
int AdjustCC(int value, unsigned number, const std::array<uint8_t, 128> *cc) {
  if (!cc || (*cc)[number] == 255)
    return value;
  const int delta = int((*cc)[number]) - 64;
  const int amount = delta > 0 ? (delta * 403 >> 8) : (delta * 99 >> 6);
  return amount > 0 ? value + ((99 - value) * amount * 331 >> 15)
                    : value - ((value * -amount * 331) >> 15);
}
} // namespace
void NativeModulation::Controllers(ModulationSources &s, const std::array<uint8_t, 128> &cc,
                                   int poly, int pressure, int bend) noexcept {
  s[16] = Velocity(poly);
  s[17] = Velocity(pressure);
  // MIDI -> native signed channel+FA encoding, then original AMS getter.
  const int value = std::clamp(bend + 8192, 0, 16383);
  const int native = ((value << 2) | ((value >> 7) & 3)) - 32768;
  s[18] = (native + (native > 0)) >> 3;
  constexpr int unipolar[][2] = {{19, 1},  {20, 2},  {23, 4},  {25, 18}, {30, 17},
                                 {31, 19}, {32, 20}, {33, 21}, {34, 64}, {35, 65},
                                 {36, 66}, {37, 67}, {38, 80}, {39, 81}, {40, 82},
                                 {41, 83}, {42, 85}, {43, 86}, {44, 87}, {45, 88}};
  constexpr int bipolar[][2] = {{24, 16}, {26, 17}, {27, 19}, {28, 20}, {29, 21}};
  for (auto &p : unipolar)
    s[p[0]] = cc[p[1]] == 255 ? 0 : Velocity(cc[p[1]]);
  for (auto &p : bipolar) {
    int v = cc[p[1]] == 255 ? 0 : (int(cc[p[1]]) - 64) * 2;
    s[p[0]] = v < 0 ? v * 32 : Velocity(v + (v > 0));
  }
}
void NativeModulation::Start(const uint8_t *program, int oscillator, ModulationSources initial,
                             uint32_t seed, const std::array<uint8_t, 128> *cc) noexcept {
  *this = {};
  mOsc = program + 0x564 + 380 * std::clamp(oscillator, 0, 1);
  sources = initial;
  mRandom = seed ? seed : 1;
  sources[1] = sources[2] = sources[3] = sources[4] = sources[5] = sources[6] = sources[7] = 0;
  for (int i = 1; i >= 0; --i) {
    const auto p = mOsc + 0x30 + 28 * i;
    lfo[i].Start(p, 0, mRandom, sources, i == 0 ? AdjustCC(p[6], 78, cc) : -1);
    sources[6 + i] = lfo[i].Source();
  }
  for (int i = 0; i < 2; ++i)
    Mix(i, true);
  mPitch.Start(program + 0x520, sources);
  sources[3] = mPitch.Level() * 32770 >> 18;
}
void NativeModulation::Mix(unsigned slot, bool initial) noexcept {
  const auto p = mOsc + 0x14c + 24 * slot;
  auto src = [&](unsigned n) { return n < sources.size() ? sources[n] : 0; };
  int value = 0;
  const int kind = p[0] & 7;
  if (kind == 0)
    value = Scale(S8(p[2]), src(p[1])) + Scale(S8(p[4]), src(p[3]));
  else if (kind == 1)
    value = Scale(S8(p[2]) + (S32(99ll * Scale(S8(p[4]), src(p[3]))) >> 12), src(p[1]));
  else if (kind == 2)
    value = Scale(S16(p + 6), src(p[1])) + (S32(S16(p + 8) * 165) >> 2);
  else if (kind == 3) {
    const int target = Scale(99, src(p[1])), old = initial ? target : sources[1 + slot];
    value =
        old +
        (S32(int64_t(
                 modulation_data::kSmoothing[std::min<unsigned>(p[target >= old ? 10 : 11], 99)]) *
             (target - old)) >>
         16);
  } else if (kind == 4) {
    int x = src(p[1]), a = S8(p[12]) * 331;
    if (p[13])
      value = x + (S32(int64_t(4096 - (S32(int64_t(x) * x) >> 12)) * a) >> 16);
    else {
      int v = 2 * std::abs(x) - 4096;
      v += S32(int64_t(4096 - (S32(int64_t(v) * v) >> 12)) * a) >> 16;
      value = ((v + 4096) >> 1) * (x < 0 ? -1 : 1);
    }
  } else if (kind == 5) {
    int x = src(p[1]), steps = std::clamp(int(p[5]), 2, 32),
        i = S32(int64_t(std::abs(x)) * (steps + 1)) >> 12;
    value = (i < steps ? i * (4096 / steps) : 4096) * (x < 0 ? -1 : 1);
  } else if (kind == 6 && p[17]) {
    bool gate = src(p[17]) >= Mod(S8(p[18]), 4096);
    if (initial)
      mGate[slot] = gate;
    else if (p[16] & 1)
      gate = mGate[slot];
    value = gate ? (p[16] & 4 ? Scale(99, src(p[3])) : Mod(S8(p[20]), 4096))
                 : (p[16] & 2 ? Scale(99, src(p[1])) : Mod(S8(p[19]), 4096));
  }
  sources[1 + slot] = std::clamp(value, -24576, 24576);
}
void NativeModulation::Tick(ModulationSources input, uint32_t clock,
                            const std::array<uint8_t, 128> *cc) noexcept {
  if (!mOsc)
    return;
  input[1] = sources[1];
  input[2] = sources[2];
  input[3] = sources[3];
  input[6] = sources[6];
  input[7] = sources[7];
  sources = input;
  mPitch.Advance(sources);
  sources[3] = mPitch.Level() * 32770 >> 18;
  lfo[1].Advance(sources, clock);
  sources[7] = lfo[1].Source();
  lfo[0].Advance(sources, clock, AdjustCC(mOsc[0x31], 76, cc));
  sources[6] = lfo[0].Source();
  lfo[1].Wave(sources, mRandom);
  sources[7] = lfo[1].Source();
  lfo[0].Wave(sources, mRandom);
  for (int i = 0; i < 2; ++i)
    sources[6 + i] = lfo[i].Source();
  mPitch.Refresh(sources);
  sources[3] = mPitch.Level() * 32770 >> 18;
  Mix(0, false);
  Mix(1, false);
}
int NativeModulation::PitchOffset() const noexcept {
  if (!mOsc)
    return 0;
  const auto p = mOsc + 0x68;
  auto src = [&](unsigned n) { return n < sources.size() ? sources[n] : 0; };
  int eg = NativeLFO::Depth(S8(p[21]));
  if (S8(p[5]))
    eg += S32(int64_t(src(p[4])) * 16 * NativeLFO::Depth(S8(p[5]))) >> 16;
  int pitch = S32(int64_t(eg) * mPitch.Level()) >> 15;
  if (S8(p[1]))
    pitch += S32(int64_t(src(p[0])) * 16 * NativeLFO::Depth(S8(p[1]))) >> 16;
  for (int i = 0; i < 2; ++i) {
    const int variable =
        S32(int64_t(src(p[8 + 4 * i])) * 16 * NativeLFO::Depth(S8(p[9 + 4 * i]))) >> 16;
    const int base = NativeLFO::Depth(S8(p[22 + i])) * int(lfo[i].Fade()) >> 16;
    pitch += S32(int64_t(variable + base) * lfo[i].Value()) >> 14;
  }
  return pitch;
}
} // namespace segrand
