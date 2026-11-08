#pragma once
#include "../Parameters.h"
#include "JsonFile.h"
#include <array>
#include <algorithm>
#include <cmath>

namespace krose::storage {
using PresetValues = std::array<double, kNumParams>;
inline bool SoundParameter(int id) { return id < kEGTarget && (id < kSW1Assign || id >= kFXBypass); }
inline PresetValues DecodePreset(const nlohmann::json &data) {
  if (!data.is_object() || data.value("format", "") != "krose-preset" ||
      !data.contains("version") || (data["version"] != 1 && data["version"] != 2 && data["version"] != 3 && data["version"] != 4) || !data.contains("values") ||
      !data["values"].is_array() || (data["values"].size() != kNumParams && data["values"].size() != kFxEditorRequest && data["values"].size() != kEGTarget && data["values"].size() != kArpSwing && data["values"].size() != kExtendedFxDetails))
    throw std::runtime_error("Unsupported preset file");
  PresetValues values{};
  for (int slot=0;slot<4;++slot) for(int detail=0;detail<segrand::kFxDetailCount;++detail) {
    const auto &spec=segrand::kFxValues[detail];
    values[FxDetailParameter(slot,detail)]=(spec.initial-spec.min)/(spec.max-spec.min);
  }
  values[kArpSwing] = .5; values[kArpVelocity] = 1;
  for (int id = 0; id < int(data["values"].size()); ++id) {
    if (!data["values"][id].is_number())
      throw std::runtime_error("Invalid preset value");
    values[id] = data["values"][id].get<double>();
    if (!std::isfinite(values[id]) || values[id] < -1e-9 || values[id] > 1 + 1e-9)
      throw std::runtime_error("Preset value outside range");
    values[id] = std::clamp(values[id], 0., 1.);
  }
  if (int(data["version"]) < 3) {
    values[kArpPattern] *= 4. / (segrand::kArpPatternCount - 1);
    values[kArpGate] *= 99. / 100.;
  }
  if (data["version"] == 1) {
    // V1 saved normalized values against the original, narrower FX ranges.
    // Translate through physical units, preserving the sound of old files.
    for (int slot = 0; slot < 4; ++slot) {
      const int first = slot < 2 ? 0 : int(segrand::kDepth);
      const int end = slot < 2 ? int(segrand::kDepth) : int(segrand::kGraphicGain);
      for (int detail = first; detail < end; ++detail) {
        const auto &spec = segrand::kFxValues[detail];
        double oldMax = spec.max;
        if (detail < segrand::kThreshold && detail % 3 == 1) oldMax = 18;
        if (detail < segrand::kThreshold && detail % 3 == 2) oldMax = 10;
        switch (detail) {
          case segrand::kRatio: oldMax = 20; break;
          case segrand::kAttack: oldMax = 100; break;
          case segrand::kRelease: oldMax = 500; break;
          case segrand::kDrive: oldMax = 100; break;
          case segrand::kDelayLeft: case segrand::kDelayRight: oldMax = 550; break;
          case segrand::kFeedback: oldMax = 90; break;
          case segrand::kDecay: oldMax = 6; break;
          default: break;
        }
        const int id = FxDetailParameter(slot, detail);
        values[id] *= (oldMax - spec.min) / (spec.max - spec.min);
      }
    }
  }
  // V1..3 normalized type values used the old 7/6-entry lists.
  if (int(data["version"]) < 4) for (int slot=0;slot<4;++slot)
    values[kFxType1+slot] *= double(slot<2 ? 6 : 5) /
        double((slot<2 ? segrand::kInsertTypes.size() : segrand::kSendTypes.size())-1);
  return values;
}
inline nlohmann::json EncodePreset(const PresetValues &values) {
  auto data = nlohmann::json{{"format", "krose-preset"}, {"version", 4}, {"values", values}};
  DecodePreset(data);
  return data;
}
} // namespace krose::storage
