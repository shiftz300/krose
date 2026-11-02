#!/usr/bin/env python3
"""Original ARM musical tick generator and beat-synchronous voice waits."""
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
Q = 1_000_000_000
NUMERATOR = 12_500_000_000_000
MASK = (1 << 64)-1


def signed64(value):
    value &= MASK
    return value-(1 << 64) if value >> 63 else value


class ClockModel:
    def __init__(self):
        self.now = self.origin = self.remainder = 0
        self.desired_tempo = self.active_tempo = 12000
        self.desired_period = NUMERATOR//12000
        self.active_period = 0
        self.initial = 1
        self.paused = 0

    def tempo(self, value):
        if 4000 <= value <= 30000:
            self.desired_tempo = value
            self.desired_period = NUMERATOR//value

    def resume(self, reset):
        self.origin = self.now
        if reset:
            self.active_period = self.desired_period
            self.active_tempo = self.desired_tempo
            self.remainder = 0
        self.paused = 0

    def advance(self):
        self.now = (self.now+Q) & MASK
        if self.initial:
            self.resume(True)
            self.initial = 0
            return 0
        if self.paused:
            return 0
        ticks = 0
        while ticks < 11:
            elapsed = signed64(self.now-self.origin+self.remainder)
            due = self.active_period < elapsed+Q
            self.origin = self.now
            if due:
                self.remainder = signed64(elapsed-self.active_period)
                self.active_period = self.desired_period
                self.active_tempo = self.desired_tempo
                ticks += 1
            else:
                self.remainder = elapsed
                break
        return ticks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    f = Firmware()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('internal-tick-generator', 0x2C8024, 0x2C838C),
                         ('timer21-clock-call', 0x117064, 0x117144),
                         ('timer21-register-setup', 0x130620, 0x130650),
                         ('voice-wait-countdown', 0x1FCECC, 0x1FCF58),
                         ('voice-wait-manager', 0x1FD3CC, 0x1FD45C),
                         ('sound-manager-clock-dispatch', 0x271324, 0x271400),
                         ('tempo-delay-value', 0x2C4DE0, 0x2C4DF8)]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(output.getvalue())
    if not args.verify_arm:
        return
    a = Arm(f)
    clock, shared, head, nodes, voices = [0x11000000+0x10000*i for i in range(5)]

    def word(p):
        return struct.unpack('<I', a.uc.mem_read(p, 4))[0]

    def quad(p):
        return struct.unpack('<Q', a.uc.mem_read(p, 8))[0]

    def putq(p, value):
        a.uc.mem_write(p, struct.pack('<Q', value & MASK))

    def put16(p, value):
        a.uc.mem_write(p, struct.pack('<H', value & 65535))

    def call(entry, *argv, **kwargs):
        return a.call(entry, *argv, **kwargs)

    events = []
    a.write(0xC1B5720C, shared)
    # Keep the original tick dispatcher and source-selection predicate.
    # Musical consumers and interrupt-mask helpers are boundary intercepts.
    a.stubs = {0x132660: lambda m: 0x53, 0x132670: lambda m: 0,
               0x240DAC: lambda m: 0, 0x1396CC: lambda m: events.append('internal') or 0,
               0x415CC: lambda m: events.append('external') or 0,
               0x2B00: lambda m: events.append('three-consumers') or 0,
               0x24725C: lambda m: events.append('sequencer') or 0}
    clock_stubs = dict(a.stubs)
    # Default source=internal. 0x276090 runs against the actual global bytes.
    a.uc.mem_write(0xC1DCD62A, b'\0')
    a.uc.mem_write(0xC1B58348, bytes(4))

    def initialize():
        a.uc.mem_write(clock, bytes(0x38))
        call(0x2C8024, clock)
        return ClockModel()

    def check(model):
        expected = [model.origin & MASK, model.remainder & MASK, model.desired_period,
                    model.active_period, model.now, model.active_tempo, model.desired_tempo,
                    model.initial, model.paused]
        actual = [quad(clock+o) for o in [0, 8, 16, 24, 32]]+[word(clock+o) for o in [40, 44, 48, 52]]
        assert actual == expected, (actual, expected)

    model = initialize()
    # The constructor intentionally leaves active fields 0..0xF and +0x18
    # for the first advance; this fixture supplies zeroed storage.
    check(model)
    period_cases = 0
    for tempo in range(4000, 30001):
        call(0x2C80D0, clock, tempo)
        assert word(clock+0x2C) == tempo and quad(clock+0x10) == NUMERATOR//tempo
        period_cases += 1
    for tempo in [0, 3999, 30001, 65535, 0xFFFFFFFF]:
        before = bytes(a.uc.mem_read(clock, 0x38))
        call(0x2C80D0, clock, tempo)
        assert bytes(a.uc.mem_read(clock, 0x38)) == before
    trajectories = []
    for tempo in [4000, 6000, 12000, 18000, 24000, 30000]:
        model = initialize()
        model.tempo(tempo)
        call(0x2C80D0, clock, tempo)
        total, ticks_by_visit, checkpoints = 0, [], []
        for visit in range(1, 2001):
            events.clear()
            expected = model.advance()
            before = word(shared+4)
            call(0x2C832C, clock)
            actual = (word(shared+4)-before) & 0xFFFFFFFF
            assert actual == expected
            assert events == ['internal', 'three-consumers', 'sequencer']*expected
            check(model)
            total += actual
            ticks_by_visit.append(actual)
            if visit in [1, 2, 10, 100, 1000, 2000]:
                checkpoints.append(dict(visit=visit, ticks=total, remainder=model.remainder))
        trajectories.append(dict(tempo_raw=tempo, visits=2000, total_ticks=total,
                                 ticks_by_visit=ticks_by_visit, checkpoints=checkpoints))
    # Mid-period changes, explicit hold/resume, integer carry and clock wrap.
    transitions = []
    for reset_on_resume in [0, 1]:
        model = initialize()
        for visit in range(1, 601):
            if visit in [37, 173, 299]:
                value = {37: 30000, 173: 4000, 299: 15555}[visit]
                model.tempo(value)
                call(0x2C80D0, clock, value)
            if visit == 320:
                model.paused = 1
                call(0x2C8190, clock)
            if visit == 400:
                model.resume(reset_on_resume)
                call(0x2C819C, clock, reset_on_resume)
            before = word(shared+4)
            expected = model.advance()
            call(0x2C832C, clock)
            assert (word(shared+4)-before) & 0xFFFFFFFF == expected
            check(model)
            if visit in [36, 37, 38, 172, 173, 174, 299, 319, 320, 399, 400, 401, 600]:
                transitions.append(dict(visit=visit, reset_on_resume=reset_on_resume, ticks=expected,
                                        active_tempo=model.active_tempo, desired_tempo=model.desired_tempo,
                                        remainder=model.remainder, paused=model.paused))
    wrap_cases = 0
    for origin in [(1 << 32)-Q//2, (1 << 64)-Q//2]:
        model = initialize()
        model.initial = 0
        model.resume(True)
        model.now = model.origin = origin
        putq(clock, origin)
        putq(clock+0x20, origin)
        putq(clock+0x18, model.active_period)
        a.write(clock+0x30, 0)
        a.write(shared+4, 0xFFFFFFFE)
        for _ in range(20):
            before = word(shared+4)
            expected = model.advance()
            call(0x2C832C, clock)
            assert (word(shared+4)-before) & 0xFFFFFFFF == expected
            check(model)
            wrap_cases += 1
    # A deliberately seeded backlog tests the per-visit cap of eleven ticks.
    model = initialize()
    call(0x2C832C, clock)
    putq(clock+8, 100*Q)
    before = word(shared+4)
    call(0x2C832C, clock)
    backlog_ticks = (word(shared+4)-before) & 0xFFFFFFFF
    assert backlog_ticks == 11
    # The source gate changes consumers and decides whether shared +4 advances.
    source_cases = []
    for mode, external_present in itertools.product(range(8), [0, 1]):
        a.uc.mem_write(0xC1DCD62A, bytes([mode << 1]))
        a.write(0xC1B58348, external_present)
        internal = mode == 0 or mode == 3 and not external_present
        events.clear()
        before = word(shared+4)
        call(0x2C82C0)
        assert events == ['internal' if internal else 'external', 'three-consumers', 'sequencer']
        assert (word(shared+4)-before) & 0xFFFFFFFF == int(internal)
        source_cases.append(dict(raw_mode=mode, external_present=bool(external_present), internal=internal))
    a.uc.mem_write(0xC1DCD62A, b'\0')
    a.write(0xC1B58348, 0)
    # Beat delay uses ten bases; 10..15 would read beyond this table and are
    # deliberately excluded. Multipliers below exhaust the stored byte.
    bases = list(struct.unpack_from('<10H', f.data, 0x457B9C))
    delay_value_cases = 0
    for base, multiplier in itertools.product(range(10), range(256)):
        assert call(0x2C4DE0, base, multiplier) == bases[base]*multiplier
        delay_value_cases += 1
    # Original delay list body: beat waiting is serviced before fixed waiting.
    a.stubs = {}
    a.write(head, nodes, nodes, 0)
    a.write(nodes, head, head, voices)
    countdown_cases, countdown_examples = 0, []
    for ticks, delay, delta in itertools.product([0, 1, 2, 480], [-1, 0, 1, 3], [0, 1, 2, 20, 480]):
        a.uc.mem_write(voices, bytes(588))
        put16(voices+0x10, 0x80)
        put16(voices+0x208, delay)
        a.write(voices+0x234, ticks)
        expected_ticks, expected_delay, ready = ticks, delay, False
        if ticks:
            expected_ticks = max(0, ticks-delta)
            ready = expected_ticks == 0 and delay == 0
        elif delay > 0:
            expected_delay -= 1
            ready = expected_delay == 0
        call(0x1FCECC, head, delta)
        actual_delay = struct.unpack('<h', a.uc.mem_read(voices+0x208, 2))[0]
        assert (word(voices+0x234), actual_delay, bool(struct.unpack('<H', a.uc.mem_read(voices+0x10, 2))[0] & 8)) == (expected_ticks, expected_delay, ready)
        countdown_cases += 1
        if ticks in [0, 2] and delta in [0, 2]:
            countdown_examples.append(dict(before=[ticks, delay], delta=delta, after=[expected_ticks, expected_delay], ready=ready))
    # Connect the real musical counter to CSoundManager's real virtual dispatch
    # and the original PCM delay list. The per-voice control slice is empty;
    # readiness and later TG startup remain distinct scheduling stages.
    sound, manager, managers, timbres = 0x11080000, 0x11081000, 0x11082000, 0x11083000
    a.write(sound+8, 1)
    a.write(sound+0x38, managers)
    a.write(sound+0x1C, timbres)
    a.write(managers, manager)
    a.write(manager, 0xC0470EBC)
    a.write(manager+4, voices)
    a.write(manager+0xE4, 5)
    a.uc.mem_write(manager+0xE8, b'\0')
    a.stubs = dict(clock_stubs)
    a.stubs[0x2741EC] = lambda m: 0
    bridge_runs = []
    for initial_tempo, later_tempo in [(4000, None), (12000, None), (30000, None), (12000, 24000)]:
        model = initialize()
        model.tempo(initial_tempo)
        call(0x2C80D0, clock, initial_tempo)
        a.write(shared+4, 0)
        a.write(0xC174327C, 0)
        a.write(0xC1743278, 0)
        a.write(sound+0x3C, 0)
        delay_head = manager+0xCC
        a.write(delay_head, delay_head, delay_head, 0)
        states = [[60, 0, False], [480, 0, False], [480, 3, False], [0, 3, False], [0, -1, False]]
        first_ready = [None]*5
        for i in reversed(range(5)):
            v = voices+588*i
            a.uc.mem_write(v, bytes(588))
            put16(v+0x10, 0x80)
            put16(v+0x208, states[i][1])
            a.write(v+0x234, states[i][0])
            a.write(nodes+12*i, 0, 0, v)
            call(0x272458, delay_head, nodes+12*i)
        for visit in range(1, 2001):
            if later_tempo and visit == 200:
                model.tempo(later_tempo)
                call(0x2C80D0, clock, later_tempo)
            delta = model.advance()
            call(0x2C832C, clock)
            call(0x271324, sound)
            for i, state in enumerate(states):
                ticks, delay, ready = state
                if ticks:
                    ticks = max(0, ticks-delta)
                    ready |= ticks == 0 and delay == 0
                elif delay > 0:
                    delay -= 1
                    ready |= delay == 0
                state[:] = [ticks, delay, ready]
                v = voices+588*i
                actual = [word(v+0x234), struct.unpack('<h', a.uc.mem_read(v+0x208, 2))[0],
                          bool(struct.unpack('<H', a.uc.mem_read(v+0x10, 2))[0] & 8)]
                assert actual == state
                if ready and first_ready[i] is None:
                    first_ready[i] = visit
            assert word(0xC174327C) == word(shared+4)
            assert word(sound+0x3C) == visit
        assert first_ready[2] == first_ready[1]+3 and first_ready[3] == 3 and first_ready[4] is None
        bridge_runs.append(dict(initial_tempo=initial_tempo, tempo_at_visit_200=later_tempo,
                                voices=[dict(beat_delay=t, fixed_delay=d, ready_visit=first_ready[i])
                                        for i, (t, d) in enumerate([(60, 0), (480, 0), (480, 3), (0, 3), (0, -1)])]))
    # Modular 32-bit counter subtraction is performed before virtual dispatch.
    # A busy manager skips its body after the shared counter snapshot advances.
    bridge_boundaries = []
    for previous, current, busy in itertools.product([0, 0xFFFFFFFE], [0, 2], [0, 1]):
        a.write(0xC174327C, previous)
        a.write(shared+4, current)
        a.uc.mem_write(manager+0xE0, bytes([busy]))
        for i in range(5):
            a.write(voices+588*i+0x234, 480)
            put16(voices+588*i+0x208, 0)
            put16(voices+588*i+0x10, 0x80)
        call(0x271324, sound)
        delta = (current-previous) & 0xFFFFFFFF
        # The countdown uses signed 32-bit subtraction; retain its exact raw
        # arithmetic even for an intentionally backwards synthetic counter.
        remaining = (480-delta) & 0xFFFFFFFF
        if remaining & 0x80000000 or remaining == 0:
            remaining = 0
        expected = 480 if busy else remaining
        assert all(word(voices+588*i+0x234) == expected for i in range(5))
        assert word(0xC174327C) == current
        bridge_boundaries.append(dict(previous=previous, current=current, delta=delta, busy=bool(busy), remaining=expected))
    # Verify the producer of both wait fields through complete voice control
    # initialization. Use one real ROM sample with Concert OSC parameters.
    from voice_firmware import VoiceOracle
    oracle = VoiceOracle()
    a = oracle.arm
    sample, region, clock = 0x11050000, 0x11051000, 0x11052000
    region_raw = f.data[0x492C28:0x492C28+20]
    sample_id = struct.unpack_from('<H', region_raw)[0]
    fixed_table = list(struct.unpack_from('<98h', f.data, 0x406226))
    starts = []
    a.stubs[0x275564] = lambda m: 0
    a.stubs[0x1F9028] = lambda m: starts.append(m.get('R0')) or 0
    initialization_cases = []
    combinations = [(0, 0, 0, od, pd) for od, pd in itertools.product([0, 1, 97], [0, 12, 97])]
    combinations += [(1, base, mult, od, pd) for base, mult, od, pd in itertools.product(range(10), [0, 1, 2], [0, 1, 97], [0, 12, 97])]
    for enabled, base, multiplier, osc_delay, part_delay in combinations:
        oracle.initialize(36, 85, 0)
        v = oracle.voice
        a.write(v+0x0C, oracle.controls)
        a.write(v+0x20, sample)
        a.write(v+0x22C, region)
        a.write(oracle.context+0x10, oracle.controls)
        a.uc.mem_write(sample, f.data[0x410ABC+sample_id*64:0x410ABC+(sample_id+1)*64])
        a.uc.mem_write(region, region_raw)
        a.write(0xC1B5720C, clock)
        a.write(clock, 12000, 123)
        a.write(0xC165D9B4, 36)
        a.write(0xC165D9B0, region_raw[4] << 8)
        a.write(0xC165D9AC, struct.unpack_from('<h', region_raw, 6)[0])
        a.write(0xC165D9A8, 36 << 8)
        a.write(0xC165D9A0, 64)
        for p, value in [(0xC165D9A4, 127), (0xC165D9A5, 0), (0xC165D9B8, 0),
                         (oracle.osc+0x2C, osc_delay), (oracle.part+0x0A, part_delay),
                         (oracle.part+0x0C, (enabled << 7) | base), (oracle.part+0x0D, multiplier)]:
            a.uc.mem_write(p, bytes([value]))
        starts.clear()
        assert call(0x1F7278, v, oracle.runtime, 0) == 1
        ticks = bases[base]*multiplier if enabled else 0
        delay = fixed_table[osc_delay]+(0 if enabled else fixed_table[part_delay])
        if fixed_table[osc_delay] == -1 or not enabled and fixed_table[part_delay] == -1:
            delay, ticks = -1, 0
        assert word(v+0x234) == ticks
        assert struct.unpack('<h', a.uc.mem_read(v+0x208, 2))[0] == delay
        assert starts == ([v] if ticks == delay == 0 else [])
        initialization_cases.append(dict(sync=bool(enabled), base=base, multiplier=multiplier,
                                        osc_delay_index=osc_delay, part_delay_index=part_delay,
                                        beat_wait=ticks, fixed_wait=delay, immediate_start=bool(starts)))
    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False, period_cases=period_cases,
                  invalid_tempo_cases=5, trajectories=trajectories, transition_visits=1200,
                  transitions=transitions, wrap_visits=wrap_cases, backlog_ticks=backlog_ticks,
                  source_cases=source_cases, delay_bases=bases, delay_value_cases=delay_value_cases,
                  countdown_cases=countdown_cases, countdown_examples=countdown_examples,
                  bridge_visits=8000, bridge_runs=bridge_runs, bridge_boundaries=bridge_boundaries,
                  initialization_cases=initialization_cases,
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                  additional_helpers={'voice_firmware.py': hashlib.sha256((ROOT/'research/tools/voice_firmware.py').read_bytes()).hexdigest()},
                  inputs=[dict(path='research/output/kep-analysis/Concert_SE_Grand/program.bin', sha256=hashlib.sha256(oracle.program).hexdigest())],
                  boundaries=['Clock constructor, 64-bit division, tempo setter, tick loop, source predicate and counter increment execute',
                              'Interrupt-mask helpers and musical consumers intercepted; no physical timer or audio',
                              'Timing plots use timer visits; conversion to measured seconds not asserted',
                              'Clock counter -> original CSoundManager -> original virtual PCM manager -> delay list connected for 8000 visits',
                              'Clock advance and sound-manager service invoked sequentially in fixture; OS scheduling and TG consumption remain separate',
                              '279 complete control initializations verify fixed/beat wait production and immediate TG-start gate; TG body captured',
                              'Multiplier byte exhausted; UI multiplier range not inferred from raw coverage'])
    (OUT/'music-clock-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, period_cases=period_cases, clock_visits=12000+1200+wrap_cases,
                          bridge_visits=8000, initialization_cases=len(initialization_cases),
                          delay_value_cases=delay_value_cases, countdown_cases=countdown_cases), indent=2))


if __name__ == '__main__':
    main()
