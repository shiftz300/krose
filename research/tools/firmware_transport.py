#!/usr/bin/env python3
"""Original ARM MIDI transport requests and deferred position handling."""
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
STATE, FLAGS, BUSY = 0xC1714360, 0xC04ADF70, 0xC17163C1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    f = Firmware()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('transport-requests', 0x23F7E0, 0x23FDBC+4),
                         ('transport-deferred-completion', 0x23F570, 0x23F6A4),
                         ('transport-stop-request', 0x2650B4, 0x26514C),
                         ('transport-external-gate', 0x240F6C, 0x240FAC),
                         ('transport-deferred-dispatch', 0x24A3AC, 0x24A6E4)]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out): inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm: return
    a = Arm(f)
    def b(p): return bytes(a.uc.mem_read(p, 1))[0]
    def h(p): return struct.unpack('<H', a.uc.mem_read(p, 2))[0]
    def w(p): return struct.unpack('<I', a.uc.mem_read(p, 4))[0]
    def pb(p, v): a.uc.mem_write(p, bytes([v & 255]))
    def ph(p, v): a.uc.mem_write(p, struct.pack('<H', v & 65535))
    def call(p, *args): return a.call(p, *args)
    a.stubs = {0x132660: lambda m: 0x53, 0x132670: lambda m: 0}
    rng = random.Random(0x23F7E0)
    starts = []
    for case in range(8192):
        command = case & 1
        source, present, enabled, blocked = [rng.randrange(n) for n in [4, 2, 2, 2]]
        pending, flags, primary = [rng.randrange(n) for n in [256, 65536, 256]]
        phase, busy = rng.choice([0, 7, 1, 255]), rng.randrange(2)
        a.uc.mem_write(STATE, bytes([primary, pending]))
        ph(FLAGS, flags)
        ph(FLAGS+2, blocked << 5)
        pb(BUSY, busy)
        pb(0xC17163D1, phase)
        pb(0xC1714371, enabled)
        pb(0xC1DCD62A, source << 1)
        a.write(0xC1B58348, present)
        a.write(0xC1714358, 123)
        a.write(0xC171435C, 456)
        external = source != 0 and (source != 3 or present != 0)
        accepted = enabled and external and not blocked
        ef, ep, eb, ec, eq, result = flags, primary, busy, 123, 456, 0
        if accepted:
            if 0 < pending < 128:
                if not primary & 0x18:
                    ep |= 0x10 if command else 8
                    ec = int(command and not primary & 0x20)
            elif not flags & 8 and phase in [0, 7] and not busy:
                ef |= 0xAC
                eb = 1
                eq = int(command and not primary & 0x20)
                result = 1
            ep &= ~0x20
        actual = call(0x23F93C if command else 0x23F7E0)
        assert [actual, h(FLAGS), b(STATE), b(STATE+1), b(BUSY), w(0xC1714358), w(0xC171435C)] == [result, ef, ep, pending, eb, ec, eq]
        if case < 32: starts.append(dict(continue_command=bool(command), source=source, pending=pending,
            primary_before=primary, primary_after=ep, flags_before=flags, flags_after=ef, forwarded=bool(result)))

    stop_cases = 0
    for source, present, enabled, blocked, flags in itertools.product(range(4), [0, 1], [0, 1], [0, 1], [0, 0x10, 0xFFFF]):
        pb(0xC1DCD62A, source << 1)
        a.write(0xC1B58348, present)
        pb(0xC1714371, enabled)
        ph(FLAGS+2, blocked << 5)
        ph(FLAGS, flags)
        ph(0xC171C3BE, 0xFFFF)
        ph(0xC171C42C, 0xFFFF)
        pb(0xC17163C0, 255)
        pb(0xC17163CE, 0xA0)
        ph(0xC171D526, 0x40)
        request = enabled and source != 0 and (source != 3 or present) and not blocked and not flags & 0x10
        assert call(0x23FAC0) == 1
        assert [h(FLAGS), h(0xC171C3BE), h(0xC171C42C), b(0xC17163C0), b(0xC17163CE), h(0xC171D526)] == (
            [flags | 0x34, 0xFFFB, 0xFFE8, 0, 0xA1, 0x2040] if request else [flags, 0xFFFF, 0xFFFF, 255, 0xA0, 0x40])
        stop_cases += 1

    # Exhaust the request byte and its signed completion comparison. Complete
    # handlers execute the original nested critical-section and decrement code.
    deferred_cases = 0
    for pending, primary, previous in itertools.product(range(256), [0, 8, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38], [0, 1, 2, 3, 4]):
        a.uc.mem_write(STATE, bytes([primary, pending]))
        a.write(0xC17163C8, previous)
        call(0x23F5F4, STATE)
        after = pending-1 if pending else 0
        ep, priority = primary, previous
        if not 0 < after < 128:
            request = 3 if primary & 8 else 2 if primary & 0x10 else 0
            priority = max(previous, request)
            ep &= ~0x18
        assert [b(STATE), b(STATE+1), w(0xC17163C8)] == [ep, after, priority]
        deferred_cases += 1

    # SPP acceptance increments the pending byte; processing stores the full
    # 14-bit position and invokes the original completion on rejected paths.
    events = []
    action_result = 0
    def action(m):
        events.append(['schedule', h(0xC17163C2)])
        return action_result
    def position(m):
        events.append(['position-notification', m.get('R1')])
        return 0
    a.stubs.update({0x23F118: lambda m: 0, 0x23F13C: lambda m: 0,
                    0x24A3AC: action, 0x242918: position})
    pb(0xC1DCD62A, 2)
    pb(0xC1714371, 1)
    ph(FLAGS+2, 0)
    pb(0xC1714350, 0)
    pb(0xC171D504, 0)
    pb(0xC17163CE, 0)
    for value in range(16384):
        a.uc.mem_write(STATE, bytes(2))
        pb(BUSY, 0)
        pb(0xC17163CD, 0)
        a.write(0xC171434C, 0)
        assert call(0x23FB4C) == 1
        assert [b(STATE), b(STATE+1)] == [0x20, 1]
        events.clear()
        call(0x23FBD8, 0, value & 127, value >> 7)
        assert h(0xC17163C2) == value
        assert b(0xC17163CD) == 2 and b(BUSY) == 0 and w(0xC171434C) == 0
        assert events == [['schedule', value], ['position-notification', value]]

    spp_gate_cases = 0
    for enabled, internal, blocked, locked, primary, pending in itertools.product([0, 1], [0, 1], [0, 1], [0, 1], [0, 8, 0x10, 0x18, 0x20], [0, 1, 127, 255]):
        pb(0xC1714371, enabled)
        pb(0xC1DCD62A, 0 if internal else 2)
        ph(FLAGS+2, blocked << 5)
        pb(0xC1714350, locked << 1)
        a.uc.mem_write(STATE, bytes([primary, pending]))
        accepted = enabled and not internal and not blocked and not locked and not primary & 0x18
        assert call(0x23FB4C) == int(accepted)
        assert [b(STATE), b(STATE+1)] == [primary | (0x20 if accepted else 0), (pending+int(accepted)) & 255]
        spp_gate_cases += 1

    # Deferred request sequences: position -> Start/Continue -> completion.
    sequences = []
    a.stubs.pop(0x24A3AC)
    a.stubs[0x24A290] = lambda m: events.append(['start-body']) or 0
    a.stubs[0x24D4CC] = lambda m: events.append(['continue-body']) or 0
    for commands in [(0,), (1,), (0, 1), (1, 0)]:
        pb(0xC1714371, 1)
        pb(0xC1DCD62A, 2)
        ph(FLAGS+2, 0)
        ph(FLAGS, 0)
        pb(0xC1714350, 0)
        a.uc.mem_write(STATE, bytes(2))
        a.write(0xC17163C8, 0)
        for ptr in [0xC17163C6, 0xC17163CC, 0xC17163CD, 0xC17163CE, 0xC17163CF, 0xC17163D1]: pb(ptr, 0)
        assert call(0x23FB4C) == 1
        trace = [['position-pending', b(STATE), b(STATE+1), 0]]
        for command in commands:
            assert call(0x23F93C if command else 0x23F7E0) == 0
            trace.append(['continue' if command else 'start', b(STATE), b(STATE+1), w(0xC17163C8)])
        call(0x23F5F4, STATE)
        assert b(STATE+1) == 0 and not b(STATE) & 0x18
        assert w(0xC17163C8) == (2 if commands[0] else 3)
        trace.append(['complete', b(STATE), b(STATE+1), w(0xC17163C8)])
        events.clear()
        assert call(0x24A3AC) == 1
        assert w(0xC17163C8) == 0 and h(FLAGS) == 0xAC
        assert w(0xC171435C) == w(0xC1714358) == 0
        assert events == [['continue-body' if commands[0] else 'start-body']]
        trace.append(['dispatch', h(FLAGS), w(0xC171435C), events[0][0]])
        sequences.append(trace)

    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False,
        start_continue_cases=8192, stop_cases=stop_cases, deferred_cases=deferred_cases,
        spp_value_cases=16384, spp_gate_cases=spp_gate_cases, sequences=sequences, examples=starts,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        boundaries=['Original external-source predicate, Start/Continue/Stop and stop flag writes execute',
                    'Original pending decrement, completion priority and 14-bit SPP storage execute',
                    'SPP scheduler, UI notification and outer lock bodies intercepted; deferred Start/Continue dispatch runs to body boundaries',
                    'Positions are request units; actual seek, track traversal and audio not executed',
                    'Random flag combinations and byte overflow characterize raw branches, not proven reachable states'])
    (OUT/'transport-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k == 'passed' or k.endswith('_cases')}, indent=2))


if __name__ == '__main__': main()
