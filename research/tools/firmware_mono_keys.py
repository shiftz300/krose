#!/usr/bin/env python3
"""Run original ARM mono-key priority and Note On/Off fallback state machines."""
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

OUT = ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'


class Model:
    def __init__(self, capacity, priority, legato):
        self.capacity, self.priority, self.legato = capacity, priority, legato
        self.keys = []
        self.velocity = 0

    def on(self, note, velocity):
        empty = not self.keys
        selected = empty or self.priority == 2 or (
            note < self.keys[0] if self.priority == 0 else note > self.keys[0])
        if len(self.keys) == self.capacity:
            self.keys.pop()
        if selected:
            self.keys.insert(0, note)
            self.velocity = velocity
        else:
            self.keys.append(note)
            self.keys.sort(reverse=self.priority == 1)
        return int(selected), int(empty and self.legato)

    def off(self, note):
        if note not in self.keys:
            return None
        index = self.keys.index(note)
        self.keys.pop(index)
        return self.keys[0] if index == 0 and self.keys else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    f = Firmware()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, lo, hi in [('mono-key-list', 0x270210, 0x270890),
                         ('timbre-key-capacity', 0x2724B0, 0x2725B0),
                         ('mono-note-on', 0x273D4C, 0x273E30),
                         ('mono-note-off', 0x274374, 0x274590)]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            inspect(f.data, lo, hi)
        (OUT/(name+'.arm.txt')).write_text(output.getvalue())
    if not args.verify_arm:
        return
    a = Arm(f)
    obj, nodes, payloads = 0x11000000, 0x11001000, 0x11002000
    timbre, meta, program, first = 0x11010000, 0x11011000, 0x11012000, 0x11014000
    channel, event = 0x11015000, 0x11016000

    def word(p):
        return struct.unpack('<I', a.uc.mem_read(p, 4))[0]

    def byte(p):
        return a.uc.mem_read(p, 1)[0]

    def put8(p, v):
        a.uc.mem_write(p, bytes([v & 255]))

    def put16(p, v):
        a.uc.mem_write(p, struct.pack('<H', v & 65535))

    def call(entry, *argv, **kwargs):
        return a.call(entry, *argv, **kwargs) & 0xFFFFFFFF

    def setup(capacity, priority, legato):
        a.uc.mem_write(obj, bytes(0x30))
        a.uc.mem_write(timbre, bytes(0x100))
        a.uc.mem_write(meta, bytes(0x100))
        a.uc.mem_write(program, bytes(0x900))
        a.uc.mem_write(channel, bytes(0x200))
        a.write(obj+0x18, nodes)
        put8(obj+0x1C, capacity)
        for i in range(capacity):
            a.write(nodes+12*i, 0, 0, payloads+4*i)
        a.write(timbre+4, meta, program)
        a.write(timbre+0x10, channel)
        a.write(timbre+0x24, obj)
        put8(program+0x508, 0x80)
        put8(program+0x509, (priority << 2) | (legato << 4))
        put8(meta+0x1B, 0x20)  # Original scale helper uses local equal temperament.
        put8(meta+0x1E, 127)
        call(0x270210, obj)

    def inspect_lists(capacity):
        lists = []
        for head in [obj, obj+12]:
            current, previous, seen = word(head), head, []
            while current != head:
                assert current in range(nodes, nodes+12*capacity, 12)
                assert current not in seen and word(current+4) == previous
                seen.append(current)
                previous, current = current, word(current)
            assert word(head+4) == previous and word(head+8) == 0
            lists.append(seen)
        active, free = lists
        assert len(active)+len(free) == capacity and not set(active) & set(free)
        return [byte(word(n+8)) for n in active]

    # The original constructor allocates 12-byte nodes and four-byte payloads.
    # 0x272560 supplies the literal 10 in the timbre constructor.
    allocations, cursor = [], [0x11030000]

    def allocate(m):
        size = m.get('R0')
        ptr = cursor[0]
        cursor[0] += (size+15) & ~15
        allocations.append(dict(bytes=size, address=hex(ptr)))
        return ptr

    a.stubs = {0x2DC184: lambda m: 0, 0x2DC1BC: lambda m: 0, 0x2E2F9C: allocate}
    call(0x2703C0, obj, 10)
    assert byte(obj+0x1C) == 10 and [r['bytes'] for r in allocations] == [120, 40]
    original_nodes = word(obj+0x18)
    assert [word(original_nodes+12*i+8) for i in range(10)] == [int(allocations[1]['address'], 16)+4*i for i in range(10)]
    a.stubs = {}
    rng = random.Random(0x270658)
    # Overflow, repeats, missing releases and recovery are deliberately mixed.
    sequences = [
        [('on', n, 40+i % 88) for i, n in enumerate(range(36, 60))] + [('off', n, 0) for n in range(36, 60)],
        [('on', n, 100-i % 88) for i, n in enumerate(range(84, 60, -1))] + [('off', n, 0) for n in range(84, 60, -1)],
        [('on', 60, 20+i) for i in range(24)] + [('off', 60, 0)]*26,
        [(rng.choice(['on', 'on', 'off']), rng.choice([0, 127, 48, 60, 64, 67, 72]), rng.randrange(1, 128)) for _ in range(700)],
    ]
    list_cases, transitions, overflows = [], 0, 0
    for capacity, priority, legato, sequence_id in itertools.product([4, 10, 16], range(3), [0, 1], range(len(sequences))):
        setup(capacity, priority, legato)
        model = Model(capacity, priority, legato)
        for op, note, velocity in sequences[sequence_id]:
            if op == 'on':
                overflows += int(len(model.keys) == capacity)
                selected, initial = model.on(note, velocity)
                got = call(0x270658, obj, timbre, note, velocity, stack=(program+0x508, first))
                assert (got, word(first)) == (selected, initial), (capacity, priority, legato, model.keys)
            else:
                expected = model.off(note)
                pointer = call(0x2707E0, obj, note)
                assert (byte(pointer) if pointer else None) == expected
            assert inspect_lists(capacity) == model.keys
            assert byte(obj+0x1D) == model.velocity
            transitions += 1
        list_cases.append(dict(capacity=capacity, priority=priority, legato=bool(legato), sequence=sequence_id,
                               operations=len(sequences[sequence_id]), final_keys=model.keys))
    # Execute the timbre Note On/Off bodies and actual priority/scale/fade helpers.
    # Capture OSC dispatch and reset boundaries; sound generation is separate.
    events = []

    def capture(kind):
        def stub(m):
            packed = m.get('R1')
            events.append([kind, packed & 255, (packed >> 8) & 255, (packed >> 16) & 255] if kind != 'reset' else [kind])
            return 0
        return stub

    a.stubs = {0x272D0C: capture('reset'), 0x2737F8: capture('on'), 0x272C3C: capture('off'),
               0x54C74: lambda m: 0, 0x54E40: lambda m: 0}
    timelines, wrapper_transitions = [], 0
    scenarios = [
        [('on', 60, 40), ('on', 64, 80), ('on', 62, 100), ('off', 62, 0), ('off', 64, 0), ('off', 60, 0)],
        [('on', 60, 40), ('on', 64, 80), ('on', 62, 100), ('off', 64, 0), ('off', 60, 0), ('off', 62, 0)],
        [('on', 60, 40), ('on', 60, 80), ('on', 60, 100), ('off', 60, 0), ('off', 60, 0), ('off', 60, 0)],
        sequences[0], sequences[1], sequences[3],
    ]
    for priority, legato, scenario in itertools.product(range(3), [0, 1], range(len(scenarios))):
        setup(10, priority, legato)
        model, rows, count = Model(10, priority, legato), [], 0
        for op, note, velocity in scenarios[scenario]:
            expected, events[:] = [], []
            packed = (0x90 if op == 'on' else 0x80) | (note << 8) | (velocity << 16)
            a.write(event, packed)
            if op == 'on':
                empty = not model.keys
                selected, initial = model.on(note, velocity)
                if selected and not legato or initial:
                    expected.append(['reset'])
                if selected:
                    expected.append(['on', 0x90, note, velocity])
                count += 1
                put8(timbre+0x44, note)
                put8(timbre+0x45, velocity)
                put16(timbre+0x46, count)
                call(0x273D4C, timbre, packed, event)
                assert byte(timbre+0x4F) == int(empty)
            else:
                if not legato:
                    expected.append(['off', 0x80, note, velocity])
                fallback = model.off(note)
                if fallback is not None:
                    if not legato:
                        expected.append(['reset'])
                    expected.append(['on', 0x80, fallback, model.velocity])
                elif legato and not model.keys:
                    expected.append(['off', 0x80, note, velocity])
                count = max(0, count-1)
                call(0x2743E4, timbre, packed)
            assert events == expected, (priority, legato, scenario, op, note, events, expected)
            assert struct.unpack('<H', a.uc.mem_read(timbre+0x46, 2))[0] == count
            assert inspect_lists(10) == model.keys and byte(obj+0x1D) == model.velocity
            if scenario < 3:
                rows.append(dict(input=[op, note, velocity], keys=list(model.keys), cached_velocity=model.velocity, dispatch=list(events)))
            wrapper_transitions += 1
        timelines.append(dict(priority=['Low', 'High', 'Last'][priority], legato=bool(legato), scenario=scenario, rows=rows,
                              operations=len(scenarios[scenario])))
    result = dict(passed=True, firmware_sha256=FW_SHA, device_access=False,
                  factory_key_capacity=10, constructor_allocations=allocations,
                  list_cases=list_cases, list_transitions=transitions, overflow_insertions=overflows,
                  timbre_timelines=timelines, timbre_transitions=wrapper_transitions,
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                  boundaries=['Original mono predicates, lists, priority dispatch, Note On/Off timbre bodies execute',
                              'OSC reset/Note On/Note Off and UI notifications intercepted',
                              'Equal temperament and full keyboard range; no pedals; timbre index zero',
                              'Tests compare independent list model and check active/free partition after every event',
                              'Program priority encodings 0, 1, 2; raw encoding 3 excluded',
                              'No physical keyboard timing or generated audio'])
    (OUT/'mono-keys-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(passed=True, key_capacity=10, list_transitions=transitions,
                          overflow_insertions=overflows, timbre_transitions=wrapper_transitions), indent=2))


if __name__ == '__main__':
    main()
