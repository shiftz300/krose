#include "samples/SampleLoader.h"
#include "samples/SampleBank.h"
#include <chrono>
#include <set>
#include <stdexcept>
namespace segrand {
SampleLoader::SampleLoader(std::string path, std::shared_ptr<const ProgramLibrary> library)
    : mConcertPath(std::move(path)), mLibrary(std::move(library)), mThread([this] { Run(); }) {}
SampleLoader::~SampleLoader() {
  mStop.store(true, std::memory_order_release);
  mThread.join();
}
const SampleResidency *SampleLoader::Acquire(int program) noexcept {
  const SampleResidency *result = nullptr;
  for (auto &slot : mSlots) {
    const auto state = slot.state.load(std::memory_order_acquire);
    if (state == Ready) {
      auto expected = Ready;
      if (!slot.state.compare_exchange_strong(expected, InUse, std::memory_order_acq_rel))
        continue;
      if (slot.data->program == program && !result) {
        result = slot.data.get();
      } else
        slot.state.store(Retired, std::memory_order_release);
    } else if (state == InUse && slot.data->program == program)
      result = slot.data.get();
  }
  return result;
}
const SampleResidency *SampleLoader::Wait(int program) {
  Request(program);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(30);
  for (;;) {
    if (auto result = Acquire(program))
      return result;
    if (FailedProgram() == program || std::chrono::steady_clock::now() > deadline)
      return nullptr;
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
}
void SampleLoader::RetireUnused(const std::array<bool, kSlots> &used) noexcept {
  for (unsigned i = 0; i < kSlots; ++i)
    if (!used[i] && mSlots[i].state.load(std::memory_order_acquire) == InUse)
      mSlots[i].state.store(Retired, std::memory_order_release);
}
void SampleLoader::Run() {
  while (!mStop.load(std::memory_order_acquire)) {
    bool changed = false;
    for (auto &slot : mSlots)
      if (slot.state.load(std::memory_order_acquire) == Retired) {
        slot.data.reset();
        slot.state.store(Free, std::memory_order_release);
        changed = true;
      }
    const int requested = mRequested.load(std::memory_order_acquire);
    // The host may be stopped: reclaim cancelled, unclaimed results even when
    // no audio callbacks run. CAS competes with Acquire; an InUse set is pinned.
    for (auto &slot : mSlots)
      if (slot.state.load(std::memory_order_acquire) == Ready && slot.data->program != requested) {
        auto expected = Ready;
        if (slot.state.compare_exchange_strong(expected, Loading, std::memory_order_acq_rel)) {
          slot.data.reset();
          slot.state.store(Free, std::memory_order_release);
          changed = true;
        }
      }
    if (requested != mFailed.load(std::memory_order_acquire)) {
      // Ready/InUse snapshots are immutable; state transitions never modify their contents.
      bool existing = false;
      for (const auto &slot : mSlots) {
        auto s = slot.state.load(std::memory_order_acquire);
        if ((s == Ready || s == InUse) && slot.data->program == requested) {
          existing = true;
          break;
        }
      }
      if (existing)
        mReadyProgram.store(requested, std::memory_order_release);
      if (!existing)
        for (unsigned i = 0; i < kSlots; ++i)
          if (mSlots[i].state.load(std::memory_order_acquire) == Free) {
            changed = true;
            auto &slot = mSlots[i];
            slot.state.store(Loading, std::memory_order_relaxed);
            try {
              auto data = std::make_unique<SampleResidency>();
              data->slot = i;
              data->program = requested;
              if (requested == 0)
                data->concert = SampleBank::Load(mConcertPath);
              else
                data->factory = mLibrary->LoadProgram(unsigned(requested - 1));
              if (mRequested.load(std::memory_order_acquire) == requested) {
                slot.data = std::move(data);
                slot.state.store(Ready, std::memory_order_release);
                mFailed.store(-1, std::memory_order_release);
                mReadyProgram.store(requested, std::memory_order_release);
              } else
                slot.state.store(Free, std::memory_order_release);
            } catch (const std::exception &) {
              slot.state.store(Free, std::memory_order_release);
              mFailed.store(requested, std::memory_order_release);
            }
            break;
          }
    }
    if (changed) {
      size_t bytes = mLibrary->ResidentBytes();
      std::set<const SampleBank *> banks;
      for (const auto &slot : mSlots)
        if (slot.data && slot.data->concert && banks.insert(slot.data->concert.get()).second)
          for (const auto &layer : slot.data->concert->layers)
            for (const auto &sample : layer)
              bytes += sample.stereo.storageBytes();
      mBytes.store(bytes, std::memory_order_relaxed);
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
}
} // namespace segrand
