#include "ParameterTransaction.h"
#include "../KrosePlugin.h"
#include "UserPreset.h"

void KrosePlugin::CaptureComparison() {
  mComparisonNeedsCapture.store(false, std::memory_order_relaxed);
  for (int id = 0; id < kNumParams; ++id)
    mComparison[id] = GetParam(id)->GetNormalized();
  mComparisonReady = true;
  mComparing = false;
}
void KrosePlugin::ApplySound(const std::array<double, kNumParams> &values) {
  krose::storage::ParameterTransaction transaction(mSoundGeneration);
  for (int id = 0; id < kNumParams; ++id)
    if (krose::storage::SoundParameter(id) && GetParam(id)->GetNormalized() != values[id]) {
      BeginInformHostOfParamChangeFromUI(id);
      SendParameterValueFromUI(id, values[id]);
      EndInformHostOfParamChangeFromUI(id);
    }
}
void KrosePlugin::ToggleComparison() {
  if (!mComparisonReady) {
    CaptureComparison();
    return;
  }
  const auto reference = mComparison;
  for (int id = 0; id < kNumParams; ++id)
    mComparison[id] = GetParam(id)->GetNormalized();
  ApplySound(reference);
  mComparing = !mComparing;
}
bool KrosePlugin::SaveUserPreset(const std::string &path) {
  try {
    krose::storage::PresetValues values;
    for (int id = 0; id < kNumParams; ++id)
      values[id] = GetParam(id)->GetNormalized();
    krose::storage::WriteJson(std::filesystem::u8path(path), krose::storage::EncodePreset(values));
    CaptureComparison();
    return true;
  } catch (const std::exception &) {
    return false;
  }
}
bool KrosePlugin::LoadUserPreset(const std::string &path) {
  try {
    const auto values = krose::storage::DecodePreset(krose::storage::ReadJson(std::filesystem::u8path(path)));
    ApplySound(values);
    CaptureComparison();
    return true;
  } catch (const std::exception &) {
    return false;
  }
}
