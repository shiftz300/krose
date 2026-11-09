"""The generic Live template must touch only the selected Krose, with no egress."""
import contextlib
import importlib.util
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import patch
from test_ableton_controller import ROOT, device


class GenericTemplate(unittest.TestCase):
    def test_selected_device_only_and_listener_cleanup(self):
        class ControlSurface:
            def __init__(self, instance): self.selected = None
            def song(self): return SimpleNamespace(appointed_device=self.selected)
            def component_guard(self): return contextlib.nullcontext()
            def disconnect(self): pass
        class Encoder:
            def __init__(self, *args): self.listeners = []
            def add_value_listener(self, listener): self.listeners.append(listener)
            def remove_value_listener(self, listener): self.listeners.remove(listener)
        framework = ModuleType('_Framework')
        base, encoder, inputs, live = [ModuleType(n) for n in ('base', 'encoder', 'inputs', 'Live')]
        base.ControlSurface, encoder.EncoderElement, inputs.MIDI_CC_TYPE = ControlSurface, Encoder, 1
        live.MidiMap = SimpleNamespace(MapMode=SimpleNamespace(absolute=0))
        modules = {'_Framework': framework, '_Framework.ControlSurface': base,
                   '_Framework.EncoderElement': encoder, '_Framework.InputControlElement': inputs, 'Live': live}
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('generic_template',
                ROOT / 'controllers/templates/ableton/Krose_Generic_Template/surface.py')
            template = importlib.util.module_from_spec(spec); spec.loader.exec_module(template)
            surface = template.KroseGenericTemplate(None)
            first, second = device(), device()
            surface.selected = first
            surface._value('Cutoff', 127)
            param = next(p for p in first.parameters if p.name == 'Cutoff')
            self.assertEqual(param.value, 1)
            surface.selected = second
            surface._value('Cutoff', 0)
            self.assertEqual(param.value, 1)
            surface.selected = SimpleNamespace(parameters=[param])  # Different synth.
            surface._value('Cutoff', 0)
            self.assertEqual(param.value, 1)
            surface.selected = first
            surface._value('Cutoff', 128)
            self.assertEqual(param.value, 1)
            self.assertEqual(param.gestures, 0)
            elements = [e for e, _ in surface._bindings]
            surface.disconnect()
            self.assertTrue(all(not e.listeners for e in elements))


if __name__ == '__main__': unittest.main()
