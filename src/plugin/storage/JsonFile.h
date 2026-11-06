#pragma once
#include "json.hpp"
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <atomic>
#include <chrono>
#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <unistd.h>
#endif

namespace krose::storage {
// Current files are only a few KiB. These ceilings leave room for future metadata
// while bounding accidental/malicious allocation; they are not format limits.
inline constexpr std::size_t kMaxJsonBytes = 8 * 1024 * 1024;
inline constexpr int kMaxJsonDepth = 64;
inline nlohmann::json ReadJson(const std::filesystem::path &path) {
  std::ifstream file(path, std::ios::binary | std::ios::ate);
  if (!file)
    throw std::runtime_error("Cannot open settings file");
  const auto size = file.tellg();
  if (size < 0 || size > std::streamoff(kMaxJsonBytes))
    throw std::runtime_error("Settings file exceeds size limit");
  std::string bytes(std::size_t(size), '\0');
  file.seekg(0);
  if (!file.read(bytes.data(), std::streamsize(bytes.size())))
    throw std::runtime_error("Cannot read settings file");
  return nlohmann::json::parse(bytes, [](int depth, nlohmann::json::parse_event_t, nlohmann::json &) {
    if (depth > kMaxJsonDepth)
      throw std::runtime_error("Settings nesting exceeds limit");
    return true;
  });
}
// Same-directory, exclusive temporary file; failed writes preserve the old file.
inline void WriteJson(const std::filesystem::path &path, const nlohmann::json &value) {
  const auto bytes = value.dump(2) + '\n';
  if (bytes.size() > kMaxJsonBytes)
    throw std::runtime_error("Settings file exceeds size limit");
  if (!path.parent_path().empty())
    std::filesystem::create_directories(path.parent_path());
  static std::atomic<unsigned> serial{0};
  auto temp = path;
  temp += "." + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) +
          "." + std::to_string(serial++) + ".tmp";
#ifdef _WIN32
  HANDLE file = CreateFileW(temp.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                            FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE)
    throw std::runtime_error("Cannot create settings file");
  DWORD written = 0;
  const bool ok = WriteFile(file, bytes.data(), DWORD(bytes.size()), &written, nullptr) &&
                  written == bytes.size() && FlushFileBuffers(file);
  CloseHandle(file);
  const bool replaced = ok && MoveFileExW(temp.c_str(), path.c_str(),
                                         MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
#else
  const int file = open(temp.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
  if (file < 0)
    throw std::runtime_error("Cannot create settings file");
  const bool ok = write(file, bytes.data(), bytes.size()) == ssize_t(bytes.size()) && fsync(file) == 0;
  close(file);
  const bool replaced = ok && rename(temp.c_str(), path.c_str()) == 0;
#endif
  if (!replaced) {
    std::error_code ignored;
    std::filesystem::remove(temp, ignored);
    throw std::runtime_error("Cannot replace settings file");
  }
}
} // namespace krose::storage
