#include "../../KrosePlugin.h"
#include "../../storage/ExpansionLoader.h"
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
  Text(g, "lcd14", "ONBOARD / GM", R(438, 145, 264, 24));
  Text(g, "lcd13", "BUILT IN", R(720, 145, 102, 24), 1);
  if (!plugin->CanManageExpansions()) {
    Text(g, "lcd13", "A SPLIT SAMPLE LIBRARY IS REQUIRED.", R(438, 180, 524, 23));
    return;
  }

  float y = 171;
  for (const auto &pack : storage::kExpansions) {
    const bool installed = mInstalledExpansions[pack.number];
    const bool loaded = plugin->ExpansionAvailable(pack.number);
    const std::string label = std::string(pack.file, 8) + "  " + pack.name;
    Text(g, "lcd13", label, R(438, y, 274, 24));
    Text(g, "lcd13", installed != loaded ? "PENDING" : installed ? "INSTALLED" : "EMPTY",
         R(720, y, 102, 24), 1);
    if (installed)
      ControllerCell(g, "UNINSTALL", R(831, y, 131, 24), "expansion-remove", int(pack.number));
    y += 27;
  }
  ControllerCell(g, "LOAD KEP / ZIP", R(438, 257, 149, 25), "expansion-import");
  Text(g, "lcd13", mExpansionStatus, R(598, 257, 364, 25));
}

} // namespace krose::ui
