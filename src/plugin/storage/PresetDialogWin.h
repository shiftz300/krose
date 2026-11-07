#pragma once
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <commdlg.h>
#include <filesystem>
#include <algorithm>
#include <iterator>
#include <stdexcept>
#include <vector>

namespace krose::storage {
// Used by both APP and VST3. The dialog owns no audio resources and never
// changes the process working directory. Paths remain UTF-16 until file I/O.
inline std::filesystem::path PresetDialog(HWND owner, bool save,
                                         const std::filesystem::path &directory = {}) {
  std::vector<wchar_t> name(32768, L'\0');
  if (save) {
    constexpr wchar_t initial[] = L"Untitled.krose";
    std::copy(std::begin(initial), std::end(initial), name.begin());
  }
  const auto folder = directory.wstring();
  OPENFILENAMEW dialog{};
  dialog.lStructSize = sizeof(dialog);
  dialog.hwndOwner = owner;
  dialog.lpstrFile = name.data();
  dialog.nMaxFile = DWORD(name.size());
  dialog.lpstrFilter = L"Krose Preset (*.krose)\0*.krose\0\0";
  dialog.lpstrDefExt = L"krose";
  dialog.lpstrInitialDir = folder.empty() ? nullptr : folder.c_str();
  dialog.Flags = OFN_EXPLORER | OFN_ENABLESIZING | OFN_NOCHANGEDIR | OFN_PATHMUSTEXIST |
                 (save ? OFN_OVERWRITEPROMPT : OFN_FILEMUSTEXIST);
  const bool chosen = save ? GetSaveFileNameW(&dialog) : GetOpenFileNameW(&dialog);
  if (!chosen) {
    if (CommDlgExtendedError()) throw std::runtime_error("Cannot open preset file dialog");
    return {}; // Cancel is not an error and must not apply any sound changes.
  }
  return std::filesystem::path(name.data());
}
} // namespace krose::storage
#endif
