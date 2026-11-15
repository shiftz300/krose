#include "../../KrosePlugin.h"
#include "../../storage/ExpansionLoader.h"
#include "../../storage/PresetDialogWin.h"
#include "NativePanel.h"
#include "PanelDrawing.h"

namespace krose::ui {
using namespace detail;

void NativePanel::ReadExpansionStatus() {
  auto *plugin = static_cast<KrosePlugin *>(GetDelegate());
  if (!plugin->CanManageExpansions()) return;
  try {
    for (const auto &pack : storage::kExpansions)
      mInstalledExpansions[pack.number] = plugin->ExpansionInstalled(pack.number);
  } catch (const std::exception &) {
    mExpansionStatus = "CANNOT READ EXPANSION STORAGE";
  }
}

void NativePanel::ExpansionPage(IGraphics &g) {
  auto *plugin = static_cast<KrosePlugin *>(GetDelegate());
  Text(g, "lcd14", "ONBOARD / GM", LCDControlRow(0, 438, 264));
  Text(g, "lcd13", "BUILT IN", LCDControlRow(0, 720, 102), 1);
  if (!plugin->CanManageExpansions()) {
    Text(g, "lcd13", "A SPLIT SAMPLE LIBRARY IS REQUIRED FOR KEP.", LCDControlRow(1));
    if (plugin->CanImportPcg())
      ControllerCell(g, "LOAD PCG", LCDControlRow(4, 438, 106), "pcg-import");
    Text(g, "lcd13", mExpansionStatus, LCDControlRow(4, 554, 408));
    return;
  }

  int row = 1;
  for (const auto &pack : storage::kExpansions) {
    const bool installed = mInstalledExpansions[pack.number];
    const bool loaded = plugin->ExpansionAvailable(pack.number);
    const std::string label = std::string(pack.file, 8) + "  " + pack.name;
    Text(g, "lcd13", label, LCDControlRow(row, 438, 274));
    Text(g, "lcd13", installed != loaded ? "PENDING" : installed ? "INSTALLED" : "EMPTY",
         LCDControlRow(row, 720, 102), 1);
    if (installed)
      ControllerCell(g, "UNINSTALL", LCDControlRow(row, 831, 131), "expansion-remove",
                     int(pack.number));
    ++row;
  }
  ControllerCell(g, "LOAD KEP / ZIP", LCDControlRow(4, 438, 149), "expansion-import");
  if (plugin->CanImportPcg())
    ControllerCell(g, "LOAD PCG", LCDControlRow(4, 598, 106), "pcg-import");
  Text(g, "lcd13", mExpansionStatus, LCDControlRow(4, 715, 247));
}

void NativePanel::QueueFileDialog(FileRequest request) {
  if (!mFileDialogOpen && mPendingFileRequest == FileRequest::None)
    mPendingFileRequest = request;
}

void NativePanel::ShowPendingFileDialog() {
  if (mPendingFileRequest == FileRequest::None || mPointerDown || !GetUI()->WindowIsOpen())
    return;
  const auto request = mPendingFileRequest;
  mPendingFileRequest = FileRequest::None;
  mFileDialogOpen = true;
  ReleaseHeld();
  // System pickers can take focus and run a modal event loop. Open after the
  // original mouse event has finished and its editor capture has been released.
  GetUI()->ReleaseMouseCapture();
  const bool save = request == FileRequest::SavePreset;
  const bool expansion = request == FileRequest::ImportExpansion;
  const bool pcg = request == FileRequest::ImportPcg;
  const std::weak_ptr<int> alive = mLifetime;
  WDL_String file(save ? "Untitled.krose" : ""), path;
#ifdef _WIN32
  try {
    const auto view = static_cast<HWND>(GetUI()->GetWindow());
    const auto window = GetAncestor(view, GA_ROOT);
    const auto owner = window && GetWindowThreadProcessId(window, nullptr) == GetCurrentThreadId()
                           ? window : view;
    const auto chosen = krose::storage::PresetDialog(owner, save, {}, {}, expansion, pcg);
    if (!alive.expired()) CompleteFileDialog(request, chosen.u8string().c_str(), false);
  } catch (const std::exception &) {
    if (!alive.expired()) CompleteFileDialog(request, "", true);
  }
#else
  GetUI()->PromptForFile(file, path, save ? EFileAction::Save : EFileAction::Open,
      pcg ? "pcg" : expansion ? "kep zip" : "krose",
      [this, alive, request](const WDL_String &chosen, const WDL_String &) {
        if (!alive.expired()) CompleteFileDialog(request, chosen.Get(), false);
      });
#endif
}

void NativePanel::CompleteFileDialog(FileRequest request, const char *path, bool error) {
  mFileDialogOpen = false;
  if (!error && !*path) return;
  auto *plugin = static_cast<KrosePlugin *>(GetDelegate());
  const bool pcg = request == FileRequest::ImportPcg;
  if (pcg || request == FileRequest::ImportExpansion) {
    try {
      if (error) {
        mExpansionStatus = "CANNOT OPEN FILE PICKER";
      } else if (pcg) {
        const auto report = plugin->ImportPcg(path);
        mExpansionStatus = std::to_string(report.playable) + " OK";
        if (report.skipped) mExpansionStatus += " / " + std::to_string(report.skipped) + " SKIP";
        else if (report.missingPcm) mExpansionStatus += " / " + std::to_string(report.missingPcm) + " MISSING PCM";
        mExpansionStatus += " / REOPEN";
      } else {
        plugin->InstallExpansion(path);
        mExpansionStatus = "INSTALLED / REOPEN KROSE TO APPLY";
        ReadExpansionStatus();
      }
    } catch (const std::filesystem::filesystem_error &) {
      mExpansionStatus = pcg ? "CANNOT ACCESS PCG STORAGE" : "CANNOT ACCESS EXPANSION STORAGE";
    } catch (const std::runtime_error &e) {
      mExpansionStatus = e.what();
    } catch (const std::exception &) {
      mExpansionStatus = pcg ? "CANNOT INSTALL PCG" : "CANNOT INSTALL EXPANSION";
    }
  } else {
    const bool save = request == FileRequest::SavePreset;
    const bool ok = !error && (save ? plugin->SaveUserPreset(path) : plugin->LoadUserPreset(path));
    mPresetStatus = ok ? (save ? "PRESET SAVED" : "PRESET LOADED") : "PRESET FILE ERROR";
    if (ok && !save) {
      mBrowsing = false;
      mControllers = false;
      mEdit = -1;
      mPage = 0;
    }
  }
  SetDirty(false);
}
} // namespace krose::ui
