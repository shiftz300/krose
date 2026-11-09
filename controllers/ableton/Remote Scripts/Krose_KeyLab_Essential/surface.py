"""Use Live's mk3 transport/navigation; Krose owns only its selected device."""
from pathlib import Path
from functools import partial

from KeyLab_Essential_mk3 import KeyLab_Essential_mk3, Specification
from .device import DeviceFeedback, is_krose
from .catalog import load_catalog


class KroseKeyLabEssential(KeyLab_Essential_mk3):
    def __init__(self, *args, **kwargs):
        self._krose = None
        self._krose_listeners = []
        self._krose_enabled = {}
        self._krose_sending = False
        super().__init__(*args, specification=Specification, **kwargs)
        try:
            order, catalog = load_catalog(Path(__file__).parent)
        except (OSError, ValueError):
            order, catalog = [], []
            self.log_message("Krose: invalid controller catalog; using parameter names")
        self._krose = DeviceFeedback(self._krose_send, order, catalog=catalog)
        with self.component_guard():
            for i, element in enumerate(self.elements.continuous_controls_raw):
                self._listen(element, partial(self._control, "knob" if i < 8 else "fader", i % 8))
            self._listen(self.elements.encoder_9, partial(self._control, "knob", 8))
            self._listen(self.elements.fader_9, partial(self._control, "fader", 8))
            for element, _ in self.elements.pad_bank_a.iterbuttons():
                self._listen(element, partial(self._control, "button", (element.original_identifier() - 36) ^ 4))
            self._listen(self.elements.display_encoder, partial(self._control, "program", None))
            for i in range(4):
                self._listen(getattr(self.elements,"context_button_"+str(i)),partial(self._control,"fx_edit",i))

    def _listen(self, element, callback):
        element.add_value_listener(callback)
        self._krose_listeners.append((element, callback))

    def _control(self, action, index, value):
        if self._krose and self._krose.device:
            if index is None:
                self._krose.program(value)
            else:
                getattr(self._krose, action)(index, value)

    def _krose_send(self, message):
        self._krose_sending = True
        try:
            self._send_midi(message)
        finally:
            self._krose_sending = False

    def _send_midi(self, message, *args, **kwargs):
        # The installed script keeps updating its display model in the
        # background. Only one producer may send screen/pad/encoder feedback.
        if self._krose and self._krose.device and not self._krose_sending:
            if len(message) == 3 and message[0] == 176 and (96 <= message[1] <= 113 or message[1] == 116):
                return True
            header = tuple(message[:9])
            if header == (240, 0, 32, 107, 127, 66, 4, 1, 96):
                return True
            if len(message) > 9 and header == (240, 0, 32, 107, 127, 66, 4, 1, 22) and 24 <= message[9] < 36:
                return True
            if len(message) > 9 and header == (240, 0, 32, 107, 127, 66, 2, 15, 64) and 3 <= message[9] <= 11:
                return True
        return super()._send_midi(message, *args, **kwargs)

    def _claim(self, active):
        if active:
            for name in ("Continuous_Control_Modes", "Device", "Mixer", "Session", "Drum_Group", "View_Control"):
                component = self.component_map.get(name)
                if component:
                    self._krose_enabled[name] = component.is_enabled()
                    component.set_enabled(False)
            for element in (*self.elements.continuous_controls_raw, self.elements.encoder_9, self.elements.fader_9):
                element.release_parameter()
        else:
            for name, enabled in self._krose_enabled.items():
                self.component_map[name].set_enabled(enabled)
            self._krose_enabled.clear()
            for element in self.controls:
                element.clear_send_cache()
            for name in ("Session", "Mixer", "Device"):
                self.component_map[name].update()
        self.request_rebuild_midi_map()

    def update_display(self):
        super().update_display()
        if self._krose is None:
            return
        try:
            device = self.song.appointed_device
            device = device if device and is_krose(device) else None
            if device != self._krose.device:
                with self.component_guard():
                    if self._krose.device is not None:
                        self._krose.clear()
                        self._claim(False)
                    if device is not None:
                        self._claim(True)
                    self._krose.bind(device)
            self._krose.tick()
        except (RuntimeError, ReferenceError):
            if self._krose.device is not None:
                with self.component_guard():
                    self._krose.clear()
                    self._claim(False)

    def port_settings_changed(self):
        super().port_settings_changed()
        if self._krose:
            device = self._krose.device
            self._krose.clear()
            self._krose.bind(device)

    def disconnect(self):
        for element, callback in self._krose_listeners:
            element.remove_value_listener(callback)
        self._krose_listeners.clear()
        if self._krose:
            self._krose.clear()
        super().disconnect()
