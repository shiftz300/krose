# Generate a small APP-only overlay. Keep the hash-verified SDK untouched.
set(_app_original "${IPLUG2_DIR}/IPlug/APP")
set(_app_overlay "${CMAKE_BINARY_DIR}/generated/iplug-app")
file(MAKE_DIRECTORY "${_app_overlay}")
file(GLOB _app_files "${_app_original}/*.cpp" "${_app_original}/*.h")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${_app_files})
foreach(_file IN LISTS _app_files)
  get_filename_component(_name "${_file}" NAME)
  configure_file("${_file}" "${_app_overlay}/${_name}" COPYONLY)
endforeach()

function(_app_replace variable before after)
  string(FIND "${${variable}}" "${before}" _found)
  if(_found LESS 0)
    message(FATAL_ERROR "Pinned iPlug APP source changed: ${before}")
  endif()
  string(REPLACE "${before}" "${after}" _result "${${variable}}")
  set(${variable} "${_result}" PARENT_SCOPE)
endfunction()

file(READ "${_app_original}/IPlugAPP_host.h" _header)
_app_replace(_header "#include <cstdlib>" "#include <cstdlib>\n#include \"standalone/Runtime.h\"")
_app_replace(_header "  bool InitMidi();" "  bool InitMidi();\n  void PollAudio();\n  void PollMidi();")
_app_replace(_header "  bool SelectMIDIDevice(" "  bool SelectMIDIDeviceImpl(ERoute direction, const char* portName);\n  bool SelectMIDIDevice(")
foreach(_flag mExiting mAudioEnding mAudioDone)
  _app_replace(_header "bool ${_flag} = false;" "std::atomic<bool> ${_flag}{false};")
endforeach()
_app_replace(_header "  bool mNoIO = false;" [=[  bool mNoIO = false;
  krose::standalone::Runtime mRuntime;
  std::unique_ptr<Timer> mRecoveryTimer;
  uint32_t mRecoveryOutput = 0;
  bool mFallbackOutput = false;]=])
_app_replace(_header "  bool mFallbackOutput = false;" "  bool mFallbackOutput = false;\n  bool mMidiInputMissing = false;")
file(CONFIGURE OUTPUT "${_app_overlay}/IPlugAPP_host.h" CONTENT "${_header}" @ONLY)

file(READ "${_app_original}/IPlugAPP_host.cpp" _host)
# Preserve F8/Start/Continue/Stop for LCD-selectable external MIDI clock.
_app_replace(_host "ignoreTypes(false, true, false )" "ignoreTypes(false, false, true)")
# Device-free launches should not touch the user's audio/MIDI settings.
_app_replace(_host "if (!InitState())" "if (!mNoIO && !IsScreenshotMode() && !InitState())")
# Manual changes and automatic recovery share selection/fallback logic, so a
# device missing at launch does not overwrite the saved preferred device.
string(FIND "${_host}" "bool IPlugAPPHost::TryToChangeAudio()" _start)
string(FIND "${_host}" "bool IPlugAPPHost::SelectMIDIDevice(" _end)
if(_start LESS 0 OR _end LESS _start)
  message(FATAL_ERROR "Pinned iPlug APP device selection source changed")
endif()
string(SUBSTRING "${_host}" 0 ${_start} _prefix)
string(SUBSTRING "${_host}" ${_end} -1 _suffix)
set(_host "${_prefix}${_suffix}")
_app_replace(_host "bool IPlugAPPHost::SelectMIDIDevice(" "bool IPlugAPPHost::SelectMIDIDeviceImpl(")
# CloseAudio and the three callbacks are implemented by the project adapter.
string(FIND "${_host}" "void IPlugAPPHost::CloseAudio()" _start)
string(FIND "${_host}" "bool IPlugAPPHost::InitAudio(" _end)
if(_start LESS 0 OR _end LESS _start)
  message(FATAL_ERROR "Pinned iPlug APP lifecycle source changed")
endif()
string(SUBSTRING "${_host}" 0 ${_start} _prefix)
string(SUBSTRING "${_host}" ${_end} -1 _suffix)
set(_host "${_prefix}${_suffix}")
string(FIND "${_host}" "// static\nint IPlugAPPHost::AudioCallback(" _start)
if(_start LESS 0)
  message(FATAL_ERROR "Pinned iPlug APP callback source changed")
endif()
string(SUBSTRING "${_host}" 0 ${_start} _host)
string(APPEND _host "#include \"standalone/HostCallbacks.inc\"\n")
_app_replace(_host "  mExiting = true;" [=[  mExiting = true;
  if (mRecoveryTimer) mRecoveryTimer->Stop();
  mRecoveryTimer.reset();
  // Quiesce the producer before Runtime's member storage is destroyed.
  if (mMidiIn) {
    mMidiIn->cancelCallback();
    mMidiIn->closePort();
    mMidiIn.reset();
  }]=])
_app_replace(_host "  mIPlug->OnActivate(true);" [=[  mIPlug->OnActivate(true);
  if (!mNoIO && !IsScreenshotMode())
    mRecoveryTimer.reset(Timer::Create([this](Timer&) { PollMidi(); PollAudio(); }, 250));]=])
_app_replace(_host "  mAudioInputDevIDs.clear();" "  mDefaultInputDev.reset();\n  mDefaultOutputDev.reset();\n  mAudioInputDevIDs.clear();")
_app_replace(_host "void IPlugAPPHost::ProbeMidiIO()\n{" "void IPlugAPPHost::ProbeMidiIO()\n{\n  mMidiInputDevNames.clear();\n  mMidiOutputDevNames.clear();")
_app_replace(_host [=[      mState.mMidiInDev.Set(OFF_TEXT);
      UpdateINI();
      port = 0;]=] [=[      if (mMidiIn) mMidiIn->closePort();
      if (!mMidiInputMissing) mRuntime.CancelMidi();
      mMidiInputMissing = true;
      return false;]=])
_app_replace(_host "    //TODO: send all notes off?\n    if (mMidiIn)" [=[    if (!mMidiInputMissing) mRuntime.CancelMidi();
    mMidiInputMissing = false;
    if (mMidiIn)]=])
_app_replace(_host [=[  mIPlug->SetBlockSize(APP_SIGNAL_VECTOR_SIZE);
  mIPlug->SetSampleRate(mSampleRate);
  mIPlug->OnReset();]=] "")
_app_replace(_host "  for (int i = 0; i < iParams.nChannels; i++)" [=[  // Open first, prepare against the actual driver rate, then start callbacks.
  mSampleRate = mDAC->getStreamSampleRate();
  mIPlug->SetBlockSize(APP_SIGNAL_VECTOR_SIZE);
  mIPlug->SetSampleRate(mSampleRate);
  mIPlug->OnReset();
  mRuntime.Reset();
  mRecoveryOutput = outID;
  mFallbackOutput = false;
  mInputBufPtrs.Empty();
  mOutputBufPtrs.Empty();
  for (int i = 0; i < iParams.nChannels; i++)]=])
file(CONFIGURE OUTPUT "${_app_overlay}/IPlugAPP_host.cpp" CONTENT "${_host}" @ONLY)

file(READ "${_app_original}/IPlugAPP_dialog.cpp" _dialog)
_app_replace(_dialog "void IPlugAPPHost::PopulatePreferencesDialog(HWND hwndDlg)\n{" "void IPlugAPPHost::PopulatePreferencesDialog(HWND hwndDlg)\n{\n  ProbeAudioIO();\n  ProbeMidiIO();")
file(CONFIGURE OUTPUT "${_app_overlay}/IPlugAPP_dialog.cpp" CONTENT "${_dialog}" @ONLY)

file(READ "${_app_original}/IPlugAPP.cpp" _app)
_app_replace(_app "void IPlugAPP::AppProcess(" [=[void IPlugAPP::DispatchTimedMidi(const IMidiMsg& message)
{
  ProcessMidiMsg(message);
  mMidiMsgsFromProcessor.Push(message);
}

void IPlugAPP::AppProcess(]=])
# Maximum scratch allocation remains fixed; actual callback lengths vary.
_app_replace(_app "inputs, GetBlockSize());" "inputs, nFrames);")
_app_replace(_app "outputs, GetBlockSize());" "outputs, nFrames);")
_app_replace(_app "ProcessBuffers(0.0, GetBlockSize());" "ProcessBuffers(0.0, nFrames);")
file(CONFIGURE OUTPUT "${_app_overlay}/IPlugAPP.cpp" CONTENT "${_app}" @ONLY)

file(READ "${_app_original}/IPlugAPP.h" _api_header)
_app_replace(_api_header "  void AppProcess(" "  void DispatchTimedMidi(const IMidiMsg& message);\n  void AppProcess(")
file(CONFIGURE OUTPUT "${_app_overlay}/IPlugAPP.h" CONTENT "${_api_header}" @ONLY)

get_target_property(_app_sources iPlug2::APP INTERFACE_SOURCES)
string(REPLACE "${_app_original}/" "${_app_overlay}/" _app_sources "${_app_sources}")
set_property(TARGET iPlug2::APP PROPERTY INTERFACE_SOURCES "${_app_sources}")
string(REPLACE "${_app_original}/" "${_app_overlay}/" IPLUG2_APP_SRC "${IPLUG2_APP_SRC}")
target_include_directories(iPlug2::APP BEFORE INTERFACE "${_app_overlay}" "${CMAKE_SOURCE_DIR}/src/plugin")
