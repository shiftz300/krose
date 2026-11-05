#pragma once
#include "engine/PianoEngine.h"
#include "engine/ProgramEngine.h"
#include "midi/Arpeggiator.h"
#include "midi/EventQueue.h"
#include "samples/SampleLoader.h"
namespace segrand {
// Routes MIDI/arp, Concert and factory playback, and immutable sample publication.
// Loading and ownership reclamation belong to the worker.
class InstrumentEngine {
public:
  InstrumentEngine(std::shared_ptr<const SampleBank> concert,
                   std::shared_ptr<const ProgramLibrary> factory);
  void Prepare(double rate);
  void SetControls(const Controls &controls, bool offline = false);
  void RequestProgram(int program) noexcept;
  bool SamplesReady(int program) const noexcept { return !mLoader || mLoader->ReadyFor(program); }
  int CurrentProgram() const noexcept { return mProgram; }
  int FailedProgram() const noexcept { return mLoader ? mLoader->FailedProgram() : -1; }
  size_t ResidentBytes() const noexcept { return mLoader ? mLoader->ResidentBytes() : 0; }
  void SetArpeggiator(const ArpControls &controls) noexcept { mArp.SetControls(controls); }
  void SetTransport(Transport transport) noexcept { mArp.SetTransport(transport); }
  double Tempo() const noexcept { return mArp.Tempo(); }
  void Queue(MidiEvent event) noexcept;
  void Process(float *left, float *right, int frames) noexcept;
  void Panic() noexcept;
  unsigned ActiveVoices() const noexcept;

private:
  std::unique_ptr<SampleLoader> mLoader;
  const SampleResidency *mResidency = nullptr;
  Arpeggiator mArp;
  PianoEngine mConcert;
  ProgramEngine mFactory;
  EventQueue<PianoEngine::kEvents> mEvents;
  unsigned mProgramCount = 0;
  int mProgram = 0;
  bool mOfflineLoadFailed = false;
  bool mRetirePending = false;
  double mPan = 0, mPanTarget = 0, mPanSmooth = 1;
};
} // namespace segrand
