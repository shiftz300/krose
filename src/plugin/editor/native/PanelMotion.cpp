#include "NativePanel.h"
#include "PanelDrawing.h"
namespace krose::ui {
using namespace detail;
double NativePanel::Visual(const std::string &key, double target, double seconds, bool immediate) {
  auto &motion = mVisuals[key];
  if (immediate) motion.Snap(target);
  else motion.Target(target, mFrameTime, seconds);
  mVisualAnimating |= motion.Active(mFrameTime);
  return motion.At(mFrameTime);
}
void NativePanel::LCDTabs(IGraphics &g) {
  mControllerWipe.Target(mControllers ? 1 : 0, mFrameTime, .20, UIMotion::Curve::Linear);
  const double position = mControllerWipe.At(mFrameTime);
  mVisualAnimating |= mControllerWipe.Active(mFrameTime);
  if (position == 1) {
    DrawControllerTabs(g);
    return;
  }
  Bitmap(g, std::string("tabs-") + Pages[mPage], 432, 115);
  Text(g, "light14", ">CTRL", R(557, 118, 93, 19), 2);
  if (position == 0) return;

  const auto strip = R(431, 115, 542, 24);
  if (mPaintedControllerTab != mControllerPage || !g.CheckLayer(mControllerTabLayer)) {
    g.StartLayer(this, strip);
    DrawControllerTabs(g);
    mControllerTabLayer = g.EndLayer();
    mPaintedControllerTab = mControllerPage;
  }
  // Reveal complete LCD columns in alternating stepped rows, only inside the tab strip.
  // Reversing the toggle reverses the same edge from its current position.
  constexpr int columns = 240, rows = 11, edge = 7;
  constexpr float dx = 542.f / columns, dy = 27.09375f / 12;
  for (int row = 0; row < rows; ++row) {
    const float right = LCDX(strip.L + dx * std::clamp(
        int(std::lround(position * (columns + edge))) - row * edge / (rows - 1), 0, columns));
    const float top = LCDY(strip.T + row * dy);
    const float bottom = row == rows - 1 ? strip.B : LCDY(strip.T + (row + 1) * dy);
    if (right <= strip.L || bottom <= top) continue;
    g.PathClipRegion({strip.L, top, right, bottom});
    g.DrawLayer(mControllerTabLayer);
  }
  g.PathClipRegion(R(424, 108, 556, 176));
}
void NativePanel::KeyImage(IGraphics &g, int note, bool black, float x) {
  const std::string prefix = black ? "black-" : "white-";
  const bool lit = mHeld[note] || mHostLit[note];
  const double down = Visual("key:" + std::to_string(note), lit ? 1 : 0, .09, lit);
  if (down < 1) Bitmap(g, prefix + "up", x, 393);
  if (down > 0) {
    auto &image = Image(prefix + "down");
    IBlend blend(EBlend::Default, float(down));
    g.DrawBitmap(image, R(x, 393, image.W(), image.H()), 1, &blend);
  }
}
void NativePanel::Reveal(IGraphics &g, bool open, int slot, const IRECT &bounds,
                         void (NativePanel::*draw)(IGraphics &)) {
  auto &motion = mReveal[slot];
  motion.Target(open ? 1 : 0, mFrameTime, open ? .18 : .22);
  const double alpha = motion.At(mFrameTime);
  mVisualAnimating |= motion.Active(mFrameTime);
  if (open) {
    // Redraw only open menus, so closed cached layers never recreate hitboxes.
    // At the first press render a zero-alpha frame to establish input immediately.
    if (g.CheckLayer(mRevealLayers[slot])) g.ResumeLayer(mRevealLayers[slot]);
    else g.StartLayer(this, bounds);
    IBlend erase(EBlend::DstOut);
    g.FillRect(COLOR_WHITE, bounds, &erase);
    (this->*draw)(g);
    mRevealLayers[slot] = g.EndLayer();
  }
  if (alpha > 0 && mRevealLayers[slot]) {
    IBlend blend(EBlend::Default, float(alpha));
    g.DrawLayer(mRevealLayers[slot], &blend);
  }
  if (!open && alpha == 0) mRevealLayers[slot].reset();
}
} // namespace krose::ui
