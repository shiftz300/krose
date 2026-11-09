#include "../storage/ParameterTransaction.h"
#include "../KrosePlugin.h"
#include "IPlugPaths.h"
#include "NativeData.h"
#include "../storage/JsonFile.h"
#include "json.hpp"
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
using Json = nlohmann::json;
namespace {
constexpr uint32_t kMappingMagic = 0x50414d4b, kMappingVersion = 1;
std::mutex settingsMutex;
std::filesystem::path SettingsPath() {
  if (const char *p = std::getenv("KROSE_MIDI_MAP_FILE"))
    return std::filesystem::u8path(p);
  WDL_String root;
  iplug::AppSupportPath(root);
  return std::filesystem::u8path(root.Get()) / "Krose" / "midi-mappings.json";
}
Json ReadSettings() {
  std::ifstream file(SettingsPath());
  if (!file) {
    if (std::filesystem::exists(SettingsPath()))
      throw std::runtime_error("Cannot read MIDI settings");
    return Json{{"version", 1}, {"profiles", Json::array()}};
  }
  auto value = krose::storage::ReadJson(SettingsPath());
  if (value.is_discarded() || !value.is_object() || !value.contains("version") || value["version"] != 1 ||
      !value.contains("profiles") || !value["profiles"].is_array())
    throw std::runtime_error("Invalid MIDI settings");
  return value;
}
constexpr int configIDs[] = {kSW1Assign,    kSW1Mode,       kSW2Assign,  kSW2Mode,
                             kInputChannel, kProgramChange, kClockSource};
} // namespace
void KrosePlugin::InitializeMidiMappings() {
  for (unsigned id = 0; id < kNumParams; ++id) {
    const auto p = GetParam(id);
    mMidiMap.SetStep(MidiTargetForParameter(id), p->GetRange() > 0 ? p->GetStep() / p->GetRange() : 1);
  }
  for (unsigned id = kNumMidiParameters; id < kNumMidiParameters + 3; ++id)
    mMidiMap.SetStep(id, 1);
  auto order = Json::parse(kNativeBrowser)["order"].get<std::vector<int>>();
  mNextPrograms.resize(order.size());
  mPreviousPrograms.resize(order.size());
  for (unsigned i = 0; i < order.size(); ++i) {
    mNextPrograms[order[i]] = order[(i + 1) % order.size()];
    mPreviousPrograms[order[i]] = order[(i + order.size() - 1) % order.size()];
  }
  StandardMidiMappings();
}
void KrosePlugin::StandardMidiMappings() {
  mMidiMap.Clear();
  const unsigned assignments[][2] = {{10, kParamPan},   {71, kParamResonance}, {74, kParamCutoff},
                                     {73, kAmpAttack},  {75, kAmpDecay},       {70, kAmpSustain},
                                     {72, kAmpRelease}, {91, kParamSpace}};
  unsigned i = 0;
  for (const auto &pair : assignments) {
    krose::midi::Binding b;
    b.source = krose::midi::Source::CC;
    b.number = pair[0];
    b.target = pair[1];
    mMidiMap.Set(i++, b);
  }
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
  for (int id = 0; id < kNumParams; ++id) {
    double value = GetParam(id)->Value();
    if (momentary[id])
      value = GetParam(id)->FromNormalized(0.);
    if ((id == kSW1State && GetParam(kSW1Mode)->Int()) ||
        (id == kSW2State && GetParam(kSW2Mode)->Int()))
      value = 0;
    chunk.Put(&value);
  }
  chunk.Put(&kMappingMagic);
  chunk.Put(&kMappingVersion);
  const uint32_t profile = mMidiProfile.load(), count = krose::midi::ControllerMap::kSlots;
  chunk.Put(&profile);
  chunk.Put(&count);
  for (unsigned i = 0; i < count; ++i) {
    const uint64_t word = mMidiMap.Get(i).Encode();
    chunk.Put(&word);
  }
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
  for (int count : {6, 17, 19, 29, kNumMidiParameters, int(kFxOn1), int(kArpSwing), int(kExtendedFxDetails), int(kEGTarget), int(kFxEditorRequest), int(kFilterEGIntensity)}) {
    const int bytes = count * int(sizeof(double));
    if (available != bytes && available != bytes + int(sizeof(int32_t)))
      continue;
    if (!validParameters(count)) return -1;
    IByteChunk upgraded;
    upgraded.PutBytes(chunk.GetData() + start, bytes);
    for (int id = count; id < kNumParams; ++id) {
      const double v =
          id >= kSW1Assign && id < kFXBypass ? GetParam(id)->Value() : GetParam(id)->GetDefault();
      upgraded.Put(&v);
    }
    if (UnserializeParams(upgraded, 0) < 0)
      return -1;
    return start + bytes;
  }
  const int parameters = kNumParams * int(sizeof(double));
  if (available == parameters || available == parameters + 4)
    return validParameters(kNumParams) ? UnserializeParams(chunk, start) : -1;
  constexpr int mappingBytes = 16 + krose::midi::ControllerMap::kSlots * int(sizeof(uint64_t));
  int storedParams = kNumParams;
  for (int oldCount : {kNumMidiParameters, int(kFxOn1), int(kArpSwing), int(kExtendedFxDetails), int(kEGTarget), int(kFxEditorRequest), int(kFilterEGIntensity)}) {
    const int bytes = oldCount * int(sizeof(double)) + mappingBytes;
    if (available == bytes || available == bytes + 4) {
      storedParams = oldCount;
      break;
    }
  }
  const int storedBytes = storedParams * int(sizeof(double));
  if ((available != storedBytes + mappingBytes && available != storedBytes + mappingBytes + 4) ||
      !validParameters(storedParams))
    return -1;
  int pos = start + storedBytes;
  uint32_t magic = 0, version = 0, profile = 0, count = 0;
  if ((pos = chunk.Get(&magic, pos)) < 0 || (pos = chunk.Get(&version, pos)) < 0 ||
      (pos = chunk.Get(&profile, pos)) < 0 || (pos = chunk.Get(&count, pos)) < 0 ||
      magic != kMappingMagic || version != 1 || profile >= 4 ||
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
  if (storedParams < kNumParams) {
    IByteChunk upgraded;
    upgraded.PutBytes(chunk.GetData() + start, storedBytes);
    for (int id = storedParams; id < kNumParams; ++id) {
      const double value = GetParam(id)->GetDefault();
      upgraded.Put(&value);
    }
    if (UnserializeParams(upgraded, 0) < 0)
      return -1;
  } else if (UnserializeParams(chunk, start) < 0) {
    return -1;
  }
  for (unsigned i = 0; i < count; ++i)
    mMidiMap.Set(i, bindings[i]);
  mMidiProfile.store(profile);
  mMidiMap.CancelLearn();
  mNotifiedMapRevision.store(mMidiMap.Revision());
  return pos;
}
void KrosePlugin::RestoreMidiProfile() {
  try {
    auto settings = ReadSettings();
    mArturiaEnabled = settings.value("arturia_feedback", true);
    krose::updates::AllowAutomaticChecks(settings.value("check_updates", true));
    const auto scale=settings.value("ui_scale",Json(0));
    if (scale.is_number_integer()) {
      const int value=scale.get<int>();
      if (value==0 || (value>=60 && value<=150)) mEditorScale=value;
    }
    if (!settings["profiles"].empty()) {
      const auto selected = settings.value("selected", Json(0u));
      if (!selected.is_number_unsigned() || selected > 3)
        throw std::runtime_error("Invalid MIDI profile selection");
      LoadMidiProfile(selected.get<unsigned>());
    }
  } catch (const std::exception &) {
    mMidiSettingsError = true;
  }
}
bool KrosePlugin::SetEditorScalePercent(int percentage) {
  if (percentage!=0 && (percentage<60 || percentage>150)) return false;
  mEditorScale=percentage;
  std::lock_guard<std::mutex> guard(settingsMutex);
  try {
    auto data=ReadSettings();
    data["ui_scale"]=percentage;
    krose::storage::WriteJson(SettingsPath(),data);
    return true;
  } catch (const std::exception &) { return false; }
}
bool KrosePlugin::SetUpdateChecksEnabled(bool enabled) {
  krose::updates::AllowAutomaticChecks(enabled);
  std::lock_guard<std::mutex> guard(settingsMutex);
  try {
    auto data = ReadSettings();
    data["check_updates"] = enabled;
    krose::storage::WriteJson(SettingsPath(), data);
    return true;
  } catch (const std::exception &) { return false; }
}
bool KrosePlugin::SetArturiaEnabled(bool enabled) {
  std::lock_guard<std::mutex> guard(settingsMutex);
  try {
    auto data = ReadSettings();
    data["arturia_feedback"] = enabled;
    krose::storage::WriteJson(SettingsPath(), data);
    mArturiaEnabled = enabled;
    mMidiSettingsError = false;
    return true;
  } catch (const std::exception &) {
    mMidiSettingsError = true;
    return false;
  }
}
bool KrosePlugin::LoadMidiProfile(unsigned profile) {
  if (profile >= 4)
    return false;
  std::lock_guard<std::mutex> guard(settingsMutex);
  try {
    auto data = ReadSettings();
    if (profile >= data["profiles"].size() || data["profiles"][profile].is_null()) {
      mMidiMap.Clear();
      for (int id : configIDs) {
        const double v = GetParam(id)->GetDefault();
        if (GetParam(id)->Value() != v) {
          BeginInformHostOfParamChangeFromUI(id);
          SendParameterValueFromUI(id, GetParam(id)->ToNormalized(v));
          EndInformHostOfParamChangeFromUI(id);
        }
      }
      for (int id : {kSW1State, kSW2State})
        if (GetParam(id)->Bool()) {
          BeginInformHostOfParamChangeFromUI(id);
          SendParameterValueFromUI(id, 0);
          EndInformHostOfParamChangeFromUI(id);
        }
      mMidiProfile.store(profile);
      mMidiSettingsError = false;
      return true;
    }
    const auto &p = data["profiles"][profile];
    if (!p.is_object() || !p.contains("bindings") || !p["bindings"].is_array() ||
        p["bindings"].size() != krose::midi::ControllerMap::kSlots)
      throw std::runtime_error("Invalid MIDI profile");
    std::array<krose::midi::Binding, krose::midi::ControllerMap::kSlots> parsed;
    for (unsigned i = 0; i < parsed.size(); ++i) {
      if (!p["bindings"][i].is_number_unsigned())
        throw std::runtime_error("Invalid binding encoding");
      const uint64_t word = p["bindings"][i].get<uint64_t>();
      parsed[i] = krose::midi::Binding::Decode(word);
      if (word >> 38 || !parsed[i].Valid(kMapTargets))
        throw std::runtime_error("Invalid binding");
    }
    std::array<double, sizeof(configIDs) / sizeof(*configIDs)> config{};
    if (!p.contains("config") || !p["config"].is_array() || p["config"].size() != config.size())
      throw std::runtime_error("Invalid controller config");
    for (unsigned i = 0; i < config.size(); ++i) {
      config[i] = p["config"][i].get<double>();
      const auto v = GetParam(configIDs[i]);
      if (!std::isfinite(config[i]) || config[i] < v->GetMin() || config[i] > v->GetMax())
        throw std::runtime_error("Invalid controller config");
    }
    mMidiMap.CancelLearn();
    for (unsigned i = 0; i < parsed.size(); ++i)
      mMidiMap.Set(i, parsed[i]);
    auto set = [&](int id, double v) {
      if (GetParam(id)->Value() == v)
        return;
      BeginInformHostOfParamChangeFromUI(id);
      SendParameterValueFromUI(id, GetParam(id)->ToNormalized(v));
      EndInformHostOfParamChangeFromUI(id);
    };
    for (unsigned i = 0; i < config.size(); ++i)
      set(configIDs[i], config[i]);
    set(kSW1State, 0);
    set(kSW2State, 0);
    mMidiProfile.store(profile);
    mMidiSettingsError = false;
    return true;
  } catch (const std::exception &) {
    mMidiSettingsError = true;
    return false;
  }
}
bool KrosePlugin::StoreMidiProfile(unsigned profile) {
  if (profile >= 4)
    return false;
  std::lock_guard<std::mutex> guard(settingsMutex);
  try {
    auto data = ReadSettings();
    while (data["profiles"].size() <= profile)
      data["profiles"].push_back(nullptr);
    Json words = Json::array(), config = Json::array();
    for (unsigned i = 0; i < krose::midi::ControllerMap::kSlots; ++i)
      words.push_back(mMidiMap.Get(i).Encode());
    for (int id : configIDs)
      config.push_back(GetParam(id)->Value());
    data["profiles"][profile] = {{"bindings", words}, {"config", config}};
    data["selected"] = profile;
    const auto destination = SettingsPath();
    krose::storage::WriteJson(destination, data);
    mMidiProfile.store(profile);
    mMidiSettingsError = false;
    return true;
  } catch (const std::exception &) {
    mMidiSettingsError = true;
    return false;
  }
}
