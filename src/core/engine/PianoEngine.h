#pragma once
#include "EngineTypes.h"
#include "effects/concert_effects.h"
#include "midi/ChannelGain.h"
#include "midi/EventQueue.h"
#include "midi/Performance.h"
#include "samples/SampleBank.h"
#include "voice/NativeFilter.h"
#include "voice/NativeVoice.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <memory>

namespace segrand {
struct SampleResidency;
class PianoEngine {
public:
  static constexpr unsigned kVoices = 64, kTails = 16, kEvents = 2048, kChunk = 128;
  explicit PianoEngine(std::shared_ptr<const SampleBank> bank);
  ~PianoEngine();
  void Prepare(double sampleRate);
  void SetControls(const Controls &controls);
  void Queue(MidiEvent event) noexcept;
  void Process(float *left, float *right, int frames) noexcept;
  const std::array<float, 2> &FxPeaks() const noexcept { return mRack.Peaks(); }
  void Panic() noexcept;
  unsigned ActiveVoices() const noexcept;
  void SetSamples(const SampleResidency *samples) noexcept;
  void MarkSamples(bool *used) const noexcept;
  void Deactivate() noexcept;
  static int VelocityLayer(int velocity) noexcept {
    return velocity < 86 ? 0 : velocity < 107 ? 1 : 2;
  }

private:
  struct Voice {
    PitchGlide glide;
    double glideRatio = 1;
    const SampleResidency *residency = nullptr;
    const Sample *sample = nullptr;
    double position = 0, step = 1, velocityTrim = 1, controlPhase = 0, nativeAudioPhase = 0;
    std::array<NativeVoice, 2> native;
    std::array<NativeSlew, 2> slew;
    std::array<NativeFilter, 2> filter;
    uint64_t age = 0;
    int note = 0, channel = 0, forcedRemaining = 0;
    bool keyDown = false, released = false;
  };
  struct EffectDeleter {
    void operator()(ConcertEffects *value) const { concert_effects_destroy(value); }
  };
  std::shared_ptr<const SampleBank> mBank;
  const SampleBank *mPlaybackBank = nullptr;
  const SampleResidency *mResidency = nullptr;
  std::array<Voice, kVoices> mVoices{};
  std::array<Voice, kTails> mTails{};
  EventQueue<kEvents> mEvents;
  std::array<std::unique_ptr<ConcertEffects, EffectDeleter>, 3> mEffects;
  std::array<bool, 16> mSustain{};
  std::array<int, 16> mPortamento{}, mPreviousPitch{};
  double mFXBlend = 1;
  int GlideAmount(int channel) const noexcept {
    return mPortamento[channel] < 0 ? mControls.glide
           : mPortamento[channel]   ? std::max(1, mControls.glide ? mControls.glide : 64)
                                    : 0;
  }
  std::array<double, 16> mBend{};
  ChannelGain mGain;
  FxRack mRack;
  Controls mControls;
  MonoPerformance mMono;
  std::array<double, 3> mWeights{{1, 0, 0}};
  uint64_t mAge = 0;
  double mRate = 48000, mControlIncrement = 0, mNativeAudioIncrement = 1, mSmoothing = 0,
         mOutput = 0.5, mOutputTarget = 0.5;
  void Midi(const MidiEvent &event) noexcept;
  void NoteOn(int note, int velocity, int channel, int previousPitch = -1) noexcept;
  void SelectMono(int note, int velocity, int channel, bool connected) noexcept;
  void Release(Voice &voice) noexcept;
  void Tail(Voice &voice) noexcept;
  void RenderVoice(Voice &voice, double &left, double &right) noexcept;
  void Render(float *left, float *right, int frames) noexcept;
};
} // namespace segrand
