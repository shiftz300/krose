#!/usr/bin/env python3
"""Execute v1.2.4 external MIDI clock gates and source watchdog in private RAM."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import random
import struct
from pathlib import Path
from program_firmware import Arm, Firmware, FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT = ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
WATCH = 0xC1B58340
CONFIG = 0xC1DCD62A
MASK = 0xFFFFFFFF


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    f = Firmware()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('external-clock-watchdog', 0x2C7020, 0x2C72B4),
                         ('midi-realtime-ingress', 0x2C21F8, 0x2C2558),
                         ('clock-source-predicate', 0x276090, 0x2760D4),
                         ('clock-tempo-restore', 0x2C4AF8, 0x2C4B60),
                         ('external-clock-consumers', 0x23F6B8, 0x23F7E0),
                         ('midi-byte-parser', 0x2C2E90, 0x2C4474)]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(output.getvalue())
    if not args.verify_arm:
        return
    a = Arm(f)
    msg, shared, mode, system, generator = [0x11000000+0x1000*i for i in range(5)]
    def word(p): return struct.unpack('<I', a.uc.mem_read(p, 4))[0]
    def byte(p): return bytes(a.uc.mem_read(p, 1))[0]
    def putb(p, v): a.uc.mem_write(p, bytes([v]))
    def half(p, v): a.uc.mem_write(p, struct.pack('<H', v & 65535))
    def call(entry, *argv): return a.call(entry, *argv)
    a.write(0xC1B5720C, shared)
    a.write(0xC199BD3C, mode)
    a.write(0xC1B58488, generator)
    constructor_cases = 0
    for entry in [0x2C7020, 0x2C7048]:
        a.uc.mem_write(WATCH, b'\xA5'*0x24)
        call(entry, WATCH)
        expected = bytearray(b'\xA5'*0x24)
        for off in [0, 4, 8, 0x14, 0x18, 0x1C]:
            expected[off:off+4] = bytes(4)
        expected[0x10] = 1
        assert bytes(a.uc.mem_read(WATCH, 0x24)) == expected
        constructor_cases += 1

    # Independent event model. Deliberately retain wrapped absolute deadline
    # comparisons: replacing them with elapsed subtraction changes the firmware.
    rng = random.Random(0x2C70B8)
    watcher_operations = 0
    timeout_examples = []
    for origin, grace_after, pulse_again in itertools.product(
            [0, 1000, MASK-501, MASK-500, MASK-100, MASK-63, MASK-1, MASK],
            [None, 0, 10, 450], [None, 50, 499]):
        state = dict(now=origin, last=origin, present=1, grace=0, marked=0)
        a.uc.mem_write(WATCH, bytes(0x24))
        a.write(WATCH, origin)
        call(0x2C7078, WATCH)
        first_absent = None
        for visit in range(1, 603):
            elapsed_before = visit-1
            if elapsed_before == grace_after:
                call(0x2C709C, WATCH)
                if state['present']:
                    state['grace'], state['marked'] = 1, state['now']
                watcher_operations += 1
            if elapsed_before == pulse_again:
                call(0x2C7078, WATCH)
                state.update(last=state['now'], present=1, grace=0)
                watcher_operations += 1
            state['now'] = (state['now']+1) & MASK
            if state['present']:
                if ((state['last']+500) & MASK) < state['now']:
                    state['present'] = 0
                elif state['grace'] and ((state['marked']+63) & MASK) < state['now']:
                    state['present'] = state['grace'] = 0
            call(0x2C70B8, WATCH)
            assert [word(WATCH+x) for x in [0, 4, 8, 0x1C, 0x20]] == [
                state[k] for k in ['now', 'last', 'present', 'grace', 'marked']]
            watcher_operations += 1
            if first_absent is None and not state['present']:
                first_absent = visit
        timeout_examples.append(dict(origin=origin, grace_after=grace_after,
                                     pulse_again=pulse_again, first_absent_visit=first_absent))
    # Random interleavings, including absence, repeated markers and fresh pulses.
    state = dict(now=0, last=0, present=0, grace=0, marked=0)
    a.uc.mem_write(WATCH, bytes(0x24))
    for _ in range(5000):
        event = rng.choices(['tick', 'pulse', 'mark'], [94, 4, 2])[0]
        if event == 'pulse':
            state.update(last=state['now'], present=1, grace=0)
            call(0x2C7078, WATCH)
        elif event == 'mark':
            if state['present']:
                state.update(grace=1, marked=state['now'])
            call(0x2C709C, WATCH)
        else:
            state['now'] = (state['now']+1) & MASK
            if state['present']:
                if ((state['last']+500) & MASK) < state['now']:
                    state['present'] = 0
                elif state['grace'] and ((state['marked']+63) & MASK) < state['now']:
                    state['grace'] = state['present'] = 0
            call(0x2C70B8, WATCH)
        assert [word(WATCH+x) for x in [0, 4, 8, 0x1C, 0x20]] == [
            state[k] for k in ['now', 'last', 'present', 'grace', 'marked']]
        watcher_operations += 1

    events = []
    consumer_result = 0
    def event(name):
        def stub(m):
            events.append(name)
            return consumer_result
        return stub
    a.stubs = {off: event(name) for off, name in [(0x2B30, 'clock-fanout'),
        (0x23F6B8, 'sequencer-clock'), (0x23F7E0, 'start'),
        (0x23F93C, 'continue'), (0x23FAC0, 'stop')]}
    ingress_stubs = dict(a.stubs)
    ingress_cases = 0
    accepted_clock_cases = 0
    ingress_examples = []
    # 4..7 and ports outside 7/8 are synthetic raw-input boundaries, not UI modes.
    for source, port, present, rt, seqmode, consumer_result, status in itertools.product(
            range(8), range(10), [0, 1], [0, 1], [0, 3], [0, 1],
            [0xF2, 0xF3, 0xF8, 0xFA, 0xFB, 0xFC]):
        a.uc.mem_write(WATCH, bytes(0x24))
        a.write(WATCH, 123, 99, present)
        a.write(WATCH+0x1C, 1)
        putb(CONFIG, (source << 1) | (rt << 7))
        a.write(mode, seqmode)
        a.write(shared+4, 0xFFFFFFF5)
        a.uc.mem_write(msg, bytes(0x20))
        putb(msg, 0x90)
        putb(msg+0xB, 0x55)
        a.write(msg+0x10, 1)
        events.clear()
        returned = call(0x2C21F8, msg, status, port)
        new_present = 1 if status == 0xF8 else present
        internal = source == 0 or source == 3 and not new_present
        accepted = port == 7 if source == 1 else port == 8 if source == 2 else not internal and port > 6
        output = accepted and rt and status in [0xFA, 0xFB, 0xFC] and (seqmode != 3 or consumer_result != 0)
        expected_events = []
        if accepted and status == 0xF8:
            expected_events = ['clock-fanout', 'sequencer-clock']
            accepted_clock_cases += 1
        elif accepted and rt and seqmode == 3 and status in [0xFA, 0xFB, 0xFC]:
            expected_events = [{0xFA:'start', 0xFB:'continue', 0xFC:'stop'}[status]]
        expected_state = 0x7C if status == 0xF3 else (0x7A if accepted and rt else 0) if status == 0xF2 else 1
        assert events == expected_events, (source, port, status, events, expected_events)
        assert returned == int(output)
        assert byte(msg) == (status if output or status == 0xF3 or status == 0xF2 and accepted and rt else 0x90)
        assert byte(msg+0xB) == (0x90 if output else 0x55)
        assert word(msg+0x10) == expected_state
        assert word(shared+4) == ((0xFFFFFFF5+20) & MASK if accepted and status == 0xF8 else 0xFFFFFFF5)
        assert word(WATCH+8) == new_present
        assert word(WATCH+4) == (123 if status == 0xF8 else 99)
        assert word(WATCH+0x1C) == (0 if status == 0xF8 else 1)
        ingress_cases += 1
        if source <= 3 and port in [6, 7, 8] and not present and rt and not seqmode and not consumer_result and status in [0xF8, 0xFA]:
            ingress_examples.append(dict(source=source, port=port, status=status,
                                         present_after=new_present, accepted=bool(accepted), forwarded=bool(output)))

    # Real byte parser: interleave clocks with incomplete and running-status
    # channel messages. Only the pre-parser sequencer observer is intercepted.
    a.stubs[0x243DB0] = lambda m: 0
    a.write(0xC1B571C4, 0)
    parser_cases = 0
    for channel, status_base, port, insert in itertools.product(range(16),
            [0x80, 0x90, 0xA0, 0xB0, 0xD0, 0xE0], [7, 8], range(6)):
        putb(CONFIG, 6)
        a.uc.mem_write(WATCH, bytes(0x24))
        a.write(shared+4, 0)
        a.uc.mem_write(msg, bytes(0x20))
        a.write(msg+0x18, MASK)
        status = status_base | channel
        stream = [status, 60, 91, 62, 105] if status_base != 0xD0 else [status, 60, 62]
        stream[insert:insert] = [0xF8, 0xFE, 0xF8]
        packets = []
        for value in stream:
            complete = call(0x2C2E90, msg, value, port)
            if complete:
                packets.append(list(a.uc.mem_read(msg, 3)))
        expected = [[status, 60, 91], [status, 62, 105]] if status_base != 0xD0 else [[status, 60, 0], [status, 62, 0]]
        assert packets == expected, (stream, packets, expected)
        assert word(shared+4) == 40 and word(WATCH+8) == 1
        parser_cases += 1

    # Publish transitions. Execute the original tempo restore and 64-bit setter;
    # intercept UI/music notifications, parameter lookup and critical helpers.
    setting = 0
    def notify(name, result=0):
        def stub(m):
            events.append(dict(name=name, switching=word(WATCH+0x14)))
            return result
        return stub
    a.stubs = {0xD5AC4: lambda m: setting, 0x132660: lambda m: 0x53,
               0x132670: lambda m: 0, 0x206FA8: notify('source-event'),
               0x2405B0: notify('sequencer-reset'), 0x41F34: notify('read-local-source', 2),
               0x345AC: notify('ui-refresh'), 0x41530: notify('music-reset'),
               0x3F64: notify('consumer-refresh')}
    publisher_cases = []
    for present, published, hold, seqmode, inhibit, setting in itertools.product(
            [0, 1], [0, 1], [0, 1], [0, 3], [0, 1], range(4)):
        a.uc.mem_write(WATCH, bytes(0x24))
        a.write(WATCH+8, present, published)
        call(0x2C72AC, WATCH, hold)
        a.write(mode, seqmode)
        putb(CONFIG, setting << 1)
        putb(0xC17163C1, inhibit)
        half(0xC171D526, 0xFFFF)
        a.write(shared, 12345, 77, MASK, 0, 9)
        a.uc.mem_write(generator, bytes(0x38))
        call(0x2C8024, generator)
        events.clear()
        assert call(0x2C7110, WATCH, system) == 0
        blocked = present == published or hold or seqmode == 3 and inhibit
        active = not blocked and setting == 3
        assert word(WATCH+0xC) == (published if blocked else present)
        assert word(WATCH+0x14) == 0
        assert word(shared+0x10) == (present if active else 9)
        assert word(generator+0x2C) == (12345 if active and not present and seqmode != 3 else 12000)
        names = []
        if active:
            if seqmode == 3:
                names = ['source-event'] if present else ['sequencer-reset', 'read-local-source', 'source-event', 'ui-refresh']
            else:
                names = ['music-reset']
            names += ['consumer-refresh']
        assert [e['name'] for e in events] == names
        assert all(e['switching'] == int(seqmode == 3 and e['name'] != 'consumer-refresh') for e in events)
        assert struct.unpack('<H', a.uc.mem_read(0xC171D526, 2))[0] == (0xFDFF if active and seqmode == 3 and not present else 0xFFFF)
        publisher_cases.append(dict(present=present, published=published, hold=hold,
                                   sequencer_mode=seqmode == 3, inhibit=inhibit, setting=setting,
                                   changed=bool(active), notifications=events[:]))

    # F8 -> original shared counter -> original virtual PCM manager -> waits.
    sound, manager, managers, timbres, nodes, voices = [0x11010000+0x1000*i for i in range(6)]
    a.write(sound+8, 1)
    a.write(sound+0x38, managers)
    a.write(sound+0x1C, timbres)
    a.write(managers, manager)
    a.write(manager, 0xC0470EBC)
    a.write(manager+4, voices)
    a.write(manager+0xE4, 4)
    putb(manager+0xE8, 0)
    a.stubs = dict(ingress_stubs)
    a.stubs[0x2741EC] = lambda m: 0
    bridge_runs = []
    for source, port in itertools.product(range(4), [7, 8]):
        putb(CONFIG, source << 1)
        a.uc.mem_write(WATCH, bytes(0x24))
        a.write(shared+4, MASK-9)
        a.write(0xC174327C, MASK-9)
        a.write(0xC1743278, 0)
        delay_head = manager+0xCC
        a.write(delay_head, delay_head, delay_head, 0)
        states = [[60, 0], [480, 0], [480, 3], [0, -1]]
        ready = [None]*4
        for i in reversed(range(4)):
            v = voices+588*i
            a.uc.mem_write(v, bytes(588))
            half(v+0x10, 0x80)
            half(v+0x208, states[i][1])
            a.write(v+0x234, states[i][0])
            a.write(nodes+12*i, 0, 0, v)
            call(0x272458, delay_head, nodes+12*i)
        accepted = source == 3 or source == 1 and port == 7 or source == 2 and port == 8
        for pulse in range(1, 31):
            call(0x2C21F8, msg, 0xF8, port)
            call(0x271324, sound)
            for i, state in enumerate(states):
                if state[0]:
                    state[0] = max(0, state[0]-(20 if accepted else 0))
                elif state[1] > 0:
                    state[1] -= 1
                v = voices+588*i
                assert word(v+0x234) == state[0]
                assert struct.unpack('<h', a.uc.mem_read(v+0x208, 2))[0] == state[1]
                is_ready = bool(struct.unpack('<H', a.uc.mem_read(v+0x10, 2))[0] & 8)
                if is_ready and ready[i] is None:
                    ready[i] = pulse
            assert word(shared+4) == (MASK-9+(20*pulse if accepted else 0)) & MASK
        assert ready == ([3, 24, 27, None] if accepted else [None]*4)
        bridge_runs.append(dict(source=source, port=port, accepted=bool(accepted), ready_service=ready))

    # Continuous Auto trajectory with real watchdog, publisher, internal
    # generator and F8 ingress. Time advances in deterministic fixture order.
    from firmware_music_clock import ClockModel
    model = ClockModel()
    setting = 3
    a.stubs = {0xD5AC4: lambda m: 3, 0x132660: lambda m: 0x53,
               0x132670: lambda m: 0, 0x41530: lambda m: 0,
               0x3F64: lambda m: 0, 0x240DAC: lambda m: 0,
               0x1396CC: lambda m: 0, 0x415CC: lambda m: 0,
               0x2B00: lambda m: 0, 0x24725C: lambda m: 0,
               0x2B30: lambda m: 0, 0x23F6B8: lambda m: 0}
    a.uc.mem_write(WATCH, bytes(0x24))
    a.uc.mem_write(generator, bytes(0x38))
    call(0x2C8024, generator)
    putb(CONFIG, 6)
    putb(0xC17163C1, 0)
    a.write(mode, 0)
    a.write(shared, 12000, 0, MASK, 0, 0)
    total = 0
    auto_trace = []
    pulse_visits = set(range(21, 253, 21))
    for visit in range(1, 1001):
        call(0x2C70B8, WATCH)
        pulse = visit in pulse_visits
        if pulse:
            # Alternate both physical input codes: Auto accepts either source.
            call(0x2C21F8, msg, 0xF8, 7+(visit//21)%2)
            total += 20
        call(0x2C7110, WATCH, system)
        internal_ticks = model.advance()
        call(0x2C832C, generator)
        external = 21 <= visit <= 752
        if not external:
            total += internal_ticks
        assert word(WATCH+8) == int(external)
        assert word(shared+0x10) == int(external)
        assert word(shared+4) == total
        auto_trace.append(dict(visit=visit, pulse=pulse, external=external,
                               shared_ticks=total, generator_ticks=internal_ticks))

    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False,
                  constructor_cases=constructor_cases, watcher_operations=watcher_operations,
                  parser_cases=parser_cases, auto_trace=auto_trace,
                  timeout_examples=timeout_examples, ingress_cases=ingress_cases,
                  accepted_clock_cases=accepted_clock_cases, ingress_examples=ingress_examples,
                  publisher_cases=publisher_cases, bridge_runs=bridge_runs, bridge_services=240,
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                  additional_helpers={'firmware_music_clock.py': hashlib.sha256((ROOT/'research/tools/firmware_music_clock.py').read_bytes()).hexdigest()},
                  boundaries=['Watchdog, ingress, source predicate, publication and tempo restore run original ARM',
                              'Musical consumers, UI notifications and parameter lookup intercepted',
                              'Source codes 4..7 and ports other than 7/8 are synthetic byte boundaries',
                              'Watchdog visits not measured physical milliseconds; manual documents 500 ms',
                              'Grace marker caller is sequencer operation 0x24D3C4; not equated with MIDI FC',
                              '24 accepted F8 pulses add 480 ticks through original virtual PCM wait path',
                              'No hardware, OS startup, DMA, audio rendering or complete sequencer state machine'])
    (OUT/'external-clock-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, watcher_operations=watcher_operations, ingress_cases=ingress_cases,
                          publisher_cases=len(publisher_cases), parser_cases=parser_cases,
                          auto_visits=len(auto_trace), bridge_services=240), indent=2))


if __name__ == '__main__':
    main()
