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
void NativePanel::KeyImage(IGraphics &g, int note, bool black, float x) {
  const std::string prefix = black ? "black-" : "white-";
  const bool lit = mLit[note] || mHostLit[note];
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
