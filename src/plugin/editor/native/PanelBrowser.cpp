#include "../../KrosePlugin.h"
#include "NativePanel.h"
#include "PanelDrawing.h"
namespace krose::ui {
using namespace detail;
void NativePanel::FilterPrograms() {
  mFiltered.clear();
  for (int i : mBrowser["order"].get<std::vector<int>>()) {
    auto &p = mPrograms[i];
    if (mCategory >= 0 && p[2] != mBrowser["categories"][mCategory])
      continue;
    if (mGroup >= 0 && p[4] != mBrowser["groups"][mGroup])
      continue;
    if (!mSearch.empty() &&
        Lower(p[0].get<std::string>() + " " + p[1].get<std::string>()).find(Lower(mSearch)) ==
            std::string::npos)
      continue;
    mFiltered.push_back(i);
  }
  mScroll = 0;
}
void NativePanel::OpenPopup(const Hit &h) {
  mPopupTarget = h;
  mChoices.clear();
  mChoiceValues.clear();
  mPopupScroll = 0;
  mPopupFocus = 0;
  auto add = [&](std::string s, int v) {
    mChoices.push_back(std::move(s));
    mChoiceValues.push_back(v);
  };
  if (h.action == "presets") {
    for (int i : mBrowser["order"].get<std::vector<int>>()) {
      auto &p = mPrograms[i];
      add(p[0].get<std::string>() + "  " + p[1].get<std::string>(), i);
      if (i == int(Value(kParamProgram)))
        mPopupFocus = int(mChoices.size()) - 1;
    }
  } else if (h.action == "group" || h.action == "category") {
    add(h.action == "group" ? "全部音色库" : "全部类型", -1);
    auto &list = mBrowser[h.action == "group" ? "groups" : "categories"];
    for (int i = 0; i < int(list.size()); ++i)
      add(list[i], i);
    mPopupFocus = (h.action == "group" ? mGroup : mCategory) + 1;
  } else {
    auto *p = GetDelegate()->GetParam(h.id);
    for (int i = int(p->GetMin()); i <= int(p->GetMax()); ++i) {
      const char *text = p->GetDisplayText(i);
      add(text ? text : Format(i), i);
    }
    mPopupFocus = int(Value(h.id));
  }
  mPopupScroll = std::clamp(mPopupFocus - 6, 0, std::max(0, int(mChoices.size()) - 12));
  SetDirty(false);
}
void NativePanel::Popup(IGraphics &g) {
  bool lcd = mPopupTarget.action == "field";
  float rowHeight = lcd ? 22 : 26;
  int count = std::min(12, int(mChoices.size()));
  float width = mPopupTarget.r.W();
  float left = mPopupTarget.r.L, top = mPopupTarget.r.B + 2;
  if (top + count * rowHeight > 646)
    top = mPopupTarget.r.T - 2 - count * rowHeight;
  top = std::max(2.f, top);
  auto r = R(left, top, width, count * rowHeight);
  HitBox(mRECT, "dismiss");
  g.FillRoundRect(lcd ? Paper : IColor(255, 35, 38, 40), r, 3);
  g.DrawRoundRect(lcd ? Ink : IColor(255, 118, 122, 125), r, 3);
  for (int n = 0; n < count; ++n) {
    int i = mPopupScroll + n;
    auto row = R(left + 1, top + n * rowHeight, width - 2, rowHeight);
    bool selected = i == mPopupFocus;
    if (selected)
      g.FillRect(lcd ? Ink : IColor(255, 65, 81, 94), row);
    g.PathClipRegion(row.GetPadded(-1));
    Text(g, lcd ? (selected ? "light14" : "lcd14") : "arial15", mChoices[i],
         R(row.L + 7, row.T, row.W() - 14, row.H()));
    g.PathClipRegion();
    HitBox(row, "choice", -1, mChoiceValues[i]);
  }
}
void NativePanel::Browser(IGraphics &g) {
  mHits.clear();
  g.FillRect(IColor(26, 0, 0, 0), mRECT);
  Bitmap(g, "browser-base", 431, 129);
  HitBox(R(995, 150, 25, 26), "close");
  Text(g, mSearch.empty() ? "placeholder15" : "search15", mSearch.empty() ? "名称或编号" : mSearch,
       R(481, 183, 185, 31));
  HitBox(R(452, 183, 227, 31), "search");
  Text(g, "search15", mGroup < 0 ? "全部音色库" : mBrowser["groups"][mGroup].get<std::string>(),
       R(695, 183, 165, 31));
  Chevron(g, R(687, 183, 197, 31), IColor(255, 38, 38, 38));
  HitBox(R(687, 183, 197, 31), "group");
  Text(g, "search15",
       mCategory < 0 ? "全部类型" : mBrowser["categories"][mCategory].get<std::string>(),
       R(900, 183, 96, 31));
  Chevron(g, R(892, 183, 128, 31), IColor(255, 38, 38, 38));
  HitBox(R(892, 183, 128, 31), "category");
  g.PathClipRegion(R(452, 226, 568, 292));
  int maxScroll = std::max(0, int(mFiltered.size()) - 8);
  mScroll = std::clamp(mScroll, 0, maxScroll);
  for (int row = 0; row < 8 && mScroll + row < int(mFiltered.size()); ++row) {
    int i = mFiltered[mScroll + row];
    auto &p = mPrograms[i];
    auto b = R(452, 226 + row * 39, 568, 37);
    g.FillRoundRect(IColor(255, 55, 59, 61), b, 3);
    g.DrawRoundRect(IColor(255, 69, 73, 75), b, 3);
    std::string s =
        p[0].get<std::string>() + "  " + p[1].get<std::string>() + " · " + p[2].get<std::string>();
    if (p.size() > 5 && !p[5].get<std::string>().empty())
      s += " · " + p[5].get<std::string>();
    Text(g, "arial15", s, b.GetPadded(-10));
    HitBox(b, "program", -1, i);
  }
  if (mFiltered.empty())
    Text(g, "arial15", "没有匹配的音色", R(452, 226, 568, 33));
  g.PathClipRegion();
  if (mFiltered.size() > 8) {
    float h = std::max(18.f, 280.f * 8 / mFiltered.size());
    g.FillRoundRect(IColor(150, 170, 175, 177),
                    R(1024, 226 + (280 - h) * mScroll / std::max(1, maxScroll), 4, h), 2);
  }
}
} // namespace krose::ui
