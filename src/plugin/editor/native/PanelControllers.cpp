#include "../../KrosePlugin.h"
#include "NativePanel.h"
#include "PanelDrawing.h"
#include "BuildInfo.h"
#include "../../standalone/AudioSettings.h"
#include "../../storage/OpenDirectory.h"
#include <filesystem>
namespace krose::ui {
using namespace detail;
using namespace krose::midi;
namespace {
constexpr const char *kControllerTabs[] = {"CTRL", "MIDI", "INPUT", "AUDIO", "EX", "SYSTEM"};
constexpr float kTabStart = 527, kTabWidth = 440.f / 6;
const char *sources[] = {"OFF",  "CC",   "CC 14 BIT", "NRPN",      "RPN",
                         "NOTE", "BEND", "PRESSURE",  "POLY PRESS"};
const char *modes[] = {"ABSOLUTE",     "REL 2'S COMP", "REL OFFSET 64",
                       "REL SIGN MAG", "TOGGLE",       "MOMENTARY"};
const int config[] = {kSW1Assign,    kSW1Mode,       kSW2Assign,  kSW2Mode,
                      kInputChannel, kProgramChange, kClockSource};
std::string Target(KrosePlugin *p, unsigned id) {
  const int parameter = ParameterForMidiTarget(id);
  if (parameter >= 0)
    return p->GetParam(parameter)->GetName();
  return id == KrosePlugin::kTargetNext       ? "NEXT PRESET"
         : id == KrosePlugin::kTargetPrevious ? "PREV PRESET"
                                              : "PANIC";
}
} // namespace
uint64_t NativePanel::ControllerHash() {
  auto *p = static_cast<KrosePlugin *>(GetDelegate());
  uint64_t hash = 1469598103934665603ull;
  auto add = [&](uint64_t v) { hash = (hash ^ v) * 1099511628211ull; };
  for (unsigned i = 0; i < ControllerMap::kSlots; ++i)
    add(p->MidiMappings().Get(i).Encode());
  for (int id : config)
    add(uint64_t(p->GetParam(id)->Int()));
  return hash;
}
void NativePanel::ControllerCell(IGraphics &g, const std::string &text, IRECT r,
                                 const std::string &action, int id, double value, bool selected) {
  r = LCDRect(r);
  g.FillRect(selected ? Ink : Paper, r);
  LCDFrame(g, r);
  const bool choice = action == "field" || action == "midi-menu" || action == "ui-scale";
  if (choice)
    LCDChevron(g, r, selected ? Paper : Ink);
  g.PathClipRegion(R(r.L + 3, r.T + 3, r.W() - (choice ? 25 : 6), r.H() - 6));
  Text(g, selected ? "light14" : "lcd14", text,
       R(r.L + 7, r.T + 2.25f, r.W() - (choice ? 32 : 14), r.H() - 2.25f), 1);
  g.PathClipRegion(R(424, 108, 556, 176));
  HitBox(r, action, id, value);
}
void NativePanel::DrawControllerTabs(IGraphics &g) {
  g.FillRect(Paper, R(431, 115, 542, 24));
  // Connected tabs use the same 45-degree, pixel-stepped shoulders as the program pages.
  LCDFrame(g, LCDRect(R(433, 115, 88, 23)));
  Text(g, "lcd14", "< PROG", R(440, 117.25f, 74, 20.75f), 1);
  for (int i = 0; i < 6; ++i) {
    const float x = kTabStart + i * kTabWidth;
    const bool active = i == int(mControllerPage);
    for (int row = 0; row < 9; ++row) {
      float inset = (8 - row) * 2.25f;
      g.FillRect(active ? Ink : Paper,
                 LCDRect(R(x + inset, 117 + row * 2.25f, kTabWidth - 2 * inset, 2.25f)));
    }
    g.FillRect(Ink, LCDRect(R(x, 136, kTabWidth, 2.25f)));
    Text(g, active ? "light14" : "lcd14", kControllerTabs[i],
         R(x + 2, 121.25f, kTabWidth - 4, 16), 1);
  }
}
void NativePanel::BindControllerTabs() {
  HitBox(LCDRect(R(433, 115, 88, 23)), "controller-close");
  for (int i = 0; i < 6; ++i)
    HitBox(R(kTabStart + i * kTabWidth, 115, kTabWidth, 23), "controller-page", -1, i);
}
void NativePanel::Controllers(IGraphics &g) {
  auto *p = static_cast<KrosePlugin *>(GetDelegate());
  auto &map = p->MidiMappings();
  const auto binding = map.Get(mMapSlot);
  g.FillRect(Paper, R(431, 139, 542, 145));
  if (mConfirmProfile != -1) {
    Text(g, "lcd16",
         mConfirmProfile >= 0 ? "Discard unsaved map changes?" : "Replace all MIDI mappings?",
         R(441, 159, 520, 27), 1);
    Text(g, "lcd14", "Project state remains available in your DAW.", R(441, 191, 520, 24), 1);
    ControllerCell(g, "CANCEL", LCDControlRow(3, 470, 180), "controller-confirm", -1, 0);
    ControllerCell(g, "CONTINUE", LCDControlRow(3, 748, 180), "controller-confirm", -1, 1);
    return;
  }
  if (mControllerPage == ControllerPage::Switches) {
    for (int sw = 0; sw < 2; ++sw) {
      int id = kSW1Assign + sw * 3;
      Text(g, "lcd14", sw ? "SW2" : "SW1", LCDControlRow(sw, 438, 39));
      const auto *a = p->GetParam(id), *b = p->GetParam(id + 1);
      ControllerCell(g, a->GetDisplayText(a->Int()), LCDControlRow(sw, 482, 237), "field", id);
      ControllerCell(g, b->GetDisplayText(b->Int()), LCDControlRow(sw, 729, 144), "field", id + 1);
      ControllerCell(g, Value(id + 2) ? "ON" : "TEST", LCDControlRow(sw, 882, 81), "switch", sw, 0,
                     Value(id + 2) > 0);
    }
    ControllerCell(g, Value(kFXBypass) ? "FX BYPASS: ON" : "FX BYPASS: OFF", LCDControlRow(2, 438, 248),
                   "toggle", kFXBypass);
    ControllerCell(g, "MAP SW1", LCDControlRow(2, 698, 126), "controller-learn", kSW1State);
    ControllerCell(g, "MAP SW2", LCDControlRow(2, 836, 126), "controller-learn", kSW2State);
    Text(g, "lcd13", "Mod CC: SW1=80 / SW2=81. Right-click a control to learn.",
         LCDControlRow(4));
  } else if (mControllerPage == ControllerPage::Midi) {
    ControllerCell(g, "#" + std::to_string(mMapSlot + 1), LCDControlRow(0, 438, 61), "midi-menu", 0);
    ControllerCell(g, Target(p, binding.target), LCDControlRow(0, 509, 453), "midi-menu", 1);
    ControllerCell(g, sources[unsigned(binding.source)], LCDControlRow(1, 438, 149), "midi-menu", 2);
    ControllerCell(
        g, mMapEdit >= 0 ? mEditText : "NO. " + std::to_string(binding.number),
        LCDControlRow(1, 597, 156),
        (binding.source == Source::Bend || binding.source == Source::Pressure) ? "" : "map-number");
    ControllerCell(g, binding.channel ? "CH " + std::to_string(binding.channel) : "OMNI",
                   LCDControlRow(1, 763, 199), "midi-menu", 3);
    ControllerCell(g, modes[unsigned(binding.mode)], LCDControlRow(2, 438, 228), "midi-menu", 4);
    ControllerCell(g, "PICKUP", LCDControlRow(2, 676, 95),
                   binding.mode == Mode::Absolute ? "map-flag" : "", 0, 0,
                   binding.pickup && binding.mode == Mode::Absolute);
    ControllerCell(g, "THRU", LCDControlRow(2, 781, 83), "map-flag", 1, 0, !binding.consume);
    ControllerCell(g, "INVERT", LCDControlRow(2, 874, 88), "map-flag", 2, 0, binding.invert);
    ControllerCell(g, map.Learning() >= 0 ? "CANCEL" : "LEARN", LCDControlRow(3, 438, 137), "map-learn",
                   -1, 0, map.Learning() >= 0);
    ControllerCell(g, "CLEAR", LCDControlRow(3, 585, 115), "map-clear");
    std::string status = map.Learning() >= 0 ? "Move ONE controller..." : mControllerStatus;
    if (status.empty())
      status = binding.source == Source::Off ? "Empty slot" : "Ready / right-click to learn";
    Text(g, "lcd13", status, LCDControlRow(4));
  } else if (mControllerPage == ControllerPage::Input) {
    ControllerCell(g,
                   "USER " + std::to_string(p->MidiProfile() + 1) +
                       (ControllerHash() != mStoredMapping ? " *" : ""),
                   LCDControlRow(0, 438, 173), "midi-menu", 5);
    ControllerCell(g, "STORE", LCDControlRow(0, 622, 101), "map-store");
    ControllerCell(g,
                   Value(kInputChannel) ? "INPUT CH " + Format(Value(kInputChannel)) : "INPUT OMNI",
                   LCDControlRow(0, 734, 228), "field", kInputChannel);
    auto enumText = [&](int id) {
      auto *v = p->GetParam(id);
      return std::string(v->GetDisplayText(v->Int()));
    };
    ControllerCell(g, "CLOCK: " + enumText(kClockSource), LCDControlRow(1, 438, 253), "field",
                   kClockSource);
#if defined(APP_API)
    ControllerCell(g, "PGM: " + enumText(kProgramChange), LCDControlRow(1, 702, 260), "field",
                   kProgramChange);
#else
    ControllerCell(g, "PGM: HOST / DAW", LCDControlRow(1, 702, 260), "controller-pgm-info");
#endif
    ControllerCell(g, "PROFILES", LCDControlRow(2, 438, 166), "midi-menu", 7);
    ControllerCell(g, "CLEAR MAP", LCDControlRow(2, 615, 157), "map-clear-all");
    ControllerCell(g, "PANIC", LCDControlRow(2, 783, 179), "panic");
#if defined(APP_API)
    ControllerCell(g, "IN: " + p->AudioChoice(3), LCDControlRow(3, 438, 253), "midi-menu", 11);
    ControllerCell(g, "OUT: " + p->AudioChoice(4), LCDControlRow(3, 702, 260), "midi-menu", 12);
#endif
    ControllerCell(g,
         p->MidiSettingsError() ? "SAVE FAILED - check settings file permissions"
         : mControllerStatus.empty()
             ? p->ArturiaStatus()
             : mControllerStatus,
         LCDControlRow(4), "controller-arturia");
  } else if (mControllerPage == ControllerPage::Audio) {
#if defined(APP_API)
    ControllerCell(g, "DRIVER: " + p->AudioChoice(0), LCDControlRow(0, 438, 253), "midi-menu", 8);
    ControllerCell(g, p->AudioChoice(2) + " Hz", LCDControlRow(0, 702, 260), "midi-menu", 10);
    ControllerCell(g, p->AudioChoice(1), LCDControlRow(1), "midi-menu", 9);
    const unsigned buffer = p->AudioBufferSize();
    const double ms = p->AudioRate() > 0 ? buffer * 1000. / p->AudioRate() : 0;
    ControllerCell(g, buffer ? std::to_string(buffer) + " / " + Format(ms, 2) + " ms" : "AUDIO OFF",
                   LCDControlRow(2, 438, 253), buffer ? "midi-menu" : "", 6);
    ControllerCell(g, "ASIO PANEL", LCDControlRow(2, 702, 260),
                   p->AudioChoices(5).empty() ? "" : "midi-menu", 13);
    Text(g, "lcd13", mControllerStatus.empty() ? "DRIVER / SAMPLE RATE / OUTPUT / BUFFER" : mControllerStatus,
         LCDControlRow(4));
#else
    Text(g, "lcd16", "Audio settings are managed by your host / DAW.", LCDControlRow(0), 1);
    Text(g, "lcd14", "BUFFER: " + std::to_string(p->AudioBufferSize()) + " / " + Format(p->AudioRate()) + " Hz",
         LCDControlRow(4), 1);
#endif
  } else if (mControllerPage == ControllerPage::Expansions) {
    ExpansionPage(g);
  } else if (!mSystemHelp) {
    const int scale = int(std::lround(GetUI()->GetDrawScale() * 100));
    ControllerCell(g, "UI SIZE: " + std::string(p->EditorScalePercent() ? "" : "AUTO ") +
                         std::to_string(scale) + "%", LCDControlRow(0), "ui-scale");
    ControllerCell(g, p->UpdateChecksEnabled() ? "CHECK UPDATES: ON" : "CHECK UPDATES: OFF",
                   LCDControlRow(1, 438, 289), "update-checks", -1, 0, p->UpdateChecksEnabled());
    ControllerCell(g, "MIDI HELP", LCDControlRow(1, 739, 223), "system-help");
    Text(g, "lcd16", std::string("KROSE ") + krose::build::kVersion, LCDControlRow(2));
    Text(g, "lcd13", mControllerStatus.empty() ? std::string("BUILD: ") + krose::build::kTimestamp
                                               : mControllerStatus, LCDControlRow(4));
  } else {
    uint32_t rx = map.LastMessage();
    unsigned s = rx & 255, a = (rx >> 8) & 127, b = (rx >> 16) & 127;
    char line[96];
    std::snprintf(line, sizeof(line), "RX %02X  %03u  %03u / CH %u", s, a, b, (s & 15) + 1);
    Text(g, "lcd14", rx ? line : "RX: waiting for MIDI input", LCDControlRow(0, 438, 354));
    ControllerCell(g, "< SYSTEM", LCDControlRow(0, 812, 150), "system-help");
    const char *lines[] = {"Right-click a control to learn a mapping.",
                           "Learn listens without changing the current sound.",
                           "Match relative mode to your keyboard encoder.",
                           "SYSTEM sets UI size. AUDIO sets the audio buffer."};
    for (int i = 0; i < 4; ++i)
      Text(g, "lcd13", lines[i], LCDControlRow(i + 1));
  }
}
void NativePanel::ControllerMenu(const Hit &h) {
  auto *p = static_cast<KrosePlugin *>(GetDelegate());
  auto b = p->MidiMappings().Get(mMapSlot);
  BeginPopup(h);
  if (h.id == 0) {
    for (unsigned i = 0; i < ControllerMap::kSlots; ++i) {
      auto n = p->MidiMappings().Get(i);
      AddChoice(std::to_string(i + 1) + (n.source == Source::Off ? " -" : " *"), i);
    }
    mPopupFocus = mMapSlot;
  }
  if (h.id == 1) {
    for (unsigned i = 0; i < KrosePlugin::kMapTargets; ++i)
      AddChoice(Target(p, i), i);
    mPopupFocus = b.target;
  }
  if (h.id == 2) {
    for (int i = 0; i < 9; ++i)
      AddChoice(sources[i], i);
    mPopupFocus = int(b.source);
  }
  if (h.id == 3) {
    AddChoice("OMNI", 0);
    for (int i = 1; i <= 16; ++i)
      AddChoice("CH " + std::to_string(i), i);
    mPopupFocus = b.channel;
  }
  if (h.id == 4) {
    for (int i = 0; i < 7; ++i)
      AddChoice(modes[i], i);
    mPopupFocus = int(b.mode);
  }
  if (h.id == 5) {
    for (int i = 0; i < 4; ++i)
      AddChoice("USER " + std::to_string(i + 1), i);
    mPopupFocus = p->MidiProfile();
  }
  if (h.id == 6) {
    for (unsigned frames : krose::standalone::kBufferSizes) {
      if (frames == p->AudioBufferSize()) mPopupFocus = int(mChoices.size());
      AddChoice(std::to_string(frames) + " SAMPLES", int(frames));
    }
  }
  if (h.id == 7) {
    mPopupTarget.r = LCDRect(R(438, 144, 524, 24));
    AddChoice("STANDARD CC", -1);
    AddChoice("EXPORT CURRENT MAP", -2);
    AddChoice("OPEN USER PROFILES", -3);
    AddChoice("OPEN BUILT-IN KIT", -4);
    mControllerFiles.clear();
    for (const auto& file : p->ControllerProfileFiles()) {
      AddChoice(std::string(!file.valid ? "INVALID / " : file.builtin ? "BUILT-IN / " : "USER / ") + file.name,
          int(mControllerFiles.size()));
      mControllerFiles.push_back(file.valid ? file.path : "");
    }
  }
  if (h.id >= 8 && h.id <= 13) {
    const int kind = h.id - 8;
    const auto current = p->AudioChoice(kind);
    for (const auto& choice : p->AudioChoices(kind)) {
      if (choice == current) mPopupFocus = int(mChoices.size());
      AddChoice(choice, int(mChoices.size()));
    }
    if (mChoices.empty()) AddChoice("NO DEVICE AVAILABLE", -1);
  }
  const float room = std::max(284 - mPopupTarget.r.B - 2, mPopupTarget.r.T - 140 - 2);
  mPopupRows = std::min(int(mChoices.size()), std::max(1, int(room / 22)));
  CenterPopup();
}
void NativePanel::ControllerChoice(int id, int value, const std::string &selected) {
  auto *p = static_cast<KrosePlugin *>(GetDelegate());
  auto &map = p->MidiMappings();
  auto b = map.Get(mMapSlot);
  map.CancelLearn();
  if (id >= 8 && id <= 13) {
    if (value >= 0 && !selected.empty()) {
      ReleaseHeld();
      const bool changed = p->SelectAudioChoice(id - 8, selected);
      mControllerStatus = changed ? "Setting applied" : "Unavailable / previous setting retained";
    }
    return;
  }
  if (id == 7) {
    if (value == -1) mConfirmProfile = -2;
    else if (value == -2)
      mControllerStatus = p->ExportControllerProfile() ? "Exported / OPEN USER PROFILES" : "Profile export failed";
    else if (value == -3 || value == -4) {
      try {
        const auto folder = std::filesystem::u8path(p->ControllerSupportFolder(value == -4));
        if (value == -3) std::filesystem::create_directories(folder);
        if (!std::filesystem::is_directory(folder)) throw std::runtime_error("Controller kit unavailable");
        mControllerStatus = krose::storage::OpenDirectory(folder) ? "Controller folder opened" : "Cannot open controller folder";
      } catch (const std::exception&) { mControllerStatus = "Controller folder unavailable"; }
    } else if (value >= 0 && value < int(mControllerFiles.size())) {
      if (mControllerFiles[value].empty()) {
        mControllerStatus = "Invalid profile / check schema.json";
        return;
      }
      mPendingControllerFile = mControllerFiles[value];
      mConfirmProfile = -4;
    }
    return;
  }
  if (id == 6) {
    ReleaseHeld();
    mControllerStatus = p->SetAudioBufferSize(unsigned(value)) ? "Buffer applied and saved" :
        "Buffer unavailable - previous setting restored";
    return;
  }
  if (id == 0) {
    mMapSlot = value;
    return;
  }
  if (id == 5) {
    if (unsigned(value) == p->MidiProfile())
      return;
    if (ControllerHash() != mStoredMapping) {
      mConfirmProfile = value;
      return;
    }
    if (p->LoadMidiProfile(value)) {
      mStoredMapping = ControllerHash();
      mControllerStatus = "Profile loaded";
    }
    return;
  }
  if (id == 1)
    b.target = value;
  if (id == 2) {
    b.source = Source(value);
    if (b.source == Source::Bend || b.source == Source::Pressure)
      b.number = 0;
    b.number = std::min(b.number, b.source == Source::CC14                                ? 31u
                                  : (b.source == Source::NRPN || b.source == Source::RPN) ? 16383u
                                                                                          : 127u);
  }
  if (id == 3)
    b.channel = value;
  if (id == 4)
    b.mode = Mode(value);
  map.Set(mMapSlot, b);
  mControllerStatus = "Edited / INPUT > STORE to keep";
}
void NativePanel::BeginLearn(int parameter) {
  const int target = MidiTargetForParameter(parameter);
  auto *p = static_cast<KrosePlugin *>(GetDelegate());
  auto &map = p->MidiMappings();
  map.CancelLearn();
  int slot = -1, empty = -1;
  for (unsigned i = 0; i < ControllerMap::kSlots; ++i) {
    auto b = map.Get(i);
    if (b.source != Source::Off && b.target == unsigned(target)) {
      slot = i;
      break;
    }
    if (empty < 0 && b.source == Source::Off)
      empty = i;
  }
  if (slot < 0)
    slot = empty;
  mControllers = true;
  mControllerPage = ControllerPage::Midi;
  mChoices.clear();
  mBrowsing = mPresetOpen = false;
  if (!mStoredMapping)
    mStoredMapping = ControllerHash();
  if (slot < 0) {
    mControllerStatus = "Map full / clear a slot first";
    return;
  }
  mMapSlot = slot;
  auto b = map.Get(slot);
  b.target = target;
  if (b.source == Source::Off) {
    b.mode = (p->GetParam(parameter)->Type() == IParam::kTypeBool)
                 ? Mode::Toggle
                 : Mode::Absolute;
    if ((target == kSW1State && Value(kSW1Mode)) || (target == kSW2State && Value(kSW2Mode)))
      b.mode = Mode::Momentary;
    b.pickup = b.mode == Mode::Absolute;
  }
  map.Set(slot, b);
  map.Learn(slot);
  mControllerStatus = "";
}
void NativePanel::ReleaseSwitches() {
  for (int i = 0; i < 2; ++i)
    if (mHeldSwitch[i]) {
      Set(kSW1State + i * 3, 0);
      mHeldSwitch[i] = false;
    }
}
bool NativePanel::ControllerAction(const Hit &h) {
  auto *p = static_cast<KrosePlugin *>(GetDelegate());
  auto &map = p->MidiMappings();
  auto b = map.Get(mMapSlot);
  if (h.action == "controller-open") {
    mControllers = true;
    mControllerPage = ControllerPage::Switches;
    mControllerStatus.clear();
  } else if (h.action == "controller-close") {
    mControllers = false;
    map.CancelLearn();
    mMapEdit = -1;
    mConfirmProfile = -1;
  } else if (h.action == "update-checks") {
    const bool enabled = !p->UpdateChecksEnabled();
    mControllerStatus = p->SetUpdateChecksEnabled(enabled) ? "" : "SAVE FAILED";
    if (!enabled) ShowUpdateNotice("");
  } else if (h.action == "controller-page") {
    mControllerPage = static_cast<ControllerPage>(int(h.value));
    if (mControllerPage != ControllerPage::Midi)
      map.CancelLearn();
    mConfirmProfile = -1;
    mSystemHelp = false;
    if (mControllerPage == ControllerPage::System)
      mControllerStatus.clear();
    if (mControllerPage == ControllerPage::Expansions)
      ReadExpansionStatus();
  } else if (h.action == "system-help") {
    mSystemHelp = !mSystemHelp;
  } else if (h.action == "expansion-import") {
    QueueFileDialog(FileRequest::ImportExpansion);
  } else if (h.action == "pcg-import") {
    QueueFileDialog(FileRequest::ImportPcg);
  } else if (h.action == "expansion-remove") {
    try {
      p->UninstallExpansion(unsigned(h.id));
      mExpansionStatus = "REMOVED / REOPEN KROSE TO APPLY";
      ReadExpansionStatus();
    } catch (const std::exception &) {
      mExpansionStatus = "CANNOT CHANGE EXPANSION STORAGE";
    }
  } else if (h.action == "controller-learn")
    BeginLearn(h.id);
  else if (h.action == "switch") {
    int id = kSW1State + h.id * 3;
    if (Value(id - 1) > 0) {
      Set(id, 1);
      mHeldSwitch[h.id] = true;
    } else
      Set(id, Value(id) ? 0 : 1);
  } else if (h.action == "midi-menu") {
    map.CancelLearn();
    ControllerMenu(h);
  } else if (h.action == "map-number") {
    map.CancelLearn();
    mMapEdit = mMapSlot;
    mEditText = std::to_string(b.number);
    mSelectAll = true;
  } else if (h.action == "map-flag") {
    map.CancelLearn();
    if (h.id == 0)
      b.pickup = !b.pickup;
    if (h.id == 1)
      b.consume = !b.consume;
    if (h.id == 2)
      b.invert = !b.invert;
    map.Set(mMapSlot, b);
  } else if (h.action == "map-learn") {
    if (map.Learning() >= 0) {
      map.CancelLearn();
      mControllerStatus = "Learning cancelled";
    } else {
      map.Learn(mMapSlot, b.source);
      mControllerStatus.clear();
    }
  } else if (h.action == "map-clear") {
    map.CancelLearn();
    b.source = Source::Off;
    map.Set(mMapSlot, b);
    mControllerStatus = "Slot cleared";
  } else if (h.action == "controller-pgm-info") {
    mControllerStatus = "VST3: use DAW program selection and host clock";
  } else if (h.action == "controller-buffer-info") {
    mControllerStatus = "Set the buffer in your DAW Audio Preferences";
  } else if (h.action == "controller-arturia") {
#if defined(APP_API)
    p->SetArturiaEnabled(!p->ArturiaEnabled());
    mControllerStatus.clear();
#else
    mControllerStatus = "Open built-in kit for DAW setup";
#endif
  } else if (h.action == "map-store") {
    if (p->StoreMidiProfile(p->MidiProfile())) {
      mStoredMapping = ControllerHash();
      mControllerStatus = "Stored in USER " + std::to_string(p->MidiProfile() + 1);
    }
  } else if (h.action == "map-standard")
    mConfirmProfile = -2;
  else if (h.action == "map-clear-all")
    mConfirmProfile = -3;
  else if (h.action == "controller-confirm") {
    int action = mConfirmProfile;
    mConfirmProfile = -1;
    if (h.value) {
      if (action >= 0) {
        if (p->LoadMidiProfile(action))
          mStoredMapping = ControllerHash();
      } else if (action == -2)
        p->StandardMidiMappings();
      else if (action == -4) {
        mControllerStatus = p->ImportControllerProfile(mPendingControllerFile)
            ? "Profile applied / STORE to keep" : "Invalid profile / map unchanged";
        mPendingControllerFile.clear();
      }
      else
        map.Clear();
    }
  } else
    return false;
  return true;
}
} // namespace krose::ui
