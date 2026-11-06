#include "storage/UserPreset.h"
#include <cassert>
#include <iostream>
#include <limits>

template<class F> void Reject(F f) {
  bool rejected = false;
  try { f(); } catch (const std::exception &) { rejected = true; }
  assert(rejected);
}
int main() {
  using namespace krose::storage;
  const auto directory = std::filesystem::temp_directory_path() /
      ("krose-preset-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::create_directory(directory);
  const auto path = directory / "sound.krose";
  PresetValues values{};
  for (int id = 0; id < kNumParams; ++id) values[id] = double(id) / kNumParams;
  WriteJson(path, EncodePreset(values));
  assert(DecodePreset(ReadJson(path)) == values);
  auto extended = EncodePreset(values);
  extended["notes"] = std::string(1024 * 1024, 'x');
  WriteJson(path, extended);
  assert(DecodePreset(ReadJson(path)) == values); // Room for additional metadata.
  auto rounded = EncodePreset(values);
  rounded["values"][0] = -1e-10;
  rounded["values"][1] = 1 + 1e-10;
  const auto normalized = DecodePreset(rounded);
  assert(normalized[0] == 0 && normalized[1] == 1);
  for (int id = 0; id < kNumParams; ++id) {
    assert(ParameterForMidiTarget(MidiTargetForParameter(id)) == id);
    assert(SoundParameter(id) == (id < kSW1Assign || id >= kFXBypass));
  }
  for (unsigned target : {39u, 40u, 41u, unsigned(kNumParams + 3), UINT32_MAX})
    assert(ParameterForMidiTarget(target) == -1);
  for (double value : {-1., 1.001, std::numeric_limits<double>::infinity(), double(NAN)}) {
    auto bad = values; bad.back() = value;
    Reject([&] { EncodePreset(bad); });
  }
  for (int mutation = 0; mutation < 5; ++mutation) {
    auto bad = EncodePreset(values);
    if (mutation == 0) bad["version"] = 2;
    if (mutation == 1) bad["values"].erase(0);
    if (mutation == 2) bad["values"][0] = "nan";
    if (mutation == 3) bad["values"][0] = nullptr;
    if (mutation == 4) bad["format"] = "other-app";
    Reject([&] { DecodePreset(bad); });
  }
  Reject([&] { WriteJson(path, std::string(kMaxJsonBytes, 'x')); });
  assert(DecodePreset(ReadJson(path)) == values); // Failed save keeps original.
  const auto malformed = directory / "bad.json";
  for (const auto &bytes : {std::string(kMaxJsonDepth + 2, '[') + "0" + std::string(kMaxJsonDepth + 2, ']'),
                            std::string("{invalid}"), std::string(kMaxJsonBytes + 1, ' ')}) {
    std::ofstream file(malformed, std::ios::binary); file << bytes; file.close();
    Reject([&] { ReadJson(malformed); });
  }
  // A replacement failure must remove its exclusive temporary file.
  const auto blocked = directory / "directory";
  std::filesystem::create_directory(blocked);
  Reject([&] { WriteJson(blocked, EncodePreset(values)); });
  for (const auto &entry : std::filesystem::directory_iterator(directory))
    assert(entry.path().extension() != ".tmp");
  std::filesystem::remove_all(directory);
  std::cout << "PASS preset roundtrip, mapping IDs, input limits and failed-save preservation\n";
}
