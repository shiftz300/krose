#include "IPlugPaths.h"
#include "NativePanel.h"
#include "PanelDrawing.h"
#include "../../storage/JsonFile.h"
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <stdexcept>

namespace krose::ui {
using namespace detail;
namespace {
std::mutex favoriteMutex;
std::filesystem::path FavoritePath() {
  if (const char *file = std::getenv("KROSE_FAVORITES_FILE"))
    return std::filesystem::u8path(file);
  WDL_String path;
  iplug::AppSupportPath(path);
  return std::filesystem::u8path(path.Get()) / "Krose" / "favorites.json";
}
std::set<std::string> ReadFavorites() {
  std::ifstream file(FavoritePath());
  if (!file)
    return {};
  auto data = krose::storage::ReadJson(FavoritePath());
  if (data.is_discarded() || !data.is_object() || !data.contains("programs") ||
      !data["programs"].is_array())
    return {};
  std::set<std::string> result;
  for (const auto &id : data["programs"])
    if (id.is_string())
      result.insert(id.get<std::string>());
  return result;
}
} // namespace
void NativePanel::LoadFavorites() {
  std::lock_guard<std::mutex> lock(favoriteMutex);
  try {
    mFavorites = ReadFavorites();
  } catch (const std::exception &) {
    mFavorites.clear();
  }
}
void NativePanel::ToggleFavorite(int program) {
  std::lock_guard<std::mutex> lock(favoriteMutex);
  try {
    auto favorites = ReadFavorites();
    std::string id = mPrograms[program][0];
    if (!favorites.erase(id))
      favorites.insert(id);
    const auto path = FavoritePath();
    krose::storage::WriteJson(path, Json{{"version", 1}, {"programs", favorites}});
    mFavorites = std::move(favorites);
    mFavoriteSaveFailed = false;
  } catch (const std::exception &) {
    mFavoriteSaveFailed = true;
  }
  if (mPresetCategory == -1)
    PresetCategory(-1);
  if (mBrowsing && mCategory == -2)
    FilterPrograms();
  SetDirty(false);
}
void NativePanel::Heart(IGraphics &g, const IRECT &r, int program) {
  const bool on = mFavorites.count(mPrograms[program][0].get<std::string>()) != 0;
  const auto color = on ? IColor(255, 196, 108, 121) : IColor(255, 173, 179, 183);
  float x = r.MW(), y = r.MH();
  g.PathClear();
  g.PathMoveTo(x, y + 6);
  g.PathCubicBezierTo(x - 15, y - 3, x - 5, y - 11, x, y - 5);
  g.PathCubicBezierTo(x + 5, y - 11, x + 15, y - 3, x, y + 6);
  g.PathClose();
  if (on)
    g.PathFill(color);
  else
    g.PathStroke(color, 1.3f);
  HitBox(r, "favorite", -1, program);
}
void NativePanel::OpenPresetMenu() {
  LoadFavorites();
  mPresetOpen = true;
  mChoices.clear();
  const auto &categories = mBrowser["categories"];
  const auto &currentCategory = mPrograms[int(Value(kParamProgram))][2];
  auto category = std::find(categories.begin(), categories.end(), currentCategory);
  if (category != categories.end())
    PresetCategory(int(category - categories.begin()), true);
  else {
    mPresetCategory = -2;
    mPresetRootFocus = 0;
    mPresetColumn = 0;
  }
}

void NativePanel::PresetCategory(int category, bool revealCurrent) {
  mPresetCategory = category;
  mPresetRootFocus = category + 1;
  mPresetItems.clear();
  for (int i : mBrowser["order"].get<std::vector<int>>())
    if (category == -1 ? mFavorites.count(mPrograms[i][0].get<std::string>()) != 0
                       : mPrograms[i][2] == mBrowser["categories"][category])
      mPresetItems.push_back(i);
  mPresetFocus = 0;
  mPresetScroll = 0;
  if (revealCurrent) {
    const int current = int(Value(kParamProgram));
    const auto selected = std::find(mPresetItems.begin(), mPresetItems.end(), current);
    if (selected != mPresetItems.end()) {
      mPresetFocus = int(selected - mPresetItems.begin());
      mPresetScroll = std::clamp(mPresetFocus - 6, 0, std::max(0, int(mPresetItems.size()) - 12));
    }
  }
  mPresetColumn = 1;
  SetDirty(false);
}
void NativePanel::PresetMenu(IGraphics &g) {
  const auto root = R(507, 84, 168, 312), child = R(675, 84, 414, 312);
  HitBox(mRECT, "dismiss");
  const auto bg = IColor(255, 35, 38, 40), border = IColor(255, 118, 122, 125),
             selected = IColor(255, 65, 81, 94);
  g.FillRect(bg, root);
  g.DrawRect(border, root);
  for (int n = 0; n < 12; ++n) {
    auto row = R(root.L + 1, root.T + n * 26, root.W() - 2, 26);
    if (n == mPresetRootFocus)
      g.FillRect(selected, row);
    Text(g, "arial15", n == 0 ? "FAVORITES" : mBrowser["categories"][n - 1].get<std::string>(),
         R(row.L + 8, row.T, row.W() - 26, 26));
    g.FillTriangle(border, row.R - 12, row.MH() - 4, row.R - 12, row.MH() + 4, row.R - 8, row.MH());
    HitBox(row, "preset-category", -1, n - 1);
  }
  if (mPresetCategory < -1) {
    mDrawnCategory = -2;
    return;
  }
  if (mDrawnCategory != mPresetCategory) {
    mCategoryReveal.Snap(.35);
    mCategoryReveal.Target(1, mFrameTime, .10);
    mDrawnCategory = mPresetCategory;
  }
  g.FillRect(bg, child);
  g.DrawRect(border, child);
  mPresetScroll = std::clamp(mPresetScroll, 0, std::max(0, int(mPresetItems.size()) - 12));
  if (mPresetItems.empty())
    Text(g, "arial15", "NO FAVORITES", child.GetPadded(-10));
  for (int n = 0; n < 12 && n + mPresetScroll < int(mPresetItems.size()); ++n) {
    int index = mPresetScroll + n, program = mPresetItems[index];
    auto &p = mPrograms[program];
    auto row = R(child.L + 1, child.T + n * 26, child.W() - 2, 26);
    if (index == mPresetFocus)
      g.FillRect(selected, row);
    auto text = R(row.L + 8, row.T, row.W() - 42, 26);
    g.PathClipRegion(text);
    Text(g, "arial15", p[0].get<std::string>() + "  " + p[1].get<std::string>(), text);
    g.PathClipRegion();
    HitBox(row, "program", -1, program);
    Heart(g, R(row.R - 32, row.T, 30, 26), program);
  }
  if (mPresetItems.size() > 12) {
    float h = child.H() * 12 / mPresetItems.size();
    g.FillRect(border,
               R(child.R - 3,
                 child.T + (child.H() - h) * mPresetScroll / (mPresetItems.size() - 12), 2, h));
  }
  const double alpha = mCategoryReveal.At(mFrameTime);
  mVisualAnimating |= mCategoryReveal.Active(mFrameTime);
  if (alpha < 1) g.FillRect(IColor(int(255 * (1 - alpha)), bg.R, bg.G, bg.B), child.GetPadded(-1));
  if (mFavoriteSaveFailed)
    Text(g, "arial13", "FAVORITES NOT SAVED", R(child.L, child.B, child.W(), 24));
}
} // namespace krose::ui
