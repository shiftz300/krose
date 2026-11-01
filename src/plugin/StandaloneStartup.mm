// Programmatic equivalent of the stock SWELL nib startup. This keeps building
// the optional audition app possible with Command Line Tools alone (no ibtool).
#import <Cocoa/Cocoa.h>
#import "swellappmain.h"
#include "resources/resource.h"
@interface SEGrandApplication : SWELLApplication
@end
@implementation SEGrandApplication
- (void)finishLaunching {
  static SWELLAppController* controller=nil;
  controller=[[SWELLAppController alloc] init];
  NSMenu* bar=[[NSMenu alloc] initWithTitle:@""];
  NSMenuItem* root=[[NSMenuItem alloc] initWithTitle:@"Krose" action:nil keyEquivalent:@""];
  NSMenu* application=[[NSMenu alloc] initWithTitle:@"Krose"];
  NSMenuItem* settings=[[NSMenuItem alloc] initWithTitle:@"Audio and MIDI Settings…" action:@selector(onSysMenuCommand:) keyEquivalent:@","];
  [settings setTarget:controller];
  [settings setTag:ID_PREFERENCES];
  [application addItem:settings];
  [application addItem:[NSMenuItem separatorItem]];
  NSMenuItem* quit=[[NSMenuItem alloc] initWithTitle:@"Quit Krose" action:@selector(terminate:) keyEquivalent:@"q"];
  [application addItem:quit];
  [root setSubmenu:application];
  [bar addItem:root];
  [self setMainMenu:bar];
  [controller awakeFromNib];
  [super finishLaunching];
}
@end
