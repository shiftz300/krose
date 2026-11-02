#!/usr/bin/env python3
"""Original ARM Portamento enable overrides, Fingered gate and cache clearing."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import struct
from pathlib import Path
from program_firmware import Arm, Firmware, FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT = ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    f = Firmware()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('portamento-enable-cache', 0x1F5FE8, 0x1F61F8),
                         ('portamento-OSC-consistency', 0x2738E8, 0x2739A0)]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(output.getvalue())
    if not args.verify_arm:
        return
    a = Arm(f)
    osc, timbre, meta, program, manager, nodes, voices = [0x11000000+0x2000*i for i in range(7)]
    head = osc+0x490

    def word(p):
        return struct.unpack('<I', a.uc.mem_read(p, 4))[0]

    def half(p):
        return struct.unpack('<H', a.uc.mem_read(p, 2))[0]

    def put8(p, value):
        a.uc.mem_write(p, bytes([value & 255]))

    def put16(p, value):
        a.uc.mem_write(p, struct.pack('<H', value & 65535))

    def call(entry, *argv, **kwargs):
        return a.call(entry, *argv, **kwargs)

    a.write(osc+0x49C, timbre)
    a.write(osc+0x48C, manager)
    a.write(timbre+4, meta, program)
    a.write(0xC174567C, manager)
    a.stubs = {0x2788C0: lambda m: program}
    overrides = []
    for mode, index, enable0, enable1, allowed, override in itertools.product([0, 1], [0, 1], [0, 1], [0, 1], [0, 1], [-1, 0, 1]):
        put8(program+0x508, mode)
        for i, enable in enumerate([enable0, enable1]):
            put8(program+0x564+380*i+0x80, enable)
        params = program+0x564+380*index
        a.write(osc+8, params)
        put8(meta+0x19, allowed << 3)
        put8(timbre+0x48, override)
        original = [enable0, enable1][index]
        expected = original
        if allowed and override != -1:
            if override == 0:
                expected = 0
            elif mode == 0 or enable0 == enable1:
                expected = 1
        got = call(0x1F5FE8, osc, original)
        assert got == expected
        overrides.append(dict(mode=mode, oscillator=index, enable=[enable0, enable1], controller_allowed=bool(allowed),
                              override=override, result=got))
    # Read the previous-pitch argument at the actual manager boundary.
    dispatched = []

    def dispatch(m):
        dispatched.append(struct.unpack('<i', m.uc.mem_read(m.get('SP'), 4))[0])
        return 0

    def setup_voices(flags):
        a.write(head, head, head, 0)
        for i in reversed(range(len(flags))):
            v = voices+588*i
            a.uc.mem_write(v, bytes(588))
            a.write(v+0x240, 0xFFFFFFFF)
            put16(v+0x10, flags[i])
            put8(v+0x12, 60)
            a.write(nodes+12*i, 0, 0, v)
            call(0x272458, head, nodes+12*i)

    a.stubs = {0x1FDC8C: dispatch}
    put8(meta+0x19, 0)
    put8(program+0x508, 0x80)
    put8(program+0x50A, 0)
    params = program+0x564
    a.write(osc+8, params)
    put8(timbre+0x4F, 1)
    gates = []
    for legato, enabled, fingered, flags, cached in itertools.product([0, 1], [0, 1], [0, 1],
            [[], [0], [0x80], [0, 0x80]], [-1, 60*256]):
        put8(program+0x509, legato << 4)
        put8(params+0x80, enabled | (fingered << 1))
        put16(osc+0x4A0, cached)
        setup_voices(flags)
        dispatched.clear()
        call(0x1F62F0, osc, 0x644090)
        expected = cached if enabled and not (legato and fingered and not any(x & 0x80 for x in flags)) else -1
        assert dispatched == [expected]*(max(1, len(flags)) if legato else 1)
        gates.append(dict(legato=bool(legato), enabled=bool(enabled), fingered=bool(fingered),
                          old_flags=flags, cached=cached, manager_previous_pitch=list(dispatched)))
    # Original OSC Note Off and periodic state visit decide when the previous
    # pitch cache is invalidated. Manager bodies are fixed boundary responses.
    def release(m):
        v = m.get('R1')
        put16(v+0x10, half(v+0x10) & ~0x80)
        return 0

    a.stubs = {0x1FD4F4: release, 0x1FDC2C: lambda m: active}
    clears = []
    for enabled, fingered, held, match in itertools.product([0, 1], repeat=4):
        put8(params+0x80, enabled | (fingered << 1))
        put16(osc+0x4A0, 60*256)
        put16(timbre+0x46, held)
        setup_voices([0x80])
        call(0x1F60A4, osc, 0x80 | ((60 if match else 61) << 8))
        expected = 65535 if enabled and fingered and not held else 60*256
        assert half(osc+0x4A0) == expected
        assert bool(half(voices+0x10) & 0x80) == (not match)
        clears.append(dict(entry='NoteOff', enabled=bool(enabled), fingered=bool(fingered),
                           held_count=held, matching_note=bool(match), cache=expected))
    for enabled, fingered, active in itertools.product([0, 1], repeat=3):
        put8(params+0x80, enabled | (fingered << 1))
        put16(osc+0x4A0, 60*256)
        call(0x1F6038, osc)
        expected = 65535 if enabled and fingered and not active else 60*256
        assert half(osc+0x4A0) == expected
        clears.append(dict(entry='periodic', enabled=bool(enabled), fingered=bool(fingered),
                           manager_active=active, cache=expected))
    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False, override_cases=overrides,
                  note_on_gate_cases=gates, cache_clear_cases=clears,
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                  boundaries=['External bank lookup returns the fixture Program; original OSC-consistency helper executes',
                              'Original Note On/Off OSC and gate/list helpers execute; manager entry/return intercepted',
                              'Controller override values -1/0/1; single/double melodic OSC modes',
                              'Previous pitch 60*256 or sentinel -1; no actual TG audio'])
    (OUT/'portamento-gate-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, override_cases=len(overrides), note_on_gate_cases=len(gates),
                          cache_clear_cases=len(clears)), indent=2))


if __name__ == '__main__':
    main()
