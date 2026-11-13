"""Check optional host adapters with only the host API calls they may use."""
import shutil
import subprocess
import unittest

from test_ableton_controller import ROOT


class DawRouting(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is optional")
    def test_bitwig_input_only(self):
        script = ROOT / "controllers/bitwig/Krose MIDI.control.js"
        subprocess.run(["node", "-e", r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
let ports, filters;
const context = vm.createContext({
    loadAPI: version => assert.equal(version, 1),
    host: {
        defineController: (vendor, name) => assert.equal(vendor + "/" + name, "maincore/Krose MIDI"),
        defineMidiPorts: (...args) => { ports = args; },
        getMidiInPort: index => {
            assert.equal(index, 0);
            return {createNoteInput: (name, ...args) => { filters = args; }};
        }
    }
});
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
context.init();
assert.deepEqual(ports, [1, 0]);
assert.deepEqual(filters, ["8?????", "9?????", "A?????", "B?????", "C?????", "D?????", "E?????"]);
""", str(script)], check=True, timeout=10)

    @unittest.skipUnless(shutil.which("lua"), "Lua is optional")
    def test_reaper_changes_only_confirmed_krose_input(self):
        script = ROOT / "controllers/reaper/Krose_Set_MIDI_Input.lua"
        subprocess.run(["lua", "-", str(script)], input=r"""
local script = arg[1]
local function run(count, fxName, accepted, choice, afterPrompt)
    local track, other, writes, undo = {}, {}, {}, 0
    local selected, port, instance = track, "Keyboard", "{original}"
    local signature = {"Program", "Amp Attack", "Arp Latch", "IFX 1 Type", "MFX 2 On"}
    reaper = {
        CountSelectedTracks = function() return count end,
        GetSelectedTrack = function() return selected end,
        TrackFX_GetInstrument = function(t) assert(t == track); return 0 end,
        TrackFX_GetNamedConfigParm = function(_, _, key) assert(key == "fx_name"); return true, fxName end,
        TrackFX_GetNumParams = function() return #signature end,
        TrackFX_GetParamName = function(_, _, p) return true, signature[p + 1] end,
        TrackFX_GetFXGUID = function() return instance end,
        GetNumMIDIInputs = function() return 64 end,
        GetMIDIInputName = function(id)
            assert(id < 62)
            return id == 3, port
        end,
        GetUserInputs = function()
            if afterPrompt == "selection" then selected = other end
            if afterPrompt == "port" then port = "Different keyboard" end
            if afterPrompt == "instance" then instance = "{replacement}" end
            return accepted, choice
        end,
        ShowMessageBox = function() end,
        GetMediaTrackInfo_Value = function() return -1 end,
        SetMediaTrackInfo_Value = function(t, key, value)
            assert(t == track and key == "I_RECINPUT")
            writes[#writes + 1] = value
            return true
        end,
        Undo_OnStateChangeEx = function() undo = undo + 1 end
    }
    assert(loadfile(script))()
    return writes, undo
end
local writes, undo = run(1, "VST3i: Krose (maincore)", true, "3")
assert(#writes == 1 and writes[1] == 4096 + 3 * 32 and undo == 1)
assert(#run(2, "Krose", true, "3") == 0)
assert(#run(1, "Other", true, "3") == 0)
assert(#run(1, "Krose", false, "3") == 0)
assert(#run(1, "Krose", true, "63") == 0)
assert(#run(1, "Krose", true, "3", "selection") == 0)
assert(#run(1, "Krose", true, "3", "port") == 0)
assert(#run(1, "Krose", true, "3", "instance") == 0)
""", text=True, check=True, timeout=10)
