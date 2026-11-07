// Run real Win32 open/save dialogs on the runner's desktop. Drive only this
// test's own process/windows; no desktop cursor, user files or audio devices.
#include "storage/PresetDialogWin.h"
#include "storage/UserPreset.h"
#include <dlgs.h>
#include <commctrl.h>
#include <atomic>
#include <cassert>
#include <chrono>
#include <iostream>
#include <thread>

namespace {
struct Driver {
  HWND owner;
  bool cancel;
  bool sent = false;
  unsigned confirmations = 0;
  HWND dialog = nullptr;
};
BOOL CALLBACK Respond(HWND window, LPARAM parameter) {
  auto &driver = *reinterpret_cast<Driver *>(parameter);
  DWORD process = 0; GetWindowThreadProcessId(window, &process);
  if (process != GetCurrentProcessId()) return TRUE;
  if (!IsWindowVisible(window) || GetAncestor(window, GA_ROOTOWNER) != driver.owner) return TRUE;
  wchar_t name[64]{}; GetClassNameW(window, name, 64);
  if (std::wstring(name) != L"#32770") return TRUE;
  if (GetDlgItem(window, IDYES) || (driver.sent && window != driver.dialog)) {
    // Modern Explorer confirmations can use DirectUI controls on a different
    // shell thread, without a child HWND for the Yes button. Task dialogs
    // accept TDM_CLICK_BUTTON; classic message boxes accept WM_COMMAND.
    ++driver.confirmations;
    PostMessageW(window, TDM_CLICK_BUTTON, IDYES, 0);
    PostMessageW(window, WM_COMMAND, IDYES, 0);
    return TRUE;
  }
  if (driver.sent) return TRUE;
  if (!GetDlgItem(window, IDOK) || !GetDlgItem(window, IDCANCEL)) return TRUE;
  driver.dialog = window;
  driver.sent = true;
  PostMessageW(window, WM_COMMAND, driver.cancel ? IDCANCEL : IDOK, 0);
  return TRUE;
}
BOOL CALLBACK Cancel(HWND window, LPARAM owner) {
  DWORD process = 0; GetWindowThreadProcessId(window, &process);
  if (process == GetCurrentProcessId() && GetAncestor(window, GA_ROOTOWNER) == HWND(owner)) {
    PostMessageW(window, TDM_CLICK_BUTTON, IDCANCEL, 0);
    PostMessageW(window, WM_COMMAND, IDCANCEL, 0);
    PostMessageW(window, WM_CLOSE, 0, 0);
  }
  return TRUE;
}
std::filesystem::path Select(HWND owner, bool save, const std::filesystem::path &file, bool cancel = false) {
  Driver driver{owner, cancel};
  std::atomic<bool> finished{false};
  std::thread automation([&] {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(20);
    while (!finished && std::chrono::steady_clock::now() < deadline) {
      EnumWindows(Respond, LPARAM(&driver));
      std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }
    for (int retry=0;!finished && retry<40;++retry) {
      EnumWindows(Cancel, LPARAM(owner));
      std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }
  });
  const auto original = std::filesystem::current_path();
  std::cout << "Dialog save=" << save << " cancel=" << cancel << std::endl;
  const auto result = krose::storage::PresetDialog(owner, save, file.parent_path(), file.filename());
  finished = true; automation.join();
  if (!driver.sent) std::cerr << "No file dialog action: save=" << save << " cancel=" << cancel << "\n";
  assert(driver.sent);
  if (std::filesystem::current_path() != original)
    std::cerr << "Changed CWD: " << std::filesystem::current_path().u8string() << "\n";
  assert(std::filesystem::current_path() == original);
  assert(!save || !std::filesystem::exists(file) || cancel || driver.confirmations > 0);
  return result;
}
}
int main() {
  using namespace krose::storage;
  auto root = std::filesystem::temp_directory_path() /
      (L"krose-dialog-" + std::to_wstring(GetCurrentProcessId())) / L"中文音色 空格";
  std::filesystem::create_directories(root);
  // Runner TEMP can use RUNNER~1 while Explorer returns runneradmin. Compare
  // the same long spelling; both paths already refer to the same directory.
  std::vector<wchar_t> longName(32768);
  const auto length = GetLongPathNameW(root.c_str(), longName.data(), DWORD(longName.size()));
  assert(length && length < longName.size());
  root = std::filesystem::path(longName.data());
  HWND owner = CreateWindowW(L"STATIC", L"Krose preset dialog regression", WS_OVERLAPPEDWINDOW,
                              50, 50, 500, 300, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
  assert(owner); ShowWindow(owner, SW_SHOW);
  PresetValues values{};
  for (int i = 0; i < kNumParams; ++i) values[i] = double(i) / kNumParams;
  const auto requested = root / L"音色 piano"; // Dialog must append the .krose extension.
  auto saved = Select(owner, true, requested);
  if (saved != root / L"音色 piano.krose")
    std::cerr << "Unexpected save path: " << saved.u8string() << "\n";
  assert(saved == root / L"音色 piano.krose");
  WriteJson(saved, EncodePreset(values));
  const auto original = ReadJson(saved);
  assert(Select(owner, false, saved, true).empty());
  assert(ReadJson(saved) == original); // Cancel never mutates the preset.
  const auto opened = Select(owner, false, saved);
  assert(opened == saved && DecodePreset(ReadJson(opened)) == values);
  assert(Select(owner, true, saved) == saved); // Real overwrite confirmation.
  values[18] = .5;
  WriteJson(saved, EncodePreset(values));
  assert(DecodePreset(ReadJson(saved)) == values);
  assert(Select(owner, true, saved, true).empty());
  DestroyWindow(owner);
  std::filesystem::remove_all(root);
  std::cout << "PASS native Windows save/open/cancel/overwrite, Unicode paths and unchanged CWD\n";
}
