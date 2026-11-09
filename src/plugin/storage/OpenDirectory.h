#pragma once
#include <filesystem>
#include <cstdint>
#ifdef _WIN32
#include <windows.h>
#include <shellapi.h>
#endif

namespace krose::storage {
#ifdef _WIN32
inline bool OpenDirectory(const std::filesystem::path& directory) {
  if (!std::filesystem::is_directory(directory)) return false;
  return reinterpret_cast<std::intptr_t>(ShellExecuteW(nullptr, L"open", directory.c_str(),
      nullptr, nullptr, SW_SHOWNORMAL)) > 32;
}
#else
bool OpenDirectory(const std::filesystem::path& directory);
#endif
} // namespace krose::storage
