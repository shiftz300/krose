#pragma once
#include "ControllerMap.h"
#include "../storage/JsonFile.h"
#include <string>
#include <string_view>

namespace krose::midi {
inline constexpr const char* kProfileSources[] = {
    "off", "cc", "cc14", "nrpn", "rpn", "note", "bend", "pressure", "poly-pressure"};
inline constexpr const char* kProfileModes[] = {
    "absolute", "relative-twos-complement", "relative-offset", "relative-sign", "toggle", "momentary"};
struct ControllerProfile {
  std::string name;
  std::array<Binding, ControllerMap::kSlots> bindings{};
};
inline void ProfileKeys(const nlohmann::json& value, std::initializer_list<std::string_view> allowed) {
  if (!value.is_object()) throw std::runtime_error("Expected profile object");
  for (auto it = value.begin(); it != value.end(); ++it)
    if (std::find(allowed.begin(), allowed.end(), it.key()) == allowed.end())
      throw std::runtime_error("Unknown controller profile field: " + it.key());
}
inline unsigned ProfileNumber(const nlohmann::json& value, unsigned limit) {
  if (!value.is_number_integer() || value < 0 || value > limit)
    throw std::runtime_error("Controller profile number out of range");
  return value.get<unsigned>();
}
template <std::size_t N> unsigned ProfileEnum(const nlohmann::json& value, const char* const (&names)[N]) {
  if (value.is_string())
    for (unsigned i = 0; i < N; ++i)
      if (value == names[i]) return i;
  throw std::runtime_error("Unknown controller profile enum");
}
// Resolve named targets against the plugin's stable parameter registry. Parsing
// completes before touching live mappings; files cannot specify code or output MIDI.
template <class Resolve> ControllerProfile ParseControllerProfile(const nlohmann::json& data,
                                                                 unsigned targets, Resolve resolve) {
  ProfileKeys(data, {"format", "version", "name", "description", "bindings"});
  if (data.value("format", "") != "krose-controller-profile" ||
      !data.contains("version") || ProfileNumber(data.at("version"), 1) != 1)
    throw std::runtime_error("Unsupported controller profile format");
  ControllerProfile result;
  result.name = data.at("name").get<std::string>();
  if (result.name.empty() || result.name.size() > 160 ||
      std::any_of(result.name.begin(), result.name.end(), [](unsigned char c) { return c < 32; }))
    throw std::runtime_error("Invalid controller profile name");
  if (data.contains("description") &&
      (!data["description"].is_string() || data["description"].get_ref<const std::string&>().size() > 4096))
    throw std::runtime_error("Invalid controller profile description");
  const auto& entries = data.at("bindings");
  if (!entries.is_array() || entries.size() > result.bindings.size())
    throw std::runtime_error("Controller profile exceeds mapping slots");
  unsigned slot = 0;
  for (const auto& entry : entries) {
    ProfileKeys(entry, {"source", "number", "channel", "target", "mode", "pickup", "consume", "invert"});
    Binding b;
    b.source = Source(ProfileEnum(entry.at("source"), kProfileSources));
    b.number = ProfileNumber(entry.value("number", nlohmann::json(0)), 16383);
    b.channel = ProfileNumber(entry.value("channel", nlohmann::json(0)), 16);
    const int target = resolve(entry.at("target").get<std::string>());
    if (target < 0) throw std::runtime_error("Unknown controller profile target");
    b.target = unsigned(target);
    b.mode = Mode(ProfileEnum(entry.value("mode", nlohmann::json("absolute")), kProfileModes));
    auto flag = [&](const char* key, bool fallback) {
      if (!entry.contains(key)) return fallback;
      if (!entry[key].is_boolean()) throw std::runtime_error("Expected boolean profile flag");
      return entry[key].get<bool>();
    };
    b.pickup = flag("pickup", true);
    b.consume = flag("consume", true);
    b.invert = flag("invert", false);
    if (!b.Valid(targets) || ((b.source == Source::Bend || b.source == Source::Pressure) && b.number))
      throw std::runtime_error("Invalid controller profile binding");
    result.bindings[slot++] = b;
  }
  return result;
}
template <class Resolve> ControllerProfile ReadControllerProfile(const std::filesystem::path& file,
                                                                unsigned targets, Resolve resolve) {
  if (std::filesystem::is_symlink(file)) throw std::runtime_error("Profile symlinks are not supported");
  return ParseControllerProfile(storage::ReadJson(file, 256 * 1024, 16), targets, resolve);
}
} // namespace krose::midi
