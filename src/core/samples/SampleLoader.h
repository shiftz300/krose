#pragma once
#include "samples/ProgramLibrary.h"
#include "samples/SampleResidency.h"
#include <array>
#include <atomic>
#include <thread>
namespace segrand {
// More slots than all Factory (128+32) and Concert (64+16) voices, plus handoff.
// Only this worker owns/frees snapshots. The audio thread publishes their liveness.
class SampleLoader {
public:
  static constexpr unsigned kSlots = 256;
  SampleLoader(std::string concertPath, std::shared_ptr<const ProgramLibrary> library);
  ~SampleLoader();
  void Request(int program) noexcept {
    if (mRequested.exchange(program, std::memory_order_acq_rel) != program) {
      mFailed.store(-1, std::memory_order_release);
      mReadyProgram.store(-1, std::memory_order_release);
    }
  }
  const SampleResidency *Acquire(int program) noexcept;
  const SampleResidency *Wait(int program); // Construction/offline rendering only.
  void RetireUnused(const std::array<bool, kSlots> &used) noexcept;
  bool ReadyFor(int program) const noexcept {
    return mReadyProgram.load(std::memory_order_acquire) == program;
  }
  int FailedProgram() const noexcept { return mFailed.load(std::memory_order_acquire); }
  size_t ResidentBytes() const noexcept { return mBytes.load(std::memory_order_relaxed); }

private:
  enum Status { Free, Loading, Ready, InUse, Retired };
  static_assert(std::atomic<Status>::is_always_lock_free && std::atomic<int>::is_always_lock_free,
                "Audio publication must use lock-free atomics");
  struct Slot {
    std::atomic<Status> state{Free};
    std::unique_ptr<SampleResidency> data;
  };
  std::array<Slot, kSlots> mSlots;
  std::string mConcertPath;
  std::shared_ptr<const ProgramLibrary> mLibrary;
  std::atomic<int> mRequested{0}, mFailed{-1}, mReadyProgram{-1};
  std::atomic<bool> mStop{false};
  std::atomic<size_t> mBytes{0};
  std::thread mThread;
  void Run();
};
} // namespace segrand
