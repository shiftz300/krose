#!/usr/bin/env python3
"""Build a patched dependency view; never modify the hash-verified originals."""
import argparse
import os
from pathlib import Path
import stat
import tempfile


def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("Pinned dependency changed near: " + old[:100])
    return text.replace(old, new)


def patch(path, text):
    if path == "Dependencies/IPlug/RTAudio/RtAudio.cpp":
        # ASIO reset/rate-change callbacks must never launch a second owner
        # closing the driver's buffers concurrently with a settings restart.
        text = replace(text, "static void sampleRateChanged( ASIOSampleRate sRate );",
                       'extern "C" void KroseRequestAsioRecovery(void*);\nstatic void sampleRateChanged( ASIOSampleRate sRate );')
        old = """    unsigned threadId;
    asioCallbackInfo->thread = _beginthreadex( NULL, 0, &asioStopStream,
                                               asioCallbackInfo, 0, &threadId );"""
        text = replace(text, old, "    KroseRequestAsioRecovery(asioCallbackInfo->userData);", count=2)
        # The legacy WASAPI worker can wait forever for an endpoint event after
        # unplug. Keep waiting event-driven, but let stop/recovery join the thread.
        for event in ("loopbackEnabled ? renderEvent : captureEvent", "renderEvent"):
            old = "WaitForSingleObject( " + event + ", INFINITE );"
            new = """const DWORD waitResult = WaitForSingleObject( """ + event + """, 100 );
        if (stream_.state == STREAM_STOPPING) break;
        if (waitResult == WAIT_TIMEOUT) continue;
        if (waitResult != WAIT_OBJECT_0) {
          errorText = "RtApiWasapi::wasapiThread: endpoint event unavailable.";
          goto Exit;
        }"""
            text = replace(text, old, new)
        text = replace(text, "  unsigned int nDevices = dataSize / sizeof( AudioDeviceID );", """  if (dataSize % sizeof(AudioDeviceID)) {
    errorText_ = "RtApiCore::probeDevices: invalid device list size.";
    error(RTAUDIO_SYSTEM_ERROR);
    return;
  }
  unsigned int nDevices = dataSize / sizeof( AudioDeviceID );""")
        text = replace(text, "AudioDeviceID ids[ nDevices ];", "std::vector<AudioDeviceID> ids( nDevices );")
        text = replace(text, "(void *) &ids", "ids.data()")
        at = text.index("  // Fill or update the deviceList_", text.index("void RtApiCore :: probeDevices"))
        text = text[:at] + "  nDevices = std::min(nDevices, static_cast<unsigned int>(dataSize / sizeof(AudioDeviceID)));\n\n" + text[at:]
        text = replace(text, "  UInt32 nRanges = dataSize / sizeof( AudioValueRange );", """  if (dataSize % sizeof(AudioValueRange)) {
    errorText_ = "RtApiCore::probeDeviceInfo: invalid sample rate list size.";
    error(RTAUDIO_WARNING);
    return false;
  }
  UInt32 nRanges = dataSize / sizeof( AudioValueRange );""")
        text = replace(text, "AudioValueRange rangeList[ nRanges ];", "std::vector<AudioValueRange> rangeList( nRanges );")
        text = replace(text, "&dataSize, &rangeList", "&dataSize, rangeList.data()")
        text = replace(text, "  // The sample rate reporting mechanism", "  nRanges = std::min(nRanges, static_cast<UInt32>(dataSize / sizeof(AudioValueRange)));\n\n  // The sample rate reporting mechanism")
    elif path == "Dependencies/IPlug/RTMidi/RtMidi.cpp":
        text = replace(text, '#include "RtMidi.h"', '#include "RtMidi.h"\n#include <algorithm>\n#include <limits>')
        # WinMM reset synchronously returns queued SysEx buffers via callbacks.
        # Do not hold the callback mutex during reset, and never throw halfway
        # through freeing headers: reconnect/destruction may call close again.
        start = text.index("void MidiInWinMM :: closePort( void )")
        end = text.index("void MidiInWinMM :: setClientName", start)
        text = text[:start] + '#include "standalone/WinMidiClose.inc"\n\n' + text[end:]
        text = replace(text, "unsigned int nSrc = MIDIGetNumberOfSources();", "ItemCount nSrc = MIDIGetNumberOfSources();")
        text = replace(text, "unsigned int nDest = MIDIGetNumberOfDestinations();", "ItemCount nDest = MIDIGetNumberOfDestinations();")
        text = replace(text, "return MIDIGetNumberOfSources();", "return static_cast<unsigned int>(std::min<ItemCount>(MIDIGetNumberOfSources(), std::numeric_limits<unsigned int>::max()));")
        text = replace(text, "return MIDIGetNumberOfDestinations();", "return static_cast<unsigned int>(std::min<ItemCount>(MIDIGetNumberOfDestinations(), std::numeric_limits<unsigned int>::max()));")
        text = replace(text, "  OSStatus err;\n  int i;\n\n  // Does the endpoint have connections?", "  OSStatus err;\n  CFIndex i;\n\n  // Does the endpoint have connections?")
        text = replace(text, "int nConnected = 0;", "CFIndex nConnected = 0;")
        text = replace(text, "CFDataGetLength( connections ) / sizeof(MIDIUniqueID)", "CFDataGetLength( connections ) / static_cast<CFIndex>(sizeof(MIDIUniqueID))")
        marker = "void MidiOutCore :: sendMessage( const unsigned char *message, size_t size )"
        start = text.index(marker)
        end = text.index("#endif  // __MACOSX_CORE__", start)
        prefix, text, suffix = text[:start], text[start:end], text[end:]
        text = replace(text, "  if ( nBytes == 0 ) {", "  if ( !message || !size || size > std::numeric_limits<unsigned int>::max() ) {")
        start = text.index("  Byte buffer[nBytes+(sizeof( MIDIPacketList ))];")
        end = text.index("  if ( !packet ) {", start)
        text = text[:start] + """  krose::standalone::CoreMidiPacket buffer;
  MIDIPacketList *packetList = buffer.Build(message, size, timeStamp);

""" + text[end:]
        text = replace(text, "  if ( !packet ) {", "  if ( !packetList ) {")
        return prefix + '#include "standalone/CoreMidiPacket.h"\n\n' + text + suffix
    elif path == "WDL/swell/swell-wnd.mm":
        text = replace(text, "case NSTextAlignmentCenter: ret |= SS_CENTER; break;", "case NSTextAlignmentCenter: ret |= SS_CENTER; break;\n        default: break; // Left, natural and justified need no extra Win32 style.")
    elif path == "WDL/swell/swell-dlg.mm":
        text = replace(text, "const int texw = [(id<MTLTexture>) m_metal_texture width];", "const CGFloat texw = static_cast<CGFloat>([(id<MTLTexture>) m_metal_texture width]);")
        text = replace(text, "const int texh = [(id<MTLTexture>) m_metal_texture height];", "const CGFloat texh = static_cast<CGFloat>([(id<MTLTexture>) m_metal_texture height]);")
        text = replace(text, 'texture width mismatch %d vs %.0f', 'texture width mismatch %.0f vs %.0f')
        text = replace(text, 'texture height mismatch %d vs %.0f', 'texture height mismatch %.0f vs %.0f')
    elif path == "Dependencies/IPlug/VST3_SDK/pluginterfaces/base/funknown.cpp":
        # Match varargs types on both Windows GUID and the SDK's own GUID.
        text = replace(text, "g->Data1, g->Data2, g->Data3,", "static_cast<unsigned int>(g->Data1), g->Data2, g->Data3,", 2)
        text = replace(text, 'sscanf (s, "%x", &g.Data1);', 'unsigned int first = 0;\n\tif (sscanf (s, "%x", &first) != 1) return false;\n\tg.Data1 = first;', 2)
        text = replace(text, 'sprintf (string, "%08X%04X%04X%s",', 'snprintf (string, 33, "%08X%04X%04X%s",')
        text = replace(text, 'sprintf (string, "{%08X-%04X-%04X-%s-%s}",', 'snprintf (string, 39, "{%08X-%04X-%04X-%s-%s}",')
    elif path == "Dependencies/IPlug/VST3_SDK/base/source/fstring.cpp":
        text = replace(text, "value <= std::numeric_limits<int64>::max ()", "value < -static_cast<double> (std::numeric_limits<int64>::lowest ())")
    elif path == "Dependencies/IPlug/VST3_SDK/pluginterfaces/base/fvariant.h":
        text = replace(text, "memset (this, 0, sizeof (FVariant));", "type = kEmpty; intValue = 0;", 2)
    elif path == "IPlug/APP/IPlugAPP_main.cpp":
        text = replace(text, '*(void **)&__SetProcessDpiAwarenessContext = GetProcAddress(h, "SetProcessDpiAwarenessContext");', '__SetProcessDpiAwarenessContext = reinterpret_cast<decltype(__SetProcessDpiAwarenessContext)>(GetProcAddress(h, "SetProcessDpiAwarenessContext"));')
        text = replace(text, "*(void **)&__SetProcessDpiAwarenessContext = (void*)(INT_PTR)1;", "__SetProcessDpiAwarenessContext = reinterpret_cast<decltype(__SetProcessDpiAwarenessContext)>(INT_PTR(1));")
        text = replace(text, "while (temphwnd = GetParent(temphwnd));", "while ((temphwnd = GetParent(temphwnd)) != nullptr);")
        # The APP overlay is moved again by StandaloneHost.cmake.
        text = replace(text, '#include "../../Dependencies/IGraphics/STB/stb_image_write.h"', '#include "stb_image_write.h"')
    elif path == "IPlug/IPlugUtilities.h":
        text = replace(text, "_wcsupr(mUTF16Str.Get());", "_wcsupr_s(mUTF16Str.Get(), mUTF16Str.GetSize());")
        text = replace(text, "_wcslwr(mUTF16Str.Get());", "_wcslwr_s(mUTF16Str.Get(), mUTF16Str.GetSize());")
    elif path == "IPlug/IPlugStructs.h":
        text = replace(text, "strcpy(utf8, _utf8);", 'snprintf(utf8, sizeof(utf8), "%s", _utf8 ? _utf8 : "");')
    elif path == "IPlug/IPlugLogger.h":
        text = replace(text, "tm* pT = localtime(&t);", "tm local{}, utc{};\n#ifdef OS_WIN\n    if (localtime_s(&local, &t) || gmtime_s(&utc, &t)) return \"\";\n#else\n    if (!localtime_r(&t, &local) || !gmtime_r(&t, &utc)) return \"\";\n#endif\n    tm* pT = &local;")
        text = replace(text, "pT = gmtime(&t);", "pT = &utc;")
        text = replace(text, "snprintf(&cStr[i], 32,", "snprintf(&cStr[i], sizeof(cStr) - i,")
        text = replace(text, "static char sTimeStr[32];\n    strcpy(sTimeStr, cStr);", "static thread_local char sTimeStr[32];\n    snprintf(sTimeStr, sizeof(sTimeStr), \"%s\", cStr);")
    elif path == "IGraphics/IGraphicsStructs.h":
        text = replace(text, "strcpy(mFont, (fontID ? fontID : DEFAULT_FONT));", 'snprintf(mFont, sizeof(mFont), "%s", (fontID ? fontID : DEFAULT_FONT));', 2)
        text = replace(text, "strcpy(newText.mFont, (fontID ? fontID : DEFAULT_FONT));;", 'snprintf(newText.mFont, sizeof(newText.mFont), "%s", (fontID ? fontID : DEFAULT_FONT));')
    elif path == "IGraphics/Platforms/IGraphicsWin_dnd.h":
        # Add override only to methods which do not already specify it.
        import re
        text, count = re.subn(r"((?:ULONG|HRESULT) STDMETHODCALLTYPE (?:AddRef|Release|QueryInterface|GetData|QueryGetData|GetDataHere|SetData|DAdvise|DUnadvise|EnumDAdvise)\([^\n]*?\))([ \t]*)(\n?[ \t]*\{)", r"\1 override\2\3", text)
        if count != 13:
            raise ValueError("Pinned Windows COM methods changed")
    elif path == "IGraphics/Platforms/IGraphicsWin.cpp":
        text = replace(text, "switch (mParamEditMsg)\n    {", "switch (mParamEditMsg)\n    {\n      default: break; // None/editing/update do not commit or cancel.")
        text = replace(text, "switch (fontLocation)\n  {", "switch (fontLocation)\n  {\n    default: return nullptr; // No loadable file/resource at this location.")
    elif path == "Dependencies/IGraphics/yoga/yoga/YGValue.h":
        text = replace(text, 'operator"" _pt', 'operator""_pt', 3)
        text = replace(text, 'operator"" _percent', 'operator""_percent', 3)
    return text


PATCHED = {
    "Dependencies/IPlug/RTAudio/RtAudio.cpp", "Dependencies/IPlug/RTMidi/RtMidi.cpp",
    "Dependencies/IPlug/VST3_SDK/pluginterfaces/base/funknown.cpp",
    "Dependencies/IPlug/VST3_SDK/base/source/fstring.cpp", "WDL/swell/swell-wnd.mm",
    "WDL/swell/swell-dlg.mm",
    "Dependencies/IPlug/VST3_SDK/pluginterfaces/base/fvariant.h",
    "IPlug/APP/IPlugAPP_main.cpp", "IPlug/IPlugUtilities.h", "IPlug/IPlugStructs.h",
    "IPlug/IPlugLogger.h", "IGraphics/IGraphicsStructs.h",
    "IGraphics/Platforms/IGraphicsWin_dnd.h", "IGraphics/Platforms/IGraphicsWin.cpp",
    "Dependencies/IGraphics/yoga/yoga/YGValue.h",
}


def write_changed(path, data, mode=None):
    if path.is_file() and path.read_bytes() == data:
        if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
            path.chmod(mode)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.close()
            if mode is not None:
                temporary.chmod(mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def prepare(source, output):
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Dependency view must be separate from the pinned source")
    # Validate all edits before writing a view. The SDK is already a verified
    # symlink/junction in the pinned iPlug checkout; follow it, omit git internals.
    patched = {name: patch(name, (source / name).read_text(encoding="utf-8")).encode("utf-8") for name in PATCHED}
    for directory, dirs, files in os.walk(source, followlinks=True):
        dirs[:] = [name for name in dirs if name != ".git"]
        for name in files:
            if name == ".git":
                continue
            file = Path(directory) / name
            relative = file.relative_to(source)
            data = patched.get(relative.as_posix())
            write_changed(output / relative, file.read_bytes() if data is None else data,
                          stat.S_IMODE(file.stat().st_mode))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.output)
