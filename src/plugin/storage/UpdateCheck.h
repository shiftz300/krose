#pragma once
#include <array>
#include <optional>
#include <string>
#include <string_view>

namespace krose::updates {
inline constexpr char kReleasePage[] = "https://github.com/shiftz300/krose/releases/latest";
inline constexpr size_t kMaxResponse = 32768;
inline std::optional<std::array<unsigned, 3>> Version(std::string_view text) {
  if (!text.empty() && text.front() == 'v') text.remove_prefix(1);
  std::array<unsigned, 3> result{};
  for (unsigned part = 0; part < 3; ++part) {
    size_t n = 0;
    while (n < text.size() && text[n] >= '0' && text[n] <= '9') {
      if (n == 6) return {};
      result[part] = result[part] * 10 + unsigned(text[n++] - '0');
    }
    if (!n || (n > 1 && text.front() == '0')) return {};
    text.remove_prefix(n);
    if (part != 2) {
      if (text.empty() || text.front() != '.') return {};
      text.remove_prefix(1);
    }
  }
  if (!text.empty()) return {};
  return result;
}
inline bool Newer(std::string_view candidate, std::string_view current) {
  const auto a = Version(candidate), b = Version(current);
  return a && b && *a > *b;
}
std::string LatestReleaseVersion(const std::string &json);
bool AutomaticChecksAllowed();
void AllowAutomaticChecks(bool allowed);
void StartAutomaticCheck(); // UI thread only; never waits for network.
std::string TakeUpdateNotice(std::string_view current); // At most one per process/module.
}
