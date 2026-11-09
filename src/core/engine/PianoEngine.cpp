#include "engine/PianoEngine.h"
#include "ConcertEqData.h"
#include "samples/SampleResidency.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace segrand {
namespace {
std::array<double, 2> Interpolate(const Sample &sample, double position) {
  const auto base = static_cast<int64_t>(position);
  const double f = position - base;
  const auto last = int64_t(sample.frames() - 1);
  auto index = [&](int64_t i) {
    return static_cast<size_t>(std::clamp(i, int64_t(0), last)) * 2;
  };
  const auto ia = index(base - 1), ib = index(base), ic = index(base + 1), id = index(base + 2);
  std::array<double, 2> result;
  for (size_t ch = 0; ch < result.size(); ++ch) {
    const double a = sample.stereo[ia + ch], b = sample.stereo[ib + ch],
                 c = sample.stereo[ic + ch], d = sample.stereo[id + ch];
    result[ch] = b + 0.5 * f * (c - a + f * (2 * a - 5 * b + 4 * c - d + f * (3 * (b - c) + d - a)));
  }
  return result;
}
} // namespace

PianoEngine::PianoEngine(std::shared_ptr<const SampleBank> bank) : mBank(std::move(bank)) {
  if (!mBank)
    throw std::invalid_argument("Missing sample bank");
  mPlaybackBank = mBank.get();
  Prepare(48000);
}
void PianoEngine::SetSamples(const SampleResidency *samples) noexcept {
  mResidency = samples;
  mPlaybackBank = samples ? samples->concert.get() : mBank.get();
}
void PianoEngine::MarkSamples(bool *used) const noexcept {
  for (const auto &v : mVoices)
    if (v.sample && v.residency)
      used[v.residency->slot] = true;
  for (const auto &v : mTails)
    if (v.sample && v.residency)
      used[v.residency->slot] = true;
}
void PianoEngine::Deactivate() noexcept {
  mMono.Reset();
  mSustain.fill(false);
  for (auto &v : mVoices)
    if (v.sample)
      Release(v);
}
PianoEngine::~PianoEngine() = default;
void PianoEngine::Prepare(double rate) {
  if (!std::isfinite(rate) || rate < 32000 || rate > 192000)
    throw std::invalid_argument("Sample rate must be 32..192 kHz");
  std::array<std::unique_ptr<ConcertEffects, EffectDeleter>, 3> effects;
  const double times[3] = {1.8, 1.5, 2.6}, wet[3] = {0.15, 0.12, 0.23}, chorus[3] = {0, 0, 0.18},
               tone[3] = {0, 8500, 0};
  for (int i = 0; i < 3; ++i) {
    const auto sends = ResolveFxSends(mControls.fx, wet[i], chorus[i], mControls.space);
    effects[i].reset(concert_effects_create(rate, kConcertEq, kConcertTrim, times[i],
                                            sends.hall, sends.chorus, tone[i]));
    if (!effects[i])
      throw std::runtime_error("Could not prepare effects");
  }
  mRack.Prepare(rate);
  mRack.SetInserts(mControls.fx, true);
  mRack.SetReturns(mControls.fx, mControls.space);
  mEffects = std::move(effects);
  mRate = rate;
  mGain.Prepare(rate);
  mControlIncrement = kNativeControlHz / rate;
  mNativeAudioIncrement = kNativeAudioHz / rate;
  mSmoothing = 1 - std::exp(-1 / (rate * 0.02));
  mOutputTarget = std::pow(10, mControls.outputDb / 20);
  mOutput = mOutputTarget;
  mWeights = {{0, 0, 0}};
  mWeights[static_cast<size_t>(mControls.preset)] = 1;
  Panic();
}
void PianoEngine::Panic() noexcept {
  mMono.Reset();
  mVoices = {};
  mTails = {};
  mOverflowTail = {};
  mOverflowPosition = 0;
  mSustain.fill(false);
  mPortamento.fill(-1);
  mPreviousPitch.fill(-1);
  mFXBlend = mControls.fxBypass ? 0 : 1;
  mBend.fill(1);
  mGain.Reset();
  mRack.Reset();
  mEvents.Clear();
  for (auto &effect : mEffects)
    concert_effects_reset(effect.get());
}
unsigned PianoEngine::ActiveVoices() const noexcept {
  unsigned n = 0;
  for (const auto &v : mVoices)
    if (v.sample)
      ++n;
  return n;
}
void PianoEngine::SetControls(const Controls &incoming) {
  Controls c = incoming;
  if (!std::isfinite(c.outputDb) || !std::isfinite(c.space) || !std::isfinite(c.releaseSeconds) ||
      !std::isfinite(c.velocityCurve))
    return;
  c.preset = std::clamp(c.preset, 0, 2);
  c.outputDb = std::clamp(c.outputDb, -60.0, 6.0);
  c.space = std::clamp(c.space, 0.0, 2.0);
  c.filterEgIntensity = std::clamp(c.filterEgIntensity, -99, 99);
  c.releaseSeconds = std::clamp(c.releaseSeconds, 0.03, 2.0);
  c.velocityCurve = std::clamp(c.velocityCurve, 0.5, 3.0);
  mOutputTarget = std::pow(10, c.outputDb / 20);
  const double wet[3] = {0.15, 0.12, 0.23}, chorus[3] = {0, 0, 0.18};
  mRack.SetInserts(c.fx, true);
  for (int i = 0; i < 3; ++i) {
    const auto sends = ResolveFxSends(c.fx, wet[i], chorus[i], c.space);
    concert_effects_set_wet(mEffects[i].get(), sends.hall, sends.chorus);
  }
  mRack.SetReturns(c.fx, c.space);
  c.voiceMode = std::clamp(c.voiceMode, 0, 2);
  c.glide = std::clamp(c.glide, 0, 127);
  if (c.voiceMode != mControls.voiceMode) {
    mMono.Reset();
    for (auto &voice : mVoices)
      if (voice.sample)
        Tail(voice);
  }
  mControls = c;
}
void PianoEngine::Queue(MidiEvent event) noexcept { mEvents.Push(event); }

void PianoEngine::Release(Voice &voice) noexcept {
  voice.keyDown = false;
  voice.released = true;
  for (auto &native : voice.native)
    native.Release(mControls.releaseSeconds);
  for (auto &filter : voice.filter)
    filter.Release();
}
void PianoEngine::Tail(Voice &voice) noexcept {
  auto tail = std::find_if(mTails.begin(), mTails.end(), [](const Voice &v) { return !v.sample; });
  if (tail == mTails.end()) {
    tail = std::min_element(mTails.begin(), mTails.end(),
        [](const Voice &a, const Voice &b) { return a.forcedRemaining < b.forcedRemaining; });
    for (unsigned frame = 0; frame < 96 && tail->sample; ++frame) {
      auto &audio = mOverflowTail[(mOverflowPosition + frame) % 96];
      RenderVoice(*tail, audio[0], audio[1]);
    }
  }
  *tail = voice;
  tail->forcedRemaining = 96;
  voice = {};
}
void PianoEngine::SelectMono(int note, int velocity, int channel, bool connected) noexcept {
  int previous = -1;
  bool reused = false;
  for (auto &voice : mVoices)
    if (voice.sample && voice.channel == channel) {
      if (connected && voice.keyDown && !voice.released) {
        previous = voice.glide.CurrentPitch();
        if (mControls.voiceMode == 2) {
          if (voice.note == note) {
            reused = true;
            continue;
          }
          voice.note = note;
          voice.step = mBank->rootRate / mRate * std::exp2((note - int(voice.sample->root)) / 12.);
          voice.glide.Start(previous, note, GlideAmount(channel));
          voice.glideRatio = voice.glide.Ratio();
          for (int osc = 0; osc < 2; ++osc) {
            voice.native[osc].Retune(note);
            voice.filter[osc].Retune(voice.native[osc]);
            voice.slew[osc].SetTarget(voice.native[osc].Gain());
          }
          reused = true;
          continue;
        }
      }
      Tail(voice);
    }
  if (!reused)
    NoteOn(note, velocity, channel, previous);
}
void PianoEngine::NoteOn(int note, int velocity, int channel, int previousPitch) noexcept {
  if (previousPitch < 0 && mPortamento[channel] > 0)
    previousPitch = mPreviousPitch[channel];
  mPreviousPitch[channel] = note * 65536;
  auto it = std::find_if(mVoices.begin(), mVoices.end(), [](const Voice &v) { return !v.sample; });
  if (it == mVoices.end()) {
    it = std::min_element(mVoices.begin(), mVoices.end(), [](const Voice &a, const Voice &b) {
      if (a.released != b.released)
        return a.released;
      return a.age < b.age;
    });
    Tail(*it);
  }
  const int layer = VelocityLayer(velocity);
  const int selection =
      GlideAmount(channel) && previousPitch >= 0 ? std::max(note, previousPitch / 65536) : note;
  const Sample &sample = mPlaybackBank->Select(layer, selection);
  *it = {};
  it->residency = mResidency;
  it->sample = &sample;
  it->note = note;
  it->channel = channel;
  it->keyDown = true;
  it->age = ++mAge;
  it->step = mBank->rootRate / mRate * std::pow(2, (note - int(sample.root)) / 12.0);
  it->glide.Start(previousPitch, note, GlideAmount(channel));
  it->glideRatio = it->glide.Ratio();
  // Native velocity/slot/AMS/keyboard response is the baseline. This optional
  // host trim changes loudness response, leaving the verified layer edges fixed.
  it->velocityTrim = std::pow(velocity / 127.0, mControls.velocityCurve - 1);
  for (int osc = 0; osc < 2; ++osc) {
    it->native[osc].SetOffsets(mControls.ampEg);
    it->filter[osc].SetOffsets(mControls.filterEg, mControls.cutoff, mControls.resonance, mControls.filterEgIntensity);
    it->native[osc].Start(note, velocity, osc, layer == 2 ? 127 : 119);
    it->slew[osc].Reset(it->native[osc].InitialGain());
    it->slew[osc].SetTarget(it->native[osc].Gain());
    it->filter[osc].Start(it->native[osc], osc, velocity, mRate);
  }
}
void PianoEngine::Midi(const MidiEvent &event) noexcept {
  const int ch = event.status & 15, type = event.status & 240, note = event.data1,
            value = event.data2;
  if (mControls.voiceMode &&
      mMono.Handle(
          event, 2, [this](int n, int v, int c, bool held) { SelectMono(n, v, c, held); },
          [this](int c) {
            for (auto &v : mVoices)
              if (v.sample && v.channel == c && v.keyDown) {
                v.keyDown = false;
                if (!mSustain[c])
                  Release(v);
              }
          }))
    return;
  if (type == 0x90 && value) {
    NoteOn(note, value, ch);
    return;
  }
  if (type == 0x80 || (type == 0x90 && !value)) {
    Voice *selected = nullptr;
    for (auto &v : mVoices)
      if (v.sample && v.note == note && v.channel == ch && v.keyDown &&
          (!selected || v.age < selected->age))
        selected = &v;
    if (selected) {
      selected->keyDown = false;
      if (!mSustain[ch])
        Release(*selected);
    }
  } else if (type == 0xE0) {
    mBend[ch] = std::pow(2, (((value * 128 + note) - 8192) / 8192.0) * 2 / 12);
  } else if (type == 0xB0) {
    mGain.Set(ch, note, value);
    if (note == 64) {
      mSustain[ch] = value >= 64;
      if (!mSustain[ch])
        for (auto &v : mVoices)
          if (v.sample && v.channel == ch && !v.keyDown && !v.released)
            Release(v);
    } else if (note == 65)
      mPortamento[ch] = value >= 64 ? 1 : 0;
    else if (note == 123) {
      for (auto &v : mVoices)
        if (v.sample && v.channel == ch) {
          v.keyDown = false;
          if (!mSustain[ch])
            Release(v);
        }
    } else if (note == 120) {
      for (auto &v : mVoices)
        if (v.channel == ch)
          v = {};
      for (auto &v : mTails)
        if (v.channel == ch)
          v = {};
    } else if (note == 121) {
      mSustain[ch] = false;
      mPortamento[ch] = -1;
      mPreviousPitch[ch] = -1;
      mBend[ch] = 1;
      for (auto &v : mVoices)
        if (v.sample && v.channel == ch && !v.keyDown)
          Release(v);
    }
  }
}
void PianoEngine::RenderVoice(Voice &voice, double &left, double &right) noexcept {
  if (!voice.sample)
    return;
  const Sample &sample = *voice.sample;
  const double end = sample.loopEnd;
  const double period = end - sample.loopStart;
  const double seam = std::min(210.0, period / 8);
  if (voice.position >= end)
    voice.position = sample.loopStart + std::fmod(voice.position - end, period);
  auto [l, r] = Interpolate(sample, voice.position);
  if (voice.position > end - seam) {
    const double t = 1 - (end - voice.position) / seam;
    const double blend = t * t * (3 - 2 * t);
    const size_t start = size_t(sample.loopStart) * 2, stop = size_t(sample.loopEnd) * 2;
    l += blend * (sample.stereo[start] - sample.stereo[stop]);
    r += blend * (sample.stereo[start + 1] - sample.stereo[stop + 1]);
  }
  // Share the sample read, but filter each OSC before applying its native gain.
  // Retain the prototype's explicit mean-OSC/0.4 headroom convention. Absolute
  // TG transfer, mixing/pan and fixed-point arithmetic remain unverified.
  double filteredL = 0, filteredR = 0;
  for (int osc = 0; osc < 2; ++osc) {
    double oscL = l, oscR = r;
    if (mControls.filterEnabled)
      voice.filter[osc].Process(oscL, oscR);
    filteredL += oscL * voice.slew[osc].Current() / 65536.0;
    filteredR += oscR * voice.slew[osc].Current() / 65536.0;
  }
  double level = 0.4 * voice.velocityTrim * mGain.Current(voice.channel);
  if (voice.forcedRemaining) {
    level *= voice.forcedRemaining / 96.0;
    if (!--voice.forcedRemaining)
      voice.sample = nullptr;
  }
  left += filteredL * level;
  right += filteredR * level;
  voice.position += voice.step * mBend[voice.channel] * voice.glideRatio;
  voice.glideRatio = voice.glide.Advance(mRate);
  // Continuous per-voice clocks make the result independent of host block
  // partitioning. TG slew advances on a nominal 48 kHz grid at every host rate.
  voice.nativeAudioPhase += mNativeAudioIncrement;
  while (voice.nativeAudioPhase >= 1) {
    for (auto &slew : voice.slew)
      slew.Advance();
    voice.nativeAudioPhase -= 1;
  }
  voice.controlPhase += mControlIncrement;
  if (voice.controlPhase >= 1) {
    voice.controlPhase -= 1;
    for (int osc = 0; osc < 2; ++osc) {
      voice.native[osc].SetOffsets(mControls.ampEg);
      voice.filter[osc].SetOffsets(mControls.filterEg, mControls.cutoff, mControls.resonance, mControls.filterEgIntensity);
      voice.native[osc].Tick();
      voice.slew[osc].SetTarget(voice.native[osc].Gain());
      voice.filter[osc].Tick();
    }
  }
  if (voice.native[0].Finished() && voice.native[1].Finished() && voice.slew[0].Silent() &&
      voice.slew[1].Silent())
    voice.sample = nullptr;
}
void PianoEngine::Render(float *left, float *right, int frames) noexcept {
  for (int start = 0; start < frames; start += kChunk) {
    const int count = std::min<int>(kChunk, frames - start);
    std::array<float, kChunk * 2> dry{};
    std::array<std::array<float, kChunk * 2>, 3> audio;
    std::array<Voice *, kVoices + kTails> active{};
    unsigned voices = 0;
    for (auto &v : mVoices)
      if (v.sample)
        active[voices++] = &v;
    for (auto &v : mTails)
      if (v.sample)
        active[voices++] = &v;
    for (int n = 0; n < count; ++n) {
      mGain.Advance();
      auto &overflow = mOverflowTail[mOverflowPosition];
      double l = overflow[0], r = overflow[1];
      overflow = {};
      mOverflowPosition = (mOverflowPosition + 1) % 96;
      for (unsigned v = 0; v < voices; ++v)
        RenderVoice(*active[v], l, r);
      dry[n * 2] = float(l);
      dry[n * 2 + 1] = float(r);
    }
    std::array<double, kChunk * 2> equalized, returns;
    concert_effects_equalize(mEffects[0].get(), dry.data(), equalized.data(), count);
    for (int n = 0; n < count; ++n) {
      auto &eqLeft = equalized[n * 2];
      auto &eqRight = equalized[n * 2 + 1];
      const double eq = mRack.ConcertEqMix();
      if (eq != 1) {
        eqLeft = dry[n * 2] + eq * (eqLeft - dry[n * 2]);
        eqRight = dry[n * 2 + 1] + eq * (eqRight - dry[n * 2 + 1]);
      }
      const double input = (dry[n * 2] + dry[n * 2 + 1]) * .5;
      mRack.Insert(eqLeft, eqRight, mControls.fx[0].type == 0 ? &input : nullptr);
    }
    std::array<std::array<double, 256>, 3> legacyChorus{}, legacyHall{};
    const bool monitoring = mRack.Monitor().Enabled();
    for (int p = 0; p < 3; ++p)
      concert_effects_process_components(mEffects[p].get(), equalized.data(), audio[p].data(), count,
          monitoring ? legacyChorus[p].data() : nullptr, monitoring ? legacyHall[p].data() : nullptr);
    mRack.Returns(equalized.data(), returns.data(), count);
    for (int n = 0; n < count; ++n) {
      double l = returns[n * 2], r = returns[n * 2 + 1];
      mOutput += mSmoothing * (mOutputTarget - mOutput);
      for (int p = 0; p < 3; ++p) {
        mWeights[p] += mSmoothing * ((p == mControls.preset ? 1 : 0) - mWeights[p]);
        l += audio[p][n * 2] * mWeights[p];
        r += audio[p][n * 2 + 1] * mWeights[p];
      }
      mFXBlend += mSmoothing * ((mControls.fxBypass ? 0. : 1.) - mFXBlend);
      if (mFXBlend < 1) {
        l = dry[n * 2] + (l - dry[n * 2]) * mFXBlend;
        r = dry[n * 2 + 1] + (r - dry[n * 2 + 1]) * mFXBlend;
      }
      if (monitoring) {
        for (int slot = 2; slot < 4; ++slot) {
          if (mControls.fx[slot].type >= 2 && mControls.fx[slot].enabled) continue;
          double wetL = 0, wetR = 0;
          const auto &tap = slot == 2 ? legacyChorus : legacyHall;
          for (int p = 0; p < 3; ++p) {
            wetL += tap[p][n * 2] * mWeights[p];
            wetR += tap[p][n * 2 + 1] * mWeights[p];
          }
          mRack.Monitor().Push(unsigned(slot), (equalized[n * 2] + equalized[n * 2 + 1]) * .5, wetL, wetR);
        }
      }
      left[start + n] = float(l * mOutput);
      right[start + n] = float(r * mOutput);
    }
    mRack.Monitor().Publish();
  }
}
void PianoEngine::Process(float *left, float *right, int frames) noexcept {
  mRack.ClearMeters();
  if (frames <= 0 || !left || !right)
    return;
  if (mEvents.Overflowed()) {
    Panic();
  }
  unsigned consumed = 0;
  int position = 0;
  while (consumed < mEvents.Size() && mEvents[consumed].offset < frames) {
    const int target = mEvents[consumed].offset;
    if (target > position)
      Render(left + position, right + position, target - position);
    position = target;
    Midi(mEvents[consumed++]);
  }
  if (position < frames)
    Render(left + position, right + position, frames - position);
  mEvents.Advance(consumed, frames);
}
} // namespace segrand
