import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import json
import sys

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


sys.path.insert(0, str(ROOT / "tools"))
bridge = module("device", ROOT / "controllers/shared/keylab-essential-mk3/device.py")
installer = module("installer", ROOT / "tools/install_ableton_controller.py")


class Parameter:
    def __init__(self, name, value=0, maximum=1, text=None):
        self.name = self.original_name = name
        self.value, self.min, self.max = value, 0, maximum
        self.is_enabled, self.is_quantized = True, maximum != 1
        self.gestures, self.text = 0, text

    def begin_gesture(self): self.gestures += 1
    def end_gesture(self): self.gestures -= 1
    def __str__(self): return self.text or str(self.value)


def device():
    names = set(filter(None, bridge.KNOBS + bridge.FADERS + bridge.PADS +
                ("Program", "EG Target", "IFX 1 Type", "IFX 2 Type", "MFX 1 Type", "MFX 2 Type", "FX Bypass", "SW1 Mode", "SW2 Mode")))
    names.add("IFX 1 Amount")
    params = [Parameter(name) for name in names]
    params += [Parameter("Program", 0, 3, "A000 Kross GrandPiano 1")]
    params += [Parameter("FX Edit",0,7)]
    return SimpleNamespace(parameters=params, name="Renamed synth")


class Controller(unittest.TestCase):
    def setUp(self):
        self.sent, self.now = [], 10
        self.feedback = bridge.DeviceFeedback(self.sent.append, [0, 3, 1, 2], lambda: self.now)
        self.feedback.bind(device())

    def tick(self, advance=.11):
        self.now += advance
        self.feedback.tick()

    def tap_fx(self,index):
        self.feedback.fx_edit(index,127)
        self.feedback.fx_edit(index,0)

    def test_mk3_wire_format(self):
        self.assertEqual(bridge.display("Cutoff", "+12")[:11], bridge.HEADER + (4, 1, 96, 18, 1))
        self.assertEqual(len(bridge.display("Cutoff", "+12")), 52)
        self.assertEqual(bridge.display_header("PROG")[:11], bridge.HEADER + (4,1,96,1,2))
        self.assertEqual(bridge.parameter_page("MFX 2 Send"), "FX / MFX 2")
        self.assertEqual(bridge.pad(0, True), bridge.HEADER + (4, 1, 22, 32, 48, 90, 90, 32, 247))
        self.assertEqual(bridge.relative(63), -1)
        self.assertEqual(bridge.relative(65), 1)

    def test_focus_timeout_deduplication(self):
        self.tick()
        self.assertIn(bridge.display_icon("A000 Kross G", "", 0x28), self.sent)
        self.assertIn(bridge.display_header("PROG"), self.sent)
        count = len(self.sent)
        self.tick()
        self.assertEqual(len(self.sent), count)
        self.feedback.knob(3, 127)
        self.tick(.01)
        self.assertEqual(len(self.sent), count)
        self.tick()
        self.assertIn(bridge.control_display(3,"Cutoff","1"), self.sent)
        self.tick(1.3)
        self.assertIn(bridge.display_icon("A000 Kross G", "",0x28), self.sent[count:])

    def test_long_name_scrolls_in_one_row_with_end_pauses(self):
        self.assertEqual(bridge.program_line("Breathy Bells",0), "Breathy Bell")
        self.assertEqual(bridge.program_line("Breathy Bells",1.6), "reathy Bells")
        self.assertEqual(bridge.program_line("Breathy Bells",2.7), "reathy Bells")
        self.assertEqual(bridge.program_line("Breathy Bells",2.8), "Breathy Bell")
        self.assertEqual(bridge.program_line("Short Piano",100), "Short Piano")
        self.tick()
        self.tick(1.6)
        self.assertIn(bridge.display_icon("000 Kross Gr", "",0x28),self.sent)

    def test_program_factory_order_and_multi_instance(self):
        self.assertTrue(bridge.is_krose(self.feedback.device))
        self.feedback.program(65)
        self.assertEqual(self.feedback.params["Program"].value, 3)
        self.feedback.program(63)
        self.assertEqual(self.feedback.params["Program"].value, 0)
        old = self.feedback.params["Cutoff"]
        self.feedback.bind(device())
        self.feedback.knob(3, 127)
        self.assertEqual(old.value, 0)
        self.feedback.clear()
        self.assertIsNone(self.feedback.device)
        self.assertIn(bridge.pad(7, False),self.sent[-12:])
        self.assertEqual(self.sent[-1],bridge.fx_button(3,(0,0,0)))

    def test_fader_takeover_and_gestures(self):
        p = self.feedback.params["Amp Attack"]
        p.value = .5
        self.feedback.fader(0, 0)
        self.assertEqual(p.value, .5)
        self.feedback.fader(0, 80)
        self.assertAlmostEqual(p.value, 80 / 127)
        self.assertEqual(p.gestures, 0)
        p.value = .95
        self.feedback.fader(0, 40)
        self.assertEqual(p.value, .95)

    def test_encoder_order_no_echo_and_filter_intensity(self):
        self.assertEqual(bridge.KNOBS[:6], ("Glide","Filter EG Intensity","Pan","Cutoff","Resonance","Velocity"))
        self.tick()
        self.sent.clear()
        self.feedback.knob(3,64)
        self.tick()
        self.assertFalse(any(m[:9] == bridge.HEADER+(2,15,64) and m[9]==6 for m in self.sent))
        self.tick(.3)
        self.feedback.params["Pan"].value = .8  # Software edits must not write back either.
        self.feedback.button(0,127)
        self.tick(.3)
        self.assertIn(bridge.control_display(3,"Cutoff",str(64 / 127)), self.sent)
        self.assertIn(bridge.pad(0,True), self.sent)
        program = self.feedback.params["Program"].value
        intensity = self.feedback.params["Filter EG Intensity"]
        for value in (0, 64, 127, 30):
            self.feedback.knob(1, value)
            self.assertAlmostEqual(intensity.value, intensity.min + value / 127 * (intensity.max - intensity.min))
            self.assertEqual(self.feedback.params["Program"].value, program)
        self.tick(2)
        self.assertFalse(any(m[:9] == bridge.HEADER+(2,15,64) for m in self.sent))

    def test_all_knobs_match_software_order_and_labels(self):
        self.assertEqual(bridge.KNOBS,("Glide","Filter EG Intensity","Pan","Cutoff","Resonance","Velocity","Output",None,None))
        self.assertEqual(bridge.KNOB_LABELS,("Glide","Filter EG Int","Pan","Cutoff","Resonance","Velocity","Volume","Unassigned","Unassigned"))
        self.assertEqual(bridge.parameter_label("Output"),"Volume")
        for index,name in enumerate(bridge.KNOBS):
            before={key:p.value for key,p in self.feedback.params.items()}
            self.feedback.knob(index,127)
            if name is not None: self.assertEqual(self.feedback.params[name].value,1)
            for key,p in self.feedback.params.items():
                if key!=name: self.assertEqual(p.value,before[key])

    def test_control_popup_cache_has_correct_labels_and_control_ids(self):
        self.assertEqual(bridge.control_display(6,"Volume","-6 dB"),
                         bridge.HEADER+(4,1,96,32,6,32,1)+tuple(b"Volume")+(0,2)+tuple(b"-6 dB")+(0,3,102,0,247))
        self.tick()
        for slot,cc in enumerate((*range(96,104),*range(105,113),104,113)):
            self.assertEqual(self.feedback.cache[("control",slot)][-3],cc)
        self.assertIn(bridge.control_display(7,"Unassigned","--"),self.sent)
        self.assertIn(bridge.control_display(16,"Unassigned","--"),self.sent)
        self.sent.clear()
        self.feedback.knob(6,127)
        self.tick()
        self.assertIn(bridge.control_display(6,"Volume","1"),self.sent)
        # Updating firmware popup text must neither recreate the whole page
        # nor send encoder position writes while the hand is still moving.
        self.assertFalse(any(m[:10]==bridge.HEADER+(4,1,96,0x19) for m in self.sent))
        self.assertFalse(any(m[:9]==bridge.HEADER+(2,15,64) for m in self.sent))

    def test_fast_quantized_faders_keep_takeover(self):
        for index, name in enumerate(bridge.FADERS):
            p = self.feedback.params[name]
            p.min, p.max, p.value, p.is_quantized = -99, 99, 0, True
            self.feedback.fader(index,0)
            self.assertEqual(p.value,0)
            for value in (80,110,127,95,40,0,90):
                self.feedback.fader(index,value)
                self.assertEqual(p.value,round(-99 + value / 127 * 198))
                self.assertEqual(p.gestures,0)
            p.value = 99  # Host automation must rearm even after a fast sweep.
            self.feedback.fader(index,40)
            self.assertEqual(p.value,99)
            self.feedback.fader(index,127)
            self.feedback.fader(index,20)
            self.assertEqual(p.value,round(-99 + 20 / 127 * 198))

    def test_eg_switch_changes_targets_labels_and_rearms_pickup(self):
        amp=self.feedback.params["Amp Attack"]
        flt=self.feedback.params["Filter Attack"]
        amp.value=flt.value=.5
        self.feedback.fader(0,0)
        self.feedback.fader(0,80)
        self.assertAlmostEqual(amp.value,80/127)
        self.feedback.params["Output"].value=.5
        self.feedback.fader(8,64)
        # Switch before a UI tick: the very next event must use FILTER.
        self.feedback.params["EG Target"].value=1
        self.feedback.fader(0,0)
        self.assertEqual(flt.value,.5)  # No crossing using the old bank's history.
        self.assertAlmostEqual(amp.value,80/127)
        self.assertTrue(self.feedback.pickup[8][1])  # Volume keeps takeover.
        self.feedback.fader(0,80)
        self.assertAlmostEqual(flt.value,80/127)
        self.tick()
        self.assertEqual(self.feedback.cache[("control",8)],bridge.control_display(8,"Flt Atk",str(flt)))
        self.assertEqual(self.feedback.cache[("control",12)],bridge.control_display(12,"Amp Atk",str(amp)))
        self.assertEqual([self.feedback.fader_name(i) for i in range(9)],
                         list(bridge.FADERS[4:8]+bridge.FADERS[:4]+bridge.FADERS[8:]))
        self.feedback.params["EG Target"].value=0
        self.feedback.fader(0,0)
        self.assertAlmostEqual(amp.value,80/127)
        self.feedback.fader(0,127)
        self.assertEqual(amp.value,1)
        self.assertAlmostEqual(flt.value,80/127)
        self.feedback.fader(8,20)
        self.assertAlmostEqual(self.feedback.params["Output"].value,20/127)
        self.tick()
        self.assertEqual(self.feedback.cache[("control",8)],bridge.control_display(8,"Amp Atk",str(amp)))

    def test_configure_added_parameters_rebinds(self):
        plugin = SimpleNamespace(parameters=[], name="Krose")
        self.feedback.bind(plugin)
        self.tick()
        self.assertEqual(self.sent[-1], bridge.display("Krose", "Configure in Live"))
        plugin.parameters = device().parameters
        self.tick()
        self.assertIn("Program", self.feedback.params)

    def test_normalized_program_parameter_and_held_switch_release(self):
        p = self.feedback.params["Program"]
        p.max, p.is_quantized = 1, False
        self.feedback.program(65)
        self.assertEqual(p.value, 1)  # Catalog index 3 out of 0..3.
        self.feedback.program(63)
        self.assertEqual(p.value, 0)
        self.feedback.params["SW1 Mode"].value = 1
        held = self.feedback.params["SW1"]
        self.feedback.button(6, 127)
        self.feedback.clear()
        self.assertEqual(held.value, 0)

    def test_switch_momentary_and_fx_bypass(self):
        self.feedback.params["SW1 Mode"].value = 1
        self.feedback.button(6, 127)
        self.assertEqual(self.feedback.params["SW1"].value, 1)
        self.feedback.button(6, 0)
        self.assertEqual(self.feedback.params["SW1"].value, 0)
        self.feedback.params["IFX 1 On"].value = 1
        self.feedback.params["IFX 1 Amount"].value = 0  # Zero wet is not the On switch.
        self.tick()
        self.assertIn(bridge.pad(2, True), self.sent)
        self.feedback.params["FX Bypass"].value = 1
        self.tick()
        self.assertIn(bridge.pad(2, False), self.sent)

    def test_fx_edit_buttons_colour_type_and_bypass(self):
        kind=self.feedback.params["IFX 1 Type"]
        kind.max,kind.value=10,4
        self.feedback.params["IFX 1 On"].value=1
        self.feedback.params["IFX 1 Amount"].value=0 # DRY still indicates enabled.
        self.tick()
        self.assertIn(bridge.fx_button(0,bridge.FX_COLOURS[4]),self.sent)
        for i,name in enumerate(bridge.FX_NAMES):
            before={key:p.value for key,p in self.feedback.params.items()}
            self.tap_fx(i)
            code=self.feedback.params["FX Edit"].value
            self.assertEqual(code%4,i)
            for key,p in self.feedback.params.items():
                if key!="FX Edit": self.assertEqual(p.value,before[key])
            self.feedback.fx_edit(i,0)
            self.assertEqual(self.feedback.params["FX Edit"].value,code)
            self.tap_fx(i)
            self.assertNotEqual(self.feedback.params["FX Edit"].value,code)
        self.tap_fx(0)
        self.tick()
        self.assertIn(bridge.display_icon("IFX 1","LIMITER",0x2f),self.sent)
        kind.value=3
        self.tick()
        self.assertEqual(self.feedback.cache[("fx-button",0)],bridge.fx_button(0,bridge.FX_COLOURS[3]))
        self.feedback.params["FX Bypass"].value=1
        self.tick()
        for i in range(4): self.assertEqual(self.feedback.cache[("fx-button",i)],bridge.fx_button(i,(0,0,0)))
        self.feedback.params["FX Bypass"].value=0
        kind.value=1
        self.tick()
        self.assertEqual(self.feedback.cache[("fx-button",0)],bridge.fx_button(0,(0,0,0)))
        self.assertEqual(len(set(bridge.FX_COLOURS[2:])),13)

    def test_normalized_fx_edit_parameter_repeats_same_slot(self):
        p=self.feedback.params["FX Edit"]
        p.max,p.is_quantized=1,False
        self.tap_fx(3)
        self.assertAlmostEqual(p.value,3/7)
        self.tap_fx(3)
        self.assertEqual(p.value,1)
        self.tick()
        self.assertIn(bridge.display_icon("MFX 2","HALL",0x2f),self.sent)

    def test_fx_long_press_toggles_once_and_short_press_edits(self):
        kind=self.feedback.params["IFX 1 Type"]
        kind.max,kind.value=10,2
        on=self.feedback.params["IFX 1 On"]
        on.value=1
        command=self.feedback.params["FX Edit"]
        self.feedback.fx_edit(0,127)
        self.assertEqual(command.value,0)  # Short action waits for release.
        self.tick(.3)
        self.feedback.fx_edit(0,127)  # Repeated key-down must not restart the hold.
        self.tick(.31)
        self.assertEqual(on.value,0)
        self.assertEqual(command.value,0)
        self.assertEqual(self.feedback.cache[("fx-button",0)],bridge.fx_button(0,(0,0,0)))
        self.tick(2)
        self.assertEqual(on.value,0)
        self.feedback.fx_edit(0,0)
        self.assertEqual(command.value,0)
        self.tap_fx(0)
        self.assertNotEqual(command.value,0)
        self.assertEqual(on.value,0)
        # Release without an intervening timer still resolves a long hold.
        self.feedback.fx_edit(0,127)
        self.now+=.61
        self.feedback.fx_edit(0,0)
        self.assertEqual(on.value,1)
        self.assertEqual(command.value,4)
        # A sound change cancels the old press, including its release.
        self.feedback.fx_edit(0,127)
        self.feedback.params["Program"].value=3
        self.tick(.7)
        self.feedback.fx_edit(0,0)
        self.assertEqual(on.value,1)
        self.assertEqual(command.value,4)

    def test_fx_hold_cancels_on_rebind_and_ignores_empty_slots(self):
        on=self.feedback.params["IFX 2 On"]
        kind=self.feedback.params["IFX 2 Type"]
        kind.max,kind.value=10,1
        self.feedback.fx_edit(1,127)
        self.tick(1)
        self.feedback.fx_edit(1,0)
        self.assertEqual(on.value,0)
        self.assertEqual(self.feedback.params["FX Edit"].value,0)
        self.feedback.fx_edit(0,127)
        self.feedback.bind(device())
        self.tick(1)
        self.feedback.fx_edit(0,0)
        self.assertEqual(self.feedback.params["FX Edit"].value,0)

    def test_install_contains_factory_order_and_preserves_backup(self):
        with tempfile.TemporaryDirectory() as root:
            library = Path(root)
            target = installer.install(library)
            self.assertTrue((target / "program_order.json").exists())
            self.assertEqual(json.loads((target / "programs.json").read_text())[1][:3],
                             ["A000", "Kross Grand Piano 1", "PIANO"])
            (target / "old.txt").write_text("user file")
            installer.install(library)
            self.assertTrue(list((library / "Krose Controller Backups").rglob("old.txt")))

    def test_default_configuration_has_every_hardware_parameter(self):
        with tempfile.TemporaryDirectory() as root:
            path = installer.install_parameter_configuration(Path(root))
            data = json.loads(path.read_text())
            params = data["groups"][0]["parameters"]
            self.assertEqual(len(params), 54)
            self.assertEqual(len({p["id"] for p in params}), 54)
            self.assertEqual(next(p["id"] for p in params if p["name"]=="EG Target"),194)
            self.assertTrue(set(filter(None,bridge.KNOBS + bridge.FADERS + bridge.PADS)).issubset({p["name"] for p in params}))
            self.assertEqual(data["device-id"], "device:vst3:instr:f2aee70d-00de-4f4e-4c6f-634953654731?n=Krose")
            self.assertFalse(any("value" in p for p in params))
            original = path.read_bytes()
            installer.install_parameter_configuration(Path(root))
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((Path(root) / "Krose Controller Backups").exists())

    def test_existing_parameter_layout_is_preserved_and_extended(self):
        with tempfile.TemporaryDirectory() as root:
            library = Path(root)
            path = installer.install_parameter_configuration(library)
            data = json.loads(path.read_text())
            original_parameter = {"id": 7, "name": "My Filter", "x-slot": 3, "y-slot": 2}
            data["groups"] = [{"name": "User controls", "parameters": [original_parameter]}]
            path.write_text(json.dumps(data))
            before = path.read_bytes()
            installer.install_parameter_configuration(library)
            merged = json.loads(path.read_text())
            self.assertEqual(merged["groups"][0]["parameters"][0], original_parameter)
            self.assertEqual(len(merged["groups"][0]["parameters"]), 54)
            self.assertEqual(next((library / "Krose Controller Backups").rglob("*.appc")).read_bytes(), before)
            merged["device-id"] = "device:vst3:instr:wrong-plugin"
            path.write_text(json.dumps(merged))
            wrong = path.read_bytes()
            with self.assertRaises(ValueError): installer.install_parameter_configuration(library)
            self.assertEqual(path.read_bytes(), wrong)

    def test_manufacturer_migration_preserves_custom_layout(self):
        with tempfile.TemporaryDirectory() as root:
            library = Path(root)
            path = installer.install_parameter_configuration(library)
            self.assertEqual(path.parts[-3:], ("maincore", "Krose", "Default.appc"))
            data = json.loads(path.read_text())
            data["groups"][0]["parameters"][0]["name"] = "My Tone"
            original = json.dumps(data).encode()
            legacy = library / installer.LEGACY_CONFIG_PATH
            legacy.parent.mkdir(parents=True)
            legacy.write_bytes(original)
            path.unlink()
            installer.install_parameter_configuration(library)
            self.assertEqual(json.loads(path.read_text()), data)
            self.assertEqual(legacy.read_bytes(), original)
            # A subsequent install prefers the current manufacturer's layout.
            data["groups"][0]["parameters"][0]["name"] = "New Tone"
            path.write_text(json.dumps(data))
            installer.install_parameter_configuration(library)
            self.assertEqual(json.loads(path.read_text()), data)


if __name__ == "__main__":
    unittest.main()
