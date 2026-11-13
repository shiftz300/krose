#include "midi/ControllerProfile.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <map>

int main(int argc, char** argv) {
  using namespace krose::midi;
  using Json = nlohmann::json;
  assert(argc == 2);
  const std::map<std::string, unsigned> targets{{"Pan", 0}, {"Resonance", 1}, {"Cutoff", 2},
    {"Amp Attack", 3}, {"Amp Decay", 4}, {"Amp Sustain", 5}, {"Amp Release", 6}, {"Space", 7}, {"Output", 8},
    {"Glide", 9}, {"Filter EG Intensity", 10}, {"Velocity", 11}, {"Filter Attack", 12}, {"Filter Decay", 13},
    {"Filter Sustain", 14}, {"Filter Release", 15}, {"Arp", 16}, {"Arp Latch", 17}, {"PREV PRESET", 18},
    {"NEXT PRESET", 19}, {"IFX 1 On", 20}, {"IFX 2 On", 21}, {"MFX 1 On", 22}, {"MFX 2 On", 23}};
  auto resolve = [&](const std::string& name) { auto it = targets.find(name); return it == targets.end() ? -1 : int(it->second); };
  auto profile = ReadControllerProfile(std::filesystem::path(argv[1]) / "profiles/builtin/standard-cc.json", 9, resolve);
  ControllerMap map(9);
  for (unsigned i = 0; i < profile.bindings.size(); ++i) map.Set(i, profile.bindings[i]);
  std::array<double, 9> values{};
  values[2] = 64. / 127;
  assert(map.Process({0, 0xb0, 74, 64}, [&](unsigned i) { return values[i]; }, [&](unsigned i, double v) { values[i] = v; }));
  assert(map.Process({0, 0xb0, 74, 127}, [&](unsigned i) { return values[i]; }, [&](unsigned i, double v) { values[i] = v; }));
  assert(values[2] == 1);
  const auto original = map.Get(2).Encode();
  ReadControllerProfile(std::filesystem::path(argv[1]) / "templates/standalone/generic-keyboard.json", 9, resolve);
  for (const auto* name : {"arturia-minilab-3.json", "akai-mpk-mini.json", "generic-custom-cc.json"}) {
    const auto path = std::filesystem::path(argv[1]) / "profiles/builtin" / name;
    const auto keyboard = ReadControllerProfile(path, unsigned(targets.size()), resolve);
    ControllerMap controls(unsigned(targets.size()));
    for (unsigned slot = 0; slot < keyboard.bindings.size(); ++slot)
      controls.Set(slot, keyboard.bindings[slot]);
    std::array<double, 24> state{};
    unsigned nextRequests = 0;
    auto read = [&](unsigned target) { return state[target]; };
    auto write = [&](unsigned target, double value) {
      if (target == 19 && value == 1) ++nextRequests;
      if (target != 19) state[target] = value;
    };
    const bool miniLab = std::string_view(name) == "arturia-minilab-3.json";
    const uint8_t cutoffCC = miniLab ? 74 : 20;
    assert(!controls.Process({0, 0xb1, cutoffCC, 127}, read, write)); // Other channels pass through.
    assert(!controls.Process({0, 0x90, 60, 127}, read, write)); // Playing the keyboard passes through.
    assert(controls.Process({0, 0xb0, cutoffCC, 127}, read, write) && state[2] == 0); // Pickup.
    controls.Process({0, 0xb0, cutoffCC, 0}, read, write);
    controls.Process({0, 0xb0, cutoffCC, 127}, read, write);
    assert(state[2] == 1);
    controls.Process({0, 0xb0, 105, 127}, read, write);
    controls.Process({0, 0xb0, 105, 127}, read, write);
    controls.Process({0, 0xb0, 105, 0}, read, write);
    controls.Process({0, 0xb0, 105, 127}, read, write);
    assert(nextRequests == 2);
  }
  auto valid = Json{{"format", "krose-controller-profile"}, {"version", 1}, {"name", "Test"},
    {"bindings", Json::array({{{"source", "cc"}, {"number", 74}, {"target", "Cutoff"}}})}};
  auto reject = [&](Json data) {
    bool rejected = false;
    try { ParseControllerProfile(data, 9, resolve); } catch (const std::exception&) { rejected = true; }
    assert(rejected && map.Get(2).Encode() == original);
  };
  for (auto number : {Json(-1), Json(128), Json(1.0), Json(1e100)}) {
    auto data = valid; data["bindings"][0]["number"] = number; reject(data);
  }
  for (const auto& key : {"script", "path", "sysex", "url"}) {
    auto data = valid; data[key] = "untrusted"; reject(data);
  }
  for (auto channel : {-1, 17, 128}) {
    auto data = valid; data["bindings"][0]["channel"] = channel; reject(data);
  }
  for (const auto& pair : {std::pair{"target", "Unknown parameter"}, {"mode", "exec"}, {"source", "sysex"}}) {
    auto data = valid; data["bindings"][0][pair.first] = pair.second; reject(data);
  }
  auto data = valid; data["bindings"][0]["pickup"] = 1; reject(data);
  data = valid; data["bindings"] = Json::array();
  for (int i = 0; i < 65; ++i) data["bindings"].push_back(valid["bindings"][0]);
  reject(data);
  data = valid; data["bindings"][0]["source"] = "cc14"; data["bindings"][0]["number"] = 31;
  assert(ParseControllerProfile(data, 9, resolve).bindings[0].number == 31);
  data["bindings"][0]["number"] = 32; reject(data);
  auto root = std::filesystem::temp_directory_path() / ("krose-controller-profile-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::create_directories(root);
  auto file = root / "invalid.json";
  auto rejectFile = [&] {
    bool rejected = false;
    try { ReadControllerProfile(file, 9, resolve); } catch (const std::exception&) { rejected = true; }
    assert(rejected);
  };
  { std::ofstream out(file); out << std::string(256 * 1024 + 1, ' '); }
  rejectFile();
  { std::ofstream out(file); out << std::string(24, '[') << '0' << std::string(24, ']'); }
  rejectFile();
  std::filesystem::remove(file);
#ifndef _WIN32
  { std::ofstream out(root / "valid.json"); out << valid; }
  std::filesystem::create_symlink(root / "valid.json", file);
  rejectFile();
#endif
  std::filesystem::remove_all(root);
  std::cout << "Controller profiles: real templates, mapping behavior and hostile data boundaries passed\n";
}
