// Exercise the exact RtMidi cleanup fragment without requiring Windows hardware.
#include <cassert>
#include <string>
struct MIDIHDR { char *lpData; };
constexpr int RT_SYSEX_BUFFER_COUNT=4, MMSYSERR_NOERROR=0, MMSYSERR_INVALHANDLE=5;
struct WinMidiData { int inHandle=1; MIDIHDR *sysexBuffer[4]{}; bool _mutex=false; };
WinMidiData *active;
int closeResult=0, unprepareResult=0, resets=0;
void midiInReset(int) { assert(!active->_mutex); ++resets; }
void midiInStop(int) { assert(!active->_mutex); }
void EnterCriticalSection(bool *lock) { assert(!*lock); *lock=true; }
void LeaveCriticalSection(bool *lock) { assert(*lock); *lock=false; }
int midiInUnprepareHeader(int, MIDIHDR *, unsigned long) { return unprepareResult; }
int midiInClose(int) { return closeResult; }
struct RtMidiError { static constexpr int WARNING=0; };
struct MidiInWinMM {
  bool connected_=true;
  void *apiData_;
  std::string errorString_;
  unsigned warnings=0;
  void error(int kind,const std::string&) { assert(kind==RtMidiError::WARNING); ++warnings; }
  void closePort();
};
#include "standalone/WinMidiClose.inc"
int main() {
  for (int result : {MMSYSERR_NOERROR,MMSYSERR_INVALHANDLE,33}) {
    WinMidiData data; active=&data;
    for(auto &p:data.sysexBuffer) { p=reinterpret_cast<MIDIHDR *>(new char[sizeof(MIDIHDR)]); p->lpData=new char[1024]; }
    MidiInWinMM input; input.apiData_=&data;
    unprepareResult=33; closeResult=result;
    input.closePort();
    assert(!data._mutex);
    if (result==33) {
      assert(input.connected_ && input.warnings==1);
      for(auto p:data.sysexBuffer) assert(p && p->lpData);
      closeResult=MMSYSERR_NOERROR;
      input.closePort();
    }
    assert(!input.connected_ && data.inHandle==0);
    for(auto p:data.sysexBuffer) assert(p==nullptr);
    int before=resets; input.closePort(); assert(resets==before);
  }
}
