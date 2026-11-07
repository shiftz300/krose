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

void KrosePlugin::LoadFactoryEffects(int program) {
  const auto effects = mEngine->FactoryEffects(program);
  krose::storage::ParameterTransaction transaction(mSoundGeneration);
  const auto write = [&](int id, double value) { SetMidiParameter(MidiTargetForParameter(id), GetParam(id)->ToNormalized(value)); };
  // Tone Adjust values are relative to the selected Program, not global controls.
  for (int id = kParamCutoff; id <= kFilterRelease; ++id) write(id, 0);
  RestoreFactoryArp();
  for (unsigned slot = 0; slot < effects.slots.size(); ++slot) {
    const auto &effect = effects.slots[slot];
    write(kFxType1 + slot, effect.type);
    write(kFxOn1 + slot, effect.enabled);
    write(kFxAmount1 + slot, effect.amount);
    const int first = 0, end = segrand::kFxDetailCount;
    for (int detail = first; detail < end; ++detail) write(FxDetailParameter(slot, detail), effect.detail[detail]);
  }
}

void KrosePlugin::RestoreFactoryArp() {
  if (!mEngine) return;
  const auto arp = mEngine->FactoryArp(GetParam(kParamProgram)->Int());
  krose::storage::ParameterTransaction transaction(mSoundGeneration);
  const auto write = [&](int id, double value) { SetMidiParameter(MidiTargetForParameter(id), GetParam(id)->ToNormalized(value)); };
  write(kArpEnabled, arp.enabled); write(kArpLatch, arp.latch);
  write(kArpPattern, arp.pattern); write(kArpResolution, arp.resolution);
  write(kArpGate, arp.gate); write(kArpTempo, arp.tempo);
  write(kArpOctaves, arp.octaves); write(kArpSort, arp.sort); write(kArpKeySync, arp.keySync);
  write(kArpSwing, arp.swing); write(kArpVelocity, arp.velocity); write(kArpKeyboard, arp.keyboard);
}
