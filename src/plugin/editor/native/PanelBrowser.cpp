#include "../../KrosePlugin.h"
#include "NativePanel.h"
#include "PanelDrawing.h"
namespace krose::ui {
using namespace detail;
void NativePanel::FilterPrograms() {
  mFiltered.clear();
  for (int i : mBrowser["order"].get<std::vector<int>>()) {
    auto &p = mPrograms[i];
    if (mCategory == -2 && !mFavorites.count(p[0].get<std::string>()))
      continue;
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
  if (h.action == "arp-edit") {
    add("Choose pattern", 0);
    add("Reset Program ARP", 1);
    add(Value(kArpKeyboard) ? "Keyboard thru: ON" : "Keyboard thru: OFF", 2);
  } else if (h.id == kArpPattern && h.action != "arp-pattern-items") {
    mPopupTarget.action = "arp-families";
    for (int i = 0; i < int(mArpFamilies.size()); ++i) add(mArpFamilies[i], i);
  } else if (h.action == "arp-pattern-items") {
    add("< Categories", -1);
    for (int i = 0; i <= 1029; ++i) {
      const std::string name = segrand::ArpPatternName(i).data();
      const auto family = i < 5 ? "Built-in" : name.substr(0, name.find('-'));
      if (family == mArpFamilies[mArpFamily]) add(name, i);
    }
    auto selected = std::find(mChoiceValues.begin(), mChoiceValues.end(), int(Value(kArpPattern)));
    mPopupFocus = selected == mChoiceValues.end() ? 0 : int(selected-mChoiceValues.begin());
  } else if (h.action == "scale" || h.action == "ui-scale") {
    add("AUTO / FIT SCREEN",0);
    for (int scale : {60, 75, 85, 100, 125, 150})
      add(std::to_string(scale) + "% / "+std::to_string(PLUG_WIDTH*scale/100)+"x"+std::to_string(PLUG_HEIGHT*scale/100), scale);
    const auto selected=static_cast<KrosePlugin *>(GetDelegate())->EditorScalePercent();
    auto it=std::find(mChoiceValues.begin(),mChoiceValues.end(),selected);
    mPopupFocus=it==mChoiceValues.end() ? 0 : int(it-mChoiceValues.begin());
  } else if (h.action == "group" || h.action == "category") {
    add(h.action == "group" ? "全部音色库" : "全部类型", -1);
    if (h.action == "category")
      add("FAVORITES", -2);
    auto &list = mBrowser[h.action == "group" ? "groups" : "categories"];
    for (int i = 0; i < int(list.size()); ++i)
      add(list[i], i);
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
      add(text ? text : Format(i), i);
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
  mPopupScroll =
      std::clamp(mPopupFocus - mPopupRows / 2, 0, std::max(0, int(mChoices.size()) - mPopupRows));
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
    Text(g, lcd ? (selected ? "light14" : "lcd14") : "arial15", mChoices[i],
         R((lcd ? r.L : row.L) + 7, row.T, row.W() - 14, row.H()));
    g.PathClipRegion();
    HitBox(row, "choice", -1, mChoiceValues[i]);
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
  Text(g, "arial13", "LOAD FILE", R(885, 150, 95, 26), 1);
  HitBox(R(885, 150, 95, 26), "load");
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
  for (int row = 0; row < 7 && mScroll + row < int(mFiltered.size()); ++row) {
    int i = mFiltered[mScroll + row];
    auto &p = mPrograms[i];
    auto b = R(452, 226 + row * 39, 568, 37);
    g.FillRoundRect(IColor(255, 55, 59, 61), b, 3);
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
