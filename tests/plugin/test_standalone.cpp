// Exercise the same callback/recovery implementation compiled into the APP,
// with a deterministic device double. No audio hardware or user settings used.
#include "standalone/Runtime.h"
#include <cassert>
#include <iostream>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <thread>
#include <vector>
#define APP_SIGNAL_VECTOR_SIZE 128
#define APP_MULT 1
#define MAX_SYSEX_SIZE 1024
#define OFF_TEXT "off"
enum class ERoute { kInput, kOutput };
using RtAudioStreamStatus = unsigned;
enum RtAudioErrorType { RTAUDIO_WARNING, RTAUDIO_DEVICE_DISCONNECT };
struct IMidiMsg {
  int mOffset;
  uint8_t mStatus, mData1, mData2;
  IMidiMsg(int o, uint8_t s, uint8_t a, uint8_t b) : mOffset(o), mStatus(s), mData1(a), mData2(b) {}
};
struct SysExData { int offset, size; const uint8_t *data; };
struct Sink { template <class T> void Push(const T &) {} };
struct Pointers {
  std::array<double *, 2> data{};
  void Set(int ch, double *p) { data[ch] = p; }
  double **GetList() { return data.data(); }
};
struct Plug {
  Sink mMidiMsgsFromProcessor, mSysExMsgsFromCallback;
  unsigned rendered = 0, largest = 0, messages = 0;
  int MaxNChannels(ERoute route) { return route == ERoute::kOutput ? 2 : 0; }
  void ProcessMidiMsg(const IMidiMsg &) { ++messages; }
  void DispatchTimedMidi(const IMidiMsg &message) { ProcessMidiMsg(message); }
  void AppProcess(double **, double **out, unsigned count) {
    largest = std::max(largest, count);
    rendered += count;
    for (int ch = 0; ch < 2; ++ch)
      std::fill(out[ch], out[ch] + count, double(ch + 1));
  }
};
struct Name {
  std::string value;
  const char *Get() const { return value.c_str(); }
};
struct Device {
  unsigned id;
  std::string name;
  std::vector<unsigned> sampleRates{44100, 48000};
  unsigned preferredSampleRate = 48000;
};
struct Driver {
  bool running = false, open = false, fail = false;
  unsigned closed = 0, aborted = 0;
  unsigned rejectBuffer = 0, roundBuffer = 0;
  std::vector<Device> devices;
  bool isStreamOpen() { return open; }
  bool isStreamRunning() { return running; }
  void abortStream() { ++aborted; running = false; }
  void closeStream() { ++closed; running = open = false; }
  Device getDeviceInfo(unsigned id) {
    for (const auto &d : devices) if (d.id == id) return d;
    std::abort();
  }
};
struct RtMidiError {};
struct MidiInput {
  bool present = true, open = true, fail = false;
  std::vector<std::string> ports{"Keyboard"};
  unsigned getPortCount() const { return present ? unsigned(ports.size()) : 0; }
  std::string getPortName(unsigned i) const { return ports.at(i); }
  void closePort() { open = false; }
  bool isPortOpen() const { return open; }
};
void Sleep(unsigned ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }
void ApplyFades(double *p, int channels, unsigned frames, bool down) {
  for (int ch = 0; ch < channels; ++ch)
    for (unsigned i = 0; i < frames; ++i)
      p[ch * frames + i] *= down ? double(frames - i - 1) / frames : double(i) / frames;
}
struct IPlugAPPHost {
  static std::unique_ptr<IPlugAPPHost> sInstance;
  std::unique_ptr<Plug> mIPlug = std::make_unique<Plug>();
  std::unique_ptr<Driver> mDAC = std::make_unique<Driver>();
  std::unique_ptr<MidiInput> mMidiIn = std::make_unique<MidiInput>();
  std::unique_ptr<MidiInput> mMidiOut;
  krose::standalone::Runtime mRuntime;
  Pointers mInputBufPtrs, mOutputBufPtrs;
  std::atomic<bool> mExiting{false}, mAudioDone{false}, mAudioEnding{false};
  bool mNoIO = false, mFallbackOutput = false;
  bool mMidiInputMissing = false, mMidiListDirty = false;
  std::string mActiveMidiInput;
  std::vector<std::string> mMidiPorts;
  void ProbeMidiIO() {}
  void RefreshMidiPreferences() {}
  unsigned mVecWait = 1, mRecoveryOutput = 0, starts = 0;
  unsigned mBufferSize = 64, saves = 0;
  void UpdateINI() { ++saves; }
  double mSampleRate = 48000;
  struct { Name mAudioInDev{""}, mAudioOutDev{"USB"}, mMidiInDev{"Keyboard"}; unsigned mAudioSR = 48000, mBufferSize = 64; } mState;
  std::optional<unsigned> mDefaultInputDev, mDefaultOutputDev;
  bool IsScreenshotMode() { return false; }
  int GetMIDIPortNumber(ERoute, const char *name) {
    if (std::string_view(name) == OFF_TEXT) return 0;
    if (!mMidiIn->present) return -1;
    auto at = std::find(mMidiIn->ports.begin(),mMidiIn->ports.end(),name);
    return at == mMidiIn->ports.end() ? -1 : int(at - mMidiIn->ports.begin()) + 1;
  }
  bool SelectMIDIDeviceImpl(ERoute direction, const char *name) {
    if (mMidiIn->fail) throw RtMidiError{};
    const int port = GetMIDIPortNumber(direction,name);
    mMidiIn->open = port > 0;
    mMidiInputMissing = port < 0;
    return port >= 0;
  }
  Plug *GetPlug() { return mIPlug.get(); }
  std::optional<unsigned> GetAudioDeviceID(const char *name) {
    for (const auto &d : mDAC->devices) if (d.name == name) return d.id;
    return {};
  }
  void ProbeAudioIO() {
    mDefaultOutputDev.reset();
    if (!mDAC->devices.empty()) mDefaultOutputDev = mDAC->devices.front().id;
  }
  bool InitAudio(unsigned, unsigned output, unsigned rate, unsigned frames) {
    ++starts;
    if (mDAC->fail || frames == mDAC->rejectBuffer) return false;
    mBufferSize = mDAC->roundBuffer ? mDAC->roundBuffer : frames;
    mDAC->open = mDAC->running = true;
    mSampleRate = rate;
    mRecoveryOutput = output;
    mFallbackOutput = false;
    mAudioDone = mAudioEnding = false;
    mRuntime.Reset();
    return true;
  }
  void CloseAudio();
  void PollAudio();
  void PollMidi();
  bool SelectMIDIDevice(ERoute, const char *);
  bool TryToChangeAudio();
  bool SetAudioBufferSize(unsigned);
  static int AudioCallback(void *, void *, uint32_t, double, RtAudioStreamStatus, void *);
  static void MIDICallback(double, std::vector<uint8_t> *, void *);
  static void ErrorCallback(RtAudioErrorType, const std::string &);
};
std::unique_ptr<IPlugAPPHost> IPlugAPPHost::sInstance;
#include "standalone/HostCallbacks.inc"

int main() {
  IPlugAPPHost buffers;
  buffers.mDAC->devices = {{1, "USB"}};
  assert(buffers.TryToChangeAudio());
  assert(buffers.SetAudioBufferSize(128) && buffers.mBufferSize == 128 && buffers.saves == 1);
  const auto starts = buffers.starts;
  assert(buffers.SetAudioBufferSize(128) && buffers.starts == starts);
  assert(!buffers.SetAudioBufferSize(127) && buffers.starts == starts);
  buffers.mDAC->rejectBuffer = 32;
  assert(!buffers.SetAudioBufferSize(32) && buffers.mDAC->running &&
         buffers.mState.mBufferSize == 128 && buffers.saves == 1);
  buffers.mDAC->roundBuffer = 128;
  assert(buffers.SetAudioBufferSize(96) && buffers.mState.mBufferSize == 128 && buffers.saves == 2);
  buffers.mNoIO = true;
  assert(!buffers.SetAudioBufferSize(256));
  IPlugAPPHost host;
  IPlugAPPHost noMidi;
  noMidi.mMidiIn.reset();
  assert(!noMidi.SelectMIDIDevice(ERoute::kInput, "Unavailable input"));
  assert(!noMidi.SelectMIDIDevice(ERoute::kOutput, "Unavailable output"));
  for (unsigned frames = 1; frames <= 1025; ++frames) {
    std::vector<double> buffer(frames * 2 + 4, 12345);
    host.mIPlug->rendered = 0;
    IPlugAPPHost::AudioCallback(buffer.data() + 2, nullptr, frames, 0, 0, &host);
    assert(buffer[0] == 12345 && buffer[1] == 12345);
    assert(buffer[frames * 2 + 2] == 12345 && buffer[frames * 2 + 3] == 12345);
    assert(host.mIPlug->rendered == frames && host.mIPlug->largest <= 128);
    for (unsigned i = 0; i < frames; ++i) {
      assert(buffer[2 + i] == 1);
      assert(buffer[2 + frames + i] == 2);
    }
  }
  host.mDAC->devices = {{1, "Built-in"}, {2, "USB"}};
  assert(host.TryToChangeAudio());
  assert(host.starts == 1 && host.mRecoveryOutput == 2 && !host.mFallbackOutput);
  IPlugAPPHost initiallyMissing;
  initiallyMissing.mDAC->devices = {{1, "Built-in", {8000, 44100}, 8000}};
  assert(initiallyMissing.TryToChangeAudio());
  assert(initiallyMissing.mFallbackOutput && initiallyMissing.mSampleRate == 44100);
  assert(initiallyMissing.mState.mAudioOutDev.value == "USB");
  host.mMidiIn->present = false;
  host.PollMidi();
  assert(host.mMidiInputMissing && !host.mMidiIn->open);
  assert(host.mState.mMidiInDev.value == "Keyboard");
  host.PollMidi(); // An absent keyboard does not repeatedly panic other input.
  host.mMidiIn->present = true;
  host.mMidiIn->fail = true;
  host.PollMidi();
  assert(host.mMidiInputMissing && !host.mMidiIn->open);
  host.mMidiIn->fail = false;
  host.PollMidi();
  assert(!host.mMidiInputMissing && host.mMidiIn->open);
  IPlugAPPHost automatic;
  automatic.mState.mMidiInDev.value = "Automatic";
  automatic.mMidiIn->ports = {"KeyLab DAW", "KeyLab MIDI"};
  automatic.PollMidi();
  assert(automatic.mActiveMidiInput == "KeyLab MIDI" && automatic.mMidiIn->open);
  automatic.mMidiIn->ports.push_back("M-WAVE MIDI");
  automatic.PollMidi();
  assert(automatic.mActiveMidiInput == "KeyLab MIDI"); // No surprise switch during a performance.
  automatic.mMidiIn->ports = {"M-WAVE MIDI"};
  automatic.PollMidi();assert(automatic.mActiveMidiInput == "M-WAVE MIDI");
  automatic.mState.mMidiInDev.value = "KeyLab MIDI"; // An explicit preference survives fallback.
  automatic.PollMidi();assert(automatic.mActiveMidiInput == "M-WAVE MIDI");
  automatic.mMidiIn->ports.push_back("KeyLab MIDI");
  automatic.PollMidi();assert(automatic.mActiveMidiInput == "KeyLab MIDI");
  automatic.mState.mMidiInDev.value = "off";
  automatic.PollMidi();assert(!automatic.mMidiIn->open && automatic.mActiveMidiInput.empty());
  automatic.mState.mMidiInDev.value = "Automatic";
  automatic.PollMidi();assert(automatic.mMidiIn->open);
  automatic.mMidiIn->present = false;
  automatic.PollMidi();assert(!automatic.mMidiIn->open);
  automatic.mMidiIn->present = true;
  automatic.PollMidi();assert(automatic.mMidiIn->open);
  // Removal, no devices, retry failure, fallback at a different rate, reconnect.
  host.mDAC->devices.clear(); host.mDAC->running = host.mDAC->open = false;
  host.PollAudio(); assert(host.starts == 1 && !host.mDefaultOutputDev);
  host.mDAC->devices = {{1, "Built-in", {44100}, 44100}};
  host.mDAC->fail = true;
  host.PollAudio(); assert(!host.mDAC->running);
  host.mDAC->fail = false;
  host.PollAudio();
  assert(host.mFallbackOutput && host.mRecoveryOutput == 1 && host.mSampleRate == 44100);
  assert(host.mState.mAudioOutDev.value == "USB" && host.mState.mAudioSR == 48000);
  host.mAudioDone = true;
  host.mDAC->devices.push_back({2, "USB"});
  host.PollAudio(); assert(host.mRecoveryOutput == 2 && !host.mFallbackOutput);
  // Driver errors publish only a flag; warning messages do not restart audio.
  IPlugAPPHost::sInstance = std::make_unique<IPlugAPPHost>();
  auto &flagHost = *IPlugAPPHost::sInstance;
  flagHost.mRuntime.Reset();
  IPlugAPPHost::ErrorCallback(RTAUDIO_WARNING, "warning");
  assert(!flagHost.mRuntime.NeedsRecovery(krose::standalone::Runtime::Now(), true));
  IPlugAPPHost::ErrorCallback(RTAUDIO_DEVICE_DISCONNECT, "removed");
  assert(flagHost.mRuntime.NeedsRecovery(krose::standalone::Runtime::Now(), true));
  IPlugAPPHost::sInstance.reset();
  // A dead callback cannot hang application shutdown indefinitely.
  const double start = krose::standalone::Runtime::Now();
  host.mAudioDone = false;
  host.CloseAudio();
  assert(krose::standalone::Runtime::Now() - start < .5 && !host.mDAC->open);
  std::cout << "PASS standalone guarded blocks 1..1025, recovery/retry/rate fallback/reconnect and bounded close\n";
}
