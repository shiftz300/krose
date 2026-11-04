#pragma once
#include "IPlugPaths.h"
#include <filesystem>
#include <cstdlib>
#include "config.h"
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
// Portable bundles keep samples beside images. Installed app and VST3 share
// one versioned sample directory; only construction touches the filesystem.
inline std::filesystem::path SampleDirectory(const std::filesystem::path& resources) {
  if (std::filesystem::exists(resources / "Factory.samples") &&
      std::filesystem::exists(resources / "SEGrand.samples"))
    return resources;
#if defined(OS_WIN)
  if (const auto* overridePath = _wgetenv(L"KROSE_SAMPLE_DIRECTORY"))
    return std::filesystem::path(overridePath);
  const auto* common = _wgetenv(L"CommonProgramFiles");
  if (!common) throw std::runtime_error("CommonProgramFiles is unavailable");
  return std::filesystem::path(common) / "Krose" / "Samples" / PLUG_VERSION_STR;
#else
  if (const auto* overridePath = std::getenv("KROSE_SAMPLE_DIRECTORY"))
    return std::filesystem::u8path(overridePath);
  return std::filesystem::path("/Library/Application Support/Krose/Samples") / PLUG_VERSION_STR;
#endif
}
} // namespace krose
