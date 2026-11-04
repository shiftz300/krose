#pragma once
#include "Performance.h"
#include "PCM24.h"
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#include "concert_effects.h"
#include "NativeVoice.h"
#include "NativeFilter.h"
#include "EngineTypes.h"

namespace segrand {
struct Sample {
  unsigned root=0, top=0, loopStart=0, loopEnd=0;
  PCM24 stereo;
  size_t frames() const { return stereo.size()/2; }
};
struct SampleBank {
  double rootRate=42017.578125;
  std::array<std::vector<Sample>,3> layers;
  static std::shared_ptr<const SampleBank> Load(const std::string& path);
  const Sample& Select(unsigned layer, unsigned note) const;
};

class PianoEngine {
public:
  static constexpr unsigned kVoices=64, kTails=16, kEvents=2048, kChunk=128;
  explicit PianoEngine(std::shared_ptr<const SampleBank> bank);
  ~PianoEngine();
  void Prepare(double sampleRate);
  void SetControls(const Controls& controls);
  void Queue(MidiEvent event) noexcept;
  void Process(float* left, float* right, int frames) noexcept;
  void Panic() noexcept;
  unsigned ActiveVoices() const noexcept;
  static int VelocityLayer(int velocity) noexcept { return velocity<86?0:velocity<107?1:2; }
private:
  struct Voice {
  PitchGlide glide;
  double glideRatio=1;
    const Sample* sample=nullptr;
    double position=0, step=1, velocityTrim=1, controlPhase=0, nativeAudioPhase=0;
    std::array<NativeVoice,2> native;
    std::array<NativeSlew,2> slew;
    std::array<NativeFilter,2> filter;
    uint64_t age=0;
    int note=0, channel=0, forcedRemaining=0;
    bool keyDown=false, released=false;
  };
  struct EffectDeleter { void operator()(ConcertEffects* value) const {concert_effects_destroy(value);} };
  std::shared_ptr<const SampleBank> mBank;
  std::array<Voice,kVoices> mVoices{};
  std::array<Voice,kTails> mTails{};
  std::array<MidiEvent,kEvents> mEvents{};
  std::array<std::unique_ptr<ConcertEffects,EffectDeleter>,3> mEffects;
  std::array<bool,16> mSustain{};
  std::array<double,16> mBend{},mVolume{},mExpression{},mSoft{};
  Controls mControls;
 MonoPerformance mMono;
  std::array<double,3> mWeights{{1,0,0}};
  unsigned mEventCount=0;
  uint64_t mAge=0;
  bool mOverflow=false;
  double mRate=48000, mControlIncrement=0, mNativeAudioIncrement=1, mSmoothing=0, mOutput=0.5, mOutputTarget=0.5;
  void Midi(const MidiEvent& event) noexcept;
  void NoteOn(int note,int velocity,int channel,int previousPitch=-1) noexcept;
 void SelectMono(int note,int velocity,int channel,bool connected) noexcept;
  void Release(Voice& voice) noexcept;
  void Tail(Voice& voice) noexcept;
  void RenderVoice(Voice& voice,double& left,double& right) noexcept;
  void Render(float* left,float* right,int frames) noexcept;
};
}
