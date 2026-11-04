// Optional integration check for a machine with a macOS WindowServer session.
#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>
#include "pluginterfaces/gui/iplugview.h"
#include <cassert>
#include <functional>

namespace {
WKWebView* findWebView(NSView* parent) {
  if([parent isKindOfClass:WKWebView.class]) return (WKWebView*)parent;
  for(NSView* child in parent.subviews) if(auto* view=findWebView(child)) return view;
  return nil;
}
void waitFor(const std::function<bool()>& predicate) {
  NSDate* deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while(!predicate()) {
    assert(deadline.timeIntervalSinceNow>0);
    [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
  }
}
id eval(WKWebView* web, NSString* script) {
  bool done=false; bool* completed=&done;
  __block id result=nil;
  [web evaluateJavaScript:script completionHandler:^(id value,NSError* error){
    if(error) NSLog(@"Editor script: %@",error);
    assert(!error);result=value;*completed=true;
  }];
  waitFor([&] {return done;});
  return result;
}
}
void verifyEditor(Steinberg::IPlugView* view,const std::function<double()>& velocity,const std::function<double()>& program) {
  [NSApplication sharedApplication];
  Steinberg::ViewRect rect{};
  assert(view->getSize(&rect)==Steinberg::kResultOk && rect.getWidth()==1472 && rect.getHeight()==648);
  NSWindow* window=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,1472,648)
    styleMask:NSWindowStyleMaskBorderless backing:NSBackingStoreBuffered defer:NO];
  [window orderFront:nil];
  for(int pass=0;pass<2;++pass){
    assert(view->attached((__bridge void*)window.contentView,Steinberg::kPlatformTypeNSView)==Steinberg::kResultOk);
    WKWebView* web=findWebView(window.contentView);assert(web);
    waitFor([&]{return !web.loading;});
    waitFor([&]{return [eval(web,@"!!document.querySelector('#krose-fixed-ui[data-ready]')") boolValue];});
    assert(![eval(web,@"!!document.documentElement.dataset.scriptError") boolValue]);
    assert([eval(web,@"document.querySelector('#kf-program').options.length") intValue]==1162);
    if(pass==0){
      eval(web,@"(()=>{const e=document.querySelector('#kf-value-velocity');e.value='2';e.dispatchEvent(new Event('change'));})()");
      waitFor([&]{return std::abs(velocity()-.6)<1e-6;});
      eval(web,@"document.querySelector('#kf-browse').click()");
      assert([eval(web,@"document.querySelector('#krose-browser').open") boolValue]);
      eval(web,@"(()=>{const e=document.querySelector('#krose-browser input');e.value='EXPCM004:063';e.dispatchEvent(new Event('input'));})()");
      assert([eval(web,@"document.querySelectorAll('#krose-browser [data-program]').length") intValue]==1);
      eval(web,@"document.querySelector('#krose-browser [data-program]').click()");
      waitFor([&]{return std::abs(program()-1.)<1e-6;});
      assert(![eval(web,@"!!document.documentElement.dataset.scriptError") boolValue]);
    }else{
      waitFor([&]{return [eval(web,@"document.querySelector('#kf-value-velocity').value") doubleValue]==2.;});
      waitFor([&]{return [eval(web,@"document.querySelector('#kf-program').value") intValue]==1161;});
    }
    view->removed();
  }
}
