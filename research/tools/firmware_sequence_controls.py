#!/usr/bin/env python3
"""Original forward CC, pressure, program/bank and pitch-bend event decoding."""
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

OUT = ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
QUEUE = 0xC171BD04
VALUES = [0xC172272C, 0xC171FE2C, 0xC171E9AC]
TIMES = [(0xC172220C, 0xC1721CEC), (0xC171F90C, 0xC171F3EC), (0xC171E48C, 0xC171DF6C)]


def event(kind, data1, data2=0, tick=120):
    return bytes([kind, 0, 0, 0, data2, data1])+struct.pack('<H', tick)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args(); f = Firmware(); OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('track-control-decode', 0x256DC0, 0x257850),
                         ('track-program-bank-convert', 0x2410C4, 0x24114C),
                         ('track-control-coalescing', 0x25F294, 0x25F410)]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream): inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm: return
    a = Arm(f); ctx, cursor, events = 0x11000000, 0x11001000, 0x11002000
    sent = []
    def w(p): return struct.unpack('<I', a.uc.mem_read(p, 4))[0]
    def ph(p, v): a.uc.mem_write(p, struct.pack('<H', v & 65535))
    def pb(p, v): a.uc.mem_write(p, bytes([v & 255]))
    def call(p, *args): return a.call(p, *args)
    def wire(m): sent.append([m.get('R0'), bytes(m.uc.mem_read(m.get('R1'), m.get('R2'))).hex()]);return 1
    a.stubs = {0x2B7E80: wire}
    cc_map = list(f.data[0x4509A6:0x4509A6+128])
    def reset(track=0, channel=0, local_off=0, wire_off=0, skip=0, config=3, coalesce=0):
        a.uc.mem_write(ctx, struct.pack('<IIIHHHHHBx', 0, track, channel, 0, 0, 120, 1920, 1 << track, 0))
        for p in VALUES: a.uc.mem_write(p, b'\xFF'*(16*41*4))
        for pair in TIMES:
            for p in pair: a.uc.mem_write(p, bytes(16*41*2))
        for p, value in [(0xC171D4DC, local_off), (0xC171D4DA, wire_off), (0xC171D4D8, skip)]: ph(p, value << track)
        a.write(0xC17231F4, 0); pb(0xC1DCD62B, config)
        a.uc.mem_write(QUEUE, bytes(0x298)); a.write(QUEUE+0x20C, 128)
        pb(QUEUE+0x294, coalesce);sent.clear()
    def run(records):
        a.uc.mem_write(events, b''.join(records)+bytes([1, 0, 0, 0, 1, 0])+struct.pack('<H', 999))
        call(0x241364, cursor);call(0x241608, cursor, events);call(0x256810, ctx, cursor)
    def queued(): return [list(a.uc.mem_read(QUEUE+4*i, 4))[1:] for i in range(w(QUEUE+0x200))]
    def ports(): return [[int(x[1], 16) for x in sent if x[0] == p] for p in [0xC10051B8, 0xC1B5AE1C]]
    def check(messages, external=None):
        assert queued() == messages, (queued(), messages)
        flat = sum(messages if external is None else external, [])
        assert ports() == [flat, flat], (ports(), flat)
    def index(kind, d1): return cc_map[d1] if kind == 11 else {12:38, 13:39, 14:40}.get(kind)

    cc_cases = 0
    for channel, cc, value in itertools.product(range(16), range(128), [0, 64, 127]):
        track = (cc+channel) % 16
        reset(track, channel);run([event(11, cc, value)])
        check([[0xB0+channel, cc, value]])
        i = cc_map[cc]
        if i < 38:
            for base, row in zip(VALUES, [track, channel, channel]):
                assert w(base+4*(41*row+i)) & 65535 == cc+256*value
        cc_cases += 1

    expression_cases = 0
    for kind, channel, d1, d2 in itertools.product([10, 13, 14], range(16), [0, 1, 64, 127], [0, 127]):
        reset(channel=channel);run([event(kind, d1, d2)])
        message = [{10:0xA0, 13:0xD0, 14:0xE0}[kind]+channel, d1, 0 if kind == 13 else d2]
        check([message], [message[:2]] if kind == 13 else [message])
        expression_cases += 1
    for value in range(16384):
        lo, hi = value & 127, value >> 7
        reset(channel=4);run([event(14, lo, hi)])
        check([[0xE4, lo, hi]])

    programs = []
    for channel, program, bank, config in itertools.product([0, 7, 15], [0, 64, 127], [0, 1, 127, 139], range(4)):
        reset(channel=channel, config=config);run([event(12, program, bank)])
        messages = []
        if config & 2 and bank != 139: messages += [[0xB0+channel, 0, 0], [0xB0+channel, 32, bank]]
        if config & 1: messages += [[0xC0+channel, program, 0]]
        check(messages, [m[:2] if m[0] >> 4 == 12 else m for m in messages])
        programs.append(dict(channel=channel, program=program, bank=bank, config=config, messages=messages))

    # Track snapshots always update; each output route independently rejects an
    # event older than the latest position already applied on that MIDI channel.
    chronology_cases = 0
    for kind, previous_bar, previous_tick, route in itertools.product([11, 12, 13, 14], [-1, 0, 1], [0, 119, 120, 121], [1, 2]):
        d1, d2 = (7, 90) if kind == 11 else (10, 139) if kind == 12 else (70, 30)
        reset(track=15, channel=3);i = index(kind, d1)
        a.write(VALUES[route]+4*(41*3+i), 1)
        ph(TIMES[route][0]+2*(41*3+i), previous_bar)
        ph(TIMES[route][1]+2*(41*3+i), previous_tick)
        run([event(kind, d1, d2)])
        status = {11:0xB3, 12:0xC3, 13:0xD3, 14:0xE3}[kind]
        message = [status, d1, 0 if kind in [12, 13] else d2]
        accepted = (previous_bar, previous_tick) <= (0, 120)
        local = [message] if route != 1 or accepted else []
        external = [message[:2] if kind in [12, 13] else message] if route != 2 or accepted else []
        check(local, external)
        assert w(VALUES[0]+4*(41*15+i)) & 65535 == d1+256*(0 if kind == 13 else d2)
        chronology_cases += 1

    routes = 0
    for kind, local_off, wire_off, skip in itertools.product([10, 11, 12, 13, 14], range(2), range(2), range(2)):
        reset(local_off=local_off, wire_off=wire_off, skip=skip)
        d2 = 139 if kind == 12 else 64
        run([event(kind, 7, d2)])
        message = [0xA0+16*(kind-10), 7, 0 if kind in [12, 13] else d2]
        check([message] if not local_off and not skip else [],
              [message[:2] if kind in [12, 13] else message] if not wire_off and not skip else [])
        routes += 1

    coalescing = []
    for kind, enabled, note_between in itertools.product([13, 14], range(2), range(2)):
        reset(coalesce=enabled)
        a.uc.mem_write(0xC171C4C8, struct.pack('<HBB', 0x7FFD, 0, 0)*64)
        pb(0xC171D4C8, 0);pb(0xC1716968, 0)
        records = [event(kind, 1, 64), event(kind, 2, 64)]
        if note_between: records += [bytes([9, 0, 60, 100])+struct.pack('<HH', 240, 120)]
        records += [event(kind, 3, 64)]
        run(records)
        def msg(value): return [0xD0 if kind == 13 else 0xE0, value, 0 if kind == 13 else 64]
        external = [msg(1), msg(2)]+([[0x90, 60, 100]] if note_between else [])+[msg(3)]
        expected = ([msg(2), [0x90, 60, 100], msg(3)] if note_between else [msg(3)]) if enabled else external
        check(expected, [m[:2] if m[0] == 0xD0 else m for m in external])
        coalescing.append(dict(kind=kind, enabled=enabled, note_between=note_between, local=expected, external=external))

    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False,
        cc_cases=cc_cases, cc_slot_map=[dict(cc=i, slot=v) for i, v in enumerate(cc_map) if v < 38],
        expression_cases=expression_cases, pitch_bend_cases=16384, program_cases=programs,
        chronology_cases=chronology_cases, route_cases=routes, coalescing=coalescing,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        boundaries=['Original forward decoder, cursor, caches, queue and MIDI formatting; synthetic eight-byte records',
                    'Port buffer 2B7E80 intercepted; local messages inspected before delivery; no sound or drivers',
                    'Bank conversion tested for raw IDs 0,1,127,139 only; extension-bank lookup pending',
                    'SysEx, parameter chase, record creation, track loops and file loading remain separate'])
    (OUT/'sequence-controls-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, cc_cases=cc_cases, expression_cases=expression_cases,
                         pitch_bend_cases=16384, program_cases=len(programs), chronology_cases=chronology_cases,
                         routes=routes, coalescing=len(coalescing)), indent=2))


if __name__ == '__main__': main()
