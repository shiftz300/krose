#include "engine/InstrumentEngine.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace segrand {
InstrumentEngine::InstrumentEngine(std::shared_ptr<const SampleBank> concert,
                                   std::shared_ptr<const ProgramLibrary> factory)
    : mConcert(concert), mFactory(factory), mProgramCount(unsigned(factory->programs.size()) + 1) {
  if (factory->OnDemand()) {
    mLoader = std::make_unique<SampleLoader>(concert->path, factory);
    mResidency = mLoader->Wait(0);
    if (!mResidency)
      throw std::runtime_error("Cannot load initial Concert samples");
    mConcert.SetSamples(mResidency);
  }
}
void InstrumentEngine::Prepare(double rate) {
  mArp.Prepare(rate);
  mConcert.Prepare(rate);
  mFactory.Prepare(rate);
  mPanSmooth = 1 - std::exp(-1 / (rate * .01));
  mPan = mPanTarget;
  Panic();
}
void InstrumentEngine::RequestProgram(int program) noexcept {
  if (mLoader)
    mLoader->Request(std::clamp(program, 0, int(mProgramCount) - 1));
}
bool InstrumentEngine::SetControls(const Controls &controls, bool offline) {
  const int program = std::clamp(controls.program, 0, int(mProgramCount) - 1);
  RequestProgram(program);
  const SampleResidency *ready = mResidency;
  // The current immutable snapshot is already pinned. Poll only a pending
  // change; unchanged controls need no 256-slot acquisition scan per block.
  if (mLoader && program != mProgram)
    ready = offline ? mLoader->Wait(program) : mLoader->Acquire(program);
  mOfflineLoadFailed = offline && mLoader && !ready;
  if (program != mProgram && mLoader && !ready) return false;
  mPanTarget = std::clamp(controls.pan, -64, 63) / (controls.pan < 0 ? 64.0 : 63.0);
  if (program != mProgram && (!mLoader || ready)) {
    if (mArp.Controls().enabled) {
      mArp.Reset();
      mConcert.Deactivate();
      mFactory.Deactivate();
    }
    if (!mProgram || !program) {
      if (mProgram)
        mFactory.Deactivate();
      else
        mConcert.Deactivate();
    }
    mProgram = program;
    mRetirePending = mLoader && mResidency != ready;
    mResidency = ready;
    if (program) {
      mFactory.SetSamples(ready);
      mFactory.SetProgram(unsigned(program - 1));
    } else
      mConcert.SetSamples(ready);
  }
  mConcert.SetControls(controls);
  mFactory.SetControls(controls);
  return true;
}
void InstrumentEngine::Queue(MidiEvent event) noexcept { mEvents.Push(event, false); }

void InstrumentEngine::Panic() noexcept {
  mArp.Reset();
  mSafety.Reset();
  mConcert.Panic();
  mFactory.Panic();
  mEvents.Clear();
  if (mRetirePending) {
    std::array<bool, SampleLoader::kSlots> used{};
    if (mResidency)
      used[mResidency->slot] = true;
    mLoader->RetireUnused(used);
    mRetirePending = false;
  }
}
unsigned InstrumentEngine::ActiveVoices() const noexcept {
  return mFactory.ActiveVoices() + mConcert.ActiveVoices();
}
void InstrumentEngine::Process(float *left, float *right, int frames) noexcept {
  if (frames <= 0 || !left || !right)
    return;
  mSafety.ClearMeters();
  if (mOfflineLoadFailed) {
    mEvents.Discard();
    std::fill(left, left + frames, 0);
    std::fill(right, right + frames, 0);
    return;
  }
  // Bound generated MIDI per engine call even for very large offline blocks.
  if (frames > 256) {
    float peak = 0, reduction = 0;
    for (int at = 0; at < frames; at += 256) {
      Process(left + at, right + at, std::min(256, frames - at));
      peak = std::max(peak, mSafety.Peak());
      reduction = std::max(reduction, mSafety.Reduction());
    }
    mSafety.MergeMeters(peak, reduction);
    return;
  }
  if (mEvents.Overflowed())
    Panic();
  const unsigned consumed = mEvents.ReadyCount(frames);
  mArp.Process(frames, mEvents.Data(), consumed, this, [](void *context, MidiEvent event) {
    auto &self = *static_cast<InstrumentEngine *>(context);
    const bool noteOn = (event.status & 240) == 0x90 && event.data2;
    if (self.mProgram || !noteOn)
      self.mFactory.Queue(event);
    if (!self.mProgram || !noteOn)
      self.mConcert.Queue(event);
  });
  mEvents.Advance(consumed, frames);
  std::array<float, 256> otherLeft{}, otherRight{};
  mConcert.Process(left, right, frames);
  mFactory.SetTempo(mArp.Tempo());
  mFactory.Process(otherLeft.data(), otherRight.data(), frames);
  for (int i = 0; i < frames; ++i) {
    mPan += mPanSmooth * (mPanTarget - mPan);
    left[i] = (left[i] + otherLeft[i]) * (1 - std::max(mPan, 0.0));
    right[i] = (right[i] + otherRight[i]) * (1 + std::min(mPan, 0.0));
    mSafety.Process(left[i], right[i]);
  }
  // A single residency stays pinned. Scan only while old voices can still
  // reference samples from a previous program.
  if (mRetirePending) {
    std::array<bool, SampleLoader::kSlots> used{};
    if (mResidency)
      used[mResidency->slot] = true;
    mFactory.MarkSamples(used.data());
    mConcert.MarkSamples(used.data());
    mRetirePending = mLoader->RetireUnused(used) > 1;
  }
}
} // namespace segrand
