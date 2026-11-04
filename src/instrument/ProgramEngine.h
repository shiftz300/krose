#pragma once
#include "Performance.h"
#include "EngineTypes.h"
#include "NativeFilter.h"
#include "ProgramLibrary.h"
#include "concert_effects.h"
#include <array>
#include <memory>
namespace segrand {
struct SampleResidency;
class ProgramEngine {
public:
 static constexpr unsigned kVoices=128,kTails=32,kEvents=2048;
 explicit ProgramEngine(std::shared_ptr<const ProgramLibrary> library);
 ~ProgramEngine();
 void Prepare(double rate);
 void SetProgram(unsigned index) noexcept;
 void SetControls(const Controls& controls) noexcept;
 void Queue(MidiEvent event) noexcept;
 void Process(float* left,float* right,int frames) noexcept;
 void Panic() noexcept;
 unsigned ActiveVoices() const noexcept;
 void SetSamples(const SampleResidency* samples) noexcept {mResidency=samples;}
 void MarkSamples(bool* used) const noexcept;
 void Deactivate() noexcept;
private:
 struct Voice {
  const SampleResidency* residency=nullptr;
  PitchGlide glide;
  double glideRatio=1;
  const ProgramRegion* region=nullptr;
  const InstrumentProgram* program=nullptr;
  std::array<double,2> position{},step{};
  NativeVoice amplitude;
  NativeSlew slew;
  NativeFilter filter;
  double phase=0,audioPhase=0,velocityTrim=1,panL=1,panR=1,ageSeconds=0;
  uint64_t age=0;
  int note=0,channel=0,forced=0;
  bool down=false,released=false;
 };
 struct DeleteEffect{void operator()(ConcertEffects* p) const{concert_effects_destroy(p);}};
 std::shared_ptr<const ProgramLibrary> mLibrary;
 const SampleResidency* mResidency=nullptr;
 std::unique_ptr<ConcertEffects,DeleteEffect> mRoom;
 std::array<Voice,kVoices> mVoices{};
 std::array<Voice,kTails> mTails{};
 std::array<MidiEvent,kEvents> mEvents{};
 std::array<bool,16> mSustain{};
 std::array<double,16> mBend{},mVolume{},mExpression{},mSoft{};
 Controls mControls;
 MonoPerformance mMono;
 double mRate=48000,mOutput=0.5,mTarget=0.5,mSmooth=0;
 unsigned mProgram=0,mEventCount=0;
 uint64_t mAge=0;
 bool mOverflow=false;
 void Midi(const MidiEvent& event) noexcept;
 void NoteOn(int note,int velocity,int channel,int previousPitch=-1) noexcept;
 void SelectMono(int note,int velocity,int channel,bool connected) noexcept;
 void Release(Voice& voice) noexcept;
 void Tail(Voice& voice) noexcept;
 void RenderVoice(Voice& voice,double& left,double& right) noexcept;
 void Render(float* left,float* right,int frames) noexcept;
};
}
