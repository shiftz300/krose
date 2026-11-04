// Authoring-only WebKit capture. The native plugin never links this tool.
#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>
#include <cstdio>
#include <cstdlib>
static void wait(bool* done) {
  NSDate* deadline=[NSDate dateWithTimeIntervalSinceNow:30];
  while(!*done && deadline.timeIntervalSinceNow>0)
    [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.005]];
  if(!*done){fprintf(stderr,"Capture timed out\n");exit(2);}
}
static id evaluate(WKWebView* view,NSString* script) {
  __block bool done=false;__block id result=nil;
  [view evaluateJavaScript:script completionHandler:^(id value,NSError* error){
    if(error){NSLog(@"%@",error);exit(3);} result=value;done=true;
  }];wait(&done);return result;
}
int main(int argc,char** argv) {@autoreleasepool {
  if(argc!=4){fprintf(stderr,"capture panel.html jobs.json output-directory\n");return 1;}
  [NSApplication sharedApplication];
  NSWindow* window=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,1472,648) styleMask:NSWindowStyleMaskBorderless backing:NSBackingStoreBuffered defer:NO];
  WKWebViewConfiguration* configuration=[WKWebViewConfiguration new];
  configuration.websiteDataStore=WKWebsiteDataStore.nonPersistentDataStore;
  WKWebView* web=[[WKWebView alloc] initWithFrame:NSMakeRect(0,0,1472,648) configuration:configuration];
  [web setValue:@NO forKey:@"drawsBackground"];window.contentView=web;[window orderFront:nil];
  NSString* source=[NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:nil];
  if(!source)return 2;
  [web loadHTMLString:source baseURL:nil];
  NSDate* deadline=[NSDate dateWithTimeIntervalSinceNow:30];
  while((web.loading||![evaluate(web,@"!!document.querySelector('#krose-fixed-ui[data-ready]')") boolValue])&&deadline.timeIntervalSinceNow>0)
    [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.02]];
  evaluate(web,@"window.__captureReady=false;document.fonts.ready.then(()=>{setTimeout(()=>window.__captureReady=true,400)});null");
  while(![evaluate(web,@"window.__captureReady") boolValue]) [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.02]];
  NSArray* jobs=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[2])] options:0 error:nil];
  [[NSFileManager defaultManager] createDirectoryAtPath:@(argv[3]) withIntermediateDirectories:YES attributes:nil error:nil];
  for(NSDictionary* job in jobs){
    id value=evaluate(web,job[@"script"]?:@"null");
    NSString* path=[@(argv[3]) stringByAppendingPathComponent:job[@"name"]];
    if([job[@"json"] boolValue]){
      NSData* data=[NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingPrettyPrinted error:nil];if(![data writeToFile:path atomically:YES])return 4;continue;
    }
    WKSnapshotConfiguration* config=[WKSnapshotConfiguration new];
    NSArray* r=job[@"rect"]?:@[@0,@0,@1472,@648];
    config.rect=NSMakeRect([r[0] doubleValue],[r[1] doubleValue],[r[2] doubleValue],[r[3] doubleValue]);
    config.snapshotWidth=@([r[2] doubleValue]);config.afterScreenUpdates=YES;
    __block bool done=false;
    [web takeSnapshotWithConfiguration:config completionHandler:^(NSImage* image,NSError* error){
      if(error||!image){NSLog(@"%@",error);exit(5);}
      NSBitmapImageRep* rep=[NSBitmapImageRep imageRepWithData:image.TIFFRepresentation];
      if(![[rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}] writeToFile:path atomically:YES])exit(6);
      done=true;
    }];wait(&done);
  }
  return 0;
}}
