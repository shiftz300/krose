#!/usr/bin/env python3
"""Original ARM Unison dispatch, detune tables and phase increment checks."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import math
import struct
from pathlib import Path
from program_firmware import Arm, Firmware, FW_SHA, BASE
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT = ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    f = Firmware()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('unison-OSC-dispatch', 0x1F62F0, 0x1F6588),
                         ('unison-pitch-update', 0x1FF38C, 0x1FF764),
                         ('unison-spread-table', 0x1FFEB0, 0x20006C),
                         ('unison-parameter-getters', 0x275688, 0x27575C)]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(output.getvalue())
    if not args.verify_arm:
        return
    a = Arm(f)

    def word(p):
        return struct.unpack('<I', a.uc.mem_read(p, 4))[0]

    def byte(p):
        return a.uc.mem_read(p, 1)[0]

    def put8(p, v):
        a.uc.mem_write(p, bytes([v & 255]))

    def call(entry, *argv, **kwargs):
        return a.call(entry, *argv, **kwargs)

    osc, params, timbre, meta, program, manager = [0x11000000+0x1000*i for i in range(6)]
    oldnodes, oldvoices, newnodes, newvoices, region = [0x11010000+0x10000*i for i in range(5)]
    calls, returned_nodes, create_chain = [], [], [0]

    def dispatch(m):
        previous = m.get('R3')
        index = byte(osc+0x4A2)
        calls.append(dict(index=index if index < 128 else index-256,
                          previous=(previous-oldvoices)//588 if previous else None,
                          previous_pitch=struct.unpack('<i', m.uc.mem_read(m.get('SP'), 4))[0]))
        head = 0
        for j in reversed(range(create_chain[0])):
            slot = (len(calls)-1)*2+j
            node, voice = newnodes+12*slot, newvoices+588*slot
            m.write(node, head, 0, voice)
            m.write(voice+0x22C, region)
            put8(voice+0x16, slot)
            head = node
            returned_nodes.append(node)
        return head

    a.stubs = {0x1FDC8C: dispatch, 0x1F5CF4: lambda m: 0}
    dispatch_rows = []
    for count, mono, legato, enabled, existing, first in itertools.product(range(2, 7), [0, 1], [0, 1], [0, 1], [0, 1, 2, 6, 8], [0, 1]):
        a.uc.mem_write(osc, bytes(0x600))
        a.uc.mem_write(params, bytes(0x200))
        a.uc.mem_write(timbre, bytes(0x100))
        a.uc.mem_write(meta, bytes(0x100))
        a.uc.mem_write(program, bytes(0x900))
        a.write(osc+8, params)
        a.write(osc+0x48C, manager)
        a.write(osc+0x49C, timbre)
        a.write(timbre+4, meta, program)
        put8(timbre+0x4F, first)
        put8(program+0x508, mono << 7)
        put8(program+0x509, legato << 4)
        put8(program+0x50A, (enabled << 7) | count)
        head = osc+0x490
        a.write(head, head, head, 0)
        for i in reversed(range(existing)):
            a.write(oldnodes+12*i, 0, 0, oldvoices+588*i)
            call(0x272458, head, oldnodes+12*i)
        calls.clear()
        create_chain[0] = 0
        call(0x1F62F0, osc, 0x643C90)
        if mono and enabled:
            n = max(count, existing)
            indices = [max(0, count-1-i) for i in range(n)]
            previous = [i if i < existing else None for i in range(n)]
        elif mono and legato:
            n = existing or first
            indices, previous = [-1]*n, list(range(existing)) if existing else [None]*n
        else:
            indices, previous = [-1], [0 if existing else None]
        assert [r['index'] for r in calls] == indices
        assert [r['previous'] for r in calls] == previous
        assert all(r['previous_pitch'] == -1 for r in calls)
        dispatch_rows.append(dict(voices=count, mono=bool(mono), legato=bool(legato), enabled=bool(enabled),
                                  existing=existing, first=bool(first), calls=list(calls)))
    # With no existing voices, concatenate each manager result and then insert
    # the complete group into the OSC list using original list helpers.
    chain_rows = []
    for count, width in itertools.product(range(2, 7), [1, 2]):
        put8(program+0x508, 0x80)
        put8(program+0x50A, 0x80 | count)
        a.write(head, head, head, 0)
        a.uc.mem_write(newvoices, bytes(12*588))
        calls.clear()
        returned_nodes.clear()
        create_chain[0] = width
        call(0x1F62F0, osc, 0x643C90)
        actual, current, previous = [], word(head), head
        while current != head:
            assert current not in actual and word(current+4) == previous
            actual.append(current)
            previous, current = current, word(current)
        assert word(head+4) == previous
        expected_slots = [2*i+j for i in range(count) for j in range(width)]
        assert actual == [newnodes+12*i for i in reversed(expected_slots)]
        assert all(byte(word(node+8)+0x17) == 0 for node in actual)
        chain_rows.append(dict(voices=count, nodes_per_manager_call=width, final_nodes=len(actual), common_group_id=0))
    a.stubs = {}
    # The table helper implements 2..16 voices, beyond the 2..6 UI range.
    tables, table_cases = [], 0
    for count in range(2, 17):
        table = f.u32(0x200030+4*(count-2))-BASE
        rows = []
        for thickness in range(10):
            expected = list(struct.unpack_from('<'+str(count)+'h', f.data, table+2*count*thickness))
            actual = [call(0x1FFEB0, count, i, thickness) for i in range(count)]
            assert actual == expected
            assert actual[0] == -8192 and actual[-1] == 8192
            assert actual == sorted(actual)
            rows.append(actual)
            table_cases += count
        tables.append(dict(voices=count, table_offset=hex(table), UI_available=count <= 6, thickness_rows=rows))
    for count in [0, 1, 17, 32, 255]:
        assert call(0x1FFEB0, count, 0, 0) == 0
    # Original complete pitch initializer/update, with unrelated modulation
    # getters and pitch-EG update fixed to zero. The Unison getter stays live.
    voice, context, oscparams, part, controls, oscruntime, sample, pitchctx, patch = [0x11080000+i*0x2000 for i in range(9)]
    a.uc.mem_write(voice, bytes(0x12000))
    a.write(voice+4, oscruntime, context)
    a.write(voice+0x20, sample)
    a.write(voice+0x21C, patch, 0, oscparams)
    a.write(context+4, part)
    a.write(context+0x8C, controls)
    put8(sample+7, 0x11)
    a.write(sample+0x14, 0, 4095)
    a.stubs = {offset: lambda m: 0 for offset in [0x2753DC, 0x2754AC, 0x274DC4, 0x1F8A64, 0x1FFDE8]}
    from unicorn import UC_HOOK_CODE
    exponents = []

    def exponential_entry(uc, address, size, unused):
        value = a.get('R0')
        exponents.append(value-2**32 if value & 0x80000000 else value)

    hook = a.uc.hook_add(UC_HOOK_CODE, exponential_entry, begin=BASE+0x1FF348, end=BASE+0x1FF348)
    pitch_cases, examples = 0, []
    for count, thickness, detune in itertools.product(range(2, 7), range(10), range(100)):
        put8(patch+0x50A, 0x80 | count)
        put8(patch+0x50B, detune)
        put8(patch+0x50C, thickness)
        row = []
        for index in range(count):
            put8(oscruntime+0x4A2, index)
            exponents.clear()
            call(0x1FF764, pitchctx, voice, 60*256, 0, stack=(sample, 60*256, 0, 0))
            coefficient = tables[count-2]['thickness_rows'][thickness][index]
            expected_exponent = (detune*coefficient*331) >> 22
            expected_increment = f.phase_increment(expected_exponent)
            assert len(exponents) == 4 and exponents[0] == exponents[2] == expected_exponent, exponents
            assert word(pitchctx+0x18) == expected_increment
            assert byte(pitchctx+0x2C) == index and byte(pitchctx+0x2D) == count
            pitch_cases += 1
            row.append(dict(index=index, coefficient=coefficient, exponent=expected_exponent,
                            phase_increment=expected_increment, rate_cents=1200*math.log2(expected_increment/8192)))
        if count in [3, 4, 6] and thickness in [0, 1, 9] and detune in [24, 99]:
            examples.append(dict(voices=count, thickness=thickness, detune=detune, results=row))
    a.uc.hook_del(hook)
    # Repeat representative spreads through complete voice initialization with
    # two real Concert OSC parameter blocks and a real ROM region/sample.
    from voice_firmware import VoiceOracle
    oracle = VoiceOracle()
    a = oracle.arm
    a.stubs[0x275564] = lambda m: 0
    sample, region, clock = 0x11050000, 0x11051000, 0x11052000
    region_raw = f.data[0x492C28:0x492C28+20]
    sample_id = struct.unpack_from('<H', region_raw)[0]
    full_exponents, starts = [], []

    def full_exponential_entry(uc, address, size, unused):
        if a.get('LR') == BASE+0x1FF69C:
            value = a.get('R0')
            full_exponents.append(value-2**32 if value & 0x80000000 else value)

    a.uc.hook_add(UC_HOOK_CODE, full_exponential_entry, begin=BASE+0x1FF348, end=BASE+0x1FF348)
    a.stubs[0x1F9028] = lambda m: starts.append(word(oracle.voice+0x9C)) or 0
    complete_rows = []
    for oscillator, count, thickness, detune in itertools.product([0, 1], [3, 4, 6], [0, 9], [24, 99]):
        baseline = None
        for index in [-1]+list(range(count)):
            # Note 36 keeps this independent sample fixture below its playback
            # increment ceiling; the ceiling otherwise hides small offsets.
            oracle.initialize(36, 85, oscillator)
            v = oracle.voice
            a.write(v+0x0C, oracle.controls)
            a.write(v+0x20, sample)
            a.write(v+0x22C, region)
            a.write(oracle.context+0x10, oracle.controls)
            a.uc.mem_write(sample, f.data[0x410ABC+sample_id*64:0x410ABC+(sample_id+1)*64])
            a.uc.mem_write(region, region_raw)
            a.write(0xC1B5720C, clock)
            a.write(clock, 0, 123)
            a.write(0xC165D9B4, 36)
            a.write(0xC165D9B0, region_raw[4] << 8)
            a.write(0xC165D9AC, struct.unpack_from('<h', region_raw, 6)[0])
            a.write(0xC165D9A8, 36 << 8)
            a.write(0xC165D9A0, 64)
            put8(0xC165D9A4, 127)
            put8(0xC165D9A5, 0)
            put8(0xC165D9B8, 0)
            put8(oracle.runtime+0x4A2, index)
            put8(oracle.patch+0x50A, 0x80 | count)
            put8(oracle.patch+0x50B, detune)
            put8(oracle.patch+0x50C, thickness)
            full_exponents.clear()
            starts.clear()
            assert call(0x1F7278, v, oracle.runtime, 0) == 1
            assert len(starts) == 1 and len(full_exponents) == 2
            if index == -1:
                baseline = list(full_exponents)
            else:
                offset = (detune*tables[count-2]['thickness_rows'][thickness][index]*331) >> 22
                assert full_exponents == [x+offset for x in baseline]
                assert starts == [f.phase_increment(full_exponents[-1])], (oscillator, count, thickness, detune, index, starts, full_exponents)
                complete_rows.append(dict(oscillator=oscillator+1, voices=count, thickness=thickness,
                                          detune=detune, index=index, exponent_offset=offset,
                                          TG_start_increment=starts[0]))
    descriptors = [r for r in f.group(0x3E, bytes(2140)) if r['program_offset'] in [0x50A, 0x50B, 0x50C]]
    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False,
                  dispatch_cases=dispatch_rows, chain_cases=chain_rows, table_cases=table_cases,
                  tables=tables, out_of_range_count_cases=5, pitch_cases=pitch_cases, pitch_examples=examples,
                  full_initialization_cases=complete_rows,
                  parameter_descriptors=descriptors,
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                  additional_helpers={'voice_firmware.py': hashlib.sha256((ROOT/'research/tools/voice_firmware.py').read_bytes()).hexdigest()},
                  inputs=[dict(path='research/output/kep-analysis/Concert_SE_Grand/program.bin',
                               sha256=hashlib.sha256(oracle.program).hexdigest())],
                  boundaries=['Manager output intercepted; OSC predicates/getters, loop and chain insertion execute',
                              'Returned chains use synthetic zero exclusive-group regions; group filtering intercepted',
                              'All pitch table entries 2..16 voices checked; UI permits 2..6',
                              'Full pitch initializer and phase-increment helper execute with unrelated modulation zero',
                              '104 full voice initializations compare Unison-on increments against matched bypass baselines; TG start captured',
                              'Rate cents derives from programmed phase increments; TG audio not executed',
                              'Manual spread examples differ by approximately factor two from this firmware path; unresolved'])
    (OUT/'unison-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, dispatch_cases=len(dispatch_rows), chain_cases=len(chain_rows),
                          table_cases=table_cases, pitch_cases=pitch_cases, full_initialization_cases=len(complete_rows)), indent=2))


if __name__ == '__main__':
    main()
