#pragma once
#include "samples/ProgramLibrary.h"
#include <memory>
namespace segrand {
struct SampleBank;
// Published once by the loader. Audio uses raw views; destruction belongs to the worker.
struct SampleResidency {
  unsigned slot = 0;
  int program = 0;
  std::shared_ptr<const SampleBank> concert;
  std::shared_ptr<const SampleWindow> factory;
};
} // namespace segrand
