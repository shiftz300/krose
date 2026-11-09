#include "voice/NativeLFO.h"
#include "voice/ModulationData.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>
namespace segrand {
namespace {
using namespace modulation_data;
int S8(uint8_t x) { return x < 128 ? x : int(x) - 256; }
int S16(uint16_t x) { return x < 32768 ? x : int(x) - 65536; }
int32_t S32(int64_t x) {
  uint32_t b = uint32_t(x);
  int32_t s;
  std::memcpy(&s, &b, 4);
  return s;
}
int Draw(uint32_t &seed) {
  const uint32_t old = seed;
  seed *= 625;
  return S32(uint64_t(old) * 49920) >> 16;
}
int GetSource(const ModulationSources &s, unsigned n) { return n < s.size() ? s[n] : 0; }
int Mod(int a, int x) { return std::clamp(int((int64_t(a) * x * 331) >> 15), -32768, 32767); }
int Interpolate(int a, int b, int f) {
  return a < b ? a + ((b - a) * f >> 8) : b + ((a - b) * (255 - f) >> 8);
}
unsigned Factor(const uint8_t *p, unsigned offset, const ModulationSources &s, int secondary = -1) {
  int amount = S8(p[offset + 1]);
  const int delta = secondary < 0 ? 0 : S8(p[secondary + 1]) * GetSource(s, p[secondary]) >> 12;
  if (!amount && !delta)
    return 256;
  const int product = Mod(amount + delta, GetSource(s, p[offset]));
  const int index = std::clamp(product * 3 >> 7, -128, 255) + 128;
  return index <= 255 ? kFactor[index] : unsigned(kFactor[index - 128]) << 8;
}
} // namespace
int NativeLFO::Depth(int value) noexcept {
  const int a = std::abs(value);
  const int d = a <= 50   ? 21 * a / 8
                : a <= 60 ? (1024 + 103 * (a - 50)) / 8
                          : (2048 + 410 * (a - 60)) / 8;
  return value < 0 ? -d : d;
}
void NativeLFO::Start(const uint8_t *p, uint32_t clock, uint32_t &random,
                      const ModulationSources &sources, int delayOverride) noexcept {
  *this = {};
  mParameters = p;
  mClock = clock;
  mWrapped = true;
  const int kind = p[0] & 63, start = S8(p[3]);
  if (kind <= 11)
    mPhase = start == 37 ? uint16_t(Draw(random))
                         : uint16_t(kPhase[std::min(36, std::abs(start))] * (start < 0 ? -1 : 1));
  mStartPhase = mPhase;
  mDelay = unsigned(delayOverride < 0 ? p[6] : std::clamp(delayOverride, 0, 99)) << 9;
  mFadeStep = uint16_t(kFade[std::min<unsigned>(p[7], 99)] >> 1);
  mFade = !mDelay && mFadeStep == 32767 ? 65535 : 0;
  if (kind >= 15 && kind <= 17) {
    mCurrent = uint16_t(Draw(random));
    if (kind == 16)
      mCurrent >>= 1;
    if (kind == 17)
      mCurrent = mCurrent > 32768 ? 32767 : 0;
  }
  Wave(sources, random);
}
int NativeLFO::Wave(const ModulationSources &s, uint32_t &random) noexcept {
  const auto p = mParameters;
  if (!p)
    return 0;
  const int kind = p[0] & 63, phase = mPhase;
  int raw = 0;
  if (kind == 0) {
    int v = S16(uint16_t(phase + 16384));
    if (v < 0)
      v = (~v) & 65535;
    raw = S16(uint16_t(v - 16384)) * 2;
  } else if (kind == 1)
    raw = 32768 - phase;
  else if (kind == 2)
    raw = phase < 32768 ? 32767 : -32767;
  else if (kind == 3) {
    auto point = [](int i) {
      const bool negative = i >= 128;
      i %= 128;
      if (i > 63)
        i = 127 - i;
      return int(kSine[i]) * (negative ? -1 : 1);
    };
    raw = Interpolate(point(phase / 256), point((phase / 256 + 1) & 255), phase & 255);
  } else if (kind == 4)
    raw = Interpolate(kGuitar[phase / 256], kGuitar[(phase / 256 + 1) & 255], phase & 255);
  else if (kind == 5) {
    auto point = [](int i) { return int(kExp[i > 127 ? 255 - i : i]); };
    raw = Interpolate(point(phase / 256), point((phase / 256 + 1) & 255), phase & 255);
  } else if (kind == 6 || kind == 7) {
    int q = kind == 6 ? 65535 - phase : phase, i = q / 512;
    raw = kExp[i];
    if (i < 127)
      raw += (kExp[i + 1] - kExp[i]) * (q & 511) >> 9;
  } else if (kind == 8) {
    const int a[] = {-32767, 0, 32767, 0};
    raw = a[phase / 16384];
  } else if (kind == 9)
    raw = phase <= 0x2aaa   ? -32767
          : phase <= 0x5554 ? -10923
          : phase < 0x8000  ? 10923
          : phase <= 0xaaaa ? 32767
          : phase <= 0xd554 ? 10923
                            : -10923;
  else if (kind == 10) {
    const int a[] = {32767, 10923, -10923, -32767};
    raw = a[phase / 16384];
  } else if (kind == 11)
    raw = phase <= 0x2aaa   ? 32767
          : phase <= 0x5554 ? 19660
          : phase < 0x8000  ? 6553
          : phase <= 0xaaaa ? -6553
          : phase <= 0xd554 ? -19660
                            : -32767;
  else if (kind == 15) {
    const uint16_t next = uint16_t(mCurrent + 2 * int(mRandomStep));
    if (mWrapped) {
      mCurrent = next;
      mRandomStep = int16_t((int(uint16_t(Draw(random))) - next) >> 1);
      raw = int(next) - 32768;
    } else
      raw = int(uint16_t(mCurrent + (int(mRandomStep) * phase >> 15))) - 32768;
  } else if (kind >= 12 && kind <= 17) {
    if (mWrapped) {
      const uint16_t previous = mCurrent;
      if (kind == 12)
        mCurrent = uint16_t(Draw(random));
      else {
        mRandomStep = int16_t(std::max(1, int(uint16_t(Draw(random)) >> 2)));
        mCurrent = uint16_t(Draw(random));
      }
      if (kind == 16 || kind == 17) {
        mPrevious = previous;
        mCurrent = kind == 16 ? mCurrent >> 1 : previous ? 0 : 32767;
      }
    }
    if (kind == 12 || kind == 13)
      raw = S16(mCurrent);
    else if (kind == 14)
      raw = S16(mCurrent) >= 0 ? 32767 : -32767;
    else
      raw = (mPrevious + ((int(mCurrent) - mPrevious) * phase >> 16)) * 2 - 32768;
  }
  mWrapped = false;
  int shape = S8(p[4]) * 331;
  if (S8(p[9]))
    shape = std::clamp(shape + 8 * Mod(S8(p[9]), GetSource(s, p[8])), -32768, 32768);
  raw += int((int64_t(32767 - (int64_t(raw) * raw >> 15)) * shape) >> 16);
  mValue = int16_t((661 * S8(p[5]) >> 2) + (raw >> 1));
  return mValue;
}
void NativeLFO::Advance(const ModulationSources &s, uint32_t clock,
                        int frequencyOverride) noexcept {
  const auto p = mParameters;
  if (!p)
    return;
  const int kind = p[0] & 63;
  const int scale =
      int(std::min<uint64_t>(INT32_MAX, uint64_t(Factor(p, 16, s, 20)) * Factor(p, 24, s) >> 8));
  const int delay = int(mDelay) - std::max(scale, 1);
  mDelay = uint16_t(delay);
  if (delay < 0) {
    mRunning = true;
    mDelay = 0;
    mFade = uint16_t(std::clamp(int(mFade) + (int64_t(scale) * S16(mFadeStep) >> 8), int64_t(0),
                                int64_t(65535)));
  }
  if (!mRunning || (p[0] & 64))
    return;
  int delta;
  if (p[12] & 128) {
    const unsigned period = kPeriods[std::min<unsigned>(p[12] & 15, 9)] * p[13];
    if (!period)
      delta = 1;
    else {
      uint32_t elapsed = clock - mClock;
      if (elapsed > period)
        elapsed = (elapsed - 1) % period + 1;
      mClock = clock - elapsed;
      const uint32_t target = elapsed * 65535 / period + mStartPhase;
      delta = int(target) - mPhase + (target < mPhase ? 65536 : 0);
    }
  } else
    delta = std::clamp(
        S32(int64_t(kRate[frequencyOverride < 0 ? std::min<unsigned>(p[1], 99)
                                                : unsigned(std::clamp(frequencyOverride, 0, 99))]) *
                scale >>
            8),
        1, 27525);
  int next;
  if (kind == 13 || kind == 14 || kind == 16 || kind == 17) {
    const unsigned speed = uint16_t(mRandomStep), i = speed >> 8;
    const int jitter = kJitter[i] + ((int(kJitter[i + 1]) - kJitter[i]) * (speed & 255) >> 8);
    next = mPhase + int(int64_t(jitter) * delta >> 13);
    if (next >= 65536) {
      mWrapped = true;
      next = 0;
    }
  } else {
    next = mPhase + delta;
    if (next >= 65536)
      mWrapped = true;
  }
  mPhase = uint16_t(next);
}
int NativeLFO::Source() const noexcept { return ((int(mValue) * mFade >> 16) * 16387) >> 16; }
} // namespace segrand
