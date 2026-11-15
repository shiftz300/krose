#include "../../KrosePlugin.h"
#include "../../storage/JsonFile.h"
#include "IPlugPaths.h"
#include "NativePanel.h"
#include "PanelDrawing.h"
#include <algorithm>
#include <cstdlib>
#include <mutex>

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
std::set<std::string> ReadFavorites(const std::filesystem::path &path) {
  if (!std::filesystem::exists(path))
    return {};
  const auto data = storage::ReadJson(path);
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
    mFavorites = ReadFavorites(FavoritePath());
  } catch (const std::exception &) {
    mFavorites.clear();
  }
}
void NativePanel::ToggleFavorite(int program) {
  std::lock_guard<std::mutex> lock(favoriteMutex);
  try {
    const auto path = FavoritePath();
    auto favorites = ReadFavorites(path);
    const std::string id = Program(program)[0];
    if (!favorites.erase(id))
      favorites.insert(id);
    storage::WriteJson(path, Json{{"version", 1}, {"programs", favorites}});
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
  const bool on = mFavorites.count(Program(program)[0].get<std::string>()) != 0;
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
  const auto &currentCategory = Program(int(Value(kParamProgram)))[2];
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
  CollectPrograms(mPresetItems, category == -1 ? -2 : category);
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
    const auto &p = Program(program);
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

void NativePanel::StepProgram(int delta) {
  const auto &order = mProgramOrder;
  if (order.empty())
    return;
  auto it = std::find(order.begin(), order.end(), int(Value(kParamProgram)));
  const int count = int(order.size());
  int index = it == order.end() ? (delta > 0 ? count - 1 : 0) : int(it - order.begin());
  for (int i = 0; i < count; ++i) {
    index = (index + delta + count) % count;
    if (static_cast<KrosePlugin *>(GetDelegate())->ProgramAvailable(order[index])) {
      SetProgram(order[index]);
      return;
    }
  }
}
void NativePanel::SetProgram(int i) {
  auto *plugin = static_cast<KrosePlugin *>(GetDelegate());
  if (!plugin->ProgramAvailable(i)) return;
  mPresetStatus.clear();
  const auto [id, value] = plugin->ProgramParameter(i);
  Set(id, value);
  plugin->CaptureComparison();
  mPage = 0;
  mSlot = 0;
  mBrowsing = false;
  mPresetOpen = false;
  mEdit = -1;
}
void NativePanel::OpenBrowser() {
  ReleaseHeld();
  if (mPresetStatus == "PRESET FILE ERROR")
    mPresetStatus.clear();
  mBrowsing = true;
  LoadFavorites();
  mEdit = -2;
  const int current = int(Value(kParamProgram));
  FilterPrograms();
  auto selected = std::find(mFiltered.begin(), mFiltered.end(), current);
  if (selected == mFiltered.end()) {
    // A search or filter from the previous visit can hide the active Program.
    mSearch.clear();
    mGroup = mCategory = -1;
    FilterPrograms();
    selected = std::find(mFiltered.begin(), mFiltered.end(), current);
  }
  if (selected != mFiltered.end())
    mScroll = std::clamp(int(selected - mFiltered.begin()) - 3, 0,
                         std::max(0, int(mFiltered.size()) - 7));
}

void NativePanel::CollectPrograms(std::vector<int> &result, int category, int group,
                                  const std::string &search) {
  result.clear();
  auto *plugin = static_cast<KrosePlugin *>(GetDelegate());
  const auto query = Lower(search);
  for (int i : mProgramOrder) {
    if (!plugin->ProgramAvailable(i)) continue;
    const auto &p = Program(i);
    if (category == -2 && !mFavorites.count(p[0].get<std::string>()))
      continue;
    if (category >= 0 && p[2] != mBrowser["categories"][category])
      continue;
    if (group >= 0 && p[4] != mBrowser["groups"][group])
      continue;
    if (!query.empty() &&
        Lower(p[0].get<std::string>() + " " + p[1].get<std::string>()).find(query) ==
            std::string::npos)
      continue;
    result.push_back(i);
  }
}

void NativePanel::FilterPrograms() {
  CollectPrograms(mFiltered, mCategory, mGroup, mSearch);
  mScroll = 0;
}
void NativePanel::BeginPopup(const Hit &h) {
  mPopupTarget = h;
  mChoices.clear();
  mPopupFocus = 0;
}
void NativePanel::AddChoice(std::string label, int value) {
  mChoices.push_back({std::move(label), value});
}
void NativePanel::FocusChoice(int value) {
  const auto choice = std::find_if(mChoices.begin(), mChoices.end(),
                                   [value](const auto &item) { return item.value == value; });
  mPopupFocus = choice == mChoices.end() ? 0 : int(choice - mChoices.begin());
}
void NativePanel::CenterPopup() {
  mPopupScroll = std::clamp(mPopupFocus - mPopupRows / 2, 0,
                           std::max(0, int(mChoices.size()) - mPopupRows));
}
void NativePanel::OpenPopup(const Hit &h) {
  BeginPopup(h);
  if (h.action == "arp-edit") {
    AddChoice("Choose pattern", 0);
    AddChoice("Reset Program ARP", 1);
    AddChoice(Value(kArpKeyboard) ? "Keyboard thru: ON" : "Keyboard thru: OFF", 2);
  } else if (h.id == kArpPattern && h.action != "arp-pattern-items") {
    mPopupTarget.action = "arp-families";
    for (int i = 0; i < int(mArpFamilies.size()); ++i) AddChoice(mArpFamilies[i], i);
  } else if (h.action == "arp-pattern-items") {
    AddChoice("< Categories", -1);
    for (int i = 0; i <= 1029; ++i) {
      const std::string name = segrand::ArpPatternName(i).data();
      const auto family = i < 5 ? "Built-in" : name.substr(0, name.find('-'));
      if (family == mArpFamilies[mArpFamily]) AddChoice(name, i);
    }
    FocusChoice(int(Value(kArpPattern)));
  } else if (h.action == "scale" || h.action == "ui-scale") {
    AddChoice("AUTO / FIT SCREEN",0);
    for (int scale : {60, 75, 85, 100, 125, 150})
      AddChoice(std::to_string(scale) + "% / "+std::to_string(PLUG_WIDTH*scale/100)+"x"+std::to_string(PLUG_HEIGHT*scale/100), scale);
    FocusChoice(static_cast<KrosePlugin *>(GetDelegate())->EditorScalePercent());
  } else if (h.action == "group" || h.action == "category") {
    AddChoice(h.action == "group" ? "全部音色库" : "全部类型", -1);
    if (h.action == "category")
      AddChoice("FAVORITES", -2);
    auto &list = mBrowser[h.action == "group" ? "groups" : "categories"];
    for (int i = 0; i < int(list.size()); ++i)
      AddChoice(list[i], i);
    mPopupFocus = h.action == "group" ? mGroup + 1
                  : mCategory == -2   ? 1
                  : mCategory < 0     ? 0
                                      : mCategory + 2;
  } else {
    auto *p = GetDelegate()->GetParam(h.id);
    int maximum = int(p->GetMax());
#if defined(VST3_API)
    if (h.id == kClockSource)
      maximum = 1; // VST3 transports do not deliver raw F8 clock.
#endif
    for (int i = int(p->GetMin()); i <= maximum; ++i) {
      const char *text = p->GetDisplayText(i);
      AddChoice(text ? text : Format(i), i);
    }
    mPopupFocus = std::min(maximum, int(Value(h.id)));
  }
  mPopupRows = std::min(12, int(mChoices.size()));
  // Effect types start at y=142 inside the LCD; appended algorithms scroll
  // through the same seven rows instead of spilling onto the panel below.
  if (IsFxTypeParameter(h.id)) mPopupRows = std::min(mPopupRows, 7);
  if ((h.action == "field" && !IsFxTypeParameter(h.id)) || h.action == "midi-menu" || mPopupTarget.action.rfind("arp-",0) == 0) {
    // Keep LCD menus inside the display; scroll when the available side is short.
    float room = std::max(284 - h.r.B - 2, h.r.T - (mControllers ? 140 : 164) - 2);
    mPopupRows = std::min(mPopupRows, std::max(1, int(room / 22)));
  }
  CenterPopup();
  SetDirty(false);
}
void NativePanel::Popup(IGraphics &g) {
  bool lcd = mPopupTarget.action == "field" || mPopupTarget.action == "midi-menu" || mPopupTarget.action == "ui-scale" || mPopupTarget.action.rfind("arp-",0) == 0;
  const bool effectType = IsFxTypeParameter(mPopupTarget.id);
  const float rowHeight = effectType ? 20 : lcd ? 22 : 26;
  int count = mPopupRows;
  float width = mPopupTarget.r.W();
  float left = mPopupTarget.r.L, top = mPopupTarget.r.B + 2;
  if (effectType)
    top = 142;
  else if (top + count * rowHeight > (lcd ? 284 : 646))
    top = mPopupTarget.r.T - 2 - count * rowHeight;
  top = std::max(2.f, top);
  if (mPopupTarget.action=="ui-scale") top=std::clamp(top,115.f,284-count*rowHeight);
  auto r = R(left, top, width, count * rowHeight);
  if (lcd)
    r = LCDRect(r);
  HitBox(mRECT, "dismiss");
  g.FillRect(lcd ? Paper : IColor(255, 35, 38, 40), r);
  if (lcd)
    LCDFrame(g, r);
  else
    g.DrawRect(IColor(255, 118, 122, 125), r, nullptr, 1);
  for (int n = 0; n < count; ++n) {
    int i = mPopupScroll + n;
    auto row = R(left + 1, top + n * rowHeight, width - 2, rowHeight);
    if (lcd) {
      row = LCDRect(row);
      row.L = LCDX(r.L + 2.25f);
      row.R = LCDX(r.R - 2.25f);
      row.T = std::max(row.T, LCDY(r.T + 2.25f));
      row.B = std::min(row.B, LCDY(r.B - 2.25f));
    }
    bool selected = i == mPopupFocus;
    if (selected)
      g.FillRect(lcd ? Ink : IColor(255, 65, 81, 94), row);
    g.PathClipRegion(row.GetPadded(-1));
    Text(g, lcd ? (selected ? "light14" : "lcd14") : "arial15", mChoices[i].label,
         R((lcd ? r.L : row.L) + 7, row.T, row.W() - 14, row.H()));
    g.PathClipRegion();
    HitBox(row, "choice", -1, mChoices[i].value);
  }
  if (int(mChoices.size()) > count) {
    float h = r.H() * count / mChoices.size();
    auto bar = R(r.R - (lcd ? 4.5f : 3),
                 r.T + (r.H() - h) * mPopupScroll / (mChoices.size() - count), lcd ? 2.25f : 1, h);
    g.FillRect(lcd ? Ink : IColor(255, 150, 157, 162), lcd ? LCDRect(bar) : bar);
  }
  if (lcd)
    LCDGrid(g, r);
}
void NativePanel::Browser(IGraphics &g) {
  mHits.clear();
  Bitmap(g, "browser-base", 431, 129);
  // Replace the exported button chrome with a plain, high-contrast dismiss glyph.
  g.FillRect(IColor(255, 40, 43, 45), R(992, 147, 31, 32));
  const IColor closeInk(255, 225, 225, 220);
  g.DrawLine(closeInk, 1002, 157.5f, 1013, 168.5f, nullptr, 1.75f);
  g.DrawLine(closeInk, 1013, 157.5f, 1002, 168.5f, nullptr, 1.75f);
  HitBox(R(995, 150, 25, 26), "close");
  if (mPresetStatus == "PRESET FILE ERROR")
    Text(g, "arial13", mPresetStatus, R(704, 150, 166, 26), 2);
  Text(g, "arial13", "LOAD PRESET", R(875, 150, 115, 26), 1);
  HitBox(R(875, 150, 115, 26), "load");
  g.FillRoundRect(IColor(255, 35, 38, 40), R(452, 183, 227, 31), 2);
  g.DrawRect(IColor(255, 118, 122, 125), R(452, 183, 227, 31));
  g.DrawCircle(IColor(255, 173, 179, 183), 466, 197, 5, nullptr, 1.5f);
  g.DrawLine(IColor(255, 173, 179, 183), 470, 201, 475, 206, nullptr, 1.5f);
  g.PathClipRegion(R(481, 183, 185, 31));
  Text(g, "arial15", mSearch.empty() ? "名称或编号" : mSearch,
       R(481, 183, 185, 31));
  g.PathClipRegion();
  HitBox(R(452, 183, 227, 31), "search");
  for (auto r : {R(687, 183, 197, 31), R(892, 183, 128, 31)}) {
    g.FillRect(IColor(255, 35, 38, 40), r);
    g.DrawRect(IColor(255, 118, 122, 125), r, nullptr, 1);
  }
  Text(g, "arial15", mGroup < 0 ? "全部音色库" : mBrowser["groups"][mGroup].get<std::string>(),
       R(695, 183, 165, 31));
  Chevron(g, R(687, 183, 197, 31), IColor(255, 227, 227, 227));
  HitBox(R(687, 183, 197, 31), "group");
  Text(g, "arial15",
       mCategory == -2 ? "FAVORITES"
       : mCategory < 0 ? "全部类型"
                       : mBrowser["categories"][mCategory].get<std::string>(),
       R(900, 183, 96, 31));
  Chevron(g, R(892, 183, 128, 31), IColor(255, 227, 227, 227));
  HitBox(R(892, 183, 128, 31), "category");
  g.PathClipRegion(R(452, 226, 568, 292));
  // Keep seven complete rows; the last item can scroll fully into view.
  int maxScroll = std::max(0, int(mFiltered.size()) - 7);
  mScroll = std::clamp(mScroll, 0, maxScroll);
  const int current = int(Value(kParamProgram));
  for (int row = 0; row < 7 && mScroll + row < int(mFiltered.size()); ++row) {
    int i = mFiltered[mScroll + row];
    const auto &p = Program(i);
    auto b = R(452, 226 + row * 39, 568, 37);
    g.FillRoundRect(i == current ? IColor(255, 65, 81, 94) : IColor(255, 55, 59, 61), b, 3);
    g.DrawRoundRect(IColor(255, 69, 73, 75), b, 3);
    std::string s =
        p[0].get<std::string>() + "  " + p[1].get<std::string>() + " · " + p[2].get<std::string>();
    if (p.size() > 5 && !p[5].get<std::string>().empty())
      s += " · " + p[5].get<std::string>();
    auto text = b.GetPadded(-10);
    text.R -= 30;
    text.B = std::min(text.B, 518.f);
    g.PathClipRegion(text);
    Text(g, "arial15", s, text);
    g.PathClipRegion(R(452, 226, 568, 292));
    b.B = std::min(b.B, 518.f);
    HitBox(b, "program", -1, i);
    Heart(g, R(b.R - 32, b.T, 30, b.H()), i);
  }
  if (mFiltered.empty())
    Text(g, "arial15", "没有匹配的音色", R(452, 226, 568, 33));
  g.PathClipRegion();
  if (mFiltered.size() > 7) {
    float h = std::max(18.f, 280.f * 7 / mFiltered.size());
    g.FillRoundRect(IColor(150, 170, 175, 177),
                    R(1024, 226 + (280 - h) * mScroll / std::max(1, maxScroll), 4, h), 2);
  }
}
} // namespace krose::ui
