// Run real Win32 open/save dialogs on the runner's desktop. Drive only this
// test's own thread/windows; no desktop cursor, user files or audio devices.
#include "storage/PresetDialogWin.h"
#include "storage/UserPreset.h"
#include <dlgs.h>
#include <atomic>
#include <cassert>
#include <chrono>
#include <iostream>
#include <thread>

namespace {
struct Driver {
  DWORD thread;
  HWND owner;
  std::wstring filename;
  bool cancel;
  bool sent = false;
  unsigned confirmations = 0;
};
BOOL CALLBACK FindFilename(HWND child, LPARAM output) {
  wchar_t name[64]{}; GetClassNameW(child, name, 64);
  const int id = GetDlgCtrlID(child), parent = GetDlgCtrlID(GetParent(child));
  if (std::wstring(name) == L"Edit" && (id == edt1 || parent == cmb13 || id == 1001)) {
    *reinterpret_cast<HWND *>(output) = child;
    return FALSE;
  }
  return TRUE;
}
BOOL CALLBACK Respond(HWND window, LPARAM parameter) {
  auto &driver = *reinterpret_cast<Driver *>(parameter);
  if (!IsWindowVisible(window) || GetAncestor(window, GA_ROOTOWNER) != driver.owner) return TRUE;
  wchar_t name[64]{}; GetClassNameW(window, name, 64);
  if (std::wstring(name) != L"#32770") return TRUE;
  if (GetDlgItem(window, IDYES)) {
    ++driver.confirmations;
    PostMessageW(window, WM_COMMAND, IDYES, 0);
    return TRUE;
  }
  if (driver.sent) return TRUE;
  auto edit = GetDlgItem(window, edt1);
  if (!edit) {
    const auto combo = GetDlgItem(window, cmb13);
    if (combo) edit = FindWindowExW(combo, nullptr, L"Edit", nullptr);
  }
  if (!edit) EnumChildWindows(window, FindFilename, LPARAM(&edit));
  if (!edit && !driver.cancel) return TRUE;
  if (edit && !driver.cancel) {
    SendMessageW(edit, WM_SETTEXT, 0, LPARAM(driver.filename.c_str()));
    // Explorer stores the file name in its shell view as well as the nested
    // edit. Notify the combo so IDOK uses the newly supplied Unicode path.
    SendMessageW(window, WM_COMMAND, MAKEWPARAM(cmb13, CBN_EDITCHANGE), LPARAM(GetParent(edit)));
  }
  driver.sent = true;
  PostMessageW(window, WM_COMMAND, driver.cancel ? IDCANCEL : IDOK, 0);
  return TRUE;
}
BOOL CALLBACK Cancel(HWND window, LPARAM owner) {
  if (GetAncestor(window, GA_ROOTOWNER) == HWND(owner) && GetDlgItem(window, IDCANCEL))
    PostMessageW(window, WM_COMMAND, IDCANCEL, 0);
  return TRUE;
}
std::filesystem::path Select(HWND owner, bool save, const std::filesystem::path &file, bool cancel = false) {
  Driver driver{GetCurrentThreadId(), owner, file.wstring(), cancel};
  std::atomic<bool> finished{false};
  std::thread automation([&] {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(20);
    while (!finished && std::chrono::steady_clock::now() < deadline) {
      EnumThreadWindows(driver.thread, Respond, LPARAM(&driver));
      std::this_thread::sleep_for(std::chrono::milliseconds(25));
    }
    if (!finished) EnumThreadWindows(driver.thread, Cancel, LPARAM(owner));
  });
  const auto original = std::filesystem::current_path();
  const auto result = krose::storage::PresetDialog(owner, save, file.parent_path());
  finished = true; automation.join();
  assert(driver.sent && std::filesystem::current_path() == original);
  assert(!save || !std::filesystem::exists(file) || cancel || driver.confirmations > 0);
  return result;
}
}
int main() {
  using namespace krose::storage;
  const auto root = std::filesystem::temp_directory_path() /
      (L"krose-dialog-" + std::to_wstring(GetCurrentProcessId())) / L"中文音色 空格";
  std::filesystem::create_directories(root);
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
