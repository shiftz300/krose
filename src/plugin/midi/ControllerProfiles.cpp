#include "../KrosePlugin.h"
#include "../ResourcePath.h"
#include "ControllerProfile.h"
#include "NativeData.h"
#include "../storage/JsonFile.h"
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <mutex>
using Json = nlohmann::json;
namespace {
std::mutex settingsMutex;
std::filesystem::path SettingsPath() {
  if (const char *p = std::getenv("KROSE_MIDI_MAP_FILE"))
    return std::filesystem::u8path(p);
  WDL_String root;
  iplug::AppSupportPath(root);
  return std::filesystem::u8path(root.Get()) / "Krose" / "midi-mappings.json";
}
Json ReadSettings(const std::filesystem::path &path) {
  if (!std::filesystem::exists(path))
    return Json{{"version", 1}, {"profiles", Json::array()}};
  auto value = krose::storage::ReadJson(path);
  if (value.is_discarded() || !value.is_object() || !value.contains("version") || value["version"] != 1 ||
      !value.contains("profiles") || !value["profiles"].is_array())
    throw std::runtime_error("Invalid MIDI settings");
  return value;
}
bool WriteSetting(const char *key, Json value) {
  try {
    const auto path = SettingsPath();
    auto data = ReadSettings(path);
    data[key] = std::move(value);
    krose::storage::WriteJson(path, data);
    return true;
  } catch (const std::exception &) {
    return false;
  }
}
constexpr std::array configIDs{kSW1Assign, kSW1Mode, kSW2Assign, kSW2Mode,
                               kInputChannel, kProgramChange, kClockSource};

std::filesystem::path UserProfiles() {
  WDL_String root;
  iplug::AppSupportPath(root);
  return std::filesystem::u8path(root.Get()) / "Krose/Controllers/Profiles";
}
int TargetNamed(const KrosePlugin* plugin, const std::string& name) {
  if (name == "NEXT PRESET") return KrosePlugin::kTargetNext;
  if (name == "PREV PRESET") return KrosePlugin::kTargetPrevious;
  if (name == "PANIC") return KrosePlugin::kTargetPanic;
  for (int id = 0; id < kNumParams; ++id)
    if (name == plugin->GetParam(id)->GetName()) return MidiTargetForParameter(id);
  return -1;
}
std::string TargetName(const KrosePlugin* plugin, unsigned target) {
  const int parameter = ParameterForMidiTarget(target);
  if (parameter >= 0) return plugin->GetParam(parameter)->GetName();
  return target == KrosePlugin::kTargetNext ? "NEXT PRESET" :
         target == KrosePlugin::kTargetPrevious ? "PREV PRESET" : "PANIC";
}
} // namespace
void KrosePlugin::InitializeMidiMappings() {
  for (unsigned id = 0; id < kNumParams; ++id) {
    const auto p = GetParam(id);
    mMidiMap.SetStep(MidiTargetForParameter(id), p->GetRange() > 0 ? p->GetStep() / p->GetRange() : 1);
  }
  for (unsigned id = kNumMidiParameters; id < kNumMidiParameters + 3; ++id)
    mMidiMap.SetStep(id, 1);
  auto order = Json::parse(kNativeBrowser)["order"].get<std::vector<int>>();
  const int factoryCount = int(order.size());
  for (unsigned i = 0; i < segrand::kPcgProgramCount; ++i)
    if (PcgProgram(factoryCount + int(i))) order.push_back(factoryCount + int(i));
  mNextPrograms.resize(factoryCount + kMissingPcgSelection, factoryCount > 1 ? 1 : 0);
  mPreviousPrograms.resize(mNextPrograms.size(), order.back());
  for (unsigned i = 0; i < order.size(); ++i) {
    auto step = [&](int delta) {
      const int count = int(order.size());
      int position = int(i);
      do {
        position = (position + delta + count) % count;
      } while (position != int(i) && !ProgramAvailable(order[position]));
      return order[position];
    };
    mNextPrograms[order[i]] = step(1);
    mPreviousPrograms[order[i]] = step(-1);
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
void KrosePlugin::RestoreMidiProfile() {
  try {
    const auto settings = ReadSettings(SettingsPath());
    mArturiaEnabled = settings.value("arturia_feedback", true);
    krose::updates::AllowAutomaticChecks(settings.value("check_updates", true));
    const auto scale = settings.value("ui_scale", Json(0));
    if (scale.is_number_integer()) {
      const int value = scale.get<int>();
      if (value == 0 || (value >= 60 && value <= 150)) mEditorScale = value;
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
  if (percentage != 0 && (percentage < 60 || percentage > 150)) return false;
  mEditorScale = percentage;
  std::lock_guard<std::mutex> guard(settingsMutex);
  return WriteSetting("ui_scale", percentage);
}
bool KrosePlugin::SetUpdateChecksEnabled(bool enabled) {
  krose::updates::AllowAutomaticChecks(enabled);
  std::lock_guard<std::mutex> guard(settingsMutex);
  return WriteSetting("check_updates", enabled);
}
bool KrosePlugin::SetArturiaEnabled(bool enabled) {
  std::lock_guard<std::mutex> guard(settingsMutex);
  mMidiSettingsError = !WriteSetting("arturia_feedback", enabled);
  if (!mMidiSettingsError) mArturiaEnabled = enabled;
  return !mMidiSettingsError;
}
bool KrosePlugin::LoadMidiProfile(unsigned profile) {
  if (profile >= 4)
    return false;
  std::lock_guard<std::mutex> guard(settingsMutex);
  try {
    const auto data = ReadSettings(SettingsPath());
    const auto &profiles = data["profiles"];
    std::array<double, configIDs.size()> config{};
    if (profile >= profiles.size() || profiles[profile].is_null()) {
      mMidiMap.Clear();
      for (size_t i = 0; i < config.size(); ++i)
        config[i] = GetParam(configIDs[i])->GetDefault();
    } else {
      const auto &p = profiles[profile];
      std::array<krose::midi::Binding, krose::midi::ControllerMap::kSlots> bindings;
      if (!p.contains("bindings") || !p["bindings"].is_array() ||
          p["bindings"].size() != bindings.size())
        throw std::runtime_error("Invalid MIDI profile");
      for (size_t i = 0; i < bindings.size(); ++i) {
        if (!p["bindings"][i].is_number_unsigned())
          throw std::runtime_error("Invalid binding encoding");
        const uint64_t word = p["bindings"][i].get<uint64_t>();
        bindings[i] = krose::midi::Binding::Decode(word);
        if (word >> 38 || !bindings[i].Valid(kMapTargets))
          throw std::runtime_error("Invalid binding");
      }
      if (!p.contains("config") || !p["config"].is_array() || p["config"].size() != config.size())
        throw std::runtime_error("Invalid controller config");
      for (size_t i = 0; i < config.size(); ++i) {
        config[i] = p["config"][i].get<double>();
        const auto *parameter = GetParam(configIDs[i]);
        if (!std::isfinite(config[i]) || config[i] < parameter->GetMin() ||
            config[i] > parameter->GetMax())
          throw std::runtime_error("Invalid controller config");
      }
      mMidiMap.CancelLearn();
      for (unsigned i = 0; i < bindings.size(); ++i)
        mMidiMap.Set(i, bindings[i]);
    }
    for (size_t i = 0; i < config.size(); ++i) {
      const int id = configIDs[i];
      if (GetParam(id)->Value() != config[i])
        SendUiParameter(id, GetParam(id)->ToNormalized(config[i]));
    }
    for (int id : {kSW1State, kSW2State})
      if (GetParam(id)->Bool())
        SendUiParameter(id, 0);
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
    const auto path = SettingsPath();
    auto data = ReadSettings(path);
    while (data["profiles"].size() <= profile)
      data["profiles"].push_back(nullptr);
    Json words = Json::array(), config = Json::array();
    for (unsigned i = 0; i < krose::midi::ControllerMap::kSlots; ++i)
      words.push_back(mMidiMap.Get(i).Encode());
    for (int id : configIDs)
      config.push_back(GetParam(id)->Value());
    data["profiles"][profile] = {{"bindings", words}, {"config", config}};
    data["selected"] = profile;
    krose::storage::WriteJson(path, data);
    mMidiProfile.store(profile);
    mMidiSettingsError = false;
    return true;
  } catch (const std::exception &) {
    mMidiSettingsError = true;
    return false;
  }
}

std::string KrosePlugin::ControllerSupportFolder(bool builtin) const {
  return (builtin ? krose::ResourceDirectory(GetBundleID()) / "Controllers" : UserProfiles()).u8string();
}
std::vector<KrosePlugin::ControllerProfileFile> KrosePlugin::ControllerProfileFiles() const {
  std::vector<ControllerProfileFile> result;
  for (bool builtin : {true, false}) {
    try {
      const auto directory = builtin ? std::filesystem::u8path(ControllerSupportFolder(true)) / "profiles/builtin"
                                     : UserProfiles();
      if (!std::filesystem::is_directory(directory)) continue;
      unsigned scanned = 0;
      for (const auto& entry : std::filesystem::directory_iterator(directory)) {
        if (++scanned > 1024 || result.size() >= 256) break;
        if (entry.is_symlink() || !entry.is_regular_file() || entry.path().extension() != ".json") continue;
        try {
          const auto profile = krose::midi::ReadControllerProfile(entry.path(), kMapTargets,
              [&](const std::string& name) { return TargetNamed(this, name); });
          result.push_back({profile.name, entry.path().u8string(), builtin});
        } catch (const std::exception&) {
          result.push_back({entry.path().stem().u8string(), entry.path().u8string(), builtin, false});
        }
      }
    } catch (const std::exception&) { /* A missing/unreadable folder is optional. */ }
  }
  std::sort(result.begin(), result.end(), [](const auto& a, const auto& b) {
    return a.builtin != b.builtin ? a.builtin : a.name != b.name ? a.name < b.name : a.path < b.path;
  });
  return result;
}
bool KrosePlugin::ImportControllerProfile(const std::string& path) {
  try {
    const auto profile = krose::midi::ReadControllerProfile(std::filesystem::u8path(path), kMapTargets,
        [&](const std::string& name) { return TargetNamed(this, name); });
    mMidiMap.CancelLearn();
    for (unsigned slot = 0; slot < profile.bindings.size(); ++slot)
      mMidiMap.Set(slot, profile.bindings[slot]);
    return true;
  } catch (const std::exception&) { return false; }
}
bool KrosePlugin::ExportControllerProfile() {
  using namespace krose::midi;
  try {
    auto entries = nlohmann::json::array();
    for (unsigned slot = 0; slot < ControllerMap::kSlots; ++slot) {
      const auto b = mMidiMap.Get(slot);
      if (b.source == Source::Off) continue;
      entries.push_back({{"source", kProfileSources[unsigned(b.source)]}, {"channel", b.channel},
          {"number", b.number}, {"target", TargetName(this, b.target)}, {"mode", kProfileModes[unsigned(b.mode)]},
          {"pickup", b.pickup}, {"consume", b.consume}, {"invert", b.invert}});
    }
    const auto directory = UserProfiles();
    // Export always creates a new file; user-edited profiles survive upgrades
    // and repeated exports, and cannot redirect the write through a symlink.
    std::filesystem::create_directories(directory);
    const auto name = "USER " + std::to_string(MidiProfile() + 1);
    auto file = directory / ("user-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".json");
    if (std::filesystem::exists(file) || std::filesystem::is_symlink(file)) return false;
    krose::storage::WriteJson(file, {{"format", "krose-controller-profile"}, {"version", 1},
                                    {"name", name}, {"bindings", entries}});
    return true;
  } catch (const std::exception&) { return false; }
}
