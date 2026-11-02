#!/usr/bin/env python3
"""Version-locked forward note events, duration slots and MIDI output queues."""
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
SLOTS, COUNTS, QUEUE = 0xC171C4C8, 0xC171D4C8, 0xC171BD04
FREE, TIE_WAIT, TIE = 0x7FFD, 0x7FFE, 0x7FFF


def record(kind=9, note=60, velocity=100, duration=480, tick=0):
    return struct.pack('<BBBBHH', kind, 0, note, velocity, duration, tick)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    f = Firmware(); OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('track-note-expiry', 0x2562F8, 0x2564C8),
                         ('track-forward-decoder', 0x256810, 0x257850),
                         ('track-forward-dispatch', 0x257850, 0x257AE0),
                         ('track-output-queue', 0x25F0A8, 0x25F4AC),
                         ('track-midi-output', 0x240044, 0x2400AC),
                         ('track-midi-byte-fanout', 0x138178, 0x1381E0)]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream): inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm: return
    a = Arm(f)
    ctx, cursor, events = 0x11000000, 0x11001000, 0x11002000
    wire, local = [], []
    def w(p): return struct.unpack('<I', a.uc.mem_read(p, 4))[0]
    def h(p): return struct.unpack('<H', a.uc.mem_read(p, 2))[0]
    def b(p): return a.uc.mem_read(p, 1)[0]
    def ph(p, value): a.uc.mem_write(p, struct.pack('<H', value & 65535))
    def pb(p, value): a.uc.mem_write(p, bytes([value & 255]))
    def call(p, *values): return a.call(p, *values)
    def send(m):
        wire.append([m.get('R0'), bytes(m.uc.mem_read(m.get('R1'), m.get('R2'))).hex()])
        return 1
    def ingress(m):
        local.append([m.get('R1') & 255, m.get('R2') & 255, m.get('R3') & 255])
        return 1
    # Byte-buffer transport and local MIDI ingress are the two output boundaries.
    # Original decoder, queue operations, formatter and fanout remain executable.
    a.stubs = {0x2B7E80: send, 0x2BD7B4: ingress}
    def clear_outputs():
        wire.clear(); local.clear()
        a.uc.mem_write(QUEUE, bytes(0x298)); a.write(QUEUE+0x20C, 128)
    def reset(track=0, channel=0, tick=120, bar=0, bar_length=1920, local_off=0, wire_off=0, skip=0):
        a.uc.mem_write(ctx, struct.pack('<IIIHHHHHBx', 0, track, channel, bar, bar, tick, bar_length, 1 << track, 0))
        a.uc.mem_write(SLOTS, struct.pack('<HBB', FREE, 0, 0)*1024)
        a.uc.mem_write(COUNTS, bytes(16))
        for p in [0xC171D4D8, 0xC171D4DA, 0xC171D4DC, 0xC171D514, 0xC171D518]: ph(p, 0)
        ph(0xC171D4DC, local_off << track); ph(0xC171D4DA, wire_off << track)
        ph(0xC171D4D8, skip << track)
        pb(0xC1716968, 0); pb(0xC1DCD62A, 1)
        a.write(0xC17231F4, 0)
        clear_outputs()
    def load(records):
        # Future bar marker terminates processing without invoking song-end effects.
        a.uc.mem_write(events, b''.join(records)+record(kind=1, duration=1, tick=999))
        call(0x241364, cursor); call(0x241608, cursor, events)
    def run(records):
        load(records); call(0x256810, ctx, cursor)
    def queued():
        count, read = w(QUEUE+0x200), w(QUEUE+0x208)
        return [list(a.uc.mem_read(QUEUE+4*((read+i) & 127), 4))[1:] for i in range(count)]
    def ports():
        return [[int(pair[1], 16) for pair in wire if pair[0] == p] for p in [0xC10051B8, 0xC1B5AE1C]]
    def slot(track=0, index=0): return list(struct.unpack('<HBB', a.uc.mem_read(SLOTS+track*256+index*4, 4)))
    def put_slots(track, values):
        for i, row in enumerate(values): a.uc.mem_write(SLOTS+track*256+i*4, struct.pack('<HBB', *row))
        pb(COUNTS+track, sum(row[0] != FREE for row in values))

    note_cases = 0
    for channel, note, velocity in itertools.product(range(16), range(128), [0, 1, 64, 127]):
        track = (note+channel) % 16
        reset(track, channel)
        run([record(note=note, velocity=velocity, tick=120)])
        message = [0x90+channel, note, velocity]
        assert queued() == [message]
        assert ports() == [message, message]
        assert slot(track) == [600, note, velocity] and b(COUNTS+track) == 1
        call(0x25F184, QUEUE)
        assert local == [message] and w(QUEUE+0x200) == 0
        note_cases += 1

    timing_cases = 0
    for start, now, duration, size in itertools.product([0, 1, 119, 120, 479, 1919], [0, 120, 480, 1919], [0, 1, 120, 480, 32767], [480, 1920]):
        reset(tick=now, bar_length=size)
        run([record(tick=start, duration=duration)])
        accepted = start <= now and start < size
        assert len(queued()) == int(accepted)
        assert b(COUNTS) == int(accepted)
        if accepted:
            assert slot() == [TIE if duration == TIE else min(start+duration, size), 60, 100]
        assert w(cursor+4) == events+(8 if start <= now else 0)
        timing_cases += 1

    route_cases = []
    for local_off, wire_off, skip, local_gate in itertools.product(range(2), repeat=4):
        reset(local_off=local_off, wire_off=wire_off, skip=skip)
        pb(0xC1DCD62A, local_gate)
        run([record(tick=120)])
        assert len(queued()) == int(not skip and not local_off)
        assert ports() == ([[0x90, 60, 100]]*2 if not skip and not wire_off else [[], []])
        allocated = not skip and not (local_off and wire_off)
        assert b(COUNTS) == int(allocated)
        call(0x25F184, QUEUE)
        assert len(local) == int(not skip and not local_off and local_gate)
        route_cases.append(dict(local_off=local_off, wire_off=wire_off, skip=skip, local_gate=local_gate,
                                allocated=allocated, delivered_local=len(local), port_bytes=ports()))

    expiry_cases = 0
    initial = [(FREE, 1, 1), (0, 60, 1), (120, 61, 2), (121, 62, 3),
               (1919, 63, 4), (TIE_WAIT, 64, 5), (TIE, 65, 6)]
    for track, channel, now, local_off, wire_off in itertools.product([0, 7, 15], [0, 9, 15], [0, 119, 120, 121, 1919], range(2), range(2)):
        reset(track, channel, local_off=local_off, wire_off=wire_off)
        put_slots(track, initial)
        expected = [[0x80+channel, note, 64] for end, note, vel in initial if end < FREE and end <= now]
        nearest = min([end for end, note, vel in initial if now < end < FREE]+[TIE_WAIT])
        assert call(0x2562F8, track, channel, now) == nearest
        assert queued() == ([] if local_off else expected)
        flat = sum(expected, []) if not wire_off else []
        assert ports() == [flat, flat]
        assert b(COUNTS+track) == 6-len(expected)
        for i, (end, note, vel) in enumerate(initial):
            assert slot(track, i) == [FREE if end < FREE and end <= now else end, note, vel]
        expiry_cases += 1

    # A full duration table replaces the first slot with the smallest signed end.
    capacity_cases = []
    for choice, local_off, wire_off in itertools.product([0, 17, 63], range(2), range(2)):
        reset(local_off=local_off, wire_off=wire_off)
        states = [(800+i, i, 70) for i in range(64)]
        states[choice] = (200, choice, 70)
        put_slots(0, states)
        run([record(note=100, velocity=99, tick=120)])
        expected = [[0x80, choice, 64], [0x90, 100, 99]]
        assert queued() == ([] if local_off else expected)
        assert ports() == ([sum(expected, [])]*2 if not wire_off else [[], []])
        assert slot(0, choice) == ([FREE, choice, 70] if local_off and wire_off else [600, 100, 99])
        assert b(COUNTS) == (63 if local_off and wire_off else 64)
        capacity_cases.append(dict(replaced=choice, local_off=local_off, wire_off=wire_off, remaining=b(COUNTS)))
    reset(); put_slots(0, [(200, i, 80) for i in range(64)])
    run([record(tick=120)])
    assert slot() == [600, 60, 100] and queued()[0] == [0x80, 0, 64]

    # Tie markers cross a bar without retriggering; matching includes velocity.
    tie_cases = []
    for continuation, matching in itertools.product([0, 1, 480, TIE], [False, True]):
        reset(tick=0, bar=1)
        put_slots(0, [(TIE, 60, 100), (100, 62, 80)])
        run([record(kind=1, duration=1, tick=1),
             record(velocity=100 if matching else 99, duration=continuation, tick=TIE)])
        expected = [[0x80, 62, 64]]
        if matching and continuation == 0: expected.append([0x80, 60, 64])
        assert queued() == expected
        expected_end = FREE if matching and continuation == 0 else continuation if matching else TIE_WAIT
        assert slot() == [expected_end, 60, 100]
        assert b(COUNTS) == int(expected_end != FREE)
        tie_cases.append(dict(continuation=continuation, matching=matching, end=expected_end, messages=expected))

    # Queue insertion reports route eligibility even when the queue has no room.
    queue_limits = []
    for capacity in [0, 1, 32, 128]:
        reset(); a.write(QUEUE+0x20C, capacity)
        run([record(note=60+i, tick=120) for i in range(4)])
        assert w(QUEUE+0x200) == min(capacity, 4) and b(COUNTS) == 4
        assert len(ports()[0]) == 12
        queue_limits.append(dict(capacity=capacity, queued=w(QUEUE+0x200), active=b(COUNTS), port_bytes=len(ports()[0])))

    flush_cases = 0
    for track, channel, local_off, wire_off in itertools.product([0, 15], [0, 15], range(2), range(2)):
        reset(track, channel, local_off=local_off, wire_off=wire_off)
        put_slots(track, initial)
        call(0x256408, track, channel)
        expected = [[0x80+channel, note, 64] for end, note, vel in initial if end != FREE]
        assert queued() == ([] if local_off else expected)
        assert ports() == ([sum(expected, [])]*2 if not wire_off else [[], []])
        assert b(COUNTS+track) == 0
        assert all(slot(track, i)[0] == FREE for i in range(len(initial)))
        flush_cases += 1

    # Queue head/tail wrap and full-buffer release use the original draining loop.
    reset(); a.write(QUEUE+0x204, 127); a.write(QUEUE+0x208, 127)
    run([record(note=60, tick=120), record(note=64, tick=120)])
    assert w(QUEUE+0x204) == 1
    call(0x25F184, QUEUE)
    assert local == [[0x90, 60, 100], [0x90, 64, 100]] and w(QUEUE+0x208) == 1
    reset(); a.uc.mem_write(QUEUE, bytes([1, 0x90, 60, 100])*128)
    a.write(QUEUE+0x200, 128, 0, 0)
    put_slots(0, [(120, 60, 100)])
    call(0x2562F8, 0, 0, 120)
    assert local == [[0x90, 60, 100]]*128 and queued() == [[0x80, 60, 64]]
    call(0x25F184, QUEUE)
    assert local[-1] == [0x80, 60, 64] and w(QUEUE+0x200) == 0

    # The caller visits all active tracks, expires old notes before decoding new
    # ones, and resolves channel 16..31 through the global-channel byte.
    dispatcher_runs = []
    for global_channel in [0, 9, 15]:
        reset(tick=0)
        ph(0xC171D518, 0x8001); ph(0xC171D502, 0); ph(0xC171D500, 1920)
        pb(0xC1DCD628, global_channel)
        for track, channel in [(0, 3), (15, 16)]:
            pb(0xC17456AC+0x4FC+44*track+2, channel)
            stream = events+0x100*track
            a.uc.mem_write(stream, record(note=60+track, tick=120, duration=120)+record(kind=1, duration=1, tick=999))
            cur = 0xC1714408+40*track
            call(0x241364, cur); call(0x241608, cur, stream)
        call(0x257850, 0, 119); assert queued() == []
        call(0x257850, 0, 120)
        on = [[0x93, 60, 100], [0x90+global_channel, 75, 100]]
        assert queued() == on
        clear_outputs(); call(0x257850, 0, 239); assert queued() == []
        call(0x257850, 0, 240)
        off = [[0x83, 60, 64], [0x80+global_channel, 75, 64]]
        assert queued() == off and b(COUNTS) == b(COUNTS+15) == 0
        dispatcher_runs.append(dict(global_channel=global_channel, on=on, off=off, ticks=[119, 120, 239, 240]))

    reset(); ph(0xC171D518, 1); ph(0xC171D502, 0); ph(0xC171D500, 1920)
    pb(0xC17456AC+0x4FE, 0)
    song_cursor = 0xC1714408
    a.uc.mem_write(events, b''.join([
        record(kind=1, duration=3, tick=0),
        record(note=60, duration=TIE, tick=1800),
        record(note=62, duration=0, tick=1800),
        record(kind=1, duration=2, tick=1),
        record(note=60, duration=120, tick=TIE),
        record(kind=1, duration=1, tick=2)]))
    call(0x241364, song_cursor); call(0x241608, song_cursor, events)
    continuous = []
    for bar, tick, expected in [
        (0, 1799, []), (0, 1800, [[0x90, 60, 100], [0x90, 62, 100]]),
        (0, 1801, [[0x80, 62, 64]]), (0, 1919, []), (1, 0, []),
        (1, 119, []), (1, 120, [[0x80, 60, 64]])]:
        clear_outputs(); call(0x257850, bar, tick)
        assert queued() == expected, (bar, tick, queued())
        continuous.append(dict(bar_index=bar, tick=tick, messages=expected, active=b(COUNTS), first_slot=slot()))

    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False,
        note_cases=note_cases, timing_cases=timing_cases, route_cases=route_cases,
        expiry_cases=expiry_cases, capacity_cases=capacity_cases, capacity_tie_first=True,
        tie_cases=tie_cases, queue_limits=queue_limits, queue_wrap=True, full_release_drain=True,
        flush_cases=flush_cases, dispatcher_runs=dispatcher_runs, continuous=continuous,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        boundaries=['Synthetic 8-byte records and cursor objects, original forward decoder and active-track caller',
                    'Original slot lifetime, queue insertion/drain, local-enable gate and dual-port byte formatting',
                    'Local MIDI ingress 2BD7B4 and port buffer 2B7E80 captured; no driver or voice/audio execution',
                    '64 slots are per-track pending note ends, not TG voice polyphony',
                    'File loading, record generation, general loops, CC/program/SysEx and reverse playback remain separate'])
    (OUT/'sequence-notes-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, note_cases=note_cases, timing_cases=timing_cases,
                         expiry_cases=expiry_cases, routes=len(route_cases), capacity_cases=len(capacity_cases)+1,
                         ties=len(tie_cases), dispatcher_runs=len(dispatcher_runs)), indent=2))


if __name__ == '__main__': main()
