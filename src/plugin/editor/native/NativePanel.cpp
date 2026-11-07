#include "NativePanel.h"
#include "../../KrosePlugin.h"
#include "../../ResourcePath.h"
#include "NativeData.h"
#include "PanelDrawing.h"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <fstream>

namespace krose::ui {
using namespace detail;
namespace {
constexpr const char *FxSlots[] = {"IFX 1", "IFX 2", "MFX 1", "MFX 2"};
struct PanelResources {
  const nlohmann::json data = nlohmann::json::parse(kNativeData);
  const nlohmann::json programs = nlohmann::json::parse(kNativePrograms);
  const nlohmann::json browser = nlohmann::json::parse(kNativeBrowser);
  const nlohmann::json lcd = nlohmann::json::parse(kNativeLCD);
  const std::vector<int> order = browser.at("order").get<std::vector<int>>();
};
const PanelResources &Resources() {
  static const PanelResources resources;
  return resources;
}
} // namespace
NativePanel::NativePanel()
    : IControl(R(0, 0, 1472, 648)), mData(Resources().data), mPrograms(Resources().programs),
      mBrowser(Resources().browser), mLCD(Resources().lcd), mProgramOrder(Resources().order) {
  // Buttons and keys must receive every press, including OS double-clicks.
  mDblAsSingleClick = true;
}
NativePanel::~NativePanel() {
  if (const char *path = std::getenv("KROSE_UI_PROFILE")) {
    Json result;
    auto summary = [](std::vector<double> v) {
      if (v.empty())
        return Json::object();
      std::sort(v.begin(), v.end());
      return Json{{"count", v.size()},
                  {"median_ms", v[v.size() / 2]},
                  {"p95_ms", v[std::min(v.size() - 1, size_t(v.size() * .95))]}};
    };
    result["draw_cpu"] = summary(mDrawTimes);
    result["animation_frame_gap"] = summary(mFrameGaps);
    std::ofstream(path) << result.dump(2) << '\n';
  }
}
void NativePanel::OnInit() {
  mResourceRoot =
      krose::ResourceDirectory(static_cast<KrosePlugin *>(GetDelegate())->GetBundleID()).u8string();
  for (auto it = mData["fonts"].begin(); it != mData["fonts"].end(); ++it) {
    auto &f = mFonts[it.key()];
    // These four export-only atlases have no native controls. Keep the active
    // atlases preloaded so opening menus/pages never decodes during animation.
    if (it.key() != "light16" && it.key() != "light14" && it.key() != "search15" &&
        it.key() != "placeholder15")
      f.image = Image("font-" + it.key());
    f.chars = Chars(it.value()["chars"]);
    f.advances = it.value()["advances"].get<std::vector<double>>();
    f.glyphs = it.value()["glyphs"].get<std::vector<std::array<float, 6>>>();
    for (size_t i = 0; i < f.chars.size(); ++i)
      f.indices.emplace(f.chars[i], i);
    f.size = it.value()["size"];
  }
  Image("fx-faces");
  GetUI()->LoadFont("meter", "Roboto-Regular.ttf");
  Image("fx-region-0");
  FilterPrograms();
  mStoredMapping = ControllerHash();
  auto *plugin = static_cast<KrosePlugin *>(GetDelegate());
  plugin->EnableVisuals(true);
  if (!plugin->ComparisonReady())
    plugin->CaptureComparison();
}
double NativePanel::Value(int id) { return GetDelegate()->GetParam(id)->Value(); }
void NativePanel::Set(int id, double v, bool gesture) {
  if (mParameters.Set(*GetDelegate(), id, v, gesture)) {
    mPresetStatus.clear();
    // Editing an AUTO effect promotes only this slot to its explicit type.
    if (id >= kFxDetails && !Value(kFxType1 + mSlot) && FxType(mSlot) > 1)
      Set(kFxType1 + mSlot, FxType(mSlot));
    SetDirty(false);
  }
}
void NativePanel::Refresh(double tempo, bool host, bool loading, bool loadFailed) {
  bool changed = tempo != mTempo || host != mHost || FoldProgress() != mRenderedFold ||
                 loading != mLoading || loadFailed != mLoadFailed;
  mLoading = loading;
  mLoadFailed = loadFailed;
  mTempo = tempo;
  mHost = host;
  changed = mParameters.Changed(*GetDelegate()) || changed;
  auto &map = static_cast<KrosePlugin *>(GetDelegate())->MidiMappings();
  if (mControllers && (mMapRevision != map.Revision() ||
                       (mControllerPage == 3 && mLastMidi != map.LastMessage()))) {
    if (map.Learning() < 0 && mMapRevision != map.Revision())
      mControllerStatus = "Map updated / INPUT > STORE";
    changed = true;
  }
  mMapRevision = map.Revision();
  mLastMidi = map.LastMessage();
  if (changed)
    SetDirty(false);
}
void NativePanel::HitBox(IRECT r, std::string action, int id, double v) {
  mHits.push_back({r, std::move(action), id, v});
}
void NativePanel::Bitmap(IGraphics &g, const std::string &name, float x, float y) {
  auto &b = Image(name);
  g.DrawBitmap(b, R(x, y, b.W(), b.H()));
}
const IBitmap &NativePanel::Image(const std::string &name) {
  auto found = mImages.find(name);
  if (found != mImages.end())
    return found->second;
  auto path = std::filesystem::u8path(mResourceRoot) / (name + ".png");
  return mImages.emplace(name, GetUI()->LoadBitmap(path.u8string().c_str(), 1, false, 2))
      .first->second;
}
double NativePanel::TextWidth(const std::string &font, const std::string &s) const {
  auto &f = mFonts.at(font);
  double w = 0;
  for (auto &ch : Chars(s)) {
    auto i = f.indices.find(ch);
    w += i == f.indices.end() ? f.size * .6 : f.advances[i->second];
  }
  return w;
}
void NativePanel::Text(IGraphics &g, const std::string &font, const std::string &s, const IRECT &r,
                       int align) {
  auto &f = mFonts.at(font);
  if (!f.image.IsValid())
    f.image = Image("font-" + font);
  float x = align == 1   ? r.MW() - TextWidth(font, s) / 2
            : align == 2 ? r.R - TextWidth(font, s)
                         : r.L;
  float baseline = r.MH() + f.size * .3f;
  if (font.rfind("mono", 0) == 0)
    baseline += 1;
  if (font == "arial14")
    baseline += .5f;
  for (auto &ch : Chars(s)) {
    auto it = f.indices.find(ch);
    if (it == f.indices.end()) {
      x += f.size * .6;
      continue;
    }
    size_t i = it->second;
    const auto &a = f.glyphs[i];
    if (a[2] > 0)
      g.DrawBitmap(f.image, R(x + a[4], baseline + a[5], a[2], a[3]), a[0], a[1]);
    x += f.advances[i];
  }
}
void NativePanel::Button(IGraphics &g, const std::string &name, bool on, const std::string &action,
                         int id, double v, bool enabled) {
  std::string key = "button-" + name + (on ? "-on" : "-off");
  auto it = std::find_if(mData["assets"].begin(), mData["assets"].end(),
                         [&](const Json &e) { return e["name"] == key; });
  if (it == mData["assets"].end())
    return;
  auto r = (*it)["rect"];
  const auto bounds = R(r[0], r[1], r[2], r[3]);
  const double light = Visual("button:" + name, on ? 1 : 0);
  if (light < 1) Bitmap(g, "button-" + name + "-off", r[0], r[1]);
  if (light > 0) {
    IBlend blend(EBlend::Default, float(light));
    g.DrawBitmap(Image("button-" + name + "-on"), bounds, 1, &blend);
  }
  const bool hover = enabled && !mBrowsing && !mPresetOpen && mChoices.empty() &&
                     bounds.Contains(mMouseX, mMouseY);
  const double glow = Visual("hover:" + name, hover ? 1 : 0, .10);
  if (glow > 0) g.FillRect(IColor(int(10 * glow), 255, 255, 255), bounds.GetPadded(-5));
  if (mPointerDown && hover) mPressedButton = name;
  double press = Visual("press:" + name,
      mPointerDown && mPressedButton == name ? 1 : 0, .08);
  const double clickAge = mFrameTime - mClickTime;
  if (bounds.Contains(mClickX, mClickY) && clickAge >= 0 && clickAge < .09) {
    press = std::max(press, .65 * (1 - clickAge / .09));
    mVisualAnimating = true;
  }
  if (press > 0) g.FillRect(IColor(int(35 * press), 0, 0, 0), bounds.GetPadded(-5));
  if (enabled)
    HitBox(R(float(r[0]) + 3, float(r[1]) + 3, float(r[2]) - 6, float(r[3]) - 6), action, id, v);
}
void NativePanel::Draw(IGraphics &g) {
  mFrameTime = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
  mVisualAnimating = false;
  const bool profiling = std::getenv("KROSE_UI_PROFILE");
  const auto start =
      profiling ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};

  mHits.clear();
  const char *capture = std::getenv("KROSE_NATIVE_CAPTURE");
  if (capture) {
    g.StartLayer(this, mRECT);
    Render(g);
    auto layer = g.EndLayer();
    RawBitmapData pixels;
    g.GetLayerBitmapData(layer, pixels);
    auto bitmap = layer->GetAPIBitmap();
    std::ofstream out(capture, std::ios::binary);
    out << "P7\nWIDTH " << bitmap->GetWidth() << "\nHEIGHT " << bitmap->GetHeight()
        << "\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n";
    out.write(reinterpret_cast<const char *>(pixels.Get()), pixels.GetSize());
    g.DrawLayer(layer);
  } else
    Render(g);
  if (profiling) {
    mDrawTimes.push_back(
        std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start)
            .count());
    const bool animating = mVisualAnimating || FoldProgress() != double(mFold);
    if (animating && mPreviousAnimating)
      mFrameGaps.push_back(
          std::chrono::duration<double, std::milli>(start - mPreviousFrame).count());
    mPreviousAnimating = animating;
    mPreviousFrame = start;
  }
}
bool NativePanel::IsDirty() {
  const bool signalChanged = UpdateFxVisuals();
  return IControl::IsDirty() || mVisualAnimating || FoldProgress() != mRenderedFold ||
         (signalChanged && FoldProgress() < 1) || mOutputReduction > .0001f;
}
double NativePanel::FoldProgress() const {
  return mFXMotion
      .At(std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch())
              .count())
      .position;
}
void NativePanel::Render(IGraphics &g) {
  Bitmap(g, "native-base", 0, 0);
  int program = int(Value(kParamProgram));
  double folded = FoldProgress();
  mRenderedFold = folded;
  if (folded < 1) {
    if (folded > 0) {
      if (g.CheckLayer(mFXLayer))
        g.ResumeLayer(mFXLayer);
      else
        g.StartLayer(this, R(0, 19, 428, 332));
      IBlend erase(EBlend::DstOut);
      g.FillRect(COLOR_WHITE, R(0, 19, 428, 332), &erase);
    }
    Bitmap(g, "fx-region-1", 0, 19);
    int slot = 0;
    for (const auto &module : mData["fxHits"]["1"]) {
      if (module["kind"] != "module")
        continue;
      const auto &rect = module["rect"];
      DrawFxFace(g, R(rect[0], rect[1], rect[2], rect[3]), slot++);
    }
    if (folded > 0) {
      g.PathClear();
      g.PathRect(R(0, 19, 428, 332));
      g.PathSetWinding(false);
      g.PathCircle(71.5, 84.59375, 550 * (1 - folded));
      g.PathSetWinding(true);
      IBlend cut(EBlend::DstOut);
      g.PathFill(COLOR_WHITE, IFillOptions(false, EFillRule::Preserve), &cut);
      mFXLayer = g.EndLayer();
      g.DrawLayer(mFXLayer);
    }
    // The exposed material already includes its red rail. Keep the white rail
    // from native-base everywhere outside the revealed FX region.
  }
  HitBox(R(38.5, 57.59375, 66, 54), "fold");
  struct KnobInfo {
    int id;
    float x, y;
  };
  const KnobInfo knobs[] = {{kGlide, 151, 176},         {kParamPan, 307, 176},
                            {kParamCutoff, 151, 278},   {kParamResonance, 229, 278},
                            {kParamVelocity, 307, 278}, {kParamOutput, 1370, 176}};
  for (auto k : knobs) {
    Bitmap(g, "knob-shell", k.x - 8, k.y - 8);
    g.DrawRotatedBitmap(Image("knob-pointer"), k.x + 24, k.y + 24,
                        -135 + 270 * Visual("knob:" + std::to_string(k.id),
                            GetDelegate()->GetParam(k.id)->GetNormalized(), .12, mDrag == k.id));
    HitBox(R(k.x - 8, k.y - 8, 64, 64), "knob", k.id);
    double v = Value(k.id);
    std::string s = k.id == kParamOutput     ? Format(v, 1) + " dB"
                    : k.id == kParamVelocity ? Format(v, 2) + "×"
                    : k.id == kParamPan
                        ? (v == 0 ? "C" : std::string(v < 0 ? "L" : "R") + Format(std::abs(v)))
                    : k.id == kGlide ? Format(v)
                                     : Signed(v);
    auto r = R(k.x - 10, k.y + 55, 68, 22);
    Text(g, "mono12", mEdit == k.id ? mEditText : s, r, 1);
    HitBox(r, "edit", k.id);
  }
  const double clock = mFrameTime;
  if (clock < mOverloadUntil) {
    Text(g, "mono10", "SAFE", R(1336, 258, 68, 16), 1);
    g.FillRect(IColor(180, 155, 67, 62), R(1346, 275, 48 * std::clamp(mOutputReduction, 0.f, 1.f), 2));
  }
  Bitmap(g, "knob-shell", 221, 168);
  Bitmap(g, "knob-pointer", 229, 176);
  HitBox(R(221, 168, 64, 64), "step", -1, 1);
  Button(g, "arp", Value(kArpEnabled) > 0, "toggle", kArpEnabled);
  Button(g, "latch", Value(kArpLatch) > 0, "toggle", kArpLatch);
  Button(g, "amp", mEG == 0, "eg", -1, 0);
  Button(g, "filter", mEG == 1, "eg", -1, 1);
  for (int i = 0; i < 4; ++i) {
    int id = (mEG ? kFilterAttack : kAmpAttack) + i;
    float cx = 1057 + i * 60, cy = 132 + 135 * (1 -
        Visual("fader:" + std::to_string(i), (Value(id) + 99) / 198, .12, mDrag == id));
    Bitmap(g, "fader-thumb", cx - 20, cy - 14.5);
    auto r = R(cx - 27, 278, 54, 15);
    Text(g, "mono12", Signed(Value(id)), r, 1);
    HitBox(R(cx - 20, 123, 40, 153), "fader", id);
  }
  for (int i = 0; i < 3; ++i)
    Button(g, Lower(Modes[i]), int(Value(kVoiceMode)) == i, "set", kVoiceMode, i);
  Button(g, "sustain", mSustain, "sustain");
  Button(g, "kf-panic", false, "panic");
  Button(g, "kf-prev", false, "step", -1, -1);
  Button(g, "kf-next", false, "step", -1, 1);
  Button(g, "kf-browse", false, "browse");
  Button(g, "kf-save", false, "save");
  Button(g, "kf-compare", static_cast<KrosePlugin *>(GetDelegate())->Comparing(), "compare");
  Button(g, "sw1", Value(kSW1State) > 0, "switch", 0);
  Button(g, "sw2", Value(kSW2State) > 0, "switch", 1);
  // Each white key is drawn first, then the raised black keys and their shadows.
  int white = 0;
  for (int i = 0; i < 61; ++i) {
    bool black = (i % 12 == 1 || i % 12 == 3 || i % 12 == 6 || i % 12 == 8 || i % 12 == 10);
    if (black)
      continue;
    int note = 36 + i + 12 * mOctave;
    float x = 198 + 34 * white++;
    KeyImage(g, note, false, x - 3);
    HitBox(R(x, 396, 34, 216), "note", note);
    if (i % 12 == 0)
      Text(g, "arial9", "C" + std::to_string(note / 12 - 1), R(x, 590, 34, 18), 1);
  }
  white = 0;
  for (int i = 0; i < 61; ++i) {
    bool black = (i % 12 == 1 || i % 12 == 3 || i % 12 == 6 || i % 12 == 8 || i % 12 == 10);
    if (!black) {
      ++white;
      continue;
    }
    int note = 36 + i + 12 * mOctave;
    float x = 198 + 34 * white - 10.203125f;
    KeyImage(g, note, true, std::floor(x) - 3);
    HitBox(R(x, 396, 20.390625f, 134), "note", note);
  }
  // The pitch indicator shares the reference's unscaled travel distance.
  Bitmap(g, "pitch-mark", 56, 491 - Visual("pitch", mPitch / 8192, .12, mDrag == -2) * 50.82);
  Bitmap(g, "pitch-mark", 128, 541.82 - Visual("mod", mMod / 127, .12, mDrag == -3) * 101.64);
  HitBox(R(129, 433, 29, 127), "mod");
  HitBox(R(57, 433, 29, 127), "pitch");
  Bitmap(g, "kf-oct-down", 36, 589);
  Bitmap(g, "kf-oct-up", 132, 589);
  Text(g, "mono10",
       std::string("OCT") +
           (mOctave < 0   ? "−"
            : mOctave > 0 ? "+"
                          : " ") +
           std::to_string(std::abs(mOctave)),
       R(79, 592, 57, 32), 1);
  HitBox(R(39, 592, 40, 32), "octave", -1, -1);
  HitBox(R(136, 592, 40, 32), "octave", -1, 1);
  auto &p = mPrograms[program];
  g.FillRect(IColor(255, 34, 34, 34), R(507, 52, 482, 30));
  g.DrawRect(IColor(255, 94, 99, 102), R(507, 52, 482, 30), nullptr, 1);
  auto presetText = R(515.015625, 52, mLoading ? 340 : 444, 30);
  g.PathClipRegion(R(presetText.L - 4, presetText.T, presetText.W() + 4, presetText.H()));
  Text(g, "arial14", p[0].get<std::string>() + " " + p[1].get<std::string>(), presetText);
  g.PathClipRegion();
  if (mLoading)
    Text(g, "arial13", mLoadFailed ? "LOAD FAILED" : "LOADING", R(862, 52, 97, 30), 2);
  Chevron(g, R(507, 52, 482, 30), IColor(255, 227, 227, 227));
  HitBox(R(507, 52, 482, 30), "presets");
  if (!mFold && !mBrowsing) {
    int slot = 0;
    for (const auto &h : mData["fxHits"]["1"])
      if (h["kind"] == "module") {
        auto a = h["rect"];
        auto r = R(a[0], a[1], a[2], a[3]);
        const bool empty = FxType(slot) <= 1;
        HitBox(r, empty ? "fx-add" : "fx-toggle", -1, slot);
        if (r.Contains(mMouseX, mMouseY)) {
          const std::string label = std::string(FxSlots[slot]) + " / " +
                                    (empty ? "ADD FX" : FxEnabled(slot) ? FxName(slot) : "OFF");
          float width = TextWidth("mono10", label) + 14;
          auto box = R(r.L, r.B + 3, width, 23);
          g.FillRoundRect(IColor(255, 34, 50, 47), box, 2);
          g.DrawRoundRect(IColor(255, 120, 137, 132), box, 2);
          Text(g, "mono10", label, box.GetPadded(-7));
        }
        ++slot;
      }
  }
  g.PathClipRegion(R(424, 108, 556, 176));
  LCD(g);
  if (!mPresetStatus.empty() && !mControllers && mPage == 0) {
    g.FillRect(Paper, R(431, 260, 542, 24));
    Text(g, "lcd13", mPresetStatus, R(437, 263, 530, 20));
  }
  const int lcdState = mPage + 8 * mSlot + 32 * mFxBand +
                       256 * int(mControllers) + 512 * mControllerPage + 4096 * program;
  if (mLCDState != lcdState) {
    mLCDReveal.Snap(mLCDState < 0 ? 1 : .65);
    mLCDReveal.Target(1, mFrameTime, .10);
    mLCDState = lcdState;
  }
  const double lcdAlpha = mLCDReveal.At(mFrameTime);
  mVisualAnimating |= mLCDReveal.Active(mFrameTime);
  if (lcdAlpha < 1) g.FillRect(IColor(int(255 * (1 - lcdAlpha)), Paper.R, Paper.G, Paper.B),
                              R(431, 115, 542, 169));
  LCDGrid(g, R(431, 115, 542, 169));
  g.PathClipRegion();
  // Opacity only: text stays on the pixel grid and hit regions are live immediately.
  if (mBrowsing) g.FillRect(IColor(26, 0, 0, 0), mRECT);
  Reveal(g, mBrowsing, 0, R(425, 123, 616, 410), &NativePanel::Browser);
  Reveal(g, !mChoices.empty(), 1,
         R(mPopupTarget.r.L - 4, 0, mPopupTarget.r.W() + 8, 648), &NativePanel::Popup);
  Reveal(g, mPresetOpen, 2, R(505, 82, 586, 340), &NativePanel::PresetMenu);
  if (mKeyboardFocus && mFocus >= 0 && mFocus < int(mHits.size()))
    g.DrawRect(IColor(180, 215, 225, 230), mHits[mFocus].r.GetPadded(2), nullptr, 1);
}
void NativePanel::ProgramRow(IGraphics &g) {
  const auto &p = mPrograms[int(Value(kParamProgram))];
  std::string code = p[0], cat = p[2];
  std::string symbol = cat.rfind("SYNTH ", 0) == 0 ? "SYNTH" : cat;
  constexpr float sx = 542.f / 240.f, sy = 27.09375f / 12.f;
  const float left = 431, top = 139;
  auto stamp = [&](const Json &rows, int width, int x, int y, size_t firstRow = 0) {
    int j = 0;
    for (size_t row = firstRow; row < rows.size(); ++row) {
      int bits = rows[row];
      for (int i = 0; i < width;) {
        if (!(bits & (1 << (width - 1 - i)))) {
          ++i;
          continue;
        }
        int start = i;
        while (i < width && (bits & (1 << (width - 1 - i))))
          ++i;
        float l = std::round((left + (x + start) * sx) * 2) / 2,
              t = std::round((top + (y + j) * sy) * 2) / 2,
              r = std::round((left + (x + i) * sx) * 2) / 2,
              b = std::round((top + (y + j + 1) * sy) * 2) / 2;
        g.FillRect(Ink, {l, t, r, b});
      }
      ++j;
    }
  };
  if (mLCD["symbols"].contains(symbol)) {
    const auto &icon = mLCD["symbols"][symbol];
    stamp(icon["rows"], icon["width"], 10, 0);
  }
  if (code.rfind("EXPCM00", 0) == 0)
    code = "E" + code.substr(7, 1) + "-" + code.substr(9);
  if (cat.rfind("SYNTH ", 0) == 0)
    cat = cat.substr(6);
  char index[16];
  std::snprintf(index, sizeof(index), "%03d", p[3].get<int>());
  std::string label = cat + ":" + index + " (" + code + ")";
  static const Json dash = Json::array({6, 0, 0, 0, 248, 0, 0, 0, 0, 0});
  auto glyph = [&](const std::string &ch) -> const Json & {
    if (mLCD["font"]["glyphs"].contains(ch))
      return mLCD["font"]["glyphs"][ch];
    if (ch == "-")
      return dash;
    return mLCD["font"]["glyphs"][" "];
  };
  int width = 0;
  for (auto ch : Chars(label))
    width += glyph(ch)[0].get<int>();
  int x = std::min(59, 154 - width);
  auto text = [&](std::string s, int x, int y) {
    for (auto ch : Chars(s)) {
      const auto &a = glyph(ch);
      int advance = a[0];
      stamp(a, 8, x, y, 1);
      x += advance;
    }
  };
  text(label, x, 2);
  const auto &sprites = mLCD["tempoReference"]["sprites"];
  stamp(sprites["["], 3, 157, 1);
  stamp(sprites["note"], 4, 162, 2);
  stamp(sprites["="], 5, 169, 4);
  stamp(sprites["]"], 3, 222, 1);
  text(Format(Value(kArpHostSync) && mHost ? mTempo : Value(kArpTempo), 2), 178, 0);
  stamp(mLCD["symbols"]["AC"]["rows"], 13, 227, 2);
}
void NativePanel::Chevron(IGraphics &g, const IRECT &r, const IColor &color) {
  const float x = std::floor(r.R - 12), y = std::floor(r.MH());
  // Integer dot runs keep the selector arrow on the LCD's pixel grid.
  for (int row = 0; row < 4; ++row) {
    float width = 1 + row * 2;
    g.FillRect(color, R(x - row, y - 6 + row, width, 1));
    g.FillRect(color, R(x - row, y + 5 - row, width, 1));
  }
}
void NativePanel::Field(IGraphics &g, const std::string &label, const IRECT &bounds, int id,
                        const std::string &text, bool enabled) {
  const auto r = LCDRect(bounds);
  const char *font = mPage == 3 ? "lcd14" : "lcd16";
  bool check = id == kArpSort || id == kArpKeySync;
  bool choice = id == kParamTone || id == kArpPattern || id == kArpResolution || IsFxTypeParameter(id);
  float left = r.L < 700 ? 437 : mPage == 3 ? 711 : 713.5;
  constexpr float textInset = 27.09375f / 12;
  Text(g, font, label, R(left, r.T + textInset, r.L - left - 4, r.H()));
  if (check) {
    g.FillRect(Value(id) > 0 ? Ink : Paper, r);
    LCDFrame(g, r);
    if (Value(id) > 0) {
      constexpr float dot = 542.f / 240;
      for (const auto &cell : {std::pair<int, int>{1, 3}, {2, 4}, {3, 3}, {4, 2}, {5, 1}})
        g.FillRect(Paper, LCDRect(R(r.L + cell.first * dot, r.T + cell.second * dot, dot, dot)));
    }
  } else {
    if (choice)
      LCDFrame(g, r);
    else
      g.FillRect(Ink, LCDRect(R(r.L, r.B - 2.25f, r.W(), 2.25f)));
    bool editing = mEdit >= 0 && mEdit == id;
    if (editing)
      g.FillRect(Ink, r);
    if (choice)
      LCDChevron(g, r, editing ? Paper : Ink);
    else {
      auto a = R(r.R - 19, r.T + 2, 16, r.H() - 4);
      LCDChevron(g, R(a.L + 5, a.T, a.W(), a.H()), editing ? Paper : Ink);
    }
    const auto textBox = R(r.L + (choice ? 7 : 3), r.T, r.W() - (choice ? 31 : 24), r.H() - 2);
    g.PathClipRegion(textBox);
    Text(g, editing ? (mPage == 3 ? "light14" : "light16") : font, editing ? mEditText : text,
         R(textBox.L, textBox.T + textInset, textBox.W(), textBox.H()), choice ? 0 : 2);
    g.PathClipRegion(R(424, 108, 556, 176));
  }
  if (enabled) {
    HitBox(r, check ? "toggle" : "field", id);
    if (!check && !choice) {
      HitBox(R(r.R - 19, r.T, 16, r.H() / 2), "increment", id, 1);
      HitBox(R(r.R - 19, r.MH(), 16, r.H() / 2), "increment", id, -1);
    }
  }
}
void NativePanel::LCD(IGraphics &g) {
  if (mControllers) {
    Controllers(g);
    return;
  }
  HitBox(R(432, 115, 220, 23), "controller-open");
  Bitmap(g, std::string("tabs-") + Pages[mPage], 432, 115);
  Text(g, "light14", ">CTRL", R(557, 118, 93, 19), 2);
  for (int i = 0; i < 4; ++i)
    HitBox(R(667 + i * 76, 116, 76, 20), "page", -1, i);
  int program = int(Value(kParamProgram));
  auto &p = mPrograms[program];
  std::string name = p[1], code = p[0], category = p[2];
  if (mPage == 0) {
    ProgramRow(g);
    Text(g, "lcd35", name, R(436, 187.5, 532, 35), 1);
    g.DrawLine(Ink, 436, 250, 968, 250);
    Text(g, "lcd15",
         p.size() > 5 && !p[5].get<std::string>().empty()
             ? p[5].get<std::string>()
             : std::string("Voice: ") + Modes[int(Value(kVoiceMode))],
         R(436, 258, 210, 18));
    std::string effects = Value(kFXBypass) ? "FX BYPASS" : "IFX 1/2  MFX 1/2";
    Text(g, "lcd15", effects, R(436, 258, 532, 18), 2);
    HitBox(R(783.3125, 139, 189.6875, 27.09375), "toggle", kArpHostSync);
    return;
  }
  std::string source = category + " (" + code + ")";
  std::string tempo =
      std::string(Value(kArpHostSync) && mHost ? (Value(kClockSource) == 2 ? "MIDI " : "HOST ")
                                               : "INT ") +
      Format(Value(kArpHostSync) && mHost ? mTempo : Value(kArpTempo), 2);
  float sourceWidth = TextWidth("lcd16", source), tempoWidth = TextWidth("lcd16", tempo);
  float nameX = 446 + sourceWidth, nameRight = 958 - tempoWidth;
  Text(g, "lcd16", source, R(436, 140, sourceWidth, 20));
  g.FillRect(Ink, LCDRect(R(nameX, 141, nameRight - nameX, 18)));
  Text(g, "light16", name, R(nameX + 6, 140, nameRight - nameX - 12, 20));
  Text(g, "lcd16", tempo, R(968 - tempoWidth, 140, tempoWidth, 20), 2);
  HitBox(R(968 - tempoWidth, 140, tempoWidth, 20), "toggle", kArpHostSync);
  if (mPage == 1) {
    Field(g, "Cutoff:", R(621.5, 168, 68, 24), kParamCutoff, Format(Value(kParamCutoff)));
    Field(g, "Resonance:", R(899, 168, 68, 24), kParamResonance, Format(Value(kParamResonance)));
    Field(g, "Pan:", R(621.5, 200, 68, 24), kParamPan, Format(Value(kParamPan)), false);
    Field(
        g, "Velocity:", R(899, 200, 68, 24), kParamVelocity,
        Format(Value(kParamVelocity), Value(kParamVelocity) == int(Value(kParamVelocity)) ? 0 : 2));
    const char *t[] = {"Concert", "Warm", "Wide"};
    Field(g, "Tone", R(581.5, 232, 108, 24), kParamTone, t[int(Value(kParamTone))], program == 0);
    Field(g, "Release", R(899, 232, 68, 24), kParamRelease, Format(Value(kParamRelease)));
    Field(g, "Space", R(621.5, 264, 68, 24), kParamSpace, Format(Value(kParamSpace)));
  }
  if (mPage == 3) {
    Text(g, "lcd13",
         std::string("ARP ") + (Value(kArpEnabled) ? "ON" : "OFF") + " · LATCH " +
             (Value(kArpLatch) ? "ON" : "OFF"),
         R(437, 257, 530, 18));
    const char *patterns[] = {"UP", "DOWN", "ALT 1", "ALT 2", "RANDOM"};
    const char *rates[] = {"1/32T", "1/32", "1/16T", "1/16", "1/8T", "1/8", "1/4T", "1/4"};
    Field(g, "Pattern:", R(585, 168, 108, 18), kArpPattern, patterns[int(Value(kArpPattern))]);
    Field(g, "Resolution:", R(859, 168, 108, 18), kArpResolution,
          rates[int(Value(kArpResolution))]);
    Field(g, "Gate (%):", R(625, 190, 68, 18), kArpGate, Format(Value(kArpGate)));
    Field(g, "Tempo:", R(883, 190, 84, 18), kArpTempo, Format(Value(kArpTempo), 2));
    Field(g, "Octave:", R(625, 212, 68, 18), kArpOctaves, Format(Value(kArpOctaves)));
    Field(g, "Sort:", R(949, 212, 18, 18), kArpSort, "");
    Field(g, "Key Sync:", R(675, 234, 18, 18), kArpKeySync, "");
    Field(g, "Swing (%):", R(899, 234, 68, 18), -1, "0", false);
  }
  if (mPage == 2)
    FxPage(g);
}
} // namespace krose::ui
