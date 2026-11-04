#pragma once
#include "PCM24.h"
#include <memory>
#include <vector>
namespace segrand {
struct SampleBank;
// Published once by the loader. Audio uses raw views; destruction belongs to the worker.
struct SampleResidency {
  unsigned slot = 0;
  int program = 0;
  std::shared_ptr<const SampleBank> concert;
  std::vector<std::shared_ptr<const PCM24>> factory;
};
} // namespace segrand
