#include "OpenDirectory.h"
#import <AppKit/AppKit.h>

namespace krose::storage {
bool OpenDirectory(const std::filesystem::path& directory) {
  if (!std::filesystem::is_directory(directory)) return false;
  NSString* path = [NSString stringWithUTF8String:directory.u8string().c_str()];
  return path && [[NSWorkspace sharedWorkspace] openURL:[NSURL fileURLWithPath:path isDirectory:YES]];
}
} // namespace krose::storage
