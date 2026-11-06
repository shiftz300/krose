#pragma once
#include "../Parameters.h"
#include "JsonFile.h"
#include <array>
#include <algorithm>
#include <cmath>

namespace krose::storage {
using PresetValues = std::array<double, kNumParams>;
inline bool SoundParameter(int id) { return id < kSW1Assign || id >= kFXBypass; }
inline PresetValues DecodePreset(const nlohmann::json &data) {
  if (!data.is_object() || data.value("format", "") != "krose-preset" ||
      !data.contains("version") || data["version"] != 1 || !data.contains("values") ||
      !data["values"].is_array() || data["values"].size() != kNumParams)
    throw std::runtime_error("Unsupported preset file");
  PresetValues values{};
  for (int id = 0; id < kNumParams; ++id) {
    if (!data["values"][id].is_number())
      throw std::runtime_error("Invalid preset value");
    values[id] = data["values"][id].get<double>();
    if (!std::isfinite(values[id]) || values[id] < -1e-9 || values[id] > 1 + 1e-9)
      throw std::runtime_error("Preset value outside range");
    values[id] = std::clamp(values[id], 0., 1.);
  }
  return values;
}
inline nlohmann::json EncodePreset(const PresetValues &values) {
  auto data = nlohmann::json{{"format", "krose-preset"}, {"version", 1}, {"values", values}};
  DecodePreset(data);
  return data;
}
} // namespace krose::storage
