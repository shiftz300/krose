// Exercise the compiled native editor through Cocoa events. No browser runtime.
#include "pluginterfaces/gui/iplugview.h"
#import <Cocoa/Cocoa.h>
#include <mach/mach.h>
#include <cassert>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <filesystem>
#include <fstream>
#include <unistd.h>
namespace {
void pump(double seconds = .15) {
  NSDate *end = [NSDate dateWithTimeIntervalSinceNow:seconds];
  while (end.timeIntervalSinceNow > 0) {
    // A real Cocoa event loop drains transient objects each iteration. Keeping
    // them until process exit inflated the old UI-memory measurements.
    @autoreleasepool {
      [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
    }
  }
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
void mouse(NSView *v, float x, float y, NSEventType type, NSInteger count = 1) {
  NSPoint p = [v convertPoint:NSMakePoint(x, v.isFlipped ? y : v.bounds.size.height - y)
                       toView:nil];
  NSEvent *e = [NSEvent mouseEventWithType:type
                                  location:p
                             modifierFlags:0
                                 timestamp:0
                              windowNumber:v.window.windowNumber
                                   context:nil
                               eventNumber:0
                                clickCount:count
                                  pressure:1];
  if (type == NSEventTypeLeftMouseDown)
    [v mouseDown:e];
  else if (type == NSEventTypeLeftMouseDragged)
    [v mouseDragged:e];
  else
    [v mouseUp:e];
}
void click(NSView *v, float x, float y, NSInteger count = 1) {
  mouse(v, x, y, NSEventTypeLeftMouseDown, count);
  mouse(v, x, y, NSEventTypeLeftMouseUp, count);
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
                  const std::function<double(const char *)> &parameter,
                  const std::function<void(const char *, double)> &setParameter) {
  [NSApplication sharedApplication];
  const std::string favoritesFile="/tmp/krose-favorites-test-"+std::to_string(getpid())+".json";
  const bool ownFavorites=!std::getenv("KROSE_FAVORITES_FILE");
  if(ownFavorites)setenv("KROSE_FAVORITES_FILE",favoritesFile.c_str(),1);
  Steinberg::ViewRect rect{};
  assert(view->getSize(&rect) == Steinberg::kResultOk && rect.getWidth() == 1472 &&
         rect.getHeight() == 648);
  NSWindow *window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1472, 648)
                                                 styleMask:NSWindowStyleMaskBorderless
                                                   backing:NSBackingStoreBuffered
                                                     defer:NO];
  [window orderFront:nil];
  auto memory = [](const char *stage) {
    task_vm_info_data_t info{}; mach_msg_type_number_t count=TASK_VM_INFO_COUNT;
    if(task_info(mach_task_self(), TASK_VM_INFO, reinterpret_cast<task_info_t>(&info), &count)==KERN_SUCCESS)
      std::cout << "MEMORY " << stage << " footprint=" << info.phys_footprint << " resident=" << info.resident_size << std::endl;
  };
  if(std::getenv("KROSE_UI_BENCH")) memory("engine");
  for (int pass = 0; pass < 2; ++pass) {
    @autoreleasepool {
      assert(view->attached((__bridge void *)window.contentView, Steinberg::kPlatformTypeNSView) ==
             Steinberg::kResultOk);
      pump(1);
    }
    NSView *v = findNative(window.contentView);
    assert(v);
    [window makeFirstResponder:v];
    std::cout << "Native editor ready pass " << pass << std::endl;
    if (std::getenv("KROSE_UI_BENCH")) {
      memory("editor");
      for(int n=0;n<12;++n){click(v,71,85);pump(.45);}
      memory("animated");
      view->removed();pump(.3);memory("closed");
      [window orderOut:nil];return;
    }
    if (const char *directory = std::getenv("KROSE_UI_REFERENCE")) {
      auto capture = [&](const char *name, float x, float y) {
        std::string path = std::string(directory) + "/native-" + name + ".pam";
        setenv("KROSE_NATIVE_CAPTURE", path.c_str(), 1);
        click(v, x, y);
        pump(.6); // Include the final settled frame of a reversed FX transition.
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
      capture("preset-secondary", 550, 123);
      const double current=program();
      click(v,1070,97);assert(program()==current);
      capture("favorites",550,97);
      key(v, @"\x1b", 53);
      capture("browser", 620, 331);
      capture("filter-dropdown", 950, 198);
      key(v, @"\x1b", 53);
      view->removed();
      [window orderOut:nil];
      return;
    }
    if (pass == 0) {
      if (!std::getenv("KROSE_NATIVE_CAPTURE")) {
        // Compare actual Metal frames: the second note must light while held
        // and return to the released frame on mouse-up (capture must survive).
        const auto path = "/tmp/krose-click-note-" + std::to_string(getpid()) + ".pam";
        setenv("KROSE_NATIVE_CAPTURE", path.c_str(), 1);
        auto noteFrame = [&](NSEventType type, NSInteger count) {
          mouse(v, 210, 560, type, count);
          pump(.08);
          std::ifstream stream(path, std::ios::binary);
          std::string frame((std::istreambuf_iterator<char>(stream)), {});
          assert(!frame.empty());
          return frame;
        };
        const auto pressed = noteFrame(NSEventTypeLeftMouseDown, 1);
        const auto released = noteFrame(NSEventTypeLeftMouseUp, 1);
        assert(pressed != released);
        assert(noteFrame(NSEventTypeLeftMouseDown, 2) == pressed);
        assert(noteFrame(NSEventTypeLeftMouseUp, 2) == released);
        unsetenv("KROSE_NATIVE_CAPTURE");
        std::filesystem::remove(path);
      }
      click(v, 70, 285);
      assert(parameter("Arp") == 1.);
      click(v, 70, 285, 2);
      assert(parameter("Arp") == 0.); // The OS double-click is still a second button press.
      for (int count = 1; count <= 6; ++count) {
        mouse(v, 70, 285, NSEventTypeLeftMouseDown, count);
        assert(parameter("Arp") == double(count % 2)); // Applied before the next redraw.
        mouse(v, 70, 285, NSEventTypeLeftMouseUp, count);
      }
      click(v, 70, 285);
      assert(parameter("Arp") == 1.);
      click(v, 70, 331);
      assert(parameter("Arp Latch") == 1.);
      click(v, 930, 125);
      click(v, 910, 150);
      assert(parameter("Arp Host Sync") == 0.);
      number(v, 930, 199, @"143.25");
      assert(std::abs(parameter("Arp Tempo") - 123.25 / 280.) < 1e-8);
      click(v, 956, 194);
      click(v, 956, 194, 2);
      assert(std::abs(parameter("Arp Tempo") - 123.27 / 280.) < 1e-8);
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
      click(v, 175, 200);
      click(v, 175, 200, 2);
      assert(glide() == 0.); // Knob double-click still resets the parameter.
      mouse(v, 146, 200, NSEventTypeLeftMouseDown);
      mouse(v, 146, 180, NSEventTypeLeftMouseDragged);
      mouse(v, 146, 180, NSEventTypeLeftMouseUp);
      assert(glide() > 0.); // The visible outer edge of the knob accepts dragging.
      number(v, 175, 241, @"80");
      click(v, 1057, 150);
      assert(parameter("Amp Attack") > .5);
      click(v, 1057, 150, 2);
      assert(parameter("Amp Attack") == .5);
      click(v, 253, 200);
      const auto firstStep = program();
      click(v, 253, 200, 2);
      assert(program() != firstStep);
      number(v, 330, 343, @"2");
      assert(std::abs(velocity() - .6) < 1e-6);
      click(v, 700, 67);
      key(v, @"\uf729", 115);
      key(v, @"\uf701", 125);
      key(v, @"\r", 36);
      const double beforeFavorite=program();
      click(v,1070,97);
      assert(program()==beforeFavorite);
      assert(std::filesystem::exists(std::getenv("KROSE_FAVORITES_FILE")));
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
      click(v, 71, 85, 2);
      pump(.6); // The second click reverses the transition before it settles.
      click(v, 215, 460);
      click(v, 1305, 331);
      click(v, 1380, 331);
    } else {
      assert(std::abs(velocity() - .6) < 1e-6);
      assert(std::abs(glide() - 80. / 127.) < 1e-8);
      assert(parameter("Arp") == 1.);
      assert(program() == 1.);
      click(v,700,67);key(v,@"\r",36);
      key(v,@"\r",36);
      assert(std::abs(program()-1./1161.)<1e-8); // Favorite survived editor destruction.
      click(v,700,67);key(v,@"\r",36);click(v,1070,97);
      key(v,@"\r",36); // Empty favorites must not select another program.
      assert(std::abs(program()-1./1161.)<1e-8);
      key(v,@"\x1b",53);
      // A host update while the native editor is open must become the starting
      // value for the next drag, rather than an old cached UI value.
      setParameter("Glide",40./127.);
      pump();
      mouse(v,146,200,NSEventTypeLeftMouseDown);
      mouse(v,146,180,NSEventTypeLeftMouseDragged);
      mouse(v,146,180,NSEventTypeLeftMouseUp);
      assert(std::abs(glide()-56./127.)<1e-8);
      setParameter("Glide",80./127.);
    }
    if (const char *path = std::getenv("KROSE_NATIVE_CAPTURE")) {
      pump();
      std::cout << "Native framebuffer: " << path << std::endl;
    }
    assert(view->removed() == Steinberg::kResultOk);
    pump();
  }
  [window orderOut:nil];
  if(ownFavorites){std::filesystem::remove(favoritesFile);unsetenv("KROSE_FAVORITES_FILE");}
  std::cout << "PASS native UI: Cocoa clicks, numeric editing, arp, voice, catalog search, FX "
               "folding, keyboard, panic, double-click routing, knob edge dragging and reopen\n";
}
