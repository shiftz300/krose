# name=Krose Generic CC
"""Forward keyboard CC to the selected Krose channel's wrapper MIDI input."""
import channels
import device
import general
import plugins


WRAPPER_PORT = 10
enabled = False


def OnInit():
    global enabled
    enabled = general.getVersion() >= 26 and 0 <= WRAPPER_PORT <= 127
    if not enabled:
        print("Krose Generic CC requires MIDI scripting API 26+ and a wrapper port from 0 to 127.")


def OnMidiMsg(event):
    if not enabled or event.handled:
        return
    status, cc, value = event.status, event.data1, event.data2
    if not (0xb0 <= status <= 0xbf and 0 <= cc < 128 and 0 <= value < 128):
        return
    channel = channels.channelNumber(1)
    if channel < 0 or channels.channelNumber(1, 1) >= 0:
        return
    if (not plugins.isValid(channel, -1, True)
            or plugins.getPluginName(channel, -1, 0, True).strip().lower() != "krose"):
        return
    device.forwardMIDICC(status | (cc << 8) | (value << 16) | (WRAPPER_PORT << 24), 2)
    event.handled = True
