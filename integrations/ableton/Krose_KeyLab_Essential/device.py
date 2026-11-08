"""Host-independent mapping and wire encoding. No ports or background threads."""
import time

HEADER = (240, 0, 32, 107, 127, 66)
KNOBS = ("Glide", "Program", "Pan", "Cutoff", "Resonance", "Velocity",
         "Output", None, None)
KNOB_LABELS = ("Glide", "Value", "Pan", "Cutoff", "Resonance", "Velocity",
               "Volume", "Unassigned", "Unassigned")
FADERS = ("Amp Attack", "Amp Decay", "Amp Sustain", "Amp Release",
          "Filter Attack", "Filter Decay", "Filter Sustain", "Filter Release", "Output")
PADS = ("Arp", "Arp Latch", "IFX 1 On", "IFX 2 On", "MFX 1 On", "MFX 2 On", "SW1", "SW2")
FX_NAMES = ("IFX 1","IFX 2","MFX 1","MFX 2")
INSERT_TYPES = ("AUTO","OFF","EQ","COMPRESSOR","LIMITER","DRIVE","EXCITER","GRAPHIC 7 EQ","PHASER","TREMOLO","AUTO PAN")
SEND_TYPES = ("AUTO","OFF","CHORUS","STEREO DELAY","HALL","PLATE","EQ","COMPRESSOR","LIMITER","DRIVE","EXCITER","GRAPHIC 7 EQ","PHASER","TREMOLO","AUTO PAN")
FX_COLOURS = ((0,0,0),(0,0,0),(32,80,127),(127,78,24),(127,104,24),
              (127,38,20),(127,28,62),(24,110,127),(99,44,127),(50,127,74),
              (24,127,114),(48,80,127),(30,127,110),(102,64,127),(127,64,112))


def ascii_text(value):
    return "".join(c if 32 <= ord(c) < 127 else "?" for c in str(value))


def display(first, second):
    line = lambda text: tuple(ord(c) for c in ascii_text(text)[:18].ljust(18))
    return HEADER + (4, 1, 96, 18, 1) + line(first) + (0, 2) + line(second) + (0, 0, 247)


def pad(index, on):
    return HEADER + (4, 1, 22, 28 + (index ^ 4)) + ((48, 90, 90) if on else (0, 0, 0)) + (32, 247)


def fx_button(index, colour):
    return HEADER + (4,1,22,24+index) + tuple(colour) + (32,247)


def display_header(title):
    return HEADER + (4, 1, 96, 1, 2) + tuple(ord(c) for c in ascii_text(title)[:14]) + (0, 0, 247)


def category_icon(category):
    return {"PIANO": 0x28, "E.PIANO": 0x0d, "ORGAN": 0x1f, "BASS": 3,
            "STRINGS": 0x31, "BRASS": 5, "SYNTH LEAD": 0x1a,
            "SYNTH PAD": 0x21, "DRUM/SFX": 0x0b}.get(category, 0x18)


def parameter_label(name):
    if name == "Output": return "Volume"
    for a, b in (("IFX ", "IFX"), ("MFX ", "MFX"), ("Filter ", "Flt "),
                 ("Resonance", "Reso"), ("Sustain", "Sust"), ("Release", "Rel"), ("Attack", "Atk")):
        name = name.replace(a, b)
    return ascii_text(name)[:12]


def program_line(name, elapsed):
    text = ascii_text(name)
    if len(text) <= 12: return text
    travel = len(text) - 12
    phase = max(0, elapsed) % (2.4 + travel * .35)
    offset = 0 if phase <= 1.2 else min(travel, int((phase - 1.2) / .35))
    return text[offset:offset + 12]


def display_icon(first, second, icon):
    text = lambda value, limit: tuple(ord(c) for c in ascii_text(value)[:limit])
    return HEADER + (4,1,96,0x19,1) + text(first,12) + (0,2) + text(second,18) + (0,3,icon,0,0,247)


def control_display(index, label, value):
    cc = 96 + index if index < 8 else 105 + index - 8 if index < 16 else 104 if index == 16 else 113
    text = lambda value, limit: tuple(ord(c) for c in ascii_text(value)[:limit])
    return HEADER + (4,1,96,32,index,32,1) + text(label,11) + (0,2) + text(value,18) + (0,3,cc,0,247)


def parameter_page(name):
    if name.startswith(("IFX ", "MFX ")): return "FX / " + name[:5]
    if name.startswith("Arp"): return "ARP"
    if name.startswith("Amp "): return "TONE / AMP EG"
    if name.startswith("Filter "): return "TONE / FILTER EG"
    if name.startswith(("SW", "MIDI")): return "CTRL"
    if name in ("FX Bypass", "Space"): return "FX"
    return "TONE"


def relative(value):
    return value - 64 if 0 <= value < 128 else 0


def parameters(device):
    return {getattr(p, "original_name", p.name): p for p in device.parameters} if device else {}


def is_krose(device):
    # Stable parameter signature also works when the user renames the instance.
    if device is None:
        return False
    return (getattr(device, "class_display_name", "").lower() == "krose" or
            (getattr(device, "class_name", "") == "PluginDevice" and device.name.lower() == "krose") or
            {"Program", "Amp Attack", "Arp Latch", "IFX 1 Type", "MFX 2 On"}.issubset(parameters(device)))


class DeviceFeedback:
    def __init__(self, send, order, clock=time.monotonic, catalog=None):
        self.send, self.order, self.clock = send, order, clock
        self.catalog = catalog or []
        self.device, self.params = None, {}
        self.cache, self.values, self.pickup = {}, {}, {}
        self.focus, self.until, self.next_update = None, 0, 0
        self.held = set()
        self.value_position = None
        self.program_started = None
        self.control_until, self.restore_screen = 0, False
        self.eg_target = None
        self.fx_presses = {}

    def bind(self, device):
        self.device = device
        self.params = parameters(device)
        self.values = {name: p.value for name, p in self.params.items()}
        self.cache.clear()
        self.pickup.clear()
        self.focus, self.until, self.next_update = None, 0, 0
        self.held.clear()
        self.value_position = None
        self.program_started = None
        self.control_until, self.restore_screen = 0, False
        self.eg_target = None
        self.fx_presses = {}

    def _write(self, name, value):
        p = self.params.get(name)
        if p is None or not p.is_enabled:
            return
        p.begin_gesture()
        try:
            p.value = max(p.min, min(p.max, round(value) if p.is_quantized else value))
        finally:
            p.end_gesture()
        self.focus, self.until = name, self.clock() + 1.2
        self.program_started = None

    def knob(self, index, value):
        self.control_until, self.restore_screen = self.clock() + 1.2, True
        if index == 1:
            delta = value - self.value_position if self.value_position is not None else 0
            self.value_position = value
            self._step_program(delta)
            return
        p = self.params.get(KNOBS[index])
        if p:
            self._write(KNOBS[index], p.min + max(0, min(127, value)) / 127 * (p.max - p.min))

    def fader(self, index, value):
        self.control_until, self.restore_screen = self.clock() + 1.2, True
        self._sync_eg()
        name = self.fader_name(index)
        p = self.params.get(name)
        if p is None or p.max == p.min:
            return
        normalized = max(0, min(1, value / 127))
        target = (p.value - p.min) / (p.max - p.min)
        previous, caught, last_target = self.pickup.get(index, (normalized, False, target))
        if abs(last_target - target) > 1e-6:
            caught = False
        caught = caught or abs(normalized - target) <= .04 or (previous - target) * (normalized - target) <= 0
        if caught:
            self._write(name, p.min + normalized * (p.max - p.min))
        self.pickup[index] = normalized, caught, (p.value - p.min) / (p.max - p.min)

    def fader_name(self, index):
        target = self.params.get("EG Target")
        filter_eg = bool(target and target.value > target.min)
        return FADERS[index ^ (4 if filter_eg else 0)] if index < 8 else FADERS[index]

    def _sync_eg(self):
        target = self.params.get("EG Target")
        filter_eg = bool(target and target.value > target.min)
        if filter_eg != self.eg_target:
            for index in range(8): self.pickup.pop(index,None)
            self.eg_target = filter_eg

    def button(self, index, value):
        name = PADS[index]
        p = self.params.get(name)
        if p is None:
            return
        mode = self.params.get(name + " Mode") if index >= 6 else None
        if mode and mode.value >= .5:
            self._write(name, p.max if value else p.min)
            if value:
                self.held.add(name)
            else:
                self.held.discard(name)
        elif value:
            self._write(name, p.min if p.value > p.min else p.max)

    def program(self, value):
        direction = relative(value)
        self._step_program(1 if direction > 0 else -1 if direction < 0 else 0)

    def fx_edit(self, index, value):
        now=self.clock()
        if value:
            if index not in self.fx_presses:
                program=self.params.get("Program")
                self.fx_presses[index]=(now,False,program.value if program else None)
            return
        press=self.fx_presses.pop(index,None)
        program=self.params.get("Program")
        if press is None or press[1] or press[2]!=(program.value if program else None): return
        if now-press[0]>=.6: self._toggle_fx(index)
        elif now>=press[0]: self._open_fx_editor(index)

    def _poll_fx_presses(self, now):
        program=self.params.get("Program")
        context=program.value if program else None
        for index,(started,fired,owner) in list(self.fx_presses.items()):
            if owner!=context:
                self.fx_presses.pop(index,None)
            elif not fired and now-started>=.6:
                self.fx_presses[index]=(started,True,owner)
                self._toggle_fx(index)

    def _toggle_fx(self, index):
        p=self.params.get(FX_NAMES[index]+" On")
        if p is not None and self.fx_state(index)[0]!="OFF":
            self._write(FX_NAMES[index]+" On",p.min if p.value>p.min else p.max)

    def _open_fx_editor(self, index):
        p=self.params.get("FX Edit")
        if p is None: return
        current=round((p.value-p.min)/(p.max-p.min)*7) if p.max<=1 and p.max>p.min else round(p.value)
        code=index+4 if current==index else index
        self._write("FX Edit",p.min+code/7*(p.max-p.min) if p.max<=1 else code)

    def fx_state(self, index):
        kind=self.params.get(FX_NAMES[index]+" Type")
        names=INSERT_TYPES if index<2 else SEND_TYPES
        text=str(kind).upper() if kind else "OFF"
        if text not in names:
            raw=round((kind.value-kind.min)/(kind.max-kind.min)*(len(names)-1)) if kind and kind.max<=1 and kind.max>kind.min else round(kind.value) if kind else 1
            text=names[max(0,min(len(names)-1,raw))]
        if text=="AUTO":
            tone=self.params.get("Tone")
            wide=bool(tone and (str(tone).lower()=="wide" or tone.value==2))
            text=("EQ" if self.program_index()==0 else "OFF","OFF","CHORUS" if wide else "OFF","HALL")[index]
        algorithm=(INSERT_TYPES+SEND_TYPES[2:6]).index(text)
        on=self.params.get(FX_NAMES[index]+" On")
        bypass=self.params.get("FX Bypass")
        active=bool(on and on.value>on.min and not (bypass and bypass.value) and text!="OFF")
        return text,FX_COLOURS[algorithm] if active else (0,0,0)

    def _step_program(self, steps):
        p = self.params.get("Program")
        if p is None or not steps:
            return
        current = self.program_index()
        order = self.order
        if current in order:
            value = order[(order.index(current) + steps) % len(order)]
        else:
            value = current + steps
        if p.max <= 1 and len(order) > 2:
            value = p.min + value / (len(order) - 1) * (p.max - p.min)
        self._write("Program", value)
        self.focus, self.until = None, 0

    def program_index(self):
        p = self.params["Program"]
        return round((p.value - p.min) / (p.max - p.min) * (len(self.order) - 1)) if p.max <= 1 and p.max > p.min and len(self.order) > 2 else round(p.value)

    def _emit(self, key, message):
        if self.cache.get(key) != message:
            self.send(message)
            self.cache[key] = message

    def tick(self):
        if self.device is None:
            return
        current = parameters(self.device)
        if current != self.params:
            device = self.device
            self.clear()
            self.bind(device)
        now = self.clock()
        self._poll_fx_presses(now)
        if now < self.next_update:
            return
        self.next_update = now + .1
        if "Program" not in self.params:
            self._emit("screen", display("Krose", "Configure in Live"))
            return
        changed = [name for name, p in self.params.items() if self.values.get(name) != p.value]
        if "Program" in changed:
            self.focus, self.until = None, 0
            self.program_started = None
            self.pickup.clear()
        elif changed:
            self.focus, self.until = changed[-1], now + 1.2
        self.values = {name: p.value for name, p in self.params.items()}
        self._sync_eg()
        for i in range(18):
            index = i if i < 8 else i - 8 if i < 16 else 8
            knob = i < 8 or i == 16
            name = KNOBS[index] if knob else self.fader_name(index)
            p = self.params.get(name)
            label = KNOB_LABELS[index] if knob else parameter_label(name)
            self._emit(("control",i),control_display(i,label,str(p) if p else "--"))
        if now >= self.control_until:
            if self.restore_screen:
                self.cache.pop("screen",None)
                self.cache.pop("header",None)
                self.restore_screen = False
            self._display(now)
        self._pads()

    def _display(self, now):
        if self.focus=="FX Edit" and now<self.until:
            p=self.params["FX Edit"]
            code=round((p.value-p.min)/(p.max-p.min)*7) if p.max<=1 and p.max>p.min else round(p.value)
            slot=code%4
            first,second=FX_NAMES[slot],self.fx_state(slot)[0]
            title,icon="FX / "+first,0x2f
        elif self.focus and now < self.until:
            self.program_started = None
            first, second = parameter_label(self.focus), str(self.params[self.focus])
            title = parameter_page(self.focus)
            icon = 0x2d if title == "ARP" else 0x2f if title.startswith("FX") else 9
        else:
            text = ascii_text(str(self.params["Program"]))
            if self.program_started is None: self.program_started = now
            first, second = program_line(text, now - self.program_started), ""
            index = self.program_index()
            title, icon = "PROG", 0x28
            if 0 <= index < len(self.catalog):
                row = self.catalog[index]
                title, icon = row[0] + " " + row[2], category_icon(row[2])
        screen = display_icon(first, second, icon)
        if self.cache.get("screen") != screen: self.cache.pop("header", None)
        self._emit("screen", screen)
        self._emit("header", display_header(title))

    def _pads(self):
        for i, name in enumerate(PADS):
            p = self.params.get(name)
            on = bool(p and p.value > p.min)
            if 2 <= i < 6:
                on=any(self.fx_state(i-2)[1])
            self._emit(i, pad(i, on))
        for i in range(4): self._emit(("fx-button",i),fx_button(i,self.fx_state(i)[1]))

    def clear(self):
        try:
            for name in self.held:
                p = self.params.get(name)
                if p and p.is_enabled:
                    self._write(name, p.min)
            for i in range(8):
                self.send(pad(i, False))
            for i in range(4): self.send(fx_button(i,(0,0,0)))
        except (RuntimeError, ReferenceError):
            pass
        finally:
            self.held.clear()
            self.bind(None)
