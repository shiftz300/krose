#include "../../KrosePlugin.h"
#include "NativePanel.h"
#include "PanelDrawing.h"
namespace krose::ui {
using namespace detail;
using namespace krose::midi;
namespace {
const char *sources[] = {"OFF",  "CC",   "CC 14 BIT", "NRPN",      "RPN",
                         "NOTE", "BEND", "PRESSURE",  "POLY PRESS"};
const char *modes[] = {"ABSOLUTE",     "REL 2'S COMP", "REL OFFSET 64",
                       "REL SIGN MAG", "TOGGLE",       "MOMENTARY"};
const int config[] = {kSW1Assign,    kSW1Mode,       kSW2Assign,  kSW2Mode,
                      kInputChannel, kProgramChange, kClockSource};
std::string Target(KrosePlugin *p, unsigned id) {
  if (id < kNumMidiParameters)
    return p->GetParam(id)->GetName();
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
  const bool choice = action == "field" || action == "midi-menu";
  if (choice)
    LCDChevron(g, r, selected ? Paper : Ink);
  g.PathClipRegion(R(r.L + 3, r.T + 3, r.W() - (choice ? 25 : 6), r.H() - 6));
  Text(g, selected ? "light14" : "lcd14", text,
       R(r.L + 7, r.T + 2.25f, r.W() - (choice ? 32 : 14), r.H() - 2.25f), 1);
  g.PathClipRegion(R(424, 108, 556, 176));
  HitBox(r, action, id, value);
}
void NativePanel::Controllers(IGraphics &g) {
  auto *p = static_cast<KrosePlugin *>(GetDelegate());
  auto &map = p->MidiMappings();
  const auto binding = map.Get(mMapSlot);
  g.FillRect(Paper, R(431, 115, 542, 169));
  // Connected tabs use the same 45-degree, pixel-stepped shoulders as the program pages.
  ControllerCell(g, "< PROG", R(433, 115, 111, 23), "controller-close");
  const char *tabs[] = {"CTRL", "MIDI", "INPUT", "HELP"};
  for (int i = 0; i < 4; ++i) {
    float x = 548 + i * 106;
    bool active = i == mControllerPage;
    for (int row = 0; row < 9; ++row) {
      float inset = (8 - row) * 2.25f;
      g.FillRect(active ? Ink : Paper,
                 LCDRect(R(x + inset, 117 + row * 2.25f, 106 - 2 * inset, 2.25f)));
    }
    g.FillRect(Ink, LCDRect(R(x, 136, 106, 2.25f)));
    Text(g, active ? "light14" : "lcd14", tabs[i], R(x + 15, 119, 76, 17), 1);
    HitBox(R(x, 115, 106, 23), "controller-page", -1, i);
  }
  if (mConfirmProfile != -1) {
    Text(g, "lcd16",
         mConfirmProfile >= 0 ? "Discard unsaved map changes?" : "Replace all MIDI mappings?",
         R(441, 159, 520, 27), 1);
    Text(g, "lcd14", "Project state remains available in your DAW.", R(441, 191, 520, 24), 1);
    ControllerCell(g, "CANCEL", R(470, 235, 180, 28), "controller-confirm", -1, 0);
    ControllerCell(g, "CONTINUE", R(748, 235, 180, 28), "controller-confirm", -1, 1);
    return;
  }
  if (mControllerPage == 0) {
    for (int sw = 0; sw < 2; ++sw) {
      int id = kSW1Assign + sw * 3;
      float y = 146 + sw * 39;
      Text(g, "lcd14", sw ? "SW2" : "SW1", R(438, y + 3, 39, 24));
      const auto *a = p->GetParam(id), *b = p->GetParam(id + 1);
      ControllerCell(g, a->GetDisplayText(a->Int()), R(482, y, 237, 28), "field", id);
      ControllerCell(g, b->GetDisplayText(b->Int()), R(729, y, 144, 28), "field", id + 1);
      ControllerCell(g, Value(id + 2) ? "ON" : "TEST", R(882, y, 81, 28), "switch", sw, 0,
                     Value(id + 2) > 0);
    }
    ControllerCell(g, Value(kFXBypass) ? "FX BYPASS: ON" : "FX BYPASS: OFF", R(438, 226, 248, 27),
                   "toggle", kFXBypass);
    ControllerCell(g, "MAP SW1", R(698, 226, 126, 27), "controller-learn", kSW1State);
    ControllerCell(g, "MAP SW2", R(836, 226, 126, 27), "controller-learn", kSW2State);
    Text(g, "lcd13", "Mod CC: SW1=80 / SW2=81. Right-click a control to learn.",
         R(438, 262, 531, 19));
  } else if (mControllerPage == 1) {
    ControllerCell(g, "#" + std::to_string(mMapSlot + 1), R(438, 144, 61, 26), "midi-menu", 0);
    ControllerCell(g, Target(p, binding.target), R(509, 144, 453, 26), "midi-menu", 1);
    ControllerCell(g, sources[unsigned(binding.source)], R(438, 178, 149, 26), "midi-menu", 2);
    ControllerCell(
        g, mMapEdit >= 0 ? mEditText : "NO. " + std::to_string(binding.number),
        R(597, 178, 156, 26),
        (binding.source == Source::Bend || binding.source == Source::Pressure) ? "" : "map-number");
    ControllerCell(g, binding.channel ? "CH " + std::to_string(binding.channel) : "OMNI",
                   R(763, 178, 199, 26), "midi-menu", 3);
    ControllerCell(g, modes[unsigned(binding.mode)], R(438, 212, 228, 26), "midi-menu", 4);
    ControllerCell(g, "PICKUP", R(676, 212, 95, 26),
                   binding.mode == Mode::Absolute ? "map-flag" : "", 0, 0,
                   binding.pickup && binding.mode == Mode::Absolute);
    ControllerCell(g, "THRU", R(781, 212, 83, 26), "map-flag", 1, 0, !binding.consume);
    ControllerCell(g, "INVERT", R(874, 212, 88, 26), "map-flag", 2, 0, binding.invert);
    ControllerCell(g, map.Learning() >= 0 ? "CANCEL" : "LEARN", R(438, 246, 137, 26), "map-learn",
                   -1, 0, map.Learning() >= 0);
    ControllerCell(g, "CLEAR", R(585, 246, 115, 26), "map-clear");
    std::string status = map.Learning() >= 0 ? "Move ONE controller..." : mControllerStatus;
    if (status.empty())
      status = binding.source == Source::Off ? "Empty slot" : "Ready / right-click to learn";
    Text(g, "lcd13", status, R(711, 249, 257, 22));
  } else if (mControllerPage == 2) {
    ControllerCell(g,
                   "USER " + std::to_string(p->MidiProfile() + 1) +
                       (ControllerHash() != mStoredMapping ? " *" : ""),
                   R(438, 144, 173, 27), "midi-menu", 5);
    ControllerCell(g, "STORE", R(622, 144, 101, 27), "map-store");
    ControllerCell(g,
                   Value(kInputChannel) ? "INPUT CH " + Format(Value(kInputChannel)) : "INPUT OMNI",
                   R(734, 144, 228, 27), "field", kInputChannel);
    auto enumText = [&](int id) {
      auto *v = p->GetParam(id);
      return std::string(v->GetDisplayText(v->Int()));
    };
    ControllerCell(g, "CLOCK: " + enumText(kClockSource), R(438, 181, 253, 27), "field",
                   kClockSource);
#if defined(APP_API)
    ControllerCell(g, "PGM: " + enumText(kProgramChange), R(702, 181, 260, 27), "field",
                   kProgramChange);
#else
    ControllerCell(g, "PGM: HOST / DAW", R(702, 181, 260, 27), "controller-pgm-info");
#endif
    ControllerCell(g, "STANDARD CC", R(438, 220, 166, 27), "map-standard");
    ControllerCell(g, "CLEAR MAP", R(615, 220, 157, 27), "map-clear-all");
    ControllerCell(g, "PANIC", R(783, 220, 179, 27), "panic");
    Text(g, "lcd13",
         p->MidiSettingsError() ? "SAVE FAILED - check settings file permissions"
         : mControllerStatus.empty()
             ? "STORE saves this map for other projects. DAW saves its own copy."
             : mControllerStatus,
         R(438, 259, 531, 20));
  } else {
    uint32_t rx = map.LastMessage();
    unsigned s = rx & 255, a = (rx >> 8) & 127, b = (rx >> 16) & 127;
    char line[96];
    std::snprintf(line, sizeof(line), "RX %02X  %03u  %03u / CH %u", s, a, b, (s & 15) + 1);
    Text(g, "lcd14", rx ? line : "RX: waiting for MIDI input", R(438, 147, 530, 23));
    const char *lines[] = {"Right-click a knob, fader or switch to learn.",
                           "Learn captures first message without changing sound.",
                           "Relative modes follow the keyboard's encoder setting.",
                           "Chord / scale / arp notes work as normal MIDI notes.",
                           "DAW / MCU / HUI and vendor screens belong to the host."};
    for (int i = 0; i < 5; ++i)
      Text(g, "lcd13", lines[i], R(438, 175 + 20 * i, 530, 19));
  }
}
void NativePanel::ControllerMenu(const Hit &h) {
  auto *p = static_cast<KrosePlugin *>(GetDelegate());
  auto b = p->MidiMappings().Get(mMapSlot);
  mPopupTarget = h;
  mChoices.clear();
  mChoiceValues.clear();
  mPopupFocus = 0;
  auto add = [&](std::string s, int v) {
    mChoices.push_back(std::move(s));
    mChoiceValues.push_back(v);
  };
  if (h.id == 0) {
    for (unsigned i = 0; i < ControllerMap::kSlots; ++i) {
      auto n = p->MidiMappings().Get(i);
      add(std::to_string(i + 1) + (n.source == Source::Off ? " -" : " *"), i);
    }
    mPopupFocus = mMapSlot;
  }
  if (h.id == 1) {
    for (unsigned i = 0; i < KrosePlugin::kMapTargets; ++i)
      add(Target(p, i), i);
    mPopupFocus = b.target;
  }
  if (h.id == 2) {
    for (int i = 0; i < 9; ++i)
      add(sources[i], i);
    mPopupFocus = int(b.source);
  }
  if (h.id == 3) {
    add("OMNI", 0);
    for (int i = 1; i <= 16; ++i)
      add("CH " + std::to_string(i), i);
    mPopupFocus = b.channel;
  }
  if (h.id == 4) {
    for (int i = 0; i < 6; ++i)
      add(modes[i], i);
    mPopupFocus = int(b.mode);
  }
  if (h.id == 5) {
    for (int i = 0; i < 4; ++i)
      add("USER " + std::to_string(i + 1), i);
    mPopupFocus = p->MidiProfile();
  }
  const float room = std::max(284 - h.r.B - 2, h.r.T - 140 - 2);
  mPopupRows = std::min(int(mChoices.size()), std::max(1, int(room / 22)));
  mPopupScroll =
      std::clamp(mPopupFocus - mPopupRows / 2, 0, std::max(0, int(mChoices.size()) - mPopupRows));
}
void NativePanel::ControllerChoice(int id, int value) {
  auto *p = static_cast<KrosePlugin *>(GetDelegate());
  auto &map = p->MidiMappings();
  auto b = map.Get(mMapSlot);
  map.CancelLearn();
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
void NativePanel::BeginLearn(int target) {
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
  mControllerPage = 1;
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
    b.mode = (target >= kNumMidiParameters || p->GetParam(target)->Type() == IParam::kTypeBool)
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
    mControllerPage = 0;
    mControllerStatus.clear();
  } else if (h.action == "controller-close") {
    mControllers = false;
    map.CancelLearn();
    mMapEdit = -1;
    mConfirmProfile = -1;
  } else if (h.action == "controller-page") {
    mControllerPage = int(h.value);
    if (mControllerPage != 1)
      map.CancelLearn();
    mConfirmProfile = -1;
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
      else
        map.Clear();
    }
  } else
    return false;
  return true;
}
} // namespace krose::ui
