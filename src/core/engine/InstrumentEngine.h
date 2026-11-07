#pragma once
#include "engine/PianoEngine.h"
#include "effects/OutputSafety.h"
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
  void EnableMonitoring(bool enabled) noexcept {
    mConcert.Monitor().Enable(enabled);
    mFactory.Monitor().Enable(enabled);
  }
  unsigned ReadVisual(unsigned slot, FxVisualSample *output, unsigned capacity) noexcept {
    std::array<FxVisualSample, FxMonitor::kCapacity> other;
    capacity = std::min(capacity, unsigned(other.size()));
    const auto a = mConcert.Monitor().Read(slot, output, capacity);
    const auto b = mFactory.Monitor().Read(slot, other.data(), capacity);
    for (unsigned i = a; i < b; ++i) output[i] = {};
    for (unsigned i = 0; i < b; ++i) {
      output[i].input += other[i].input;
      output[i].left += other[i].left;
      output[i].right += other[i].right;
      output[i].reduction = std::max(output[i].reduction, other[i].reduction);
    }
    return std::max(a, b);
  }
  float OutputPeak() const noexcept { return mSafety.Peak(); }
  float OutputReduction() const noexcept { return mSafety.Reduction(); }
  std::array<float, 2> FxPeaks() const noexcept {
    if (mOfflineLoadFailed)
      return {};
    return {mConcert.FxPeaks()[0] + mFactory.FxPeaks()[0],
            mConcert.FxPeaks()[1] + mFactory.FxPeaks()[1]};
  }

private:
  std::unique_ptr<SampleLoader> mLoader;
  const SampleResidency *mResidency = nullptr;
  Arpeggiator mArp;
  OutputSafety mSafety;
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
