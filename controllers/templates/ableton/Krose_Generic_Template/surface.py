"""Edit CHANNEL and CONTROLS for your keyboard; this template sends no MIDI."""
from functools import partial
import Live
from _Framework.ControlSurface import ControlSurface
from _Framework.EncoderElement import EncoderElement
from _Framework.InputControlElement import MIDI_CC_TYPE

CHANNEL = 0  # Live uses 0..15; MIDI channel 1 is 0 here.
CONTROLS = ((74, 'Cutoff'), (71, 'Resonance'), (7, 'Output'), (10, 'Pan'))


class KroseGenericTemplate(ControlSurface):
    def __init__(self, c_instance):
        super().__init__(c_instance)
        self._bindings = []
        with self.component_guard():
            for cc, name in CONTROLS:
                element = EncoderElement(MIDI_CC_TYPE, CHANNEL, cc, Live.MidiMap.MapMode.absolute)
                callback = partial(self._value, name)
                element.add_value_listener(callback)
                self._bindings.append((element, callback))

    def _value(self, name, value):
        if not isinstance(value, int) or not 0 <= value <= 127: return
        try:
            device = self.song().appointed_device
            if device is None: return
            parameters = {getattr(p, 'original_name', p.name): p for p in device.parameters}
            if not {'Program', 'Arp Latch', 'IFX 1 Type', 'MFX 2 On'}.issubset(parameters): return
            parameter = parameters.get(name)
            if parameter is None or not parameter.is_enabled: return
            parameter.begin_gesture()
            try:
                normalized = parameter.min + value / 127.0 * (parameter.max - parameter.min)
                parameter.value = round(normalized) if parameter.is_quantized else normalized
            finally:
                parameter.end_gesture()
        except (RuntimeError, ReferenceError):
            pass  # Selected device was removed by Live during a control gesture.

    def disconnect(self):
        for element, callback in self._bindings: element.remove_value_listener(callback)
        self._bindings.clear()
        super().disconnect()
