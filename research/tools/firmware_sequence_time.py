#!/usr/bin/env python3
"""Original song-position conversion, meter bounds and eight-byte tempo events."""
import argparse
import bisect
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
METER = 0xC171BFA0


def length(code): return ((code & 15)+1)*[0, 480, 240, 120][code >> 4]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    f = Firmware()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('song-position-conversion', 0x260658, 0x2608D8),
                         ('song-position-bounds', 0x262EC8, 0x262FF8),
                         ('tempo-event-consumer', 0x266578, 0x266900),
                         ('tempo-meter-load', 0x265F88, 0x265FF4),
                         ('tempo-event-iterator', 0x2413D4, 0x2416D0),
                         ('song-position-seek-dispatch', 0x24A19C, 0x24A264)]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream): inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm: return
    a = Arm(f)
    table, barp, tickp = 0x11000000, 0x11010000, 0x11010004
    def h(p): return struct.unpack('<H', a.uc.mem_read(p, 2))[0]
    def w(p): return struct.unpack('<I', a.uc.mem_read(p, 4))[0]
    def ph(p, n): a.uc.mem_write(p, struct.pack('<H', n & 65535))
    def pb(p, n): a.uc.mem_write(p, bytes([n & 255]))
    def call(p, *args): return a.call(p, *args)
    meter_rows = []
    for code in range(16, 64):
        a.uc.mem_write(table, bytes(2)+bytes([code])*1000)
        assert call(0x2606E4, table, 0) == length(code)
        assert call(0x2606C0, table, 0) == [0, 480, 240, 120][code >> 4]
        call(0x268E30, code, barp, tickp)
        assert [h(barp), h(tickp)] == [length(code), [0, 480, 240, 120][code >> 4]]
        meter_rows.append(dict(code=code, numerator=(code & 15)+1, denominator=1 << ((code >> 4)+1), ticks=length(code)))
    a.uc.mem_write(table, b'\xA5'*1004)
    call(0x260658, table)
    assert bytes(a.uc.mem_read(table, 1004)) == bytes(2)+b'\x13'*1000+b'\xA5'*2
    # Mixed meters keep all 14-bit positions within the initialized table.
    codes = [0x13, 0x26, 0x1A, 0x28]*250
    a.uc.mem_write(table, bytes(2)+bytes(codes))
    prefix = [0]
    for code in codes: prefix.append(prefix[-1]+length(code)//120)
    forward_cases = 0
    inverse_examples = []
    for position in range(16384):
        bar = bisect.bisect_right(prefix, position)-1
        tick = (position-prefix[bar])*120
        call(0x26078C, table, position, barp, tickp)
        assert [h(barp), h(tickp)] == [bar, tick]
        if position % 127 == 0 or position in prefix or position == 16383:
            assert call(0x260700, table, bar, tick) == position
            forward_cases += 1
        if position < 40 or position == 16383:
            inverse_examples.append(dict(position=position, bar_index=bar, tick=tick))
    # Quantization to 120 ticks and saturation of the outgoing 14-bit value.
    for bar, tick in itertools.product([0, 1, 2, 998, 999], [0, 1, 119, 120, 121, 479, 480, 32767]):
        expected = min(16383, prefix[bar]+tick//120)
        assert call(0x260700, table, bar, tick) == expected
        forward_cases += 1
    movement_cases = 0
    for code, bar, tick in itertools.product(range(16, 64), [0, 1, 997, 998], [0, 1, -1]):
        a.uc.mem_write(table, bytes(2)+bytes([code])*1000)
        size = length(code)
        actual_tick = size-1 if tick == -1 else tick
        for direction in [1, -1]:
            ph(barp, bar);ph(tickp, actual_tick)
            expected_bar, expected_tick, ok = bar, actual_tick+direction, 1
            if expected_tick >= size:
                if bar == 998: expected_tick, ok = size-1, 0
                else: expected_bar, expected_tick = bar+1, 0
            if expected_tick < 0:
                if bar == 0: expected_tick, ok = 0, 0
                else: expected_bar, expected_tick = bar-1, size-1
            assert call(0x260808 if direction == 1 else 0x260880, table, barp, tickp) == ok
            assert [h(barp), h(tickp)] == [expected_bar, expected_tick]
            movement_cases += 1
    # Later clamp uses global meter and operation bounds. The converter itself
    # has no table length argument. Record reads into a controlled guard region.
    guard_arm = Arm(f)
    guard_arm.uc.mem_write(table, bytes(2)+bytes([0x30])*17000)
    from unicorn import UC_HOOK_MEM_READ
    reads = []
    hook = guard_arm.uc.hook_add(UC_HOOK_MEM_READ, lambda uc, access, address, size, value, user: reads.append(address), begin=table+1002, end=table+17001)
    guard_arm.call(0x26078C, table, 2000, barp, tickp)
    guard_arm.uc.hook_del(hook)
    guard_position = [struct.unpack('<H', guard_arm.uc.mem_read(p, 2))[0] for p in [barp, tickp]]
    assert guard_position == [2000, 0]
    assert reads and min(reads) == table+1002 and max(reads) == table+2002
    guard_result = dict(position=2000, meter_code=0x30, output_bar=guard_position[0],
                        initialized_entries=1000, guard_reads=len(reads), first_guard_index=1000, last_guard_index=2000)
    a.uc.mem_write(METER, bytes(2)+b'\x13'*1000)
    clamp_cases = 0
    for flags, bar, tick in itertools.product([0, 8, 16, 24], [-1, 0, 7, 8, 9, 998, 999, 1000], [-1, 0, 1, 1919, 1920]):
        ph(0xC04ADF72, flags)
        ph(0xC17146B4+0x1C, 7);ph(0xC17146B4+0x20, 8)
        ph(barp, bar);ph(tickp, tick)
        eb, et = max(0, bar), max(0, tick)
        if bar < 0: eb, et = 0, 0
        else:
            cap_bar, cap_tick = (7, 0) if flags & 8 else (8, 0) if flags & 16 else (998, 1919)
            if (eb, et) > (cap_bar, cap_tick): eb, et = cap_bar, cap_tick
        call(0x262EC8, barp, tickp)
        assert [h(barp), h(tickp)] == [eb, et]
        clamp_cases += 1

    # Synthetic tempo track using original 8-byte pointer advance, meter loads,
    # timestamp comparison and clock setter; end-of-track operation captured.
    control, events, clock, shared, mode = 0x11020000, 0x11021000, 0x11022000, 0x11023000, 0x11024000
    a.write(0xC1B58488, clock)
    a.write(0xC1B5720C, shared)
    a.write(0xC199BD3C, mode)
    a.write(mode, 0)
    a.stubs = {0x132660: lambda m: 0x53, 0x132670: lambda m: 0, 0x2664E8: lambda m: 0}
    # kind 1: bar marker, kind 11: tempo at tick, kind 3: terminal marker.
    records = [(1, 0, 0), (11, 12000, 0), (11, 24000, 480),
               (1, 0, 1), (11, 9000, 0), (11, 18000, 300), (3, 0, 2)]
    raw = b''.join(struct.pack('<BBHHH', kind, 0, 0, value, position) for kind, value, position in records)
    a.uc.mem_write(events, raw)
    tempo_runs = []
    for tempo_mode in range(4):
        a.uc.mem_write(control, bytes(0x20))
        a.uc.mem_write(clock, bytes(0x38))
        call(0x2C8024, clock)
        a.write(shared, 12000)
        call(0x2413D4, 0xC1714400, events)
        a.uc.mem_write(METER, struct.pack('<H', 4)+bytes([0x13, 0x26, 0x22, 0x13])+b'\x13'*996)
        pb(0xC171D51C, 1)
        ph(0xC04ADF72, 0);ph(0xC171D526, 0)
        pb(0xC0483868, tempo_mode);pb(0xC1DCD62A, 0)
        trace = []
        for bar, tick, next_index, latest in [(0, 0, 2, 12000), (0, 479, 2, 12000),
                (0, 480, 3, 24000), (0, 1919, 3, 24000), (1, 0, 5, 9000),
                (1, 299, 5, 9000), (1, 300, 6, 18000), (1, 1679, 6, 18000)]:
            ph(0xC0F55A74, bar);ph(0xC0F55A72, tick)
            call(0x266578, control)
            assert w(0xC1714404) == events+8*next_index
            assert h(control+0xE) == length([0x13, 0x26][bar])
            assert h(control+4) == (latest if tempo_mode in [0, 1] else 0)
            assert h(shared) == (latest if tempo_mode == 0 else 12000)
            if tempo_mode == 0: assert w(clock+0x2C) == latest
            trace.append(dict(bar_index=bar, tick=tick, next_event=next_index,
                              recorded_tempo=h(control+4), effective_tempo=h(shared), bar_ticks=h(control+0xE)))
        tempo_runs.append(dict(mode=tempo_mode, trace=trace))
    # Position seek over an actual event cursor. Header kind 1 skips the
    # rest of an earlier bar using its record count; kind 2 advances linearly.
    cursor, scan = 0x11030000, 0x11031000
    scan_records = [(1, 4, 0), (9, 0, 0x7FFF), (4, 0, 120), (11, 12000, 480),
                    (2, 0, 1), (4, 0, 0), (4, 0, 240), (1, 3, 2),
                    (4, 0, 60), (4, 0, 60), (3, 0, 2)]
    a.uc.mem_write(scan, b''.join(struct.pack('<BBHHH', k, 0, 0, v, t) for k, v, t in scan_records))
    call(0x241608, cursor, scan)
    seek_cases = []
    for target_bar, target_tick in itertools.product(range(5), [0, 1, 59, 60, 61, 119, 120, 121, 240, 241, 480, 481]):
        current_bar = 0
        expected = None
        for index, (kind, value, time) in enumerate(scan_records):
            if kind == 3:
                expected = index;break
            if kind in [1, 2]:
                current_bar = time
                if current_bar > target_bar or current_bar == target_bar and target_tick == 0:
                    expected = index;break
            elif current_bar > target_bar or current_bar == target_bar and (0 if kind == 9 and time == 0x7FFF else time) >= target_tick:
                expected = index;break
        actual = call(0x2414C0, cursor, target_bar, target_tick) & 0xFFFFFFFF
        assert actual == scan+8*expected
        seek_cases.append(dict(bar_index=target_bar, tick=target_tick, next_event=expected))
    backscan_cases = []
    for index, (kind, value, time) in enumerate(scan_records):
        expected_bar = 3 if kind == 3 else 0 if index < 4 else 1 if index < 7 else 2
        assert call(0x24163C, cursor, scan+8*index) == expected_bar
        expected_tick = 0 if kind in [1, 2, 3] or kind == 9 and time == 0x7FFF else time
        assert call(0x241684, cursor, scan+8*index) == expected_tick
        backscan_cases.append(dict(event=index, bar_index=expected_bar, tick=expected_tick))

    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False,
        meters=meter_rows, inverse_cases=16384, forward_cases=forward_cases,
        inverse_examples=inverse_examples, movement_cases=movement_cases, clamp_cases=clamp_cases,
        guard_read=guard_result, tempo_records=records, tempo_runs=tempo_runs,
        seek_cases=seek_cases, backscan_cases=backscan_cases, seek_records=scan_records,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        boundaries=['Original conversion, length lookup, one-tick movement, clamp and tempo track iterator execute',
                    'Synthetic meter table and tempo events; no song file loader or note-track decoder yet',
                    'Position converter guard experiment is controlled memory beyond 1000 initialized entries; reachability unproven',
                    'Tempo-mode byte 0 writes real clock setter; 1 retains event value; 2/3 ignore event tempo',
                    'End-of-track side effects and interrupt masks intercepted; no hardware or audio'])
    (OUT/'sequence-time-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, inverse_cases=16384, forward_cases=forward_cases,
                          movement_cases=movement_cases, clamp_cases=clamp_cases, tempo_runs=len(tempo_runs), seek_cases=len(seek_cases)), indent=2))


if __name__ == '__main__': main()
