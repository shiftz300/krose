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
// AppKit's convenience mouse-event factory leaves other-button events with
// buttonNumber=0. Supply the real middle-button number without posting OS input.
@interface KroseMiddleMouseEvent : NSEvent
@property(nonatomic, strong) NSEvent *backing;
@end
@implementation KroseMiddleMouseEvent
- (NSInteger)buttonNumber { return 2; }
- (NSPoint)locationInWindow { return self.backing.locationInWindow; }
- (NSEventModifierFlags)modifierFlags { return self.backing.modifierFlags; }
- (NSEventSubtype)subtype { return self.backing.subtype; }
@end
namespace {
constexpr float kSettingsTabY = 125;
constexpr float kInputTabX = 684;
constexpr float kUiTabX = 810;
constexpr float kUiSizeX = 700;
constexpr float kUiSizeY = 160;

class Frame final : public Steinberg::IPlugFrame {
public:
  NSWindow *window;
  bool allow = false;
  explicit Frame(NSWindow *w) : window(w) {}
  Steinberg::tresult PLUGIN_API queryInterface(const Steinberg::TUID, void **out) override {
    *out = nullptr; return Steinberg::kNoInterface;
  }
  Steinberg::uint32 PLUGIN_API addRef() override { return 1; }
  Steinberg::uint32 PLUGIN_API release() override { return 1; }
  Steinberg::tresult PLUGIN_API resizeView(Steinberg::IPlugView *, Steinberg::ViewRect *r) override {
    if (!allow) return Steinberg::kResultFalse;
    [window setContentSize:NSMakeSize(r->getWidth(),r->getHeight())];
    return Steinberg::kResultOk;
  }
};
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
  if (type == NSEventTypeOtherMouseDown || type == NSEventTypeOtherMouseUp) {
    KroseMiddleMouseEvent *middle = [[KroseMiddleMouseEvent alloc] init];
    middle.backing = e;
    e = middle;
  }
  if (type == NSEventTypeLeftMouseDown)
    [v mouseDown:e];
  else if(type==NSEventTypeRightMouseDown)[v rightMouseDown:e];
  else if(type==NSEventTypeRightMouseUp)[v rightMouseUp:e];
  else if(type==NSEventTypeOtherMouseDown)[v otherMouseDown:e];
  else if(type==NSEventTypeOtherMouseUp)[v otherMouseUp:e];
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
    if (const char *path = std::getenv("KROSE_UI_PRESET_CHECK")) {
      setParameter("Program", 1.);
      pump();
      click(v, 700, 67);
      key(v, @"\r", 36);
      assert(program() == 1.); // PRESET opens on the last Program, even offscreen.
      click(v, 620, 331);
      key(v, @"\r", 36);
      assert(program() == 1.); // BROWSE opens with the same Program in view.
      click(v, 620, 331);
      click(v, 550, 195);
      for (char c : std::string("A000"))
        key(v, [NSString stringWithFormat:@"%c", c]);
      key(v, @"\r", 36);
      assert(std::abs(program() - 1. / 1161.) < 1e-8);
      setParameter("Program", 1.);
      pump();
      click(v, 620, 331);
      key(v, @"\r", 36);
      assert(program() == 1.); // An old search must not hide the current sound.
      setParameter("Program", 1. / 1161.);
      pump();
      setenv("KROSE_NATIVE_CAPTURE", path, 1);
      click(v, 71, 85);
      pump(.6);
      unsetenv("KROSE_NATIVE_CAPTURE");
      view->removed();
      [window orderOut:nil];
      return;
    }
    if (const char *directory = std::getenv("KROSE_UI_MIDI_TEST")) {
      setParameter("MIDI Input Channel",0);
      for(int phase=0;phase<5;++phase) {
        setParameter("__midi_test_phase",phase);pump(.4);
        const std::string path=std::string(directory)+"/host-midi-"+std::to_string(phase)+".pam";
        setenv("KROSE_NATIVE_CAPTURE",path.c_str(),1);click(v,700,125);pump(.08);unsetenv("KROSE_NATIVE_CAPTURE");
        if(phase==1){assert(parameter("Cutoff")>.7);assert(parameter("Amp Attack")>.7);}
      }
      view->removed();[window orderOut:nil];return;
    }
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
      capture("fx-dropdown", 586, 200);
      click(v, 586, 252);
      assert(std::abs(parameter("IFX 1 Type") - 5. / 10) < 1e-8);
      number(v, 887, 198, @"70");
      assert(parameter("IFX 1 Amount") == .7);
      number(v, 630, 225, @"100");
      assert(std::abs(parameter("IFX 1 Drive") - 99. / 199) < 1e-9);
      capture("fx-drive", 760, 268);
      capture("fx-drive-off", 71, 200);
      assert(parameter("IFX 1 On") == 0.);
      click(v, 71, 200);
      click(v, 640, 176); // IFX2 tab.
      click(v, 586, 200);
      click(v, 586, 192); // EQ.
      click(v, 661, 226); // Band 4.
      number(v, 897, 225, @"20000");
      assert(parameter("IFX 2 B4 Freq") == 1.);
      capture("fx-eq", 760, 268);
      click(v, 766, 176); // MFX1 tab.
      click(v, 586, 200);
      click(v, 586, 252); // Plate.
      assert(std::abs(parameter("MFX 1 Type")-5./14)<1e-8);
      capture("fx-plate", 760, 268);
      auto effectIcons = [&](const char *name, double ifx1, double ifx2, double mfx1, double mfx2) {
        setParameter("IFX 1 Type", ifx1 / 10);
        setParameter("IFX 2 Type", ifx2 / 10);
        setParameter("MFX 1 Type", mfx1 / 14);
        setParameter("MFX 2 Type", mfx2 / 14);
        capture(name, 760, 268);
      };
      effectIcons("fx-icons-a", 2, 3, 2, 3);
      effectIcons("fx-icons-b", 4, 5, 4, 5);
      setParameter("MFX 1 On", 0);
      effectIcons("fx-icons-c", 6, 1, 2, 4);
      setParameter("MFX 1 On", 1);
      capture("fx-add-menu", 175, 85);
      click(v, 586, 212); // Compressor.
      assert(parameter("IFX 2 Type") == .3);
      capture("fx-added", 760, 268);

      capture("arp", 930, 125);
      number(v, 930, 199, @"300.00");
      capture("numeric-max", 800, 270);
      number(v, 930, 199, @"120.00");
      capture("lcd-dropdown", 635, 177);
      key(v, @"\x1b", 53);
      click(v,480,125);click(v,810,125);click(v,520,234);click(v,830,249); // Standard CC template.
      capture("controller-switches", 590, 125);
      capture("controller-midi", 700, 125);
      capture("controller-map-menu", 700, 155);
      key(v, @"\x1b", 53);
      capture("controller-input", 815, 125);
      capture("controller-help", 920, 125);
      click(v,480,125);
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
      // The bank selection and the visible four faders share host parameters.
      const double savedAmp=parameter("Amp Attack"), savedFilter=parameter("Filter Attack");
      const double savedIfx=parameter("IFX 1 Type");
      click(v,1220,67);
      assert(parameter("EG Target")==1. && parameter("IFX 1 Type")==savedIfx);
      mouse(v,1057,200,NSEventTypeLeftMouseDown);
      mouse(v,1057,160,NSEventTypeLeftMouseDragged);
      mouse(v,1057,160,NSEventTypeLeftMouseUp); pump();
      assert(parameter("Filter Attack")!=savedFilter && parameter("Amp Attack")==savedAmp);
      const double filterAfter=parameter("Filter Attack");
      click(v,1147,67);
      assert(parameter("EG Target")==0.);
      mouse(v,1057,200,NSEventTypeLeftMouseDown);
      mouse(v,1057,160,NSEventTypeLeftMouseDragged);
      mouse(v,1057,160,NSEventTypeLeftMouseUp); pump();
      assert(parameter("Amp Attack")!=savedAmp && parameter("Filter Attack")==filterAfter);
      setParameter("Amp Attack",savedAmp);setParameter("Filter Attack",savedFilter);
      // Each hardware edit command opens its own slot; repeated presses
      // reopen it after leaving FX, without toggling or replacing the effect.
      const char *editTypes[]={"IFX 1 Type","IFX 2 Type","MFX 1 Type","MFX 2 Type"};
      const char *editAmounts[]={"IFX 1 Amount","IFX 2 Amount","MFX 1 Send","MFX 2 Send"};
      const char *editOn[]={"IFX 1 On","IFX 2 On","MFX 1 On","MFX 2 On"};
      for (int slot=0;slot<4;++slot) {
        const double type=parameter(editTypes[slot]), amount=parameter(editAmounts[slot]), on=parameter(editOn[slot]);
        const double active=slot<2 ? .2 : 4./14;
        setParameter(editTypes[slot],active);
        for (int press=0;press<2;++press) {
          click(v,700,125);
          const int code=int(std::lround(parameter("FX Edit")*7));
          setParameter("FX Edit",(code==slot ? slot+4 : slot)/7.);pump();
          number(v,887,198,press ? @"43" : @"42");
          assert(std::abs(parameter(editAmounts[slot])-(press ? .43 : .42))<1e-8);
          assert(parameter(editTypes[slot])==active && parameter(editOn[slot])==on);
        }
        setParameter(editTypes[slot],type);setParameter(editAmounts[slot],amount);
      }
      click(v,700,125);
      if (!std::getenv("KROSE_NATIVE_CAPTURE")) {
        // Compare actual Metal frames: the second note must light while held
        // and return to the released frame on mouse-up (capture must survive).
        const auto path = "/tmp/krose-click-note-" + std::to_string(getpid()) + ".pam";
        setenv("KROSE_NATIVE_CAPTURE", path.c_str(), 1);
        auto noteFrame = [&](NSEventType type, NSInteger count, double settle = .15) {
          mouse(v, 210, 560, type, count);
          pump(settle);
          std::ifstream stream(path, std::ios::binary);
          std::string frame((std::istreambuf_iterator<char>(stream)), {});
          assert(!frame.empty());
          return frame;
        };
        const auto pressed = noteFrame(NSEventTypeLeftMouseDown, 1);
        const auto releasing = noteFrame(NSEventTypeLeftMouseUp, 1, .025);
        const auto released = noteFrame(NSEventTypeLeftMouseUp, 1);
        assert(pressed != released && releasing != released);
        assert(noteFrame(NSEventTypeLeftMouseDown, 2) == pressed);
        assert(noteFrame(NSEventTypeLeftMouseUp, 2) == released);
        unsetenv("KROSE_NATIVE_CAPTURE");
        std::filesystem::remove(path);
      }
      // Module clicks toggle bypass without changing the LCD page or effect;
      // right-click edits it; a middle click removes it. Adding into a bypassed
      // empty slot enables it while retaining its saved amount.
      constexpr const char *fxTypes[] = {"IFX 1 Type", "IFX 2 Type", "MFX 1 Type", "MFX 2 Type"};
      constexpr const char *fxOn[] = {"IFX 1 On", "IFX 2 On", "MFX 1 On", "MFX 2 On"};
      constexpr const char *fxAmounts[] = {"IFX 1 Amount", "IFX 2 Amount", "MFX 1 Send", "MFX 2 Send"};
      constexpr float fxPositions[][2] = {{71, 200}, {175, 85}, {253, 85}, {331, 85}};
      double savedType[4], savedOn[4], savedAmount[4];
      for (int slot = 0; slot < 4; ++slot) {
        savedType[slot] = parameter(fxTypes[slot]);
        savedOn[slot] = parameter(fxOn[slot]);
        savedAmount[slot] = parameter(fxAmounts[slot]);
        const double type = 2. / (slot < 2 ? 10 : 14);
        setParameter(fxTypes[slot], type);
        setParameter(fxOn[slot], 1);
        setParameter(fxAmounts[slot], .37);
        pump();
        const auto &p = fxPositions[slot];
        click(v, p[0], p[1]);
        assert(parameter(fxOn[slot]) == 0. && parameter(fxTypes[slot]) == type);
        click(v, p[0], p[1]);
        assert(parameter(fxOn[slot]) == 1. && parameter(fxAmounts[slot]) == .37);
        // The removed LCD switch leaves no invisible clickable target.
        click(v, 850, 125); click(v, 437 + 133 * slot + 50, 176);
        click(v, 702, 199);
        assert(parameter(fxOn[slot]) == 1.);
        click(v, p[0], p[1]);
        mouse(v, p[0], p[1], NSEventTypeRightMouseDown);
        mouse(v, p[0], p[1], NSEventTypeRightMouseUp); pump();
        assert(parameter(fxTypes[slot]) == type && parameter(fxOn[slot]) == 0.);
        // Right-click selected this slot: editing Send/Wet-Dry must affect it.
        number(v,887,198,@"0");
        assert(parameter(fxAmounts[slot]) == 0.);
        click(v,p[0],p[1]);
        assert(parameter(fxOn[slot]) == 1. && parameter(fxAmounts[slot]) == 0.);
        click(v,p[0],p[1]);
        assert(parameter(fxOn[slot]) == 0.);
        setParameter(fxAmounts[slot], .37);
        mouse(v, p[0], p[1], NSEventTypeOtherMouseDown);
        mouse(v, p[0], p[1], NSEventTypeOtherMouseUp); pump();
        assert(parameter(fxTypes[slot]) == 1. / (slot < 2 ? 10 : 14));
        assert(parameter(fxOn[slot]) == 0. && parameter(fxAmounts[slot]) == .37);
        click(v, p[0], p[1]);
        key(v, @"\uf729", 115);
        key(v, @"\uf701", 125); key(v, @"\uf701", 125); key(v, @"\r", 36);
        assert(parameter(fxTypes[slot]) == type && parameter(fxOn[slot]) == 1.);
      }
      // Appended MFX algorithms remain editable inside the same pixel LCD.
      setParameter("MFX 1 Type",11./14);
      setParameter("MFX 1 Layout",0.);
      click(v,850,125);click(v,766,176);click(v,669,226);
      number(v,915,225,@"6");
      assert(std::abs(parameter("MFX 1 Band 7")-2./3)<1e-8);
      click(v,586,200);click(v,586,272); // Last visible row: Auto Pan.
      assert(parameter("MFX 1 Type")==1.);
      for (int slot = 0; slot < 4; ++slot) {
        setParameter(fxTypes[slot], savedType[slot]);
        setParameter(fxOn[slot], savedOn[slot]);
        setParameter(fxAmounts[slot], savedAmount[slot]);
      }
      click(v, 700, 125);
      // SWs are real controls. Momentary release must also work on editor close.
      click(v,70,410);assert(parameter("SW1")==1.);
      click(v,70,410);assert(parameter("SW1")==0.);
      setParameter("SW1 Mode",1.);
      mouse(v,70,410,NSEventTypeLeftMouseDown);assert(parameter("SW1")==1.);
      mouse(v,70,410,NSEventTypeLeftMouseUp);assert(parameter("SW1")==0.);
      setParameter("SW1 Mode",0.);
      click(v,480,125); // PROG > controls
      click(v,600,160);key(v,@"\uf72b",119);key(v,@"\r",36);
      assert(parameter("SW1 Assign")==1.); // Last entry is FX Bypass.
      key(v,@"\x1b",53);
      setParameter("SW1 Assign",.1);
      const double beforeLearn=glide();
      mouse(v,175,200,NSEventTypeRightMouseDown);mouse(v,175,200,NSEventTypeRightMouseUp);pump();
      assert(glide()==beforeLearn);
      key(v,@"\x1b",53);key(v,@"\x1b",53); // Cancel learn, then leave LCD settings.
      // User profiles load settings and mappings without unbalanced host edits.
      setParameter("SW1 Assign",.5);
      click(v, 480, 125);
      click(v, kInputTabX, kSettingsTabY);
      click(v, 670, 158); // STORE
      assert(std::filesystem::exists(std::getenv("KROSE_MIDI_MAP_FILE")));
      click(v,520,158);key(v,@"\uf701",125);key(v,@"\r",36);
      assert(parameter("SW1 Assign")==.1);
      click(v,520,158);key(v,@"\uf729",115);key(v,@"\r",36);
      assert(parameter("SW1 Assign")==.5);
      click(v,480,125);setParameter("SW1 Assign",.1);
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
      // Two-level pattern picker: Built-in category, then individual entries.
      click(v, 635, 177);
      key(v, @"\uf729", 115); key(v, @"\r", 36);
      key(v, @"\uf72b", 119); key(v, @"\r", 36);
      assert(std::abs(parameter("Arp Pattern") - 4. / 1284) < 1e-9);
      click(v, 635, 177);
      key(v, @"\uf729", 115); key(v, @"\r", 36);
      key(v, @"\uf729", 115); key(v, @"\uf701", 125); key(v, @"\uf701", 125); key(v, @"\r", 36);
      assert(std::abs(parameter("Arp Pattern") - 1. / 1284) < 1e-9);
      // Drag a numeric value vertically without entering a text editor.
      const double beforeDrag = parameter("Arp Tempo");
      mouse(v, 920, 199, NSEventTypeLeftMouseDown);
      mouse(v, 920, 179, NSEventTypeLeftMouseDragged);
      mouse(v, 920, 179, NSEventTypeLeftMouseUp); pump();
      assert(parameter("Arp Tempo") > beforeDrag);
      number(v, 930, 199, @"143.25");
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
      const auto beforeStep = program();
      click(v, 523, 331);
      const auto firstStep = program();
      assert(firstStep != beforeStep);
      click(v, 523, 331, 2);
      assert(program() != firstStep);
      number(v, 330, 343, @"2");
      assert(std::abs(velocity() - .6) < 1e-6);
      click(v, 700, 67);
      key(v, @"\uf702", 123);
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
      // Factory program changes restore their own ARP. Establish the explicit
      // edited state whose persistence across editor destruction is tested.
      setParameter("Arp", 1.);
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
      click(v,700,67);key(v,@"\uf702",123);key(v,@"\uf729",115);key(v,@"\r",36);
      key(v,@"\r",36);
      assert(std::abs(program()-1./1161.)<1e-8); // Favorite survived editor destruction.
      click(v,700,67);key(v,@"\uf702",123);key(v,@"\uf729",115);key(v,@"\r",36);click(v,1070,97);
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
      // Program selection establishes the Compare baseline; edits toggle A/B.
      click(v,505,331);
      const double baseline=glide();
      mouse(v,175,200,NSEventTypeLeftMouseDown);
      mouse(v,175,185,NSEventTypeLeftMouseDragged);
      mouse(v,175,185,NSEventTypeLeftMouseUp);
      const double edited=glide(); assert(edited!=baseline);
      const double inputChannel=parameter("MIDI Input Channel");
      click(v,925,331);assert(glide()==baseline);
      click(v,925,331);assert(glide()==edited);
      assert(parameter("MIDI Input Channel")==inputChannel);
      // Missing or rejecting host frames retain the existing dimensions.
      mouse(v,71,85,NSEventTypeRightMouseDown);mouse(v,71,85,NSEventTypeRightMouseUp);
      pump();key(v,@"\uf72b",119);key(v,@"\r",36);
      Steinberg::ViewRect unchanged{};view->getSize(&unchanged);assert(unchanged.getWidth()==1472);
      Frame frame(window);view->setFrame(&frame);
      mouse(v,71,85,NSEventTypeRightMouseDown);mouse(v,71,85,NSEventTypeRightMouseUp);
      pump();key(v,@"\uf72b",119);key(v,@"\r",36);
      view->getSize(&unchanged);assert(unchanged.getWidth()==1472);
      frame.allow=true;
      // Scaling changes only the window transform; control coordinates still work.
      mouse(v,71,85,NSEventTypeRightMouseDown);mouse(v,71,85,NSEventTypeRightMouseUp);
      pump();key(v,@"\uf72b",119);key(v,@"\r",36);
      Steinberg::ViewRect scaled{};assert(view->getSize(&scaled)==Steinberg::kResultOk);
      assert(scaled.getWidth()==2208 && scaled.getHeight()==972);
      mouse(v,71*1.5,85*1.5,NSEventTypeRightMouseDown);mouse(v,71*1.5,85*1.5,NSEventTypeRightMouseUp);
      pump();key(v,@"\uf729",115);for(int i=0;i<4;++i)key(v,@"\uf701",125);key(v,@"\r",36);
      assert(view->getSize(&scaled)==Steinberg::kResultOk && scaled.getWidth()==1472);
      // The same control is visible on the UI tab, with an LCD-pixel menu.
      click(v, 480, 125);
      click(v, kUiTabX, kSettingsTabY);
      click(v, kUiSizeX, kUiSizeY);
      key(v,@"\uf729",115);key(v,@"\uf701",125);key(v,@"\uf701",125);key(v,@"\r",36);
      assert(view->getSize(&scaled)==Steinberg::kResultOk && scaled.getWidth()==1104 && scaled.getHeight()==486);
      click(v, kUiSizeX * .75, kUiSizeY * .75);
      key(v,@"\uf729",115);for(int i=0;i<4;++i)key(v,@"\uf701",125);key(v,@"\r",36);
      assert(view->getSize(&scaled)==Steinberg::kResultOk && scaled.getWidth()==1472);
      click(v,480,125);
      view->setFrame(nullptr);
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
