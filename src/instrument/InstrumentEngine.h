#pragma once
#include "PianoEngine.h"
#include "ProgramEngine.h"
namespace segrand {
// Migration facade: preserves the accepted Concert path and routes factory
// Programs through the shared library. Owns no per-instance PCM copies.
class InstrumentEngine {
public:
 InstrumentEngine(std::shared_ptr<const SampleBank> concert,std::shared_ptr<const ProgramLibrary> factory);
 void Prepare(double rate);
 void SetControls(const Controls& controls);
 void Queue(MidiEvent event) noexcept;
 void Process(float* left,float* right,int frames) noexcept;
 void Panic() noexcept;
 unsigned ActiveVoices() const noexcept;
private:
 PianoEngine mConcert;
 ProgramEngine mFactory;
 std::array<MidiEvent,PianoEngine::kEvents> mEvents{};
 unsigned mEventCount=0,mFade=0,mProgramCount=0;
 int mProgram=0;
 bool mOverflow=false;
 std::array<float,2> mLast{},mFrom{};
};
}
