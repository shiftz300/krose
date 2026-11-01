#!/usr/bin/env python3
"""Extract version-locked Program fields, FX configuration and DSP resources.

Field values follow original firmware metadata (ARM getter comparison is a
separate test). Semantic labels use the parameter guide and voice-control
code; unlabelled fields remain present as field_N, without invented meanings.
"""
import contextlib
import hashlib
import json
import math
import struct

from firmware_inspect import inspect
from program_firmware import ROOT, FW_SHA, Firmware

GROUP_NAMES = {0x41: "multisamples", 0x42: "lfo1", 0x43: "lfo2", 0x44: "pitch",
               0x45: "filter_common", 0x46: "filter_a", 0x47: "filter_b", 0x48: "filter_eg",
               0x49: "filter_keyboard_tracking", 0x4A: "amp", 0x4B: "amp_eg",
               0x4C: "amp_keyboard_tracking", 0x4D: "pan_sends", 0x4E: "ams_mixer1", 0x4F: "ams_mixer2"}
# LFO and mixer group labels reflect the firmware's structure; their complete
# modulation semantics are outside this report. Basic names are individually
# supported by the control code, range metadata and parameter guide ordering.
FILTER_EG = ["start_level", "attack_time", "attack_level", "decay_time", "break_level",
             "slope_time", "sustain_level", "release_time", "release_level"]
AMP_EG = ["start_level", "attack_time", "attack_level", "decay_time", "break_level",
          "slope_time", "sustain_level", "release_time"]
LABELS = {
    0x45: {0: "routing"},
    # Confirmed by 0x1fb2b0/0x1fb3a4 and TG register packing, not UI order.
    0x46: {0: "type", 1: "bypass", 2: "trim", 3: "output", 6: "frequency", 7: "resonance",
           4: "output_ams_source", 5: "output_ams_intensity", 8: "resonance_ams_source",
           9: "resonance_ams_intensity", 10: "keyboard_tracking_intensity",
           11: "cutoff_ams1_source", 12: "cutoff_ams1_intensity", 13: "cutoff_ams2_source",
           14: "cutoff_ams2_intensity", 15: "eg_intensity", 16: "eg_velocity_intensity"},
    0x47: {0: "type", 1: "bypass", 2: "trim", 3: "output", 6: "frequency", 7: "resonance",
           4: "output_ams_source", 5: "output_ams_intensity", 8: "resonance_ams_source",
           9: "resonance_ams_intensity", 10: "keyboard_tracking_intensity",
           11: "cutoff_ams1_source", 12: "cutoff_ams1_intensity", 13: "cutoff_ams2_source",
           14: "cutoff_ams2_intensity", 15: "eg_intensity", 16: "eg_velocity_intensity"},
    0x48: {**dict(enumerate(FILTER_EG)), **{30 + i: "curve_" + n for i, n in enumerate(("attack", "decay", "slope", "release"))}},
    0x4A: {0: "level", 1: "velocity_intensity", 2: "ams_source", 3: "ams_intensity",
           4: "lfo1_intensity", 5: "lfo2_intensity", 6: "lfo1_ams_source", 7: "lfo1_ams_intensity",
           8: "lfo2_ams_source", 9: "lfo2_ams_intensity"},
    0x4B: {**dict(enumerate(AMP_EG)),
           8: "level_ams_source", 9: "start_ams_intensity", 10: "attack_ams_intensity", 11: "break_ams_intensity",
           **{12+5*i: "time_ams_source_"+str(i+1) for i in range(3)},
           **{13+5*i+j: "time_ams_"+str(i+1)+"_"+name for i in range(3) for j,name in enumerate(("attack","decay","slope","release"))},
           27: "reset_ams_source", 28: "reset_threshold",
           **{29 + i: "curve_" + n for i, n in enumerate(("attack", "decay", "slope", "release"))}},
    0x49: dict(enumerate(("key_low", "key_center", "key_high", "ramp_low_low", "ramp_low_center", "ramp_high_center", "ramp_high_high"))),
    0x4C: dict(enumerate(("key_low", "key_center", "key_high", "ramp_low_low", "ramp_low_center", "ramp_high_center", "ramp_high_high"))),
    0x4D: {0: "pan", 1: "pan_ams_source", 2: "pan_ams_intensity", 3: "send1", 4: "send2", 5: "use_drumkit_pan"},
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def display(firmware, parameter, raw):
    function = parameter["display_function"]
    label = parameter["label"].rstrip(":")
    if function == 0x741D0:
        return {"value": "Inf:1" if raw > 130 else f"{(raw + 10) / 10 if raw <= 90 else raw - 80:.1f}:1", "unit": "ratio"}
    if function == 0x676AC:
        return {"value": raw * 10, "unit": "degree"}
    if function == 0x9B34C:
        return {"value": raw / 10 if raw <= 99 else raw - 90, "unit": "ms"}
    if function in (0x9D3C0, 0x9D3A0):
        return {"value": ("Mid-Lo" if raw else "Low") if function == 0x9D3C0 else ("Mid-Hi" if raw else "High"), "unit": "EQ range"}
    if function in (0x7624C, 0x7625C, 0x7626C, 0x76280):
        multiplier, offset = {0x7624C: (10, 20), 0x7625C: (10, 50), 0x7626C: (100, 300), 0x76280: (100, 500)}[function]
        return {"value": raw * multiplier + offset, "unit": "Hz"}
    if function == 0x9B0B4:
        return {"value": (raw + 5) / 10, "unit": "Q"}
    if function == 0x9B180:
        return {"value": raw / 2, "unit": "dB"}
    if function == 0x9CFD4:
        return {"value": raw / 10, "unit": "s"}
    if function == 0x9AF10:
        a = abs(raw)
        value = 2 * a if a <= 99 else 5 * a - 300 if a <= 159 else 10 * a - 1100 if a <= 209 else 50 * a - 9500
        return {"value": (-value if raw < 0 else value) / 100, "unit": "Hz"}
    if function == 0x9B3BC:
        return {"value": firmware.string(firmware.pointer(0x336CD0 + 4 * raw)), "unit": "Dmod source"}
    if function == 0x9B3CC:
        return {"value": ("Triangle", "Sine")[raw], "unit": "waveform"}
    if function == 0x9B3EC:
        return {"value": bool(raw), "unit": "switch"}
    if function == 0x9B050:
        return {"value": "Dry" if raw == 0 else "Wet" if raw == 100 else "-Wet" if raw == -100 else f"{raw}:{100-raw}" if raw > 0 else f"{raw}:{100+raw}", "unit": "Wet/Dry"}
    if function == 0x7CB0C:
        return {"value": "-Inf" if raw == -39 else raw, "unit": "dB"}
    if label in ("Thrsh[dB]", "Gain[dB]", "LEQ [dB]", "HEQ [dB]"):
        # Unscaled threshold/gain in the limiter; EQ half-dB values handled above.
        return {"value": raw, "unit": "dB"}
    return None


def extract_effect(firmware, effect_id, destination):
    effect = firmware.effect(effect_id)
    destination.mkdir(parents=True, exist_ok=True)
    for name, offset, size in (("dsp-code.u64le.bin", effect["code_offset"], effect["code_words_64"] * 8),
                               ("initial-constants.u32le.bin", effect["constants_offset"], effect["constant_words_32"] * 4)):
        data = firmware.data[offset:offset + size]
        (destination / name).write_bytes(data)
        effect[name] = {"firmware_offset": offset, "bytes": size, "sha256": hashlib.sha256(data).hexdigest()}
    words = struct.iter_unpack("<II", (destination / "dsp-code.u64le.bin").read_bytes())
    (destination / "dsp-code.words.txt").write_text("# Raw word pairs, not a decoded ISA\n" + "\n".join(
        f"{i:03d} {low:08x} {high:08x}" for i, (low, high) in enumerate(words)) + "\n")
    with (destination / "arm-control.arm.txt").open("w") as out:
        out.write("KROSS 2 v1.2.4 file offsets; excerpts at the three ARM control entries, not DSP audio code\n")
        for entry in effect["arm_functions"]:
            # Deliberately bounded context; not a claim of exact function length.
            out.write(f"\n# entry {entry:#x}, 0x300-byte context\n")
            with contextlib.redirect_stdout(out):
                inspect(firmware.data, entry, entry + 0x300)
    effect["interpretation"] = {"dsp_code": "8-byte stored words copied by 0x5a51c; 0x12daac uploads 48 payload bits per word via 0x12e9d8, ignoring halfword at +2; ISA not decoded",
                                "constants": "32-bit coefficient words copied by 0x5a51c; updated by ARM control routines",
                                "audio_emulation_status": "No host DSP interpreter or bit-exact effect render yet"}
    write_json(destination / "definition.json", effect)
    return effect


def main():
    firmware = Firmware()
    folder = ROOT / "output/kep-analysis/Concert_SE_Grand"
    program = (folder / "program.bin").read_bytes()
    if hashlib.sha256(program).hexdigest() != "a52ae2deebe0a0997bb50d50b3b26c1e40bd278567068e6afc85ae20e09222e4":
        raise ValueError("Unexpected target Program")
    catalog = []
    for namespace in range(0x27, 0x60):
        catalog.extend(firmware.group(namespace, program))
    write_json(ROOT / "research/derived/firmware/KROSS2_V124/program-parameter-catalog.json",
               {"firmware_sha256": FW_SHA, "program_ram_base": "0xc1666c88", "parameter_group_table": "0x407bd0", "fields": catalog})
    oscillators = []
    for osc_index in range(2):
        groups = {}
        for namespace, name in GROUP_NAMES.items():
            # Firmware namespaces include a separate key-tracking group at
            # 0x50; OSC2 starts at 0x51, so the stride is 16, not 15.
            fields = firmware.group(namespace + osc_index * 16, program)
            for field in fields:
                labels = LABELS.get(namespace, {})
                field["name"] = labels.get(field["index"], f"field_{field['index']}")
                field["label_status"] = "semantic correspondence to control code and parameter guide" if field["index"] in labels else "raw firmware field, semantic name unresolved"
                if field["descriptor"]["maximum"] == 46 and field["descriptor"]["minimum"] == 0:
                    pointer = firmware.pointer(0x3D9B10 + field["value"] * 4)
                    raw_label = firmware.data[pointer:firmware.data.index(b"\0", pointer)]
                    field["ams_source_label"] = " ".join(raw_label.decode("ascii", errors="ignore").split())
                    field["ams_source_label_raw_hex"] = raw_label.hex()
            groups[name] = fields
        base = 0x564 + osc_index * 380
        slots = []
        for index in range(4):
            off = base + index * 8
            enabled = bool(program[off] & 1)
            slots.append({"slot": index + 1, "enabled": enabled, "bank": program[off + 1],
                          "number": struct.unpack_from("<H", program, off + 2)[0], "level": program[off + 4],
                          "bottom_velocity": program[base + 0x20 + index * 4] if index < 3 else 1,
                          "crossfade_width": program[base + 0x21 + index * 4] if index < 3 else 0,
                          "crossfade_curve_raw": program[base + 0x22 + index * 4] & 3 if index < 3 else 0})
        assert [s["crossfade_width"] for s in slots] == [0, 0, 0, 0]
        zones = [{"velocity_low": 1, "velocity_high": 85, "slot": 3, "layer": "mf", "level": 119},
                 {"velocity_low": 86, "velocity_high": 106, "slot": 2, "layer": "f", "level": 119},
                 {"velocity_low": 107, "velocity_high": 127, "slot": 1, "layer": "ff", "level": 127}]
        assert [s["bottom_velocity"] for s in slots[:3]] == [107, 86, 1]
        oscillators.append({"oscillator": osc_index + 1, "base_offset": base, "slots": slots,
                            "velocity_zones": zones,
                            "velocity_status": "Derived from firmware-verified Bottom Velocity and zero crossfade fields; full note-on engine not executed",
                            "groups": groups})
    # Every corresponding OSC field must retain its descriptor and advance by
    # exactly the 380-byte oscillator block, independent of semantic labels.
    for name in GROUP_NAMES.values():
        left, right = [osc['groups'][name] for osc in oscillators]
        assert len(left) == len(right), name
        for a,b in zip(left,right):
            assert a['index']==b['index'] and b['program_offset']-a['program_offset']==380, name
            # Callback pointers may be oscillator-specific; value encodings,
            # ranges and flags must match.
            assert a['descriptor']['raw_hex'][:32]==b['descriptor']['raw_hex'][:32], name
    resources = {}
    resource_root = ROOT / "research/derived/firmware/KROSS2_V124/effects"
    for effect_id in (3, 7, 64, 105):
        resources[effect_id] = extract_effect(firmware, effect_id, resource_root / f"{effect_id:03d}")
    effects = []
    for index in range(7):
        payload = 0x18 + 76 * index if index < 5 else (0x194, 0x1D8)[index - 5]
        header = payload + 64
        effect_id = program[header]
        item = {"slot": f"IFX{index + 1}" if index < 5 else f"MFX{index - 4}",
                "id": effect_id, "payload_offset": payload, "header_offset": header,
                "enabled": bool(program[header + 1] & 64), "header_raw_hex": program[header:header + (12 if index < 5 else 4)].hex()}
        if index < 5:
            item.update({"chain_enabled": bool(program[header + 1] & 128), "chain_to_ifx": program[header + 2],
                         "pan": program[header + 4], "output_bus_raw": program[header + 5] & 7,
                         "send1": program[header + 6], "send2": program[header + 7]})
        if effect_id in resources:
            definition = resources[effect_id]
            item["name"] = definition["name"]
            item["parameters"] = []
            for parameter in definition["parameters"]:
                off = payload + parameter["payload_offset"]
                raw = firmware.read_value(program, off, parameter["descriptor"])
                item["parameters"].append({**parameter, "program_offset": off, "value": raw,
                                            "display": display(firmware, parameter, raw)})
        else:
            item.update({"name": "No Effect", "parameters": []})
        effects.append(item)
    original_a, original_b = program[0x564:0x6E0], program[0x6E0:0x85C]
    differences = [{"relative_offset": i, "osc1": a, "osc2": b} for i, (a, b) in enumerate(zip(original_a, original_b)) if a != b]
    result = {"name": "Concert SE Grand", "firmware_sha256": FW_SHA,
              "program_sha256": hashlib.sha256(program).hexdigest(),
              "user_feedback": {"date": "2026-10-31", "statement": "这个听起来完全没问题", "scope": "User acceptance of prior dry-sample preview; not a recorded hardware A/B"},
              "oscillators": oscillators, "oscillator_block_differences": differences,
              "effects": effects,
              "routing": {"program_output_bus_raw": program[0x50F], "program_output_bus": "IFX1",
                          "main_piano_path": ["OSC1+OSC2", "IFX1 Stereo Parametric 4EQ", "IFX2 Stereo Parametric 4EQ", "L/R"],
                          "master_sends_from_ifx2": [program[0xAA], program[0xAB]],
                          "master_returns_raw": [program[0x21C], program[0x21D]], "master_chain_raw": program[0x21E],
                          "limiter_scope": "IFX5 enabled but outside the main piano chain; do not insert it serially by default",
                          "mfx_dry_scope": "Master effects output only the wet component, according to the official parameter guide"},
              "remaining": ["Optional deeper decoding of 48-bit DSP upload payload and hardware rounding; not an acceptance requirement",
                            "Envelope time indices to actual durations under AMS and keyboard/velocity tracking",
                            "Full filter cutoff/response coefficient semantics", "Recorded hardware A/B"]}
    result["reconstruction_target"] = {
        "user_direction_date": "2026-10-31",
        "acceptance": "Perceptually close, useful in a DAW, one or several related piano tones; exact whole-instrument/chip emulation is not required",
        "effects_prototype": "output/Concert_SE_Grand_Effects/manifest.json",
        "host_dsp_source": "src/dsp/concert_effects.c"
    }
    write_json(folder / "program-analysis.json", result)
    increment = firmware.phase_increment(-295 * 2)
    write_json(folder / "sample-rate-analysis.json", {
        "firmware_sha256": FW_SHA, "pitch_field": -295,
        "pitch_setup": "0x1ff764", "pitch_update": "0x1ff38c", "phase_helper": "0x1ff348",
        "base_output_rate_hz": 48000, "phase_increment": increment, "unity_increment": 8192,
        "effective_root_playback_rate_hz": 48000 * increment / 8192,
        "existing_wav_header_rate_hz": 42017,
        "existing_wav_difference_cents": 1200 * math.log2(42017 / (48000 * increment / 8192)),
        "scope": "Original ARM verified at root note with unrelated modulation stubbed to zero; 48 kHz clock basis; no physical clock measurement or TG interpolation emulation",
        "validation_report": "research/derived/verification/program-arm-comparison.json",
        "existing_wav_policy": "Accepted WAV files remain byte-identical; header reflects earlier ideal-log-rate rounding. Use native phase increments in a future renderer.",
        "recording_rate": "Original pre-compression studio recording rate cannot be determined from this playback calculation"
    })
    print(f"Wrote {len(catalog)} static Program fields, two oscillator analyses, seven FX slots and four DSP resource bundles")
    for e in effects:
        print(e["slot"], e["name"], "on" if e["enabled"] else "off")


if __name__ == "__main__":
    main()
