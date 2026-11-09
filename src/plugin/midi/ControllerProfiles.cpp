#include "../KrosePlugin.h"
#include "../ResourcePath.h"
#include "ControllerProfile.h"
#include <algorithm>

namespace {
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
