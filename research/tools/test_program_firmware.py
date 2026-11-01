#!/usr/bin/env python3
"""Compare Program bit fields and playback-pitch calculation with original ARM."""
import json
import math
import struct

from program_firmware import ROOT, FW_SHA, Arm, Firmware


def main():
    firmware = Firmware()
    arm = Arm(firmware)
    program = (ROOT / "output/kep-analysis/Concert_SE_Grand/program.bin").read_bytes()
    comparisons = []
    for namespace in range(0x27, 0x60):
        for field in firmware.group(namespace, program):
            actual = arm.parameter(program[field["program_offset"]:], field["descriptor"])
            assert actual == field["value"], (namespace, field["index"], actual, field["value"])
            comparisons.append({"namespace": namespace, "index": field["index"],
                                "program_offset": field["program_offset"], "value": actual})
    # Verify the published semantic grouping as well as raw numeric reads.
    # OSC2 namespaces advance by 16, independently of the 380-byte block size.
    from analyze_concert_program import GROUP_NAMES
    analysis=json.loads((ROOT/'output/kep-analysis/Concert_SE_Grand/program-analysis.json').read_text())
    alignment_checks=0
    for osc_index,osc in enumerate(analysis['oscillators']):
        for namespace,name in GROUP_NAMES.items():
            expected=firmware.group(namespace+osc_index*16,program)
            actual=osc['groups'][name]
            assert [(x['namespace'],x['index'],x['program_offset'],x['value']) for x in actual]==[(x['namespace'],x['index'],x['program_offset'],x['value']) for x in expected],(osc_index,name)
            assert all(0x564+380*osc_index<=x['program_offset']<0x564+380*(osc_index+1) for x in actual)
            alignment_checks+=len(actual)
    fx_count = 0
    for effect_id, payload in [(7, 0x18), (7, 0x64), (3, 0x148), (64, 0x194), (105, 0x1D8)]:
        for parameter in firmware.effect(effect_id)["parameters"]:
            offset = payload + parameter["payload_offset"]
            expected = firmware.read_value(program, offset, parameter["descriptor"])
            assert arm.parameter(program[offset:], parameter["descriptor"]) == expected
            fx_count += 1
    uploads = []
    for effect_id in (3, 7, 64, 105):
        definition = firmware.effect(effect_id)
        context = 0x11005000
        arm.uc.mem_write(context, bytes(32))
        arm.uc.mem_write(context, b"\x01")  # buffered upload mode; no MMIO
        arm.call(0x5A51C, context, 0, 1, 0xC0000000 + definition["definition_offset"])
        code = bytes(arm.uc.mem_read(0xC0FEB1C8 + 0x100, definition["code_words_64"] * 8))
        constants = bytes(arm.uc.mem_read(0xC0FE9DC8, definition["constant_words_32"] * 4))
        assert code == firmware.data[definition["code_offset"]:definition["code_offset"] + len(code)]
        assert constants == firmware.data[definition["constants_offset"]:definition["constants_offset"] + len(constants)]
        uploads.append({"id": effect_id, "native_loader": "0x5a51c", "mode": "buffered, no TG/MMIO",
                        "code_words_64": len(code) // 8, "constant_words_32": len(constants) // 4,
                        "code_and_constants_equal": True})
    rates = []
    exponents = sorted(set(range(-0x8000, 0x6000, 131)) | {-32768, -1, 0, 1, 24575, 24576, 32767})
    for exponent in exponents:
        assert firmware.phase_increment(exponent) == arm.call(0x1FF348, exponent), exponent
    for pitch in (0, -295, -898, -1536, 1536):
        increment = arm.pitch_rate(pitch)
        direct = arm.call(0x1FF348, pitch * 2)
        assert increment == direct, (pitch, increment, direct)
        assert increment == firmware.phase_increment(pitch * 2)
        ideal = 48000 * 2 ** (pitch / 1536)
        rates.append({"pitch_field": pitch, "native_increment": increment,
                      "native_increment_at_48000_hz": 48000 * increment / 8192,
                      "ideal_log_rate_hz": ideal,
                      "quantization_difference_cents": 1200 * math.log2(increment / 8192 / (ideal / 48000))})
    assert rates[0]["native_increment"] == 8192
    assert rates[3]["native_increment"] == 4096
    assert rates[4]["native_increment"] == 16384
    result = {"firmware_sha256": FW_SHA, "parameter_getter": "0x20af84",
              "oscillator_semantic_group_alignment_checks":alignment_checks,
              "program_field_comparisons": comparisons, "effect_field_comparisons": fx_count,
              "effect_upload_comparisons": uploads,
              "phase_helper_comparisons": len(exponents),
              "rate_oracle": "0x1ff764 calls original 0x1ff38c and 0x1ff348; external MIDI/tone-adjust getters and pitch-EG update stubbed to zero",
              "rate_scope": "Synthetic zero-modulation/root-note contexts; no TG01 device or oscillator interpolation executed",
              "rates": rates}
    output = ROOT / "research/derived/verification/program-arm-comparison.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS {len(comparisons)} Program fields and {fx_count} effect fields against ARM getter")
    print("PASS four DSP program/constant bundles against original buffered upload routine")
    print(json.dumps(rates, indent=2))


if __name__ == "__main__":
    main()
