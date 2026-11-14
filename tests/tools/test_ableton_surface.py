"""Exercise the adapter against the public interface used by Live's mk3 base."""
import contextlib
import importlib.util
import sys
from types import ModuleType, SimpleNamespace
from unittest import TestCase, main, mock

from test_ableton_controller import ROOT, bridge, device


class Element:
    def __init__(self, number):
        self.number, self.listeners = number, []
        self.released = 0
        self.identifier, self.channel = number, 10
        self.script_forwarding = "exclusive"
    def original_identifier(self): return self.number
    def add_value_listener(self, callback): self.listeners.append(callback)
    def remove_value_listener(self, callback): self.listeners.remove(callback)
    def release_parameter(self): self.released += 1
    def clear_send_cache(self): pass
    def set_identifier(self, identifier): self.identifier = identifier
    def set_channel(self, channel): self.channel = channel
    def use_default_message(self): self.identifier, self.channel = self.number, 10
    def emit(self, value):
        for callback in self.listeners: callback(value)


class Component:
    def __init__(self, enabled=True): self.enabled = enabled
    def is_enabled(self): return self.enabled
    def set_enabled(self, enabled): self.enabled = enabled
    def update(self): pass


class LiveBase:
    def __init__(self, *args, **kwargs):
        self.sent, self.rebuilds = [], 0
        pads = [Element(i) for i in range(36, 44)]
        drums = [Element(i) for i in range(44, 52)]
        self.elements = SimpleNamespace(
            continuous_controls_raw=[Element(i) for i in list(range(96, 104)) + list(range(105, 113))],
            encoder_9=Element(104), fader_9=Element(113), display_encoder=Element(116),
            context_button_0=Element(44), context_button_1=Element(45), context_button_2=Element(46), context_button_3=Element(47),
            pad_bank_a=SimpleNamespace(iterbuttons=lambda: ((p, (i % 4, i // 4)) for i, p in enumerate(pads))),
            pad_bank_b=SimpleNamespace(iterbuttons=lambda: ((p, (i, 0)) for i, p in enumerate(drums))))
        self.controls = self.elements.continuous_controls_raw + pads + drums + [self.elements.encoder_9, self.elements.fader_9]
        self.component_map = {name: Component(name != "Device") for name in
                              ("Continuous_Control_Modes", "Mixer", "Session", "Drum_Group", "Device", "View_Control", "Transport")}
        self.song = SimpleNamespace(appointed_device=None, visible_tracks=[], view=SimpleNamespace(selected_track=None))
    def component_guard(self): return contextlib.nullcontext()
    def request_rebuild_midi_map(self): self.rebuilds += 1
    def update_display(self): pass
    def port_settings_changed(self): pass
    def disconnect(self): pass
    def _send_midi(self, message, *args, **kwargs):
        self.sent.append(tuple(message))
        return True


class Surface(TestCase):
    def setUp(self):
        base = ModuleType("KeyLab_Essential_mk3")
        base.KeyLab_Essential_mk3, base.Specification = LiveBase, object
        package = ModuleType("Krose_KeyLab_Essential")
        package.__path__ = []
        input_element = ModuleType("ableton.v2.control_surface.input_control_element")
        input_element.ScriptForwarding = SimpleNamespace(non_consuming="non_consuming")
        self.modules = mock.patch.dict(sys.modules, {"KeyLab_Essential_mk3": base,
            input_element.__name__: input_element,
            "Krose_KeyLab_Essential": package, "Krose_KeyLab_Essential.device": bridge, "Krose_KeyLab_Essential.catalog": ModuleType("catalog")})
        self.modules.start()
        catalog = [("A000", "Grand", "PIANO"), ("B000", "Pad", "SYNTH PAD"),
                   ("F033", "Rock Kit", "DRUM/SFX"), ("F034", "Jazz Kit", "DRUM/SFX")]
        sys.modules["Krose_KeyLab_Essential.catalog"].load_catalog = lambda folder: ([0, 3, 1, 2], catalog)
        spec = importlib.util.spec_from_file_location("Krose_KeyLab_Essential.surface",
            ROOT / "controllers/ableton/Remote Scripts/Krose_KeyLab_Essential/surface.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.surface = module.KroseKeyLabEssential()

    def tearDown(self): self.modules.stop()

    def test_select_switch_and_restore_default_owners(self):
        surface = self.surface
        first, second = device(), device()
        surface.song.appointed_device = first
        surface.update_display()
        self.assertFalse(surface.component_map["Mixer"].is_enabled())
        self.assertTrue(surface.component_map["Transport"].is_enabled())
        surface.elements.continuous_controls_raw[3].emit(127)
        self.assertEqual(surface._krose.params["Cutoff"].value, 1)
        surface.song.appointed_device = second
        surface.update_display()
        surface.elements.continuous_controls_raw[3].emit(0)
        self.assertEqual(bridge.parameters(first)["Cutoff"].value, 1)
        self.assertEqual(bridge.parameters(second)["Cutoff"].value, 0)
        surface.song.appointed_device = None
        surface.update_display()
        self.assertTrue(surface.component_map["Mixer"].is_enabled())
        self.assertFalse(surface.component_map["Device"].is_enabled())
        self.assertTrue(surface.component_map["Transport"].is_enabled())

    def test_truncated_feedback_messages_do_not_index_past_end(self):
        surface = self.surface
        surface.song.appointed_device = device()
        surface.update_display()
        for message in [(), (240,), bridge.HEADER + (4, 1, 22), bridge.HEADER + (2, 15, 64)]:
            surface._send_midi(message)

    def test_single_feedback_owner_and_reconnect(self):
        surface = self.surface
        surface.song.appointed_device = device()
        surface.update_display()
        message = bridge.display("Official", "Background")
        before = len(surface.sent)
        surface._send_midi(message)
        self.assertEqual(len(surface.sent), before)
        surface._send_midi((176, 96, 0))  # Stock background reset must not undo our encoder sync.
        self.assertEqual(len(surface.sent), before)
        surface._send_midi((176, 21, 127))
        self.assertEqual(surface.sent[-1], (176, 21, 127))  # Transport feedback still passes.
        surface._krose_send(message)
        self.assertEqual(surface.sent[-1], message)
        switch = surface._krose.params["SW1"]
        surface._krose.params["SW1 Mode"].value = 1
        surface._krose.button(6, 127)
        self.assertEqual(switch.value, 1)
        surface.port_settings_changed()
        self.assertEqual(switch.value, 0)
        self.assertEqual(surface._krose.cache, {})
        surface.disconnect()
        self.assertEqual(surface._krose_listeners, [])
        self.assertIsNone(surface._krose.device)

    def test_four_context_buttons_edit_fx_without_track_or_bypass_changes(self):
        surface = self.surface
        tracks = [SimpleNamespace(can_be_armed=True, arm=False, name="A"),
                  SimpleNamespace(can_be_armed=True, arm=False, name="B")]
        surface.song.visible_tracks = tracks
        surface.song.view.selected_track = tracks[0]
        surface.song.appointed_device = device()
        surface.update_display()
        for i in range(4):
            element=getattr(surface.elements,"context_button_"+str(i))
            before=surface._krose.params["FX Edit"].value
            element.emit(127)
            self.assertEqual(surface._krose.params["FX Edit"].value,before)
            element.emit(0)
            code=surface._krose.params["FX Edit"].value
            self.assertEqual(code%4,i)
            element.emit(0)
            self.assertEqual(surface._krose.params["FX Edit"].value,code)
            element.emit(127)
            element.emit(0)
            self.assertNotEqual(surface._krose.params["FX Edit"].value,code)
        self.assertFalse(tracks[0].arm)
        self.assertIs(surface.song.view.selected_track, tracks[0])
        official=bridge.fx_button(0,(127,0,0))
        count=len(surface.sent)
        surface._send_midi(official)
        self.assertEqual(len(surface.sent),count)

    def test_session_pads_and_leds_stay_with_live(self):
        surface = self.surface
        surface.song.appointed_device = device()
        surface.update_display()
        first = next(p for p in surface.controls if p.original_identifier() == 40)
        first.emit(127)
        self.assertEqual(surface._krose.params["Arp"].value, 0)
        self.assertTrue(surface.component_map["Session"].is_enabled())
        self.assertTrue(surface.component_map["Drum_Group"].is_enabled())
        self.assertNotIn(bridge.pad(0, False), surface.sent)
        official = bridge.pad(0, True)
        surface._send_midi(official)
        self.assertEqual(surface.sent[-1], official)
        surface.song.appointed_device = None
        surface.update_display()
        self.assertNotIn(bridge.pad(0, False), surface.sent)

    def test_drum_program_routes_bank_b_and_restores_after_note_off(self):
        surface = self.surface
        surface.song.appointed_device = drum_kit = device()
        program = bridge.parameters(drum_kit)["Program"]
        program.value = 2
        surface.update_display()
        pads = [pad for pad, _ in surface.elements.pad_bank_b.iterbuttons()]
        self.assertTrue(surface.component_map["Session"].is_enabled())
        self.assertFalse(surface.component_map["Drum_Group"].is_enabled())
        self.assertEqual([pad.identifier for pad in pads], [36, 38, 42, 46, 45, 50, 49, 51])
        self.assertTrue(all(pad.channel == 9 and pad.script_forwarding == "non_consuming" for pad in pads))
        pads[0].emit(100)
        program.value = 1
        surface.update_display()
        self.assertEqual(pads[0].identifier, 36)
        pads[0].emit(0)
        surface.update_display()
        self.assertTrue(surface.component_map["Drum_Group"].is_enabled())
        self.assertTrue(all((pad.identifier, pad.channel, pad.script_forwarding) ==
                            (pad.number, 10, "exclusive") and not pad.listeners for pad in pads))

    def test_drum_pad_route_reconnect_and_disconnect(self):
        surface = self.surface
        surface.song.appointed_device = drum_kit = device()
        bridge.parameters(drum_kit)["Program"].value = 3
        surface.update_display()
        pad = surface._drum_pads[0]
        pad.emit(127)
        surface.port_settings_changed()
        self.assertEqual(pad.identifier, pad.number)
        surface.update_display()
        self.assertEqual(pad.identifier, 36)
        surface.disconnect()
        self.assertEqual(pad.identifier, pad.number)
        self.assertEqual(pad.listeners, [])


if __name__ == "__main__": main()
