// Included after the pinned WinMM implementation declares WinMidiData.
void MidiInWinMM :: closePort( void )
{
  if (!connected_) return;
  WinMidiData *data = static_cast<WinMidiData *>(apiData_);
  midiInReset(data->inHandle);
  midiInStop(data->inHandle);
  EnterCriticalSection(&data->_mutex);
  for (int i = 0; i < RT_SYSEX_BUFFER_COUNT; ++i)
    midiInUnprepareHeader(data->inHandle, data->sysexBuffer[i], sizeof(MIDIHDR));
  const auto result = midiInClose(data->inHandle);
  if (result == MMSYSERR_NOERROR || result == MMSYSERR_INVALHANDLE) {
    connected_ = false;
    data->inHandle = 0;
    for (int i = 0; i < RT_SYSEX_BUFFER_COUNT; ++i) {
      delete [] data->sysexBuffer[i]->lpData;
      delete [] reinterpret_cast<char *>(data->sysexBuffer[i]);
      data->sysexBuffer[i] = nullptr;
    }
  }
  LeaveCriticalSection(&data->_mutex);
  if (connected_) {
    errorString_ = "MidiInWinMM::closePort: driver still owns input buffers; retrying.";
    error(RtMidiError::WARNING, errorString_);
  }
}
