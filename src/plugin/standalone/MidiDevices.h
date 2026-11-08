#pragma once
#include <algorithm>
#include <cctype>
#include <string>
#include <string_view>
#include <vector>

namespace krose::standalone {
inline constexpr char kAutomaticMidi[] = "Automatic";
// An explicit device wins when present. Otherwise keep the current connected
// input, then prefer a musical port over a DAW/control-surface companion port.
inline std::string ChooseMidiInput(std::string_view preferred, std::string_view active,
                                   const std::vector<std::string> &ports) {
  auto available = [&](std::string_view name) {
    return std::find(ports.begin(), ports.end(), name) != ports.end();
  };
  if (preferred == "off") return {};
  if (preferred != kAutomaticMidi && available(preferred)) return std::string(preferred);
  if (available(active)) return std::string(active);
  for (const auto &port : ports) {
    auto lower = port;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char ch) { return char(std::tolower(ch)); });
    if (lower.find("daw") == std::string::npos && lower.find("mcu") == std::string::npos &&
        lower.find("hui") == std::string::npos && lower.find("alv") == std::string::npos &&
        lower.find("dinthru") == std::string::npos && lower.find("din thru") == std::string::npos &&
        port != "From Krose") return port;
  }
  // Control/thru ports must be selected explicitly if no musical input exists.
  return {};
}
}
