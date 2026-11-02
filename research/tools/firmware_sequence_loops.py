#!/usr/bin/env python3
"""Original per-track loop cursor, position mapping and note-output continuity."""
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


def rec(kind, value=0, tick=0, note=60, velocity=100):
    return struct.pack('<BBBBHH', kind, 0, note, velocity, value, tick)


def mapped(bar, start, end, enabled, intro):
    size = end-start+1
    if not enabled: return bar
    if intro and bar < start: return bar
    return start+(bar-start if intro else bar) % size


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args();f = Firmware();OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('track-loop-cursor', 0x24157C, 0x241AC0),
                         ('track-loop-setup', 0x24E91C, 0x24E99C)]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream): inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm: return
    a = Arm(f);cursor, events, ctx = 0x11000000, 0x11001000, 0x11010000
    queue = 0xC171BD04
    def w(p): return struct.unpack('<I', a.uc.mem_read(p, 4))[0]
    def h(p): return struct.unpack('<H', a.uc.mem_read(p, 2))[0]
    def ph(p, v): a.uc.mem_write(p, struct.pack('<H', v & 65535))
    def pb(p, v): a.uc.mem_write(p, bytes([v & 255]))
    def call(p, *args, **kwargs): return a.call(p, *args, **kwargs)
    def setup(start, end, enabled=1, intro=0, cur=cursor):
        call(0x241364, cur)
        call(0x24157C, cur, events, start, end, stack=(enabled, intro))
    body = b''.join(rec(1, 2, bar)+rec(9, 240, 120, note=bar % 128) for bar in range(1000))+rec(3, 0, 999)
    a.uc.mem_write(events, body)
    a.uc.mem_write(0xC171BFA0, struct.pack('<H', 1000)+b'\x13'*1000)
    pb(0xC1714D11, 1)
    mapping_cases = seek_cases = 0
    examples = []
    for start, size, enabled, intro in itertools.product([0, 2, 7, 500], [1, 2, 8, 99], range(2), range(2)):
        end = start+size-1
        setup(start, end, enabled, intro)
        assert [h(cursor+8), h(cursor+10), w(cursor+12), w(cursor+16), h(cursor+32)] == [start, end, enabled, intro, size]
        assert [w(cursor+24), w(cursor+28)] == [events+16*start, events+16*(end+1)]
        for bar in sorted(set([0, 1, max(0,start-1), start, start+1, end, end+1, 997])):
            source = mapped(bar, start, end, enabled, intro)
            assert call(0x2416D0, cursor, bar) == source
            mapping_cases += 1
            for tick in [0, 1, 120, 121]:
                call(0x241748, cursor, bar, tick)
                expected_pointer = events+16*source+(0 if tick == 0 else 8 if tick <= 120 else 16)
                offset = 0 if not enabled or intro and bar < start else ((bar-start if intro else bar)//size)*size
                assert [w(cursor+4), h(cursor+34)] == [expected_pointer, offset], (start,size,enabled,intro,bar,tick)
                if enabled:
                    current = call(0x2418FC, cursor) & 0xFFFFFFFF
                    out = bytes(a.uc.mem_read(current, 8))
                    if tick == 0: assert struct.unpack_from('<H', out, 6)[0] == bar
                    elif tick <= 120: assert out == body[expected_pointer-events:expected_pointer-events+8]
                seek_cases += 1
        if start == 2 and size == 2 and enabled:
            examples.append(dict(intro=intro, source_bars=[mapped(bar,start,end,1,intro) for bar in range(10)]))

    # Forward and reverse pointer steps retain the boundary marker for one visit.
    pointer_cases = 0
    for start, size, intro, cycle in itertools.product([0, 2, 7], [1, 2, 4], range(2), [0, 1, 7]):
        end = start+size-1;setup(start, end, intro=intro)
        begin, boundary = w(cursor+24), w(cursor+28)
        a.write(cursor+4, boundary);ph(cursor+34, size*cycle)
        call(0x241874, cursor)
        assert [w(cursor+4), h(cursor+34)] == [begin, size*(cycle+1)]
        call(0x2418B4, cursor)
        assert [w(cursor+4), h(cursor+34)] == [boundary, size*cycle]
        a.write(cursor+4, begin);ph(cursor+34, 0)
        call(0x2418B4, cursor)
        assert [w(cursor+4), h(cursor+34)] == [begin-8, 0]
        pointer_cases += 3

    # Returned loop events are synthesized in scratch memory; raw data is intact.
    wrapper_cases = []
    for intro, offset, source_bar in itertools.product(range(2), [0, 2, 10], [2, 3]):
        setup(2, 3, intro=intro)
        pointer = events+16*source_bar+8
        original = rec(9, 0x7FFF, 120, note=source_bar)
        a.uc.mem_write(pointer, original);a.write(cursor+4, pointer);ph(cursor+34, offset)
        out = call(0x2418FC, cursor) & 0xFFFFFFFF
        assert out == 0xC17146AC
        expected = 0x1DFF if source_bar == 3 else 0x7FFF
        assert h(out+4) == expected and bytes(a.uc.mem_read(pointer, 8)) == original
        wrapper_cases.append(dict(intro=intro, offset=offset, source_bar=source_bar, duration=expected))
        a.uc.mem_write(pointer, body[pointer-events:pointer-events+8])
    setup(2, 3)
    a.uc.mem_write(events+16*2+8, rec(15, 0, 120));a.write(cursor+4, events+16*2+8)
    assert call(0x2418FC, cursor) & 0xFFFFFFFF == events+16*2+8
    a.uc.mem_write(events, body)

    cap_cases = []
    for mode, song_size, offset in itertools.product(range(2), [4, 20], [0, 2, 20, 998]):
        setup(0, 1);pb(0xC1714D11, mode);ph(0xC171BFA0, song_size)
        a.write(cursor+4, events);ph(cursor+34, offset)
        out = call(0x2418FC, cursor) & 0xFFFFFFFF
        cap = 998 if mode else song_size-1
        assert a.uc.mem_read(out, 1)[0] == (3 if offset > cap else 1)
        assert h(out+6) == min(offset, cap)
        cap_cases.append(dict(mode=mode, song_size=song_size, offset=offset, kind=a.uc.mem_read(out,1)[0], bar=h(out+6)))

    # Load all sixteen cursor configurations through the original song metadata
    # reader and real track-pointer accessor, including an absent track stream.
    metadata_cases = 0
    song = 0x11020000
    for phase in range(4):
        a.uc.mem_write(song, bytes(0xB00))
        for track in range(16):
            cur = 0xC1714408+40*track;call(0x241364, cur)
            row = song+0x7C8+36*track
            enabled, intro = (track+phase) & 1, ((track+phase) >> 1) & 1
            a.write(row, events if track != 15 else 0)
            ph(row+0x1C, (enabled << 15) | (intro << 14))
            ph(row+0x20, track);ph(row+0x22, track+2)
        call(0x24E91C, 0, song)
        for track in range(16):
            cur = 0xC1714408+40*track
            expected = [track, track+2, (track+phase)&1, ((track+phase)>>1)&1, events]
            if track == 15: expected = [0]*5
            assert [h(cur+8),h(cur+10),w(cur+12),w(cur+16),w(cur+20)] == expected
            metadata_cases += 1

    # Original caller + loop vtable + decoder + duration table + output queue.
    # Loop-end tied notes are capped to the bar and shut off before the next lap.
    runs = []
    a.stubs = {0x2B7E80: lambda m: 1}
    for intro, tied in itertools.product(range(2), range(2)):
        track_cursor = 0xC1714408
        small = b''.join(rec(1, 2, bar)+rec(9, 0x7FFF if tied and bar == 3 else 240, 120, note=60+bar) for bar in range(6))+rec(3, 0, 5)
        a.uc.mem_write(events, small)
        a.uc.mem_write(0xC171BFA0, struct.pack('<H', 20)+b'\x13'*1000)
        pb(0xC1714D11, 0)
        setup(2, 3, intro=intro, cur=track_cursor);call(0x241748, track_cursor, 0, 0)
        a.uc.mem_write(0xC171C4C8, struct.pack('<HBB', 0x7FFD,0,0)*64)
        pb(0xC171D4C8, 0);pb(0xC1716968, 0);pb(0xC17456AC+0x4FE, 3)
        for p in [0xC171D4D8, 0xC171D4DA, 0xC171D4DC, 0xC171D514]: ph(p, 0)
        ph(0xC171D518, 1);ph(0xC171D502, 0);ph(0xC171D500, 1920)
        a.write(0xC17231F4, 0)
        trace, previous_tie = [], None
        for bar in range(8):
            source = mapped(bar, 2, 3, 1, intro)
            for tick in [0, 119, 120, 359, 360, 1919]:
                a.uc.mem_write(queue, bytes(0x298));a.write(queue+0x20C, 128)
                call(0x257850, bar, tick)
                messages = [list(a.uc.mem_read(queue+4*i,4))[1:] for i in range(w(queue+0x200))]
                expected = []
                if tick == 0 and previous_tie is not None: expected = [[0x83, previous_tie, 64]];previous_tie = None
                if tick == 120:
                    expected = [[0x93, 60+source, 100]]
                    if tied and source == 3: previous_tie = 63
                if tick == 360 and not (tied and source == 3): expected = [[0x83, 60+source, 64]]
                assert messages == expected, (intro,tied,bar,tick,messages,expected)
                if messages: trace.append(dict(bar=bar,tick=tick,source_bar=source,messages=messages))
        runs.append(dict(intro=intro,tied=tied,source_bars=[mapped(bar,2,3,1,intro) for bar in range(8)],trace=trace))

    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False,
        mapping_cases=mapping_cases, seek_cases=seek_cases, pointer_cases=pointer_cases,
        mapping_examples=examples, wrapper_cases=wrapper_cases, cap_cases=cap_cases, metadata_cases=metadata_cases,
        sysex_pointer_preserved=True, loop_playback=runs, playback_visits=4*8*6,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        boundaries=['Original constructor/configuration/seek/forward/reverse/current-event methods and MIDI note decoder',
                    'Synthetic valid loop ranges and song events; no file loader, record writer or full song-state startup',
                    'Original sixteen-track metadata reader and source-pointer accessor execute on synthetic song metadata',
                    'Output queue checked and port-buffer call intercepted; no sound or physical hardware',
                    'SysEx checked only for original-pointer preservation, not full SysEx playback'])
    (OUT/'sequence-loops-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,mapping_cases=mapping_cases,seek_cases=seek_cases,
                         pointer_cases=pointer_cases,wrapper_cases=len(wrapper_cases),cap_cases=len(cap_cases),playback_visits=192),indent=2))


if __name__ == '__main__': main()
