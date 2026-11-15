#include "ParameterTransaction.h"
#include "../KrosePlugin.h"
#include "UserPreset.h"

namespace {
constexpr uint32_t kMappingMagic = 0x50414d4b;
} // namespace

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
    if (krose::storage::SoundParameter(id) && GetParam(id)->GetNormalized() != values[id])
      SendUiParameter(id, values[id]);
}
void KrosePlugin::SendUiParameter(int id, double normalized) {
  BeginInformHostOfParamChangeFromUI(id);
  SendParameterValueFromUI(id, normalized);
  EndInformHostOfParamChangeFromUI(id);
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
    auto data = krose::storage::EncodePreset(values);
    const int selection = GetParam(kPcgProgram)->Int();
    if (selection)
      data["pcg_program"] = PcgSelectionFingerprint(selection);
    else
      data["values"].erase(data["values"].begin() + kPcgProgram);
    krose::storage::WriteJson(std::filesystem::u8path(path), data);
    CaptureComparison();
    return true;
  } catch (const std::exception &) {
    return false;
  }
}
bool KrosePlugin::LoadUserPreset(const std::string &path) {
  try {
    const auto data = krose::storage::ReadJson(std::filesystem::u8path(path));
    auto values = krose::storage::DecodePreset(data);
    const auto *param = GetParam(kPcgProgram);
    const int selection = int(std::round(param->FromNormalized(values[kPcgProgram])));
    if (selection) {
      const auto fingerprint = data.find("pcg_program");
      if (fingerprint == data.end() || !fingerprint->is_number_unsigned()) return false;
      values[kPcgProgram] = param->ToNormalized(ResolvePcgSelection(fingerprint->get<uint64_t>(), selection));
    }
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
  // Tone Adjust values are relative to the selected Program, not global controls.
  for (int id = kParamCutoff; id <= kFilterRelease; ++id) SetMidiParameterValue(id, 0);
  RestoreFactoryArp();
  for (unsigned slot = 0; slot < effects.slots.size(); ++slot) {
    const auto &effect = effects.slots[slot];
    SetMidiParameterValue(kFxType1 + slot, effect.type);
    SetMidiParameterValue(kFxOn1 + slot, effect.enabled);
    SetMidiParameterValue(kFxAmount1 + slot, effect.amount);
    for (int detail = 0; detail < segrand::kFxDetailCount; ++detail)
      SetMidiParameterValue(FxDetailParameter(slot, detail), effect.detail[detail]);
  }
}

void KrosePlugin::RestoreFactoryArp() {
  if (!mEngine) return;
  const auto arp = mEngine->FactoryArp(EngineProgram(SelectedProgram()));
  krose::storage::ParameterTransaction transaction(mSoundGeneration);
  SetMidiParameterValue(kArpEnabled, arp.enabled); SetMidiParameterValue(kArpLatch, arp.latch);
  SetMidiParameterValue(kArpPattern, arp.pattern); SetMidiParameterValue(kArpResolution, arp.resolution);
  SetMidiParameterValue(kArpGate, arp.gate); SetMidiParameterValue(kArpTempo, arp.tempo);
  SetMidiParameterValue(kArpOctaves, arp.octaves); SetMidiParameterValue(kArpSort, arp.sort); SetMidiParameterValue(kArpKeySync, arp.keySync);
  SetMidiParameterValue(kArpSwing, arp.swing); SetMidiParameterValue(kArpVelocity, arp.velocity); SetMidiParameterValue(kArpKeyboard, arp.keyboard);
}

bool KrosePlugin::SerializeState(IByteChunk &chunk) const {
  const auto generation = mSoundGeneration.load(std::memory_order_acquire);
  if (uint32_t(generation)) return false;
  std::array<bool, kNumParams> momentary{};
  for (unsigned slot = 0; slot < krose::midi::ControllerMap::kSlots; ++slot) {
    const auto b = mMidiMap.Get(slot);
    if (b.source != krose::midi::Source::Off && b.mode == krose::midi::Mode::Momentary &&
        ParameterForMidiTarget(b.target) >= 0)
      momentary[ParameterForMidiTarget(b.target)] = true;
  }
  const int pcg = momentary[kPcgProgram] ? 0 : GetParam(kPcgProgram)->Int();
  const uint64_t fingerprint = PcgSelectionFingerprint(pcg);
  const int parameterCount = pcg ? int(kNumParams) : int(kPcgProgram);
  for (int id = 0; id < parameterCount; ++id) {
    double value = GetParam(id)->Value();
    if (momentary[id])
      value = GetParam(id)->FromNormalized(0.);
    if ((id == kSW1State && GetParam(kSW1Mode)->Int()) ||
        (id == kSW2State && GetParam(kSW2Mode)->Int()))
      value = 0;
    chunk.Put(&value);
  }
  chunk.Put(&kMappingMagic);
  const uint32_t version = pcg ? 2 : 1;
  chunk.Put(&version);
  const uint32_t profile = mMidiProfile.load(), count = krose::midi::ControllerMap::kSlots;
  chunk.Put(&profile);
  chunk.Put(&count);
  for (unsigned i = 0; i < count; ++i) {
    const uint64_t word = mMidiMap.Get(i).Encode();
    chunk.Put(&word);
  }
  if (pcg) chunk.Put(&fingerprint);
  return mSoundGeneration.load(std::memory_order_acquire) == generation;
}
int KrosePlugin::UnserializeState(const IByteChunk &chunk, int start) {
  krose::storage::ParameterTransaction transaction(mSoundGeneration);
  if (start < 0 || start > chunk.Size())
    return -1;
  const int available = chunk.Size() - start;
  const auto validParameters = [&](int count) {
    if (available < count * int(sizeof(double))) return false;
    for (int id = 0; id < count; ++id) {
      double value = 0;
      const double margin = std::max(1., GetParam(id)->GetRange()) * 1e-9;
      if (chunk.Get(&value, start + id * int(sizeof(double))) < 0 ||
          !std::isfinite(value) || value < GetParam(id)->GetMin() - margin ||
          value > GetParam(id)->GetMax() + margin)
        return false;
    }
    return true;
  };
  const auto restoreParameters = [&](int count, bool keepMappings) {
    if (count == kNumParams) return UnserializeParams(chunk, start);
    IByteChunk upgraded;
    upgraded.PutBytes(chunk.GetData() + start, count * int(sizeof(double)));
    for (int id = count; id < kNumParams; ++id) {
      const auto *parameter = GetParam(id);
      const double value = keepMappings && id >= kSW1Assign && id < kFXBypass
                               ? parameter->Value() : parameter->GetDefault();
      upgraded.Put(&value);
    }
    return UnserializeParams(upgraded, 0);
  };
  constexpr int legacyCounts[] = {6, 17, 19, 29, kNumMidiParameters, kFxOn1, kArpSwing,
                                  kExtendedFxDetails, kEGTarget, kFxEditorRequest,
                                  kFilterEGIntensity, kPcgProgram};
  for (int count : legacyCounts) {
    const int bytes = count * int(sizeof(double));
    if (available != bytes && available != bytes + int(sizeof(int32_t)))
      continue;
    if (!validParameters(count) || restoreParameters(count, true) < 0)
      return -1;
    return start + bytes;
  }
  const int parameters = kNumParams * int(sizeof(double));
  if (available == parameters || available == parameters + 4)
    return validParameters(kNumParams) ? UnserializeParams(chunk, start) : -1;
  constexpr int mappingBytes = 16 + krose::midi::ControllerMap::kSlots * int(sizeof(uint64_t));
  int storedParams = kNumParams;
  for (int oldCount : legacyCounts) {
    if (oldCount < kNumMidiParameters) continue;
    const int bytes = oldCount * int(sizeof(double)) + mappingBytes;
    if (available == bytes || available == bytes + 4) {
      storedParams = oldCount;
      break;
    }
  }
  const int storedBytes = storedParams * int(sizeof(double));
  const bool pcgState = storedParams == kNumParams && available >= storedBytes + mappingBytes + 8;
  const int expected = storedBytes + mappingBytes + (pcgState ? 8 : 0);
  if ((available != expected && available != expected + 4) ||
      !validParameters(storedParams))
    return -1;
  int pos = start + storedBytes;
  uint32_t magic = 0, version = 0, profile = 0, count = 0;
  if ((pos = chunk.Get(&magic, pos)) < 0 || (pos = chunk.Get(&version, pos)) < 0 ||
      (pos = chunk.Get(&profile, pos)) < 0 || (pos = chunk.Get(&count, pos)) < 0 ||
      magic != kMappingMagic || version != (pcgState ? 2u : 1u) || profile >= 4 ||
      count != krose::midi::ControllerMap::kSlots)
    return -1;
  std::array<krose::midi::Binding, krose::midi::ControllerMap::kSlots> bindings;
  for (auto &b : bindings) {
    uint64_t word = 0;
    if ((pos = chunk.Get(&word, pos)) < 0 || word >> 38)
      return -1;
    b = krose::midi::Binding::Decode(word);
    if (!b.Valid(kMapTargets))
      return -1;
  }
  if (pcgState) {
    uint64_t fingerprint = 0;
    double storedSelection = 0;
    const int selectionOffset = int(kPcgProgram) * int(sizeof(double));
    if ((pos = chunk.Get(&fingerprint, pos)) < 0 ||
        chunk.Get(&storedSelection, start + selectionOffset) < 0 ||
        storedSelection <= 0 || storedSelection != std::round(storedSelection))
      return -1;
    IByteChunk upgraded;
    upgraded.PutBytes(chunk.GetData() + start, selectionOffset);
    const double selection = ResolvePcgSelection(fingerprint, int(storedSelection));
    upgraded.Put(&selection);
    if (UnserializeParams(upgraded, 0) < 0) return -1;
  } else if (restoreParameters(storedParams, false) < 0) {
    return -1;
  }
  for (unsigned i = 0; i < count; ++i)
    mMidiMap.Set(i, bindings[i]);
  mMidiProfile.store(profile);
  mMidiMap.CancelLearn();
  mNotifiedMapRevision.store(mMidiMap.Revision());
  return pos;
}
