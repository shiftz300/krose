#include "../../KrosePlugin.h"
#include "NativePanel.h"
#include "PanelDrawing.h"
namespace krose::ui {
using namespace detail;
namespace {
constexpr const char *FxSlots[] = {"IFX 1", "IFX 2", "MFX 1", "MFX 2"};
constexpr std::array<int, segrand::kInsertTypes.size() - 2> InsertFxFaces{0, 1, 2, 3, 4};
constexpr std::array<int, segrand::kSendTypes.size() - 2> SendFxFaces{5, 6, 7, 8};
}
void NativePanel::DrawFxFace(IGraphics &g, const IRECT &module, int slot) {
  constexpr int tile = 54;
  const int type = FxType(slot);
  if (type <= 1) {
    DrawEmptyFxSlot(g, module, slot == 0);
    return;
  }
  const int column = slot < 2 ? InsertFxFaces[type - 2] : SendFxFaces[type - 2];
  const bool enabled = FxEnabled(slot);
  auto pixel = [](float v) { return std::round(v * 2) / 2; };
  // The display fills the inset only. The frame and shared marble are baked separately.
  const float x = pixel(module.L + module.W() * .1f);
  const float y = pixel(module.T + module.H() * .1f);
  g.DrawBitmap(Image("fx-faces"), R(x, y, tile, tile), column * tile, enabled ? 0 : tile);
  if (enabled) {
    if (slot < 2 && (type == 3 || type == 4))
      DrawFxMeter(g, R(x, y, tile, tile), slot);
    else
      DrawFxSignal(g, R(x, y, tile, tile), slot, type);
  }
  if (!enabled) {
    const float left = pixel(module.L + module.W() * .35f);
    const float right = pixel(module.L + module.W() * .65f);
    const float top = pixel(module.T), bottom = pixel(module.T + module.H() / 24);
    g.FillRect(IColor(255, 102, 102, 102), {left, top, right, bottom});
  }
}
void NativePanel::DrawFxMeter(IGraphics &g, const IRECT &r, int slot) {
  // Same glass and dial geometry as the approved face; the needle reads the
  // actual post-insert peak (dBFS), with a time-based 250 ms release.
  g.PathClear(); g.PathRect(r);
  const bool compressor = FxType(slot) == 3;
  g.PathFill(IPattern::CreateLinearGradient(r, EDirection::Vertical,
      compressor ? std::initializer_list<IColorStop>{{IColor(255,153,154,150),0},
          {IColor(255,218,220,214),.5f}, {IColor(255,181,185,180),1}} :
          std::initializer_list<IColorStop>{{IColor(255,169,156,112),0},
          {IColor(255,229,213,155),.5f}, {IColor(255,201,188,144),1}}));
  const float cx=r.MW(), cy=r.B-4, radius=23;
  const IColor ink(255,57,55,51), red(255,161,67,54);
  for (int j=0;j<36;++j) {
    const double a=-2.47+1.8*j/36., b=-2.47+1.8*(j+1)/36.;
    g.DrawLine(j>21?red:ink, cx+radius*std::cos(a),cy+radius*std::sin(a),
        cx+radius*std::cos(b),cy+radius*std::sin(b),nullptr,.85);
  }
  for (int j=0;j<9;++j) {
    const double a=-2.47+j*.225;
    g.DrawLine(j>5?red:ink,cx+radius*std::cos(a),cy+radius*std::sin(a),
        cx+(radius+2.8)*std::cos(a),cy+(radius+2.8)*std::sin(a),nullptr,.85);
    constexpr const char *labels[]={"-20","","-7","","-3","0","1","2","3"};
    const float tx=cx+(radius+5.2)*std::cos(a), ty=cy+(radius+5.2)*std::sin(a);
    g.DrawText(IText(4.8f,j>5?red:ink,"meter"),labels[j],R(tx-6,ty-4.8,12,6));
  }
  const double db=20*std::log10(std::max(.0001,mMeterLevels[slot]));
  constexpr double ticks[] = {-20, -10, -7, -5, -3, 0, 1, 2, 3};
  double position = 0;
  for (int i = 0; i < 8; ++i)
    if (db >= ticks[i])
      position = i + std::clamp((db - ticks[i]) / (ticks[i + 1] - ticks[i]), 0., 1.);
  const double angle = -2.47 + .225 * position;
  g.DrawLine(IColor(45,48,43,37),cx+1,cy,cx+28*std::cos(angle)+1,cy+28*std::sin(angle)+1,nullptr,1.2);
  g.DrawLine(IColor(255,170,56,50),cx,cy,cx+28*std::cos(angle),cy+28*std::sin(angle),nullptr,1);
  const float reduction = mFxAnalysis[slot].reduction;
  if (reduction > .001f)
    g.FillRect(IColor(160,145,56,49), R(r.L+4,r.B-3,(r.W()-8)*reduction,1.5));
}
void NativePanel::DrawEmptyFxSlot(IGraphics &g, const IRECT &module, bool vertical) {
  // Cover the entire baked housing and its shadow with the original bare marble.
  const int left = int(std::floor(module.L)) - 2;
  const int top = int(std::floor(module.T)) - 1;
  const auto backing = R(left, top, 78, std::ceil(module.B) + 8 - top);
  g.DrawBitmap(Image("fx-region-0"), backing, left, top - 19);

  const float x = module.MW(), y = module.MH();
  const auto rail = vertical ? R(x - 8, y - 30, 16, 60) : R(x - 30, y - 8, 60, 16);
  g.PathClear();
  g.PathRect(rail);
  const auto direction = vertical ? EDirection::Vertical : EDirection::Horizontal;
  g.PathFill(IPattern::CreateLinearGradient(rail, direction, {{IColor(0, 182, 81, 76), 0},
                                                             {IColor(42, 182, 81, 76), .25f},
                                                             {IColor(42, 182, 81, 76), .75f},
                                                             {IColor(0, 182, 81, 76), 1}}));

  // Match the FX lettering in the expanded panel artwork (#614239).
  const IColor ink(255, 97, 66, 57);
  constexpr float half = 6;
  g.PathClear();
  g.PathMoveTo(x, y - half);
  g.PathLineTo(x + half, y);
  g.PathLineTo(x, y + half);
  g.PathLineTo(x - half, y);
  g.PathClose();
  g.PathFill(ink);
}
int NativePanel::FxType(int slot) {
  const bool concert = Value(kParamProgram) == 0;
  return segrand::ResolveFxType(int(Value(kFxType1 + slot)), slot, concert,
                               concert && Value(kParamTone) == 2);
}
bool NativePanel::FxEnabled(int slot) {
  return !Value(kFXBypass) && Value(kFxOn1 + slot) && Value(kFxAmount1 + slot) > 0 &&
         FxType(slot) > 1 && (slot < 2 || Value(kParamSpace) > 0 ||
                             (slot == 2 && Value(kFxType3) == 0));
}
std::string NativePanel::FxName(int slot) {
  const int type = FxType(slot);
  if (slot == 0 && !Value(kFxType1) && type == 2)
    return "CONCERT EQ";
  return slot < 2 ? segrand::kInsertTypes[type] : segrand::kSendTypes[type];
}

void NativePanel::FxPage(IGraphics &g) {
  using namespace segrand;
  for (int i = 0; i < 4; ++i) {
    const auto rect = LCDRect(R(437 + 133 * i, 164, 133, 22));
    const bool selected = i == mSlot;
    if (selected)
      g.FillRect(Ink, rect);
    g.FillRect(Ink, LCDRect(R(rect.L, rect.B - 2.25f, rect.W(), 2.25f)));
    Text(g, selected ? "light14" : "lcd14", FxSlots[i], R(rect.L, 164, rect.W(), 18), 1);
    HitBox(rect, "fx-module", -1, i);
  }

  const int slot = mSlot;
  const int typeParam = kFxType1 + slot, amount = kFxAmount1 + slot;
  const bool automatic = Value(typeParam) == 0;
  const int type = FxType(slot);
  Field(g, "Type", FxTypeField(), typeParam, (automatic ? "A: " : "") + FxName(slot));
  Text(g, "lcd14", slot < 2 ? "Wet/Dry" : "Send", R(736, 192, 91, 19));
  Field(g, "", R(850, 190, 117, 21), amount, Format(Value(amount)) + "%", type > 1);

  if (type <= 1)
    return;
  if (automatic)
    Text(g, "lcd14", "Edit a parameter to switch AUTO to manual", R(437, 264, 530, 18));

  auto field = [&](int index, int detail) {
    const auto &spec = kFxValues[detail];
    const int param = FxDetailParameter(slot, detail);
    const auto value = Format(Value(param), spec.step >= 1 ? 0 : spec.step >= .1 ? 1 : 2);
    const float x = index % 2 == 0 ? 590 : 864;
    const float y = 216 + 24 * (index / 2);
    Field(g, std::string(spec.label) + spec.unit, R(x, y, 103, 21), param, value);
  };
  if (slot < 2) {
    switch (type) {
    case 2:
      Text(g, "lcd14", "Band", R(437, 218, 47, 18));
      for (int i = 0; i < 4; ++i)
        ControllerCell(g, "B" + std::to_string(i + 1), R(492 + 49 * i, 216, 46, 21), "fx-band",
                       -1, i, i == mFxBand);
      field(1, kEqFreq + 3 * mFxBand);
      field(2, kEqGain + 3 * mFxBand);
      field(3, kEqQ + 3 * mFxBand);
      break;
    case 3:
      field(0, kThreshold);
      field(1, kRatio);
      field(2, kAttack);
      field(3, kRelease);
      break;
    case 4:
      field(0, kCeiling);
      field(1, kRelease);
      break;
    case 5: field(0, kDrive); break;
    case 6: field(0, kBlend); break;
    }
  } else {
    switch (type) {
    case 2:
      field(0, kDepth);
      field(1, kLfoRate);
      break;
    case 3:
      field(0, kDelayLeft);
      field(1, kDelayRight);
      field(2, kFeedback);
      break;
    case 4:
    case 5:
      field(0, kDecay);
      field(1, kHiDamp);
      break;
    }
  }
}

} // namespace krose::ui
