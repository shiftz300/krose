#pragma once
#include "../midi/KeyLabEssential.h"
#include "RtMidi.h"
#include <chrono>
#include <memory>

namespace krose::standalone {
// A dedicated feedback output, independent of the user's MIDI output. Controls
// arrive through the existing musical input, including on single-client Windows
// drivers. No second input handle competes with the standalone host.
class ArturiaController {
public:
  ~ArturiaController() { Disconnect(); }
  midi::essential::Feedback feedback;
  std::string status = "ARTURIA: WAITING FOR KEYLAB";
  bool Poll(bool enabled, double now) {
    if (!enabled) { Disconnect(); status = "ARTURIA: OFF"; return false; }
    try {
      if (now >= mProbe) {
        mProbe = now + 1;
        if (!mOut) mOut = std::make_unique<RtMidiOut>();
        std::vector<std::string> outputs;
        for (unsigned i = 0; i < mOut->getPortCount(); ++i) outputs.push_back(mOut->getPortName(i));
        int out = midi::essential::FindPort(outputs);
        const std::string output = out < 0 ? "" : outputs[out];
        if (mOutput != output) {
          Disconnect();
          if (out >= 0) {
            mOut->openPort(unsigned(out), "Krose KeyLab Feedback");
            mOutput = output;
            Send(midi::essential::Command({2, 15, 64, 90, 1}));
            feedback.Reset();
          }
        }
        status = mOutput.empty() ? "ARTURIA: WAITING FOR KEYLAB MK3" : "ARTURIA: KEYLAB MK3 CONNECTED";
      }
      return !mOutput.empty();
    } catch (const RtMidiError &) {
      Disconnect(); status = "ARTURIA: PORT BUSY / RETRYING"; return false;
    }
  }
  void Send(const midi::essential::Packet &bytes) {
    if (mOut && mOut->isPortOpen() && !bytes.empty()) mOut->sendMessage(&bytes);
  }
  void Update(double now, const std::array<bool, 8> &pads) {
    try { feedback.Tick(now, pads, [this](const auto &bytes) { Send(bytes); }); }
    catch (const RtMidiError &) { Disconnect(); status = "ARTURIA: PORT BUSY / RETRYING"; }
  }
private:
  void Disconnect() noexcept {
    try {
      if (mOut && mOut->isPortOpen()) {
        for (unsigned i = 0; i < 8; ++i) Send(midi::essential::Pad(i, false));
        for (unsigned i = 0; i < 4; ++i) Send(midi::essential::FxButton(i, {0,0,0}));
        Send(midi::essential::Command({2, 15, 64, 90, 0}));
      }
    } catch (...) {} // Destruction/unplug must not escape into the host.
    try { if (mOut && mOut->isPortOpen()) mOut->closePort(); } catch (...) {}
    mOutput.clear(); feedback.Reset();
  }
  std::unique_ptr<RtMidiOut> mOut;
  std::string mOutput;
  double mProbe = 0;
};
} // namespace krose::standalone
