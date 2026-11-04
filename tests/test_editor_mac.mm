// Exercise the compiled native editor through Cocoa events. No browser runtime.
#include "pluginterfaces/gui/iplugview.h"
#import <Cocoa/Cocoa.h>
#include <cassert>
#include <cstdlib>
#include <functional>
#include <iostream>
namespace {
void pump(double seconds = .15) {
  NSDate *end = [NSDate dateWithTimeIntervalSinceNow:seconds];
  while (end.timeIntervalSinceNow > 0)
    [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
}
NSView *findNative(NSView *parent) {
  NSLog(@"Native view: %@", NSStringFromClass(parent.class));
  assert(![NSStringFromClass(parent.class) containsString:@"WKWebView"]);
  if ([NSStringFromClass(parent.class) containsString:@"IGraphics"])
    return parent;
  for (NSView *child in parent.subviews)
    if (auto *v = findNative(child))
      return v;
  return nil;
}
void click(NSView *v, float x, float y) {
  NSPoint p = [v convertPoint:NSMakePoint(x, v.isFlipped ? y : v.bounds.size.height - y)
                       toView:nil];
  for (NSEventType type : {NSEventTypeLeftMouseDown, NSEventTypeLeftMouseUp}) {
    NSEvent *e = [NSEvent mouseEventWithType:type
                                    location:p
                               modifierFlags:0
                                   timestamp:0
                                windowNumber:v.window.windowNumber
                                     context:nil
                                 eventNumber:0
                                  clickCount:1
                                    pressure:1];
    if (type == NSEventTypeLeftMouseDown)
      [v mouseDown:e];
    else
      [v mouseUp:e];
  }
  pump();
}
void key(NSView *v, NSString *s, unsigned short code = 0) {
  NSEvent *e = [NSEvent keyEventWithType:NSEventTypeKeyDown
                                location:NSZeroPoint
                           modifierFlags:0
                               timestamp:0
                            windowNumber:v.window.windowNumber
                                 context:nil
                              characters:s
             charactersIgnoringModifiers:s
                               isARepeat:NO
                                 keyCode:code];
  [v keyDown:e];
  pump();
}
void number(NSView *v, float x, float y, NSString *s) {
  click(v, x, y);
  for (NSUInteger i = 0; i < s.length; ++i)
    key(v, [s substringWithRange:NSMakeRange(i, 1)]);
  key(v, @"\r", 36);
}
} // namespace
void verifyEditor(Steinberg::IPlugView *view, const std::function<double()> &velocity,
                  const std::function<double()> &program, const std::function<double()> &mode,
                  const std::function<double()> &glide,
                  const std::function<double(const char *)> &parameter) {
  [NSApplication sharedApplication];
  Steinberg::ViewRect rect{};
  assert(view->getSize(&rect) == Steinberg::kResultOk && rect.getWidth() == 1472 &&
         rect.getHeight() == 648);
  NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1472, 648)
                                                 styleMask:NSWindowStyleMaskBorderless
                                                   backing:NSBackingStoreBuffered
                                                     defer:NO];
  [window orderFront:nil];
  for (int pass = 0; pass < 2; ++pass) {
    assert(view->attached((__bridge void *)window.contentView, Steinberg::kPlatformTypeNSView) ==
           Steinberg::kResultOk);
    pump(1);
    NSView *v = findNative(window.contentView);
    assert(v);
    [window makeFirstResponder:v];
    std::cout << "Native editor ready pass " << pass << std::endl;
    if (const char *directory = std::getenv("KROSE_UI_REFERENCE")) {
      auto capture = [&](const char *name, float x, float y) {
        std::string path = std::string(directory) + "/native-" + name + ".pam";
        setenv("KROSE_NATIVE_CAPTURE", path.c_str(), 1);
        click(v, x, y);
        pump(.2);
        unsetenv("KROSE_NATIVE_CAPTURE");
      };
      capture("main", 700, 125);
      capture("tone", 780, 125);
      capture("fx", 850, 125);
      capture("arp", 930, 125);
      number(v, 930, 199, @"300.00");
      capture("numeric-max", 800, 270);
      number(v, 930, 199, @"120.00");
      capture("lcd-dropdown", 635, 177);
      key(v, @"\x1b", 53);
      capture("folded", 71, 85);
      capture("preset-dropdown", 700, 67);
      key(v, @"\x1b", 53);
      capture("browser", 620, 331);
      capture("filter-dropdown", 950, 198);
      key(v, @"\x1b", 53);
      view->removed();
      [window orderOut:nil];
      return;
    }
    if (pass == 0) {
      click(v, 70, 285);
      assert(parameter("Arp") == 1.);
      click(v, 70, 331);
      assert(parameter("Arp Latch") == 1.);
      click(v, 930, 125);
      click(v, 910, 150);
      assert(parameter("Arp Host Sync") == 0.);
      number(v, 930, 199, @"143.25");
      assert(std::abs(parameter("Arp Tempo") - 123.25 / 280.) < 1e-8);
      number(v, 930, 199, @"300.00");
      click(v, 956, 194);
      assert(parameter("Arp Tempo") == 1.);
      click(v, 956, 203);
      assert(std::abs(parameter("Arp Tempo") - 279.99 / 280.) < 1e-8);
      number(v, 930, 199, @"20.00");
      assert(parameter("Arp Tempo") == 0.);
      number(v, 930, 199, @"143.25");
      click(v, 635, 177);
      key(v, @"\uf701", 125);
      key(v, @"\r", 36);
      assert(parameter("Arp Pattern") == 1.);
      click(v, 635, 177);
      key(v, @"\uf72b", 119);
      key(v, @"\r", 36);
      assert(parameter("Arp Pattern") == 1.); // End reaches the final enum value.
      click(v, 635, 177);
      key(v, @"\uf729", 115);
      key(v, @"\uf701", 125);
      key(v, @"\r", 36);
      assert(parameter("Arp Pattern") == .25);
      click(v, 700, 125);
      click(v, 1145, 331);
      assert(std::abs(mode() - .5) < 1e-8);
      number(v, 175, 241, @"80");
      assert(std::abs(glide() - 80. / 127.) < 1e-8);
      number(v, 330, 343, @"2");
      assert(std::abs(velocity() - .6) < 1e-6);
      click(v, 700, 67);
      key(v, @"\uf729", 115);
      key(v, @"\r", 36);
      assert(std::abs(program() - 1. / 1161.) < 1e-8);
      click(v, 620, 331);
      click(v, 950, 198);
      key(v, @"\uf701", 125);
      key(v, @"\r", 36);
      click(v, 950, 198);
      key(v, @"\uf700", 126);
      key(v, @"\r", 36);
      click(v, 550, 195);
      for (char c : std::string("EXPCM004:063"))
        key(v, [NSString stringWithFormat:@"%c", c]);
      key(v, @"\r", 36);
      assert(std::abs(program() - 1.) < 1e-8);
      click(v, 71, 85);
      click(v, 71, 85);
      click(v, 215, 460);
      click(v, 1305, 331);
      click(v, 1380, 331);
    } else {
      assert(std::abs(velocity() - .6) < 1e-6);
      assert(std::abs(glide() - 80. / 127.) < 1e-8);
      assert(parameter("Arp") == 1.);
      assert(program() == 1.);
    }
    if (const char *path = std::getenv("KROSE_NATIVE_CAPTURE")) {
      pump();
      std::cout << "Native framebuffer: " << path << std::endl;
    }
    assert(view->removed() == Steinberg::kResultOk);
    pump();
  }
  [window orderOut:nil];
  std::cout << "PASS native UI: Cocoa clicks, numeric editing, arp, voice, catalog search, FX "
               "folding, keyboard, panic and reopen\n";
}
