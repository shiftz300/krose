#pragma once
#include "NativePanel.h"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
namespace krose::ui {
namespace detail {
inline IRECT R(float x, float y, float w, float h) { return {x, y, x + w, y + h}; }
inline std::vector<std::string> Chars(const std::string &s) {
  std::vector<std::string> out;
  for (size_t i = 0; i < s.size();) {
    unsigned char c = s[i];
    size_t n = c < 128 ? 1 : c < 224 ? 2 : c < 240 ? 3 : 4;
    out.push_back(s.substr(i, n));
    i += n;
  }
  return out;
}
inline std::string Format(double v, int decimals = 0) {
  char b[64];
  if (std::abs(v) < std::pow(10., -decimals) * .5)
    v = 0;
  std::snprintf(b, sizeof(b), "%.*f", decimals, v);
  return b;
}
inline std::string Signed(double v) {
  int n = std::lround(v);
  return std::string(n < 0 ? "−" : "+") + (std::abs(n) < 10 ? "0" : "") +
         std::to_string(std::abs(n));
}
inline std::string Lower(std::string s) {
  for (char &c : s)
    c = char(std::tolower((unsigned char)c));
  return s;
}
inline const char *Pages[] = {"main", "tone", "fx", "arp"};
inline const char *Modes[] = {"POLY", "MONO", "LEGATO"};
inline const IColor Ink(255, 57, 78, 98), Paper(255, 216, 226, 233);
} // namespace detail
} // namespace krose::ui
