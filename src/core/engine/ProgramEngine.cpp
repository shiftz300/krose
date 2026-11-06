#include "engine/ProgramEngine.h"
#include "samples/SampleResidency.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace segrand {
namespace {
double Read(const PCM24 &pcm, double position) {
  const auto last = pcm.size() - 1;
  const auto i = std::min(last, size_t(std::max(0.0, position)));
  return pcm[i] + (pcm[std::min(last, i + 1)] - pcm[i]) * (position - std::floor(position));
}
} // namespace
ProgramEngine::ProgramEngine(std::shared_ptr<const ProgramLibrary> library)
    : mLibrary(std::move(library)) {
  if (!mLibrary || mLibrary->programs.empty())
    throw std::invalid_argument("Missing factory Programs");
  Prepare(48000);
}
ProgramEngine::~ProgramEngine() = default;
void ProgramEngine::Prepare(double rate) {
  if (!std::isfinite(rate) || rate < 32000 || rate > 192000)
    throw std::invalid_argument("Sample rate must be 32..192 kHz");
  double identity[40]{};
  for (int i = 0; i < 8; ++i)
    identity[i * 5] = 1;
  const auto sends = ResolveFxSends(mControls.fx, .12, 0, mControls.space);
  std::unique_ptr<ConcertEffects, DeleteEffect> room(
      concert_effects_create(rate, identity, 1, 1.8, sends.hall, sends.chorus, 0));
  if (!room)
    throw std::runtime_error("Could not prepare room effect");
  mRack.Prepare(rate);
  mRack.SetInserts(mControls.fx, false);
  mRack.SetReturns(mControls.fx, mControls.space);
  mRoom = std::move(room);
  mRate = rate;
  mGain.Prepare(rate);
  mSmooth = 1 - std::exp(-1 / (rate * .02));
  mOutput = mTarget;
  Panic();
}
void ProgramEngine::Panic() noexcept {
  mAge = 0;
  mRandom = 1;
  mMono.Reset();
  mVoices = {};
  mTails = {};
  mEvents.Clear();
  mSustain.fill(false);
  mPortamento.fill(-1);
  mPreviousPitch.fill(-1);
  mFXBlend = mControls.fxBypass ? 0 : 1;
  mBend.fill(1);
  mGain.Reset();
  for (auto &cc : mCC)
    cc.fill(255);
  mPolyPressure = {};
  mPressure = {};
  mBendValue = {};
  concert_effects_reset(mRoom.get());
  mRack.Reset();
}
void ProgramEngine::MarkSamples(bool *used) const noexcept {
  for (const auto &v : mVoices)
    if (v.region && v.residency)
      used[v.residency->slot] = true;
  for (const auto &v : mTails)
    if (v.region && v.residency)
      used[v.residency->slot] = true;
}
void ProgramEngine::Deactivate() noexcept {
  mMono.Reset();
  mSustain.fill(false);
  for (auto &v : mVoices)
    if (v.region)
      Release(v);
}
void ProgramEngine::SetProgram(unsigned index) noexcept {
  if (index >= mLibrary->programs.size() || index == mProgram)
    return;
  if (mControls.voiceMode) {
    mMono.Reset();
    for (auto &voice : mVoices)
      if (voice.region)
        Tail(voice);
  }
  mProgram = index;
}
void ProgramEngine::SetControls(const Controls &c) noexcept {
  if (!std::isfinite(c.outputDb) || !std::isfinite(c.space) || !std::isfinite(c.velocityCurve) ||
      !std::isfinite(c.releaseSeconds))
    return;
  const int mode = std::clamp(c.voiceMode, 0, 2);
  if (mode != mControls.voiceMode) {
    mMono.Reset();
    for (auto &voice : mVoices)
      if (voice.region)
        Tail(voice);
  }
  mControls = c;
  mControls.voiceMode = mode;
  mControls.glide = std::clamp(c.glide, 0, 127);
  mControls.space = std::clamp(c.space, 0., 2.);
  mControls.velocityCurve = std::clamp(c.velocityCurve, .5, 3.);
  mControls.releaseSeconds = std::clamp(c.releaseSeconds, .03, 2.);
  mTarget = std::pow(10, std::clamp(c.outputDb, -60., 6.) / 20);
  mRack.SetInserts(c.fx, false);
  const auto sends = ResolveFxSends(c.fx, .12, 0, mControls.space);
  concert_effects_set_wet(mRoom.get(), sends.hall, sends.chorus);
  mRack.SetReturns(c.fx, mControls.space);
}
unsigned ProgramEngine::ActiveVoices() const noexcept {
  unsigned n = 0;
  for (const auto &v : mVoices)
    if (v.region)
      ++n;
  return n;
}
void ProgramEngine::Tail(Voice &voice) noexcept {
  auto it = std::find_if(mTails.begin(), mTails.end(), [](const Voice &v) { return !v.region; });
  if (it == mTails.end())
    it = mTails.begin();
  *it = voice;
  it->forced = 96;
  voice = {};
}
void ProgramEngine::Release(Voice &voice) noexcept {
  voice.down = false;
  if (!voice.region || voice.program->drum || voice.released)
    return;
  voice.released = true;
  voice.amplitude.ReleaseProgram(mControls.releaseSeconds / kNativeReleaseBaseSeconds);
  voice.filter.Release();
  voice.modulation.Release();
}
void ProgramEngine::SelectMono(int note, int velocity, int channel, bool connected) noexcept {
  int previous = -1;
  bool reused = false;
  for (auto &v : mVoices)
    if (v.region && v.channel == channel) {
      if (connected && v.down && !v.released) {
        previous = v.glide.CurrentPitch();
        if (mControls.voiceMode == 2 && !v.program->drum) {
          if (v.note == note) {
            reused = true;
            continue;
          }
          v.note = note;
          for (int side = 0; side < 2; ++side)
            if (v.region->sample[side] != UINT32_MAX)
              v.step[side] = mLibrary->Step(*v.program, *v.region, side, note, mRate);
          v.glide.Start(previous, note, GlideAmount(channel));
          v.glideRatio = v.glide.Ratio();
          v.amplitude.Retune(note);
          v.filter.Retune(v.amplitude);
          v.slew.SetTarget(v.amplitude.Gain());
          reused = true;
          continue;
        }
      }
      Tail(v);
    }
  if (!reused)
    NoteOn(note, velocity, channel, previous);
}
void ProgramEngine::NoteOn(int note, int velocity, int channel, int previousPitch) noexcept {
  if (previousPitch < 0 && mPortamento[channel] > 0)
    previousPitch = mPreviousPitch[channel];
  mPreviousPitch[channel] = note * 65536;
  const auto &p = mLibrary->programs[mProgram];
  std::array<int32_t, 8> indices;
  indices.fill(-1);
  unsigned selected = 0;
  for (int osc = 0; osc < 2; ++osc)
    for (int slot = 0; slot < 4; ++slot) {
      const auto *b = p.controls.data() + 0x564 + 380 * osc;
      if (velocity < std::min(b[0x2d], b[0x2e]) || velocity > std::max(b[0x2d], b[0x2e]))
        continue;
      const int selection = !p.drum && GlideAmount(channel) && previousPitch >= 0
                                ? std::max(note, previousPitch / 65536)
                                : note;
      const auto index = p.lookup[osc][selection][slot];
      if (index >= 0 && mLibrary->LayerWeight(mLibrary->regions[unsigned(index)], velocity) > 0)
        indices[selected++] = index;
    }
  unsigned needed = 0;
  for (auto i : indices)
    if (i >= 0)
      ++needed;
  if (!needed)
    return;
  if (p.drum) {
    const int group = mLibrary->regions[unsigned(indices[0])].exclusive;
    if (group)
      for (auto &v : mVoices)
        if (v.region && v.channel == channel && v.program == &p && v.region->exclusive == group)
          Tail(v);
  }
  while (kVoices - ActiveVoices() < needed) {
    const Voice *oldest = nullptr;
    for (const auto &v : mVoices)
      if (v.region && (!oldest || (v.released && !oldest->released) ||
                       (v.released == oldest->released && v.age < oldest->age)))
        oldest = &v;
    if (!oldest)
      break;
    const auto age = oldest->age;
    for (auto &v : mVoices)
      if (v.region && v.age == age)
        Tail(v);
  }
  const uint64_t age = ++mAge;
  for (auto index : indices) {
    if (index < 0)
      continue;
    const auto &r = mLibrary->regions[unsigned(index)];
    auto it =
        std::find_if(mVoices.begin(), mVoices.end(), [](const Voice &v) { return !v.region; });
    if (it == mVoices.end())
      return;
    auto &v = *it;
    v = {};
    v.residency = mResidency;
    v.region = &r;
    v.program = &p;
    v.note = note;
    v.channel = channel;
    v.down = true;
    v.age = age;
    v.glide.Start(p.drum ? -1 : previousPitch, note, GlideAmount(channel));
    v.glideRatio = v.glide.Ratio();
    const int weight = mLibrary->LayerWeight(r, velocity);
    v.velocityTrim = p.drum ? std::pow(velocity / 127., 1.4) * weight / 32768.
                            : std::pow(velocity / 127., mControls.velocityCurve - 1);
    const double pan = std::clamp((r.pan - 64) / 63., -1., 1.);
    if (r.sample[1] == UINT32_MAX) {
      v.panL = std::cos((pan + 1) * .7853981633974483);
      v.panR = std::sin((pan + 1) * .7853981633974483);
    } else {
      v.panL = pan > 0 ? 1 - pan : 1;
      v.panR = pan < 0 ? 1 + pan : 1;
    }
    for (int ch = 0; ch < 2; ++ch)
      if (r.sample[ch] != UINT32_MAX) {
        v.step[ch] = mLibrary->Step(p, r, ch, note, mRate);
        if (r.flags & 1)
          v.position[ch] = mLibrary->samples[r.sample[ch]].frames - 1;
      }
    if (!p.drum) {
      v.amplitude.SetOffsets(mControls.ampEg);
      v.filter.SetOffsets(mControls.filterEg, mControls.cutoff, mControls.resonance);
      v.amplitude.StartProgram(p.controls.data(), note, velocity, r.oscillator,
                               r.slotLevel * weight / 32768);
      v.modulation.Start(p.controls.data(), r.oscillator, Sources(v), mRandom, &mCC[channel]);
      mRandom = v.modulation.RandomState();
      v.amplitude.StartProgram(p.controls.data(), note, velocity, r.oscillator,
                               r.slotLevel * weight / 32768, &v.modulation.sources);
      v.amplitude.SetModulation(v.modulation.sources, v.modulation.lfo);
      v.filter.StartProgram(p.controls.data(), v.amplitude, r.oscillator, velocity, mRate);
      v.filter.SetModulation(v.modulation.sources, v.modulation.lfo);
      v.slew.Reset(v.amplitude.Gain());
      for (int ch = 0; ch < 2; ++ch)
        if (r.sample[ch] != UINT32_MAX)
          v.step[ch] = mLibrary->Step(p, r, ch, note, mRate, v.modulation.PitchOffset());
    }
  }
}
void ProgramEngine::Queue(MidiEvent event) noexcept { mEvents.Push(event); }

void ProgramEngine::Midi(const MidiEvent &e) noexcept {
  const int ch = e.status & 15, type = e.status & 240, note = e.data1, value = e.data2;
  if (mControls.voiceMode &&
      mMono.Handle(
          e, std::min(2, int((mLibrary->programs[mProgram].controls[0x509] >> 2) & 3)),
          [this](int n, int v, int c, bool held) { SelectMono(n, v, c, held); },
          [this](int c) {
            for (auto &v : mVoices)
              if (v.region && v.channel == c && v.down) {
                v.down = false;
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
    uint64_t age = UINT64_MAX;
    for (const auto &v : mVoices)
      if (v.region && v.note == note && v.channel == ch && v.down)
        age = std::min(age, v.age);
    for (auto &v : mVoices)
      if (v.region && v.age == age) {
        v.down = false;
        if (!mSustain[ch])
          Release(v);
      }
  } else if (type == 0xa0)
    mPolyPressure[ch][note] = uint8_t(value);
  else if (type == 0xd0)
    mPressure[ch] = uint8_t(note);
  else if (type == 0xe0) {
    mBendValue[ch] = value * 128 + note - 8192;
    mBend[ch] = std::pow(2, ((value * 128 + note - 8192) / 8192.) * 2 / 12);
  } else if (type == 0xb0) {
    mGain.Set(ch, note, value);
    mCC[ch][note] = uint8_t(value);
    if (note == 64) {
      mSustain[ch] = value >= 64;
      if (!mSustain[ch])
        for (auto &v : mVoices)
          if (v.region && v.channel == ch && !v.down)
            Release(v);
    } else if (note == 65)
      mPortamento[ch] = value >= 64 ? 1 : 0;
    else if (note == 120) {
      for (auto &v : mVoices)
        if (v.channel == ch)
          v = {};
      for (auto &v : mTails)
        if (v.channel == ch)
          v = {};
    } else if (note == 123) {
      for (auto &v : mVoices)
        if (v.region && v.channel == ch) {
          v.down = false;
          if (!mSustain[ch])
            Release(v);
        }
    } else if (note == 121) {
      mCC[ch].fill(255);
      mPolyPressure[ch].fill(0);
      mPressure[ch] = 0;
      mBendValue[ch] = 0;
      mSustain[ch] = false;
      mPortamento[ch] = -1;
      mPreviousPitch[ch] = -1;
      mBend[ch] = 1;
      for (auto &v : mVoices)
        if (v.region && v.channel == ch && !v.down)
          Release(v);
    }
  }
}
ModulationSources ProgramEngine::Sources(const Voice &v) const noexcept {
  ModulationSources s{};
  for (unsigned i = 0; i < s.size(); ++i)
    s[i] = v.amplitude.Source(i);
  s[4] = v.filter.Level() * 32770 >> 18;
  s[5] = v.amplitude.Level() * 32770 >> 18;
  NativeModulation::Controllers(s, mCC[v.channel], mPolyPressure[v.channel][v.note],
                                mPressure[v.channel], mBendValue[v.channel]);
  return s;
}
void ProgramEngine::RenderVoice(Voice &v, double &left, double &right) noexcept {
  if (!v.region)
    return;
  const auto &r = *v.region;
  std::array<double, 2> audio{};
  for (int ch = 0; ch < 2; ++ch) {
    if (r.sample[ch] == UINT32_MAX)
      continue;
    const auto &sample = mLibrary->samples[r.sample[ch]];
    const PCM24 &pcm = v.residency ? *(*v.residency->factory)[r.sample[ch]] : sample.pcm;
    const bool reverse = r.flags & 1;
    const bool loop = !reverse && !v.program->drum && (sample.flags & 16) &&
                      sample.loopEnd - sample.loopStart >= 8;
    auto &pos = v.position[ch];
    const double period = sample.loopEnd - sample.loopStart;
    if (loop && pos >= sample.loopEnd)
      pos = sample.loopStart + std::fmod(pos - sample.loopEnd, period);
    if (pos < 0 || pos >= pcm.size()) {
      v.region = nullptr;
      return;
    }
    audio[ch] = Read(pcm, pos);
    if (loop) {
      const double seam = std::min(32., period / 8);
      if (pos > sample.loopEnd - seam) {
        // Match the endpoint without consuming frames from the next cycle.
        const double t = 1 - (sample.loopEnd - pos) / seam;
        audio[ch] += t * t * (3 - 2 * t) * (pcm[sample.loopStart] - pcm[sample.loopEnd]);
      }
    }
    pos += (reverse ? -1 : 1) * v.step[ch] * mBend[v.channel] * v.glideRatio;
  }
  v.glideRatio = v.glide.Advance(mRate);
  double l = audio[0], rr = r.sample[1] == UINT32_MAX ? audio[0] : audio[1];
  double level = v.program->drum ? .75 : v.slew.Current() / 65536.;
  if (!v.program->drum && mControls.filterEnabled)
    v.filter.Process(l, rr);
  level *= r.gain * v.velocityTrim * mGain.Current(v.channel);
  level *= std::min(1., v.ageSeconds / .002);
  v.ageSeconds += 1 / mRate;
  if (!v.program->drum)
    level *= .4;
  if (v.forced) {
    level *= v.forced / 96.;
    if (!--v.forced)
      v.region = nullptr;
  }
  left += l * level * v.panL;
  right += rr * level * v.panR;
  if (!v.program->drum) {
    v.audioPhase += kNativeAudioHz / mRate;
    while (v.audioPhase >= 1) {
      v.slew.Advance();
      v.audioPhase -= 1;
    }
    v.phase += kNativeControlHz / mRate;
    if (v.phase >= 1) {
      v.phase -= 1;
      v.amplitude.SetOffsets(mControls.ampEg);
      v.filter.SetOffsets(mControls.filterEg, mControls.cutoff, mControls.resonance);
      v.amplitude.Tick();
      v.filter.AdvanceModulationEnvelope();
      v.modulation.SetRandomState(mRandom);
      v.modulation.Tick(Sources(v), uint32_t(uint64_t(v.ageSeconds * mTempo * 8)), &mCC[v.channel]);
      mRandom = v.modulation.RandomState();
      v.amplitude.SetModulation(v.modulation.sources, v.modulation.lfo);
      v.filter.SetModulation(v.modulation.sources, v.modulation.lfo);
      for (int ch = 0; ch < 2; ++ch)
        if (r.sample[ch] != UINT32_MAX)
          v.step[ch] =
              mLibrary->Step(*v.program, r, ch, v.note, mRate, v.modulation.PitchOffset());
      v.slew.SetTarget(v.amplitude.Gain());
    }
    if (v.amplitude.Finished() && v.slew.Silent())
      v.region = nullptr;
  }
}
void ProgramEngine::Render(float *left, float *right, int frames) noexcept {
  for (int start = 0; start < frames; start += 128) {
    const int count = std::min(128, frames - start);
    std::array<float, 256> bus{}, dry;
    std::array<double, 256> inserts, returns;
    const bool blend = mControls.fxBypass || mFXBlend < 1;
    // MIDI is dispatched between Render calls. Build an ordered local view once
    // per chunk; finished voices remain safe no-ops until the next chunk.
    std::array<Voice *, kVoices + kTails> active{};
    unsigned voices = 0;
    for (auto &v : mVoices)
      if (v.region)
        active[voices++] = &v;
    for (auto &v : mTails)
      if (v.region)
        active[voices++] = &v;
    for (int i = 0; i < count; ++i) {
      mGain.Advance();
      double l = 0, r = 0;
      for (unsigned v = 0; v < voices; ++v)
        RenderVoice(*active[v], l, r);
      if (blend) {
        dry[i * 2] = float(l);
        dry[i * 2 + 1] = float(r);
      }
      mRack.Insert(l, r);
      bus[i * 2] = float(l);
      bus[i * 2 + 1] = float(r);
      inserts[i * 2] = l;
      inserts[i * 2 + 1] = r;
    }
    // One shared return bus, not a separate reverb per voice or per Program.
    concert_effects_process(mRoom.get(), bus.data(), count);
    mRack.Returns(inserts.data(), returns.data(), count);
    for (int i = 0; i < count; ++i) {
      mOutput += mSmooth * (mTarget - mOutput);
      mFXBlend += mSmooth * ((mControls.fxBypass ? 0. : 1.) - mFXBlend);
      bus[i * 2] += float(returns[i * 2]);
      bus[i * 2 + 1] += float(returns[i * 2 + 1]);
      if (blend) {
        bus[i * 2] = float(dry[i * 2] + (bus[i * 2] - dry[i * 2]) * mFXBlend);
        bus[i * 2 + 1] = float(dry[i * 2 + 1] + (bus[i * 2 + 1] - dry[i * 2 + 1]) * mFXBlend);
      }
      left[start + i] = float(bus[i * 2] * mOutput);
      right[start + i] = float(bus[i * 2 + 1] * mOutput);
    }
  }
}
void ProgramEngine::Process(float *left, float *right, int frames) noexcept {
  mRack.ClearMeters();
  if (frames <= 0 || !left || !right)
    return;
  if (mEvents.Overflowed())
    Panic();
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
