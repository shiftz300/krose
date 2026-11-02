#!/usr/bin/env python3
"""Original external clock period estimator, readback filter and tick interpolation."""
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
from firmware_music_clock import ClockModel, signed64, MASK, Q
from layout import PRODUCT_ROOT as ROOT

OUT = ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
CONTROL, ESTIMATE, ACC, HOLD = 0xC1716418, 0xC17231B0, 0xC17231E8, 0xC17231F0
DEFAULT = 1_041_666_667
LIMIT = 99_999_999_999


def period_from(accumulated, elapsed):
    if accumulated > LIMIT:
        return DEFAULT
    total = signed64(accumulated+elapsed)
    raw = (abs(total)//20)*(1 if total >= 0 else -1)
    if raw > 5_000_000_000 or raw < 390_625_000:
        return DEFAULT
    return min(3_125_000_000, max(416_666_667, raw))


def tempo_from(period):
    return max(4000, min(30000, (125_000_000_000_000//period+5)//10))


class ReadbackModel:
    def __init__(self):
        self.values, self.index, self.value, self.hold = [12000]*8, 0, 12000, 8

    def push(self, value):
        self.values[self.index] = value
        self.index = (self.index+1) % 8
        candidate = sum(self.values)//8//100*100
        if candidate != self.value and 0 < self.hold < 128:
            self.hold -= 1
        else:
            self.value = candidate
            self.hold = 32


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    f = Firmware()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('external-period-estimator', 0x265994, 0x265EC4),
                         ('external-period-controller', 0x24EB3C, 0x24ECA4),
                         ('interpolated-clock-consumer', 0x267304, 0x2673D0),
                         ('tempo-readback-routing', 0x2C4D64, 0x2C4E50),
                         ('tempo-main-field-format', 0x2FE370, 0x2FE3F0)]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out): inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm: return
    a = Arm(f)
    clock, shared, msg, mode = 0x11000000, 0x11001000, 0x11002000, 0x11003000
    def w(p): return struct.unpack('<I', a.uc.mem_read(p, 4))[0]
    def q(p): return struct.unpack('<Q', a.uc.mem_read(p, 8))[0]
    def pq(p, v): a.uc.mem_write(p, struct.pack('<Q', v & MASK))
    def pb(p, v): a.uc.mem_write(p, bytes([v & 255]))
    def call(p, *args): return a.call(p, *args)
    def check_readback(model):
        assert [w(ESTIMATE+8+4*i) for i in range(8)] == model.values
        assert w(ESTIMATE+4) == model.index and w(ESTIMATE+0x28) == model.value
        assert bytes(a.uc.mem_read(HOLD, 1))[0] == model.hold
    a.write(0xC1B58488, clock)
    a.write(0xC1B5720C, shared)
    a.write(0xC199BD3C, mode)
    a.write(mode, 0)
    pb(0xC1DCD62A, 2)
    a.stubs = {0x132660: lambda m: 0x53, 0x132670: lambda m: 0,
               0x2B00: lambda m: 0, 0x24725C: lambda m: 0, 0x2B30: lambda m: 0}
    # Below, source predicates, 0x415CC -> 0x267304 -> accumulator,
    # 0x23F6B8 -> 0x265BAC and all 64-bit arithmetic remain original.
    cases = []
    periods = sorted(set([0, 1, 390_624_999, 390_625_000, 416_666_666, 416_666_667,
                          DEFAULT, 3_125_000_000, 3_125_000_001, 5_000_000_000,
                          5_000_000_001] + [12_500_000_000_000//v for v in range(4000, 30001, 25)]))
    for raw, running, remainder in itertools.product(periods, [0, 1], [0, -100, 100]):
        a.uc.mem_write(clock, bytes(0x38))
        call(0x2C8024, clock)
        pq(clock+0x20, raw*20)
        pq(clock+8, remainder)
        a.write(CONTROL, running)
        pq(CONTROL+4, DEFAULT)
        call(0x265994, ESTIMATE)
        call(0x265A3C, ESTIMATE)
        call(0x265BAC, ESTIMATE)
        expected = period_from(0, raw*20+remainder)
        assert q(CONTROL+4) == q(clock+0x10) == expected
        assert q(ACC) == 0
        assert w(CONTROL) == running and w(clock+0x34) == int(not running)
        if running:
            assert q(clock+0x18) == expected and q(clock+8) == 0 and q(clock) == raw*20
        dm = ReadbackModel()
        dm.push(tempo_from(expected))
        check_readback(dm)
        if raw in periods[:5] or raw in [3_125_000_001, 5_000_000_000, 5_000_000_001]:
            cases.append(dict(raw_period=raw, running=running, remainder=remainder,
                              period=expected, raw_tempo=tempo_from(expected)))
    period_cases = len(periods)*6

    accumulated_cases = []
    for accumulated, elapsed in itertools.product([0, LIMIT-1, LIMIT, LIMIT+1], [-Q, 0, Q, 20*Q]):
        a.uc.mem_write(clock, bytes(0x38))
        call(0x2C8024, clock)
        pq(clock+8, elapsed)
        pq(ACC, accumulated)
        a.write(CONTROL, 1)
        call(0x265BAC, ESTIMATE)
        expected = period_from(accumulated, elapsed)
        assert q(CONTROL+4) == expected and q(ACC) == 0
        accumulated_cases.append(dict(accumulated=accumulated, elapsed=elapsed, period=expected))
    accumulator_cases = []
    for initial, period in itertools.product([0, LIMIT-1, LIMIT, LIMIT+1], [416_666_667, DEFAULT, 3_125_000_000]):
        pq(ACC, initial)
        pq(CONTROL+4, period)
        call(0x265DBC, ESTIMATE)
        expected = initial+period if initial <= LIMIT else initial
        assert q(ACC) == expected
        accumulator_cases.append(dict(before=initial, period=period, after=expected))

    readback_runs = []
    for first, second in [(12000, 24000), (12000, 6000), (11900, 12100)]:
        call(0x265994, ESTIMATE)
        call(0x265A3C, ESTIMATE)
        dm = ReadbackModel()
        trace = []
        for index in range(100):
            raw = first if index < 30 else second
            call(0x265B08, ESTIMATE, raw)
            dm.push(raw)
            check_readback(dm)
            trace.append(dict(pulse=index+1, raw_tempo=raw, readback=dm.value, hold=dm.hold))
        readback_runs.append(dict(first=first, second=second, trace=trace))

    trajectories = []
    for name, intervals, change in [('120-BPM', [21, 21, 20, 21, 21, 21], None),
                                     ('60-BPM', [42, 42, 41], None),
                                     ('300-BPM', [8, 8, 9], None),
                                     ('tempo-change', [21, 21, 20, 21, 21, 21], [10, 11, 10, 11, 10, 10]),
                                     ('jitter', [19, 22, 20, 23, 20, 21], None)]:
        a.uc.mem_write(clock, bytes(0x38))
        call(0x2C8024, clock)
        a.write(shared, 12000, 0)
        pb(0xC1714371, 0)
        pb(0xC1DCD62A, 2)
        a.uc.mem_write(0xC1B58340, bytes(0x24))
        a.uc.mem_write(0xC171638A, bytes(6))
        call(0x2C832C, clock)  # complete the initial origin setup
        a.write(CONTROL, 1)
        call(0x24EBF8, CONTROL, DEFAULT, 0)
        call(0x24EB98, CONTROL)
        call(0x265994, ESTIMATE)
        call(0x265A3C, ESTIMATE)
        cm = ClockModel()
        cm.now = cm.origin = Q
        cm.initial = 0
        cm.active_period = cm.desired_period = DEFAULT
        dm = ReadbackModel()
        accumulated, controller_period, pulse_count, emitted = 0, DEFAULT, 0, 0
        next_pulse = intervals[0]
        trace = []
        for visit in range(1, 2001):
            ticks = cm.advance()
            for _ in range(ticks):
                if accumulated <= LIMIT: accumulated += controller_period
            emitted += ticks
            call(0x2C832C, clock)
            assert q(ACC) == accumulated
            if visit == next_pulse:
                elapsed = signed64(cm.now-cm.origin+cm.remainder)
                controller_period = period_from(accumulated, elapsed)
                cm.desired_period = controller_period
                cm.resume(True)
                accumulated = 0
                dm.push(tempo_from(controller_period))
                call(0x2C21F8, msg, 0xF8, 7)
                pulse_count += 1
                active_intervals = change if change and visit >= 1000 else intervals
                next_pulse += active_intervals[pulse_count % len(active_intervals)]
            assert q(clock) == cm.origin and signed64(q(clock+8)) == cm.remainder
            assert q(clock+0x10) == cm.desired_period and q(clock+0x18) == cm.active_period
            assert q(clock+0x20) == cm.now and q(ACC) == accumulated
            assert w(shared+4) == pulse_count*20
            check_readback(dm)
            trace.append(dict(visit=visit, pulses=pulse_count, interpolated_ticks=emitted,
                              period=controller_period, readback=dm.value, accumulated=accumulated))
        trajectories.append(dict(name=name, trace=trace))

    readback_cases = 0
    for seqmode, source, present, role, running, accumulated in itertools.product(
            [0, 3], range(4), [0, 1], [0, 1], [0, 1], [0, LIMIT+1]):
        a.write(mode, seqmode)
        pb(0xC1DCD62A, source << 1)
        a.write(0xC1B58348, present)
        a.write(ESTIMATE+0x30, role)
        a.write(ESTIMATE+0x28, 12300)
        a.uc.mem_write(0xC1723194+0xC, struct.pack('<H', 15000))
        a.write(shared, 18000)
        a.write(CONTROL, running)
        pq(ACC, accumulated)
        internal = source == 0 or source == 3 and not present
        value = (15000 if role else 12000) if internal else (12000 if role and (not running or accumulated > LIMIT) else 12300)
        assert call(0x265E18, ESTIMATE) == value
        current = value if seqmode == 3 or not internal else 18000
        assert call(0x2C4DF8, shared) == current
        assert call(0x2C4D64) == max(0, current-3000)
        readback_cases += 1
    format_cases = []
    for external, raw in itertools.product([0, 1], [4000, 12000, 12345, 30000]):
        a.write(shared+0x10, external)
        result_ptr = call(0x2FE370, 0, raw) & 0xFFFFFFFF
        actual = bytes(a.uc.mem_read(result_ptr, 16)).split(b'\0')[0]
        expected = f.data[0x459BC0:0x459BC7] if external else f'{raw//100}.{raw%100:02d}'.encode()
        assert actual == expected, (actual, expected)
        format_cases.append(dict(external=bool(external), tempo_raw=raw, bytes_hex=actual.hex()))

    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False,
        period_cases=period_cases, period_examples=cases, readback_cases=readback_cases, format_cases=format_cases, accumulated_cases=accumulated_cases,
        accumulator_cases=accumulator_cases, readback_runs=readback_runs, trajectories=trajectories,
        clock_visits=10000, tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        additional_helpers={'firmware_music_clock.py': hashlib.sha256((ROOT/'research/tools/firmware_music_clock.py').read_bytes()).hexdigest()},
        boundaries=['Original F8 consumer, period controller, 64-bit estimator, readback filter, tick generator and accumulator connected',
                    'Sequencer-active gate zero: recording/playback track traversal excluded',
                    'Other music consumers and critical-mask helpers intercepted',
                    'Timing measured in synthetic timer visits, not physical device milliseconds',
                    'Playback tempo interpolation and integer readback cadence are distinct'])
    (OUT/'external-tempo-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, period_cases=period_cases, accumulator_cases=len(accumulator_cases),
                          readback_updates=300, clock_visits=10000), indent=2))


if __name__ == '__main__': main()
