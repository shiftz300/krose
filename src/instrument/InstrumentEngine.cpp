#include "InstrumentEngine.h"
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
void InstrumentEngine::SetControls(const Controls &controls, bool offline) {
  mPanTarget = std::clamp(controls.pan, -64, 63) / (controls.pan < 0 ? 64.0 : 63.0);
  const int program = std::clamp(controls.program, 0, int(mProgramCount) - 1);
  RequestProgram(program);
  const SampleResidency *ready = mResidency;
  if (mLoader)
    ready = (offline && program != mProgram) ? mLoader->Wait(program) : mLoader->Acquire(program);
  mOfflineLoadFailed = offline && mLoader && !ready;
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
    mResidency = ready;
    if (program) {
      mFactory.SetSamples(ready);
      mFactory.SetProgram(unsigned(program - 1));
    } else
      mConcert.SetSamples(ready);
  }
  mConcert.SetControls(controls);
  mFactory.SetControls(controls);
}
void InstrumentEngine::Queue(MidiEvent event) noexcept {
  if (mEventCount == mEvents.size()) {
    mOverflow = true;
    return;
  }
  event.offset = std::max(0, event.offset);
  unsigned index = mEventCount++;
  while (index && mEvents[index - 1].offset > event.offset) {
    mEvents[index] = mEvents[index - 1];
    --index;
  }
  mEvents[index] = event;
}
void InstrumentEngine::Panic() noexcept {
  mArp.Reset();
  mConcert.Panic();
  mFactory.Panic();
  mEventCount = 0;
  mOverflow = false;
  if (mLoader) {
    std::array<bool, SampleLoader::kSlots> used{};
    if (mResidency)
      used[mResidency->slot] = true;
    mLoader->RetireUnused(used);
  }
}
unsigned InstrumentEngine::ActiveVoices() const noexcept {
  return mFactory.ActiveVoices() + mConcert.ActiveVoices();
}
void InstrumentEngine::Process(float *left, float *right, int frames) noexcept {
  if (frames <= 0 || !left || !right)
    return;
  if (mOfflineLoadFailed) {
    mEventCount = 0;
    std::fill(left, left + frames, 0);
    std::fill(right, right + frames, 0);
    return;
  }
  // Bound generated MIDI per engine call even for very large offline blocks.
  if (frames > 256) {
    for (int at = 0; at < frames; at += 256)
      Process(left + at, right + at, std::min(256, frames - at));
    return;
  }
  if (mOverflow)
    Panic();
  unsigned consumed = 0;
  while (consumed < mEventCount && mEvents[consumed].offset < frames)
    ++consumed;
  mArp.Process(frames, mEvents.data(), consumed, this, [](void *context, MidiEvent event) {
    auto &self = *static_cast<InstrumentEngine *>(context);
    const bool noteOn = (event.status & 240) == 0x90 && event.data2;
    if (self.mProgram || !noteOn)
      self.mFactory.Queue(event);
    if (!self.mProgram || !noteOn)
      self.mConcert.Queue(event);
  });
  for (unsigned i = consumed; i < mEventCount; ++i) {
    mEvents[i - consumed] = mEvents[i];
    mEvents[i - consumed].offset -= frames;
  }
  mEventCount -= consumed;
  std::array<float, 256> otherLeft{}, otherRight{};
  mConcert.Process(left, right, frames);
  mFactory.Process(otherLeft.data(), otherRight.data(), frames);
  for (int i = 0; i < frames; ++i) {
    mPan += mPanSmooth * (mPanTarget - mPan);
    left[i] = (left[i] + otherLeft[i]) * (1 - std::max(mPan, 0.0));
    right[i] = (right[i] + otherRight[i]) * (1 + std::min(mPan, 0.0));
  }
  if (mLoader) {
    std::array<bool, SampleLoader::kSlots> used{};
    if (mResidency)
      used[mResidency->slot] = true;
    mFactory.MarkSamples(used.data());
    mConcert.MarkSamples(used.data());
    mLoader->RetireUnused(used);
  }
}
} // namespace segrand
