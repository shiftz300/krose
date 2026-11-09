"""Exercise the bundled bridge with FL's normalized parameter and MIDI APIs."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys

from test_controller_resources import builder, module


class FLController(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        kit = Path(scratch.name) / "Controllers"
        builder.build(kit)
        builder.verify(kit)
        cls.folder = kit / builder.FL_SCRIPT

    def setUp(self):
        self.selected, self.now, self.assigned = 0, 0, True
        self.name = "KL Essential 49 mk3 (MIDI)"
        self.messages, self.transport = [], []
        names = ("Program", "Amp Attack", "Filter Attack", "Arp", "Arp Latch", "EG Target",
                 "FX Edit", "IFX 1 Type", "IFX 1 On", "MFX 2 On", "Filter EG Intensity",
                 "SW1", "SW1 Mode", "Cutoff")
        self.values = [dict.fromkeys(names, 0.0) for _ in range(2)]
        for values in self.values:
            values.update({"Amp Attack": .5, "Filter Attack": .5, "IFX 1 Type": .2,
                           "IFX 1 On": 1., "SW1 Mode": 1.})
        def get_value(parameter, index, slot, use_global):
            self.assertEqual((slot, use_global), (-1, True))
            return self.values[index][names[parameter]]

        def set_value(value, parameter, index, slot, pickup, use_global):
            self.assertEqual((slot, pickup, use_global), (-1, 0, True))
            self.values[index][names[parameter]] = value

        def send(message):
            self.assertIsInstance(message, bytes)
            self.assertEqual((message[0], message[-1]), (240, 247))
            self.messages.append(message)

        mocks = {
            "channels": SimpleNamespace(channelNumber=lambda _: self.selected),
            "device": SimpleNamespace(getName=lambda: self.name, isAssigned=lambda: self.assigned,
                                      midiOutSysex=send),
            "general": SimpleNamespace(getVersion=lambda: 26),
            "midi": SimpleNamespace(FPT_TapTempo=1, FPT_LoopRecord=2, FPT_Metronome=3, PIM_None=0,
                                    PL_Start=0, CE_New=0, CE_Delete=1, CE_Replace=2),
            "plugins": SimpleNamespace(
                isValid=lambda index, *_: 0 <= index < 3,
                getPluginName=lambda index, *_: "Krose" if index < 2 else "Other",
                getParamCount=lambda *_: len(names),
                getParamName=lambda parameter, *_: names[parameter],
                getParamValue=get_value, setParamValue=set_value, getParamValueString=lambda *_: "",
            ),
            "transport": SimpleNamespace(stop=lambda: self.transport.append("stop"),
                                         start=lambda: self.transport.append("start"),
                                         record=lambda: self.transport.append("record"),
                                         globalTransport=lambda *args: self.transport.append(args)),
            "krose_catalog": module("krose_catalog", self.folder / "krose_catalog.py"),
            "krose_keylab": module("krose_keylab", self.folder / "krose_keylab.py"),
        }
        with patch.dict(sys.modules, mocks):
            self.bridge = module("fl_krose", self.folder / "device_krose_keylab.py")
        self.bridge.monotonic = lambda: self.now
        self.bridge.OnInit()
        self.bridge.surface.clock = lambda: self.now

    def event(self, status, number, value):
        event = SimpleNamespace(status=status, data1=number, data2=value, handled=False, pmeflags=1)
        count = len(self.messages)
        self.bridge.OnMidiMsg(event)
        self.assertEqual(len(self.messages), count)  # SysEx only from idle, never from input.
        return event.handled

    def idle(self, elapsed=.11):
        self.now += elapsed
        self.bridge.OnIdle()

    def test_input_routing_pickup_and_transport(self):
        self.idle()
        self.assertIn(bytes((240, 0, 32, 107, 127, 66, 2, 15, 64, 90, 1, 247)), self.messages)
        for status, number in [(0x90, 60), (0x80, 60), (0xe0, 0), (0xb0, 1), (0xb0, 64)]:
            self.assertFalse(self.event(status, number, 64))
        self.assertTrue(self.event(0xb0, 21, 127))
        self.assertEqual(self.transport, ["start"])
        self.assertTrue(self.event(0xb0, 97, 127))
        self.assertEqual(self.values[0]["Filter EG Intensity"], 1.)
        self.assertTrue(self.event(0xb0, 105, 127))
        self.assertEqual(self.values[0]["Amp Attack"], .5)
        self.event(0xb0, 105, 63)
        self.event(0xb0, 105, 127)
        self.assertEqual(self.values[0]["Amp Attack"], 1.)
        self.values[0]["EG Target"] = 1.
        self.event(0xb0, 105, 64)
        self.event(0xb0, 105, 0)
        self.assertEqual(self.values[0]["Filter Attack"], 0.)
        self.selected = 1
        self.event(0xb0, 97, 64)
        self.assertEqual(self.values[1]["Filter EG Intensity"], 64 / 127)
        self.selected = 2
        self.assertFalse(self.event(0xb0, 97, 0))

    def test_preset_fx_and_connection_lifecycle(self):
        self.idle()
        self.assertTrue(self.event(0xb0, 116, 65))
        order = self.bridge.surface.order
        self.assertEqual(round(self.values[0]["Program"] * (len(order) - 1)),
                         order[(order.index(0) + 1) % len(order)])
        self.event(0xb0, 44, 127)
        self.event(0xb0, 44, 0)
        self.assertEqual(self.values[0]["FX Edit"], 4 / 7)
        self.event(0xb0, 44, 127)
        self.idle(.7)
        self.assertEqual(self.values[0]["IFX 1 On"], 0.)
        self.event(0xb0, 44, 0)
        self.assertEqual(self.values[0]["FX Edit"], 4 / 7)
        self.event(0x9a, 38, 127)
        self.assertEqual(self.values[0]["SW1"], 1.)
        self.selected = 1
        self.assertTrue(self.event(0x8a, 38, 64))
        self.assertEqual(self.values[0]["SW1"], 0.)
        self.assertEqual(self.values[1]["SW1"], 0.)
        self.event(0x9a, 40, 127)
        self.assertEqual(self.values[1]["Arp"], 1.)
        self.event(0x8a, 40, 0)
        self.assigned = False
        self.idle()
        self.messages.clear()
        self.assigned = True
        self.idle()
        self.assertTrue(any(message[8:10] == bytes((22, 32)) and any(message[10:13])
                            for message in self.messages))
        self.name = "KL Essential 49 mk3 (MCU/HUI)"
        self.assertFalse(self.event(0xb0, 97, 0))
