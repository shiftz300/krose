#pragma once
#include <atomic>
#include <cstdint>
namespace krose::storage {
class ParameterTransaction {
public:
  explicit ParameterTransaction(std::atomic<uint64_t> &generation) : mGeneration(generation) {
    mGeneration.fetch_add(1, std::memory_order_acq_rel);
  }
  // Low word counts writers; high word advances when any writer completes.
  // Overlapping or nested restores cannot accidentally expose an even version.
  ~ParameterTransaction() { mGeneration.fetch_add((uint64_t(1) << 32) - 1, std::memory_order_release); }
private:
  std::atomic<uint64_t> &mGeneration;
};
}
