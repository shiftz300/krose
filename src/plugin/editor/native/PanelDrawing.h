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
// Share the original 240-column LCD grid with the firmware status-row sprites.
inline float LCDX(float x) {
  return std::round((431 + std::round((x - 431) / (542.f / 240)) * (542.f / 240)) * 2) / 2;
}
inline float LCDY(float y) {
  return std::round((115 + std::round((y - 115) / (27.09375f / 12)) * (27.09375f / 12)) * 2) / 2;
}
inline IRECT LCDRect(const IRECT &r) { return {LCDX(r.L), LCDY(r.T), LCDX(r.R), LCDY(r.B)}; }
inline void LCDChevron(IGraphics &g, const IRECT &r, const IColor &color) {
  constexpr float dot = 542.f / 240;
  float x = LCDX(r.R - 12), y = LCDY(r.MH() - 2.5f * dot);
  for (int row = 0; row < 2; ++row) {
    g.FillRect(color, LCDRect(R(x - row * dot, y + row * dot, (1 + row * 2) * dot, dot)));
    g.FillRect(color, LCDRect(R(x - row * dot, y + (4 - row) * dot, (1 + row * 2) * dot, dot)));
  }
}
inline void LCDFrame(IGraphics &g, const IRECT &r) {
  constexpr float dot = 542.f / 240;
  for (auto edge : {IRECT{r.L, r.T, r.R, LCDY(r.T + dot)},
                    IRECT{r.L, LCDY(r.B - dot), r.R, r.B},
                    IRECT{r.L, r.T, LCDX(r.L + dot), r.B},
                    IRECT{LCDX(r.R - dot), r.T, r.R, r.B}})
    g.FillRect(Ink, edge);
}
inline void LCDGrid(IGraphics &g, const IRECT &r) {
  // Half-point gaps are one physical pixel at the reference 2x scale. This
  // continues through text and filled cells, including popup selections.
  const IColor seam(22, Paper.R, Paper.G, Paper.B);
  constexpr float dx = 542.f / 240, dy = 27.09375f / 12;
  for (int i = int(std::ceil((r.L - 431) / dx)); 431 + i * dx < r.R; ++i) {
    float x = std::round((431 + i * dx) * 2) / 2;
    g.FillRect(seam, {x, r.T, std::min(x + .5f, r.R), r.B});
  }
  for (int i = int(std::ceil((r.T - 115) / dy)); 115 + i * dy < r.B; ++i) {
    float y = std::round((115 + i * dy) * 2) / 2;
    g.FillRect(seam, {r.L, y, r.R, std::min(y + .5f, r.B)});
  }
}
} // namespace detail
} // namespace krose::ui
