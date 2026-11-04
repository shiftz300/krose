#pragma once
#include "PianoEngine.h"
#include "Arpeggiator.h"
#include "ProgramEngine.h"
namespace segrand {
// Migration facade: preserves the accepted Concert path and routes factory
// Programs through the shared library. Owns no per-instance PCM copies.
class InstrumentEngine {
public:
 InstrumentEngine(std::shared_ptr<const SampleBank> concert,std::shared_ptr<const ProgramLibrary> factory);
 void Prepare(double rate);
 void SetControls(const Controls& controls);
 void SetArpeggiator(const ArpControls& controls) noexcept {mArp.SetControls(controls);}
 void SetTransport(Transport transport) noexcept {mArp.SetTransport(transport);}
 double Tempo() const noexcept {return mArp.Tempo();}
 void Queue(MidiEvent event) noexcept;
 void Process(float* left,float* right,int frames) noexcept;
 void Panic() noexcept;
 unsigned ActiveVoices() const noexcept;
private:
 Arpeggiator mArp;
 PianoEngine mConcert;
 ProgramEngine mFactory;
 std::array<MidiEvent,PianoEngine::kEvents> mEvents{};
 unsigned mEventCount=0,mFade=0,mProgramCount=0;
 int mProgram=0;
 bool mOverflow=false;
 double mPan=0,mPanTarget=0,mPanSmooth=1;
 std::array<float,2> mLast{},mFrom{};
};
}
