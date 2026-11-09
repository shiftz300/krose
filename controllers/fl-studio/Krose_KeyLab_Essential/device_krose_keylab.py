# name=Krose KeyLab Essential mk3
"""FL Studio bridge for the selected Krose channel in the Channel Rack."""
from pathlib import Path
from time import monotonic

import channels
import device
import general
import midi
import plugins
import transport

import krose_catalog
from krose_keylab import DeviceFeedback, FADERS, FX_NAMES, HEADER, KNOBS, PADS, display, display_header


SIGNATURE = {"Program", "Amp Attack", "Arp Latch", "IFX 1 Type", "MFX 2 On"}
PARAMETERS = SIGNATURE | set(FADERS) | {name for name in KNOBS if name} | set(PADS) | {
    "EG Target", "FX Edit", "FX Bypass", "Tone", "SW1 Mode", "SW2 Mode",
} | {slot + " Type" for slot in FX_NAMES}

TRANSPORT = {
    20: transport.stop,
    21: transport.start,
    22: transport.record,
}
TRANSPORT_COMMAND = {
    23: midi.FPT_TapTempo,
    24: midi.FPT_LoopRecord,
    27: midi.FPT_Metronome,
}


class Parameter:
    """Expose FL's normalized values through the shared KeyLab interface."""
    min, max, is_quantized, is_enabled = 0.0, 1.0, False, True

    def __init__(self, channel, index, name):
        self.channel, self.index, self.name = channel, index, name

    @property
    def value(self):
        return plugins.getParamValue(self.index, self.channel, -1, True)

    @value.setter
    def value(self, value):
        # The adapter implements pickup itself. Avoid applying it twice.
        plugins.setParamValue(value, self.index, self.channel, -1, midi.PIM_None, True)

    def begin_gesture(self):
        pass

    def end_gesture(self):
        pass

    def __str__(self):
        if self.name == "Program":
            index = round(self.value * (len(surface.catalog) - 1))
            return surface.catalog[index][1]
        if self.name == "Tone":
            return ("Concert", "Warm", "Wide")[round(self.value * 2)]
        text = plugins.getParamValueString(self.index, self.channel, -1, True)
        if text:
            return text
        value = self.value
        if self.name.startswith(("Amp ", "Filter ")) or self.name in ("Cutoff", "Resonance"):
            return f"{round(198 * value - 99):+d}"
        if self.name == "Output":
            return f"{66 * value - 60:.1f} dB"
        if self.name == "Velocity":
            return f"{2.5 * value + .5:.2f}x"
        if self.name in ("Glide", "Pan"):
            return str(round(127 * value) - (64 if self.name == "Pan" else 0))
        return f"{value:.0%}"


class Channel:
    def __init__(self, index):
        self.index = index
        count = min(plugins.getParamCount(index, -1, True), 4096)
        self.parameters = []
        for parameter in range(count):
            name = plugins.getParamName(parameter, index, -1, True)
            if name in PARAMETERS:
                self.parameters.append(Parameter(index, parameter, name))


def mk3_port():
    name = " ".join(str(device.getName()).lower().split())
    return (("essential" in name and "mk3" in name) and
            not any(word in name for word in ("mcu", "hui", "thru", "alv")))


def send(message):
    # FL's MIDI receive callback can be inside the device I/O lock.
    # Coalesce by LED, screen field or control so only OnIdle sends feedback.
    length = 11 if message[8] == 96 and message[9] == 32 else 10
    key = message[:length]
    pending.pop(key, None)
    pending[key] = message


def connection(active):
    device.midiOutSysex(bytes(HEADER + (2, 15, 64, 90, int(active), 247)))


def control(status, number, value):
    if status == 0xb0:
        if 44 <= number <= 47:
            return "fx_edit", (number - 44, value)
        if 96 <= number <= 104:
            return "knob", (number - 96, value)
        if 105 <= number <= 113:
            return "fader", (number - 105, value)
        if number == 116:
            return "program", (value,)
    if status in (0x8a, 0x9a) and 36 <= number <= 43:
        return "button", ((number - 36) ^ 4, value if status == 0x9a else 0)
    return None


surface = None
candidate = None
dirty = True
loading = False
output = False
idle_at = 0
pending = {}
pressed = {}


def is_krose(index):
    return (index >= 0 and plugins.isValid(index, -1, True)
            and plugins.getPluginName(index, -1, 0, True).strip().lower() == "krose")


def sync_target():
    global candidate, dirty
    selected = channels.channelNumber(1)
    index = selected if is_krose(selected) else None
    if not dirty and index == candidate:
        return
    old = surface.device
    if old is not None:
        if is_krose(old.index):
            surface.clear()
        else:
            surface.bind(None)
    candidate, dirty = index, False
    if index is not None:
        target = Channel(index)
        if SIGNATURE.issubset(p.name for p in target.parameters):
            surface.bind(target)
    if output and surface.device is None:
        send(display("FL Studio", "Select Krose"))
        send(display_header("Channel Rack"))


def OnInit():
    global surface, candidate, dirty, loading, output, idle_at
    surface = None
    if general.getVersion() < 26:
        print("Krose: MIDI scripting API 26 or newer is required.")
        return
    try:
        order, catalog = krose_catalog.load_catalog(Path(krose_catalog.__file__).resolve().parent)
    except (OSError, ValueError):
        print("Krose: copy the complete controller folder with its Program catalog.")
        return
    surface = DeviceFeedback(send, order, catalog=catalog)
    candidate, dirty, loading, output, idle_at = None, True, False, False, 0
    pending.clear()
    pressed.clear()


def OnDeInit():
    global surface
    if surface is not None and surface.device is not None:
        surface.clear()
    if output and mk3_port() and device.isAssigned():
        connection(False)
    pending.clear()
    pressed.clear()
    surface = None


def OnProjectLoad(status):
    global loading, dirty
    loading = status == midi.PL_Start
    dirty = True
    if loading and surface is not None:
        # Channel indices can be reused during a project load.
        surface.bind(None)
        pending.clear()
        pressed.clear()


def OnDirtyChannel(index, flag):
    global dirty
    if surface is None or flag not in (midi.CE_New, midi.CE_Delete, midi.CE_Replace):
        return
    # Insertions/deletions can shift every subsequent global channel index.
    if flag != midi.CE_Replace or index == candidate:
        surface.bind(None)
        dirty = True


def OnMidiMsg(event):
    if surface is None or not mk3_port() or loading:
        return
    status, number, value = event.status, event.data1, event.data2
    if status == 0xb0 and number in TRANSPORT:
        event.handled = True
        if value:
            TRANSPORT[number]()
        return
    if status == 0xb0 and number in TRANSPORT_COMMAND:
        event.handled = True
        if value:
            transport.globalTransport(TRANSPORT_COMMAND[number], 1, event.pmeflags)
        return
    action = control(status, number, value)
    if action is None:
        return
    sync_target()
    method, args = action
    if method in ("button", "fx_edit"):
        key = method, args[0]
        if not args[1]:
            owner = pressed.pop(key, None)
            if owner is not None:
                event.handled = True
                if owner is surface.device:
                    getattr(surface, method)(*args)
            return
        if key in pressed:
            event.handled = True
            return
        if surface.device is not None:
            pressed[key] = surface.device
    if surface.device is not None:
        event.handled = True
        getattr(surface, method)(*args)


def OnIdle():
    global output, idle_at, dirty
    if surface is None or loading:
        return
    now = monotonic()
    if now < idle_at:
        return
    idle_at = now + .025
    assigned = mk3_port() and bool(device.isAssigned())
    if output != assigned:
        output = assigned
        if assigned:
            connection(True)
            dirty = True
        else:
            # Stop pending holds when the connection is lost.
            pressed.clear()
            dirty = True
    sync_target()
    if assigned:
        surface.tick()
        for message in pending.values():
            device.midiOutSysex(bytes(message))
    else:
        surface._poll_fx_presses(now)
    pending.clear()
