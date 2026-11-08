#pragma once
#include <algorithm>
#include <array>
#include <cctype>
#include <string>
#include <string_view>
#include <vector>
#include <utility>
#include <cmath>

namespace krose::midi::essential {
// Essential mk3 only. Reject legacy Essential and full KeyLab models: their
// ports/protocols differ. Encoding and transport run on the UI thread.
using Packet = std::vector<unsigned char>;
using RGB = std::array<unsigned char,3>;
inline Packet Command(std::initializer_list<unsigned char> data) {
  Packet bytes{0xf0, 0, 0x20, 0x6b, 0x7f, 0x42};
  bytes.insert(bytes.end(), data);
  bytes.push_back(0xf7);
  return bytes;
}
inline std::string Ascii(std::string_view value) {
  std::string text;
  for (unsigned char ch : value) {
    if (ch >= 32 && ch < 127) text.push_back(char(ch));
    else if (ch < 0x80 || ch >= 0xc0) text.push_back('?');
  }
  return text;
}
inline std::string Line(std::string_view value) {
  auto text = Ascii(value);
  text.resize(18, ' ');
  return text;
}
inline Packet Display(std::string_view first, std::string_view second) {
  Packet bytes{0xf0, 0, 0x20, 0x6b, 0x7f, 0x42, 4, 1, 0x60, 0x12, 1};
  auto a = Line(first), b = Line(second);
  bytes.insert(bytes.end(), a.begin(), a.end());
  bytes.insert(bytes.end(), {0, 2});
  bytes.insert(bytes.end(), b.begin(), b.end());
  bytes.insert(bytes.end(), {0, 0, 0xf7});
  return bytes;
}
inline Packet DisplayHeader(std::string_view title) {
  auto bytes = Command({4, 1, 0x60, 1, 2});
  bytes.pop_back();
  const auto text = Ascii(title).substr(0, 14);
  bytes.insert(bytes.end(), text.begin(), text.end());
  bytes.insert(bytes.end(), {0, 0, 0xf7});
  return bytes;
}
inline unsigned CategoryIcon(std::string_view category) {
  if (category == "PIANO") return 0x28;
  if (category == "E.PIANO") return 0x0d;
  if (category == "ORGAN") return 0x1f;
  if (category == "BASS") return 0x03;
  if (category == "STRINGS") return 0x31;
  if (category == "BRASS") return 0x05;
  if (category == "SYNTH LEAD") return 0x1a;
  if (category == "SYNTH PAD") return 0x21;
  if (category == "DRUM/SFX") return 0x0b;
  return 0x18;
}
inline std::string ParameterLabel(std::string_view name) {
  if (name == "Output") return "Volume";
  std::string label = Ascii(name);
  for (const auto &pair : {std::pair{"IFX ", "IFX"}, {"MFX ", "MFX"}, {"Filter ", "Flt "},
       {"Resonance", "Reso"}, {"Sustain", "Sust"}, {"Release", "Rel"}, {"Attack", "Atk"}}) {
    const auto pos = label.find(pair.first);
    if (pos != std::string::npos) label.replace(pos, std::string_view(pair.first).size(), pair.second);
  }
  return label.substr(0,12);
}
inline std::string ProgramLine(std::string_view name, double elapsed) {
  const auto text = Ascii(name);
  if (text.size() <= 12) return text;
  constexpr double pause = 1.2, step = .35;
  const size_t travel = text.size() - 12;
  const double phase = std::fmod(std::max(0., elapsed), 2*pause + travel*step);
  const size_t offset = phase <= pause ? 0 :
      std::min(travel, size_t((phase-pause)/step));
  return text.substr(offset,12);
}
inline Packet DisplayIcon(std::string_view first, std::string_view second, unsigned icon) {
  auto bytes = Command({4,1,96,0x19,1});
  bytes.pop_back();
  const auto a = Ascii(first).substr(0,12), b = Ascii(second).substr(0,18);
  bytes.insert(bytes.end(), a.begin(), a.end());
  bytes.insert(bytes.end(), {0,2});
  bytes.insert(bytes.end(), b.begin(), b.end());
  bytes.insert(bytes.end(), {0,3,static_cast<unsigned char>(icon <= 0x4b ? icon : 0),0,0,0xf7});
  return bytes;
}
// Firmware-owned encoder/fader popup text. This command updates its text
// cache only; it never writes an encoder position or switches programs.
inline Packet ControlDisplay(unsigned index, std::string_view name, std::string_view value) {
  if (index >= 18) return {};
  const unsigned cc = index < 8 ? 96 + index : index < 16 ? 105 + index - 8 : index == 16 ? 104 : 113;
  auto bytes = Command({4,1,96,32,static_cast<unsigned char>(index),32,1});
  bytes.pop_back();
  const auto a = Ascii(name).substr(0,11), b = Ascii(value).substr(0,18);
  bytes.insert(bytes.end(), a.begin(), a.end());
  bytes.insert(bytes.end(), {0,2});
  bytes.insert(bytes.end(), b.begin(), b.end());
  bytes.insert(bytes.end(), {0,3,static_cast<unsigned char>(cc),0,0xf7});
  return bytes;
}
inline std::string ParameterPage(std::string_view name) {
  if (name.substr(0, 4) == "IFX " || name.substr(0, 4) == "MFX ")
    return "FX / " + std::string(name.substr(0, 5));
  if (name.substr(0, 3) == "Arp") return "ARP";
  if (name.substr(0, 4) == "Amp ") return "TONE / AMP EG";
  if (name.substr(0, 7) == "Filter ") return "TONE / FILTER EG";
  if (name.substr(0, 2) == "SW" || name.substr(0, 4) == "MIDI") return "CTRL";
  if (name == "FX Bypass" || name == "Space") return "FX";
  return "TONE";
}
inline Packet Pad(unsigned index, bool active) {
  if (index >= 8) return {};
  // Dim unlit pads remain off; active controls use a restrained cyan/white.
  return Command({4, 1, 0x16, static_cast<unsigned char>(0x1c + (index ^ 4u)),
                  static_cast<unsigned char>(active ? 48 : 0),
                  static_cast<unsigned char>(active ? 90 : 0),
                  static_cast<unsigned char>(active ? 90 : 0), 32});
}
inline RGB EffectColour(unsigned algorithm, bool enabled = true) {
  static constexpr std::array<RGB,15> colours{{
    {0,0,0},{0,0,0},{32,80,127},{127,78,24},{127,104,24},
    {127,38,20},{127,28,62},{24,110,127},{99,44,127},{50,127,74},
    {24,127,114},{48,80,127},{30,127,110},{102,64,127},{127,64,112}}};
  return enabled && algorithm < colours.size() ? colours[algorithm] : RGB{0,0,0};
}
inline Packet FxButton(unsigned index, RGB colour) {
  if (index >= 4) return {};
  return Command({4,1,22,static_cast<unsigned char>(24+index),
                  static_cast<unsigned char>(std::min(127,int(colour[0]))),
                  static_cast<unsigned char>(std::min(127,int(colour[1]))),
                  static_cast<unsigned char>(std::min(127,int(colour[2]))),32});
}
inline int Relative(unsigned value) {
  return value < 128 ? int(value) - 64 : 0; // Display encoder: binary offset.
}
inline int PortScore(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return char(std::tolower(c)); });
  std::string compact;
  for (unsigned char c : value) if (std::isalnum(c)) compact.push_back(char(c));
  if ((compact.find("keylabessential") == std::string::npos && compact.find("klessential") == std::string::npos) ||
      compact.find("mk3") == std::string::npos || value.find("alv") != std::string::npos ||
      value.find("mcu") != std::string::npos || value.find("hui") != std::string::npos ||
      value.find("din") != std::string::npos) return 0;
  for (const char *port : {"midiin2", "midiin3", "midiin4", "midiout2", "midiout3", "midiout4"})
    if (compact.find(port) != std::string::npos) return 0;
  return 2;
}
// Refuse ambiguous connections rather than lighting another keyboard.
inline int FindPort(const std::vector<std::string> &names, bool dawOnly = false) {
  int best = -1, score = dawOnly ? 1 : 0;
  bool ambiguous = false;
  for (unsigned i = 0; i < names.size(); ++i) {
    const int candidate = PortScore(names[i]);
    if (candidate > score) { best = int(i); score = candidate; ambiguous = false; }
    else if (candidate && candidate == score) ambiguous = true;
  }
  return ambiguous ? -1 : best;
}
class Feedback {
public:
  void Reset() {
    mLastDisplay.clear(); mLastHeader.clear(); mLastPads.fill(-1);
    for (auto &packet : mLastControls) packet.clear();
    mLastFxColours.fill(RGB{255,255,255});
    mNext = 0; mProgramStarted = -1; mControlUntil = 0; mRestoreDisplay = false;
  }
  void Control(unsigned index, std::string_view name, std::string_view value) {
    if (index < mControls.size()) mControls[index] = ControlDisplay(index, name, value);
  }
  void ControlTouched(double now) { mControlUntil = now + 1.2; mRestoreDisplay = true; }
  void FxButtons(const std::array<RGB,4> &colours) { mFxColours = colours; mFxConfigured = true; }
  void Program(std::string_view value, std::string_view context = "PROG", unsigned icon = 0x28) {
    mProgram = Ascii(value); mContext = Ascii(context); mIcon = icon; mUntil = 0; mProgramStarted = -1;
  }
  void Parameter(std::string_view name, std::string_view value, double now) {
    mName = Ascii(name); mValue = Ascii(value); mUntil = now + 1.2; mProgramStarted = -1;
  }
  template <class Send> void Tick(double now, const std::array<bool, 8> &pads, Send send) {
    if (now < mNext) return;
    mNext = now + .1; // Coalesce fast automation; never flood the MIDI cable.
    for (unsigned i = 0; i < mControls.size(); ++i)
      if (!mControls[i].empty() && mControls[i] != mLastControls[i]) {
        send(mControls[i]); mLastControls[i] = mControls[i];
      }
    // A physical turn opens a firmware popup using the control text cache.
    // Recreating the whole screen on each value fights that popup. Let it
    // finish, then restore our main screen even if its bytes are unchanged.
    if (now >= mControlUntil) {
      if (mRestoreDisplay) { mLastDisplay.clear(); mLastHeader.clear(); mRestoreDisplay = false; }
      const bool parameter = now < mUntil;
      if (!parameter && mProgramStarted < 0) mProgramStarted = now;
      auto first = parameter ? ParameterLabel(mName) : ProgramLine(mProgram, now-mProgramStarted);
      // The scrolling viewport occupies one line only; the next row stays clear.
      auto second = parameter ? mValue : std::string{};
      auto header = DisplayHeader(parameter ? ParameterPage(mName) : mContext);
      const unsigned icon = parameter ? (ParameterPage(mName) == "ARP" ? 0x2d :
          ParameterPage(mName).substr(0,2) == "FX" ? 0x2f : 9) : mIcon;
      auto display = DisplayIcon(first, second, icon);
      const bool redraw = display != mLastDisplay;
      if (redraw) { send(display); mLastDisplay = std::move(display); }
      // Creating a new screen resets its decorations in the keyboard firmware.
      // Body first, then its header; resend after every changed body.
      if (redraw || header != mLastHeader) { send(header); mLastHeader = std::move(header); }
    }
    for (unsigned i = 0; i < pads.size(); ++i)
      if (mLastPads[i] != int(pads[i])) { send(Pad(i, pads[i])); mLastPads[i] = pads[i]; }
    if (mFxConfigured) for (unsigned i=0;i<4;++i)
      if (mFxColours[i] != mLastFxColours[i]) { send(FxButton(i,mFxColours[i])); mLastFxColours[i] = mFxColours[i]; }
  }
private:
  std::string mProgram = "Krose", mContext = "PROG", mName, mValue;
  Packet mLastDisplay, mLastHeader;
  std::array<Packet, 18> mControls{}, mLastControls{};
  std::array<RGB,4> mFxColours{}, mLastFxColours{{RGB{255,255,255},RGB{255,255,255},RGB{255,255,255},RGB{255,255,255}}};
  bool mFxConfigured = false;
  unsigned mIcon = 0x28;
  std::array<int, 8> mLastPads{{-1,-1,-1,-1,-1,-1,-1,-1}};
  double mUntil = 0, mNext = 0;
  double mProgramStarted = -1;
  double mControlUntil = 0;
  bool mRestoreDisplay = false;
};
} // namespace krose::midi::essential
