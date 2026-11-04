#pragma once
#include "IPlugPaths.h"
#include <filesystem>
#include <stdexcept>

namespace krose {
// Resolve resources from this module, never from the host's working directory.
inline std::filesystem::path ResourceDirectory(const char *bundleID) {
  WDL_String path;
#if defined(OS_WIN)
  HMODULE module = nullptr;
  if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                              GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                          reinterpret_cast<LPCWSTR>(&ResourceDirectory), &module))
    throw std::runtime_error("Cannot locate Krose module");
  wchar_t filename[32768]{};
  if (!GetModuleFileNameW(module, filename, 32768))
    throw std::runtime_error("Cannot locate Krose resources");
  auto directory = std::filesystem::path(filename).parent_path();
#if defined(VST3_API)
  return directory.parent_path() / "Resources";
#else
  return directory / "Resources";
#endif
#else
  iplug::BundleResourcePath(path, bundleID);
  return std::filesystem::path(path.Get());
#endif
}
} // namespace krose
