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
  const double down = Visual("key:" + std::to_string(note), mLit[note] ? 1 : 0, .09, mLit[note]);
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
  if (open && !mRevealOpen[slot]) {
    motion.Snap(.35);
    motion.Target(1, mFrameTime, .10);
  }
  mRevealOpen[slot] = open;
  if (!open) return; // Dismiss immediately; no invisible overlay consumes input.
  const double alpha = motion.At(mFrameTime);
  mVisualAnimating |= motion.Active(mFrameTime);
  if (alpha == 1) { (this->*draw)(g); return; }
  // Only transient layers, never a permanent full-window animation cache.
  g.StartLayer(this, bounds);
  (this->*draw)(g);
  auto layer = g.EndLayer();
  IBlend blend(EBlend::Default, float(alpha));
  g.DrawLayer(layer, &blend);
}
} // namespace krose::ui
