// Optional integration check for a machine with a macOS WindowServer session.
#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>
#include "pluginterfaces/gui/iplugview.h"
#include <cassert>
#include <functional>
#include <iostream>
#include <cstdlib>

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
void snapshotEditor(WKWebView* web) {
  const char* destination=std::getenv("KROSE_UI_SNAPSHOT_PATH");
  if(!destination)return;
  NSString* path=[NSString stringWithUTF8String:destination];
  bool done=false;bool* completed=&done;
  [web takeSnapshotWithConfiguration:nil completionHandler:^(NSImage* image,NSError* error){
    assert(image&&!error);
    NSBitmapImageRep* rep=[NSBitmapImageRep imageRepWithData:image.TIFFRepresentation];
    NSData* png=[rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
    assert([png writeToFile:path atomically:YES]);*completed=true;
  }];
  waitFor([&]{return done;});
}
void verifyEditor(Steinberg::IPlugView* view,const std::function<double()>& velocity,const std::function<double()>& program,const std::function<double()>& mode,const std::function<double()>& glide,const std::function<double(const char*)>& parameter) {
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
    std::cout<<"Editor ready pass "<<pass<<std::endl;
    if(pass==0){
      eval(web,@"document.querySelector('[data-page=arp]').click()");
      assert(![eval(web,@"document.querySelector('[data-toggle=arp]').disabled") boolValue]);
      assert([eval(web,@"document.querySelector('#kf-rate').options.length") intValue]==8);
      eval(web,@"document.querySelector('[data-toggle=arp]').click()");
      waitFor([&]{return parameter("Arp")==1.;});
      eval(web,@"document.querySelector('[data-toggle=latch]').click()");
      waitFor([&]{return parameter("Arp Latch")==1.;});
      eval(web,@"document.querySelector('[data-toggle=host]').click()");
      waitFor([&]{return parameter("Arp Host Sync")==0.;});
      eval(web,@"(()=>{const e=document.querySelector('#kf-arp [data-bind=tempo]');e.value='143.25';e.dispatchEvent(new Event('change'));})()");
      waitFor([&]{return std::abs(parameter("Arp Tempo")-123.25/280.)<1e-8;});
      eval(web,@"(()=>{const e=document.querySelector('#kf-pattern');e.value='RANDOM';e.dispatchEvent(new Event('change'));})()");
      waitFor([&]{return parameter("Arp Pattern")==1.;});
      std::cout<<"ARP values written; tempo "<<[[eval(web,@"document.querySelector('#kf-tempo').textContent") description] UTF8String]<<std::endl;
      assert([eval(web,@"document.querySelector('#kf-tempo').textContent") isEqualToString:@"INT 143.25"]);
      assert([eval(web,@"(()=>{const screen=document.querySelector('.lcd').getBoundingClientRect();return [...document.querySelectorAll('#kf-arp input,#kf-arp select')].every(e=>{const r=e.getBoundingClientRect();return r.bottom<=screen.bottom-6&&r.left>=screen.left&&r.right<=screen.right;});})()") boolValue]);
      snapshotEditor(web);
      eval(web,@"document.querySelector('[data-page=main]').click()");
      waitFor([&]{return [eval(web,@"document.querySelector('[data-voice=legato]').getAttribute('aria-pressed')") isEqualToString:@"true"];});
      assert(![eval(web,@"document.querySelector('#kf-value-glide').disabled") boolValue]);
      eval(web,@"document.querySelector('[data-voice=mono]').click()");
      waitFor([&]{return std::abs(mode()-.5)<1e-8;});
      eval(web,@"(()=>{const e=document.querySelector('#kf-value-glide');e.value='80';e.dispatchEvent(new Event('change'));})()");
      waitFor([&]{return std::abs(glide()-80./127.)<1e-8;});
      eval(web,@"(()=>{const e=document.querySelector('#kf-value-velocity');e.value='2';e.dispatchEvent(new Event('change'));})()");
      waitFor([&]{return std::abs(velocity()-.6)<1e-6;});
      eval(web,@"document.querySelector('#kf-browse').click()");
      assert([eval(web,@"document.querySelector('#krose-browser').open") boolValue]);
      assert([eval(web,@"[...document.querySelectorAll('#krose-browser select[aria-label=音色类型] option')].slice(1).map(x=>x.value).join('|')") isEqualToString:@"PIANO|E.PIANO|ORGAN|BELL|STRINGS|BRASS|SYNTH LEAD|SYNTH PAD|GUITAR|BASS|DRUM/SFX"]);
      assert([eval(web,@"[...document.querySelector('#kf-program').options].slice(0,3).map(x=>x.textContent.split('  ')[0]).join('|')") isEqualToString:@"A000|A001|A002"]);
      assert([eval(web,@"[...document.querySelectorAll('#krose-browser [data-program]')].slice(0,3).map(x=>x.textContent.split('  ')[0]).join('|')") isEqualToString:@"A000|A001|A002"]);
      eval(web,@"(()=>{const c=document.querySelector('#krose-browser select[aria-label=音色类型]');c.value='BELL';c.dispatchEvent(new Event('change'));})()");
      assert([eval(web,@"[...document.querySelectorAll('#krose-browser [data-program]')].some(x=>x.textContent.startsWith('G015  GM Tubular Bells'))") boolValue]);
      eval(web,@"(()=>{const c=document.querySelector('#krose-browser select[aria-label=音色类型]');c.value='';c.dispatchEvent(new Event('change'));})()");
      eval(web,@"(()=>{const e=document.querySelector('#krose-browser input');e.value='EXPCM004:063';e.dispatchEvent(new Event('input'));})()");
      assert([eval(web,@"document.querySelectorAll('#krose-browser [data-program]').length") intValue]==1);
      eval(web,@"document.querySelector('#krose-browser [data-program]').click()");
      waitFor([&]{return std::abs(program()-1.)<1e-6;});
      assert(![eval(web,@"!!document.documentElement.dataset.scriptError") boolValue]);
    }else{
      waitFor([&]{return [eval(web,@"document.querySelector('[data-toggle=arp]').getAttribute('aria-pressed')") isEqualToString:@"true"];});
      assert([eval(web,@"document.querySelector('#kf-pattern').value") isEqualToString:@"RANDOM"]);
      assert([eval(web,@"document.querySelector('#kf-arp [data-bind=tempo]').value") doubleValue]==143.25);
      assert([eval(web,@"document.querySelector('[data-toggle=latch]').getAttribute('aria-pressed')") isEqualToString:@"true"]);
      waitFor([&]{return [eval(web,@"document.querySelector('[data-voice=mono]').getAttribute('aria-pressed')") isEqualToString:@"true"];});
      assert([eval(web,@"document.querySelector('#kf-value-glide').value") intValue]==80);
      waitFor([&]{return [eval(web,@"document.querySelector('#kf-value-velocity').value") doubleValue]==2.;});
      waitFor([&]{return [eval(web,@"document.querySelector('#kf-program').value") intValue]==1161;});
    }
    view->removed();
  }
}
