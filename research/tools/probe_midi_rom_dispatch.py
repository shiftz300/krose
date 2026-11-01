#!/usr/bin/env python3
"""Offline SysEx/diagnostic routing research for KROSS 2 v1.2.4.

No MIDI, USB, disk-device, OS-startup or flash-writing API is used. All external
effects and semantic command leaves are intercepted before execution. Synthetic
TG reads verify the diagnostic checksum consumer, never actual ROM contents.
"""
from layout import PRODUCT_ROOT
import argparse
import contextlib
import hashlib
import io
import json
import struct
from pathlib import Path

from firmware_inspect import inspect
from program_firmware import Arm, BASE, Firmware, FW_SHA, ROOT

OUT = ROOT / 'research/derived/firmware/KROSS2_V124/rom/dispatch'
PACKET, CONTEXT = 0x11010000, 0x11011000


def sha(data): return hashlib.sha256(data).hexdigest()


def branches(fw):
    result = []
    for offset in range(0, 0x330000, 4):
        word = fw.u32(offset)
        if word & 0x0E000000 != 0x0A000000 or word >> 28 == 15: continue
        displacement = word & 0xFFFFFF
        if displacement & 0x800000: displacement -= 0x1000000
        target = offset+8+displacement*4
        if 0 <= target < 0x330000:
            result.append(dict(source=offset, target=target,
                               kind='BL' if word & 0x1000000 else 'B', condition=word >> 28))
    return result


def parser_cases(fw):
    arm = Arm(fw)
    # These are routing/monitor functions only. Parser state and byte decoding
    # execute original instructions. No semantic command consumer runs here.
    arm.stubs = {0x243DB0: lambda a: 0, 0x276090: lambda a: 1,
                 0x2BCC50: lambda a: 0x11015000,
                 0x2BCCD4: lambda a: 1, 0x2C2A70: lambda a: 0}
    cases = []
    fixtures = [
        ('bank_info_request', bytes.fromhex('f0 42 30 00 01 49 72 14 00 00 00 f7'), True),
        ('name_info_request', bytes.fromhex('f0 42 30 00 01 49 72 15 00 00 00 f7'), True),
        ('wrong_model', bytes.fromhex('f0 42 30 00 01 48 72 14 00 00 00 f7'), True),
        ('exclusive_disabled', bytes.fromhex('f0 42 30 00 01 49 72 14 00 00 00 f7'), False),
        ('diagnostic_start', bytes.fromhex('f0 42 22 22 03 00 f7'), True),
        ('diagnostic_run', bytes.fromhex('f0 42 22 22 03 01 f7'), True),
        ('diagnostic_parameter', bytes.fromhex('f0 42 22 22 03 11 00 05 f7'), True),
        ('diagnostic_ack', bytes.fromhex('f0 42 22 22 70 01 00 00 f7'), True),
    ]
    for name, wire, enabled in fixtures:
        arm.uc.mem_write(PACKET, bytes(0x100))
        arm.write(PACKET+0x18, 0xFFFFFFFF)
        arm.uc.mem_write(BASE+0x1B571C0, bytes(0x40))
        arm.uc.mem_write(BASE+0x1DCC2D8+0x1353, bytes([0x20 if enabled else 0]))
        trace, events = [], []
        for byte in wire:
            ready = arm.call(0x2C2E90, PACKET, byte, 7, count=10000)
            state = struct.unpack('<I', arm.uc.mem_read(PACKET+0x10, 4))[0]
            packet = bytes(arm.uc.mem_read(PACKET, 16))
            trace.append(dict(byte=byte, state=state, ready=ready))
            if ready: events.append(packet.hex())
        cases.append(dict(name=name, input_hex=wire.hex(), exclusive_enabled=enabled,
                          trace=trace, decoded_events_hex=events))
    by_name = {c['name']: c for c in cases}
    for name, subcommand in [('bank_info_request', 0x14), ('name_info_request', 0x15)]:
        events = by_name[name]['decoded_events_hex']
        assert len(events) == 1 and bytes.fromhex(events[0])[:2] == bytes([0x72, subcommand])
    assert not by_name['wrong_model']['decoded_events_hex']
    assert not by_name['exclusive_disabled']['decoded_events_hex']
    for name in ('diagnostic_start', 'diagnostic_run', 'diagnostic_parameter', 'diagnostic_ack'):
        assert len(by_name[name]['decoded_events_hex']) == 1, name
        assert bytes.fromhex(by_name[name]['decoded_events_hex'][0])[0] == 7
    return cases


def request_dispatch(fw):
    arm = Arm(fw)
    terminal = [0x2BEEA0, 0x2BEF74, 0x136454, 0x2BF000, 0x2BF074,
                0x13280C, 0x132950, 0x132C30, 0x135DAC, 0x2BF18C,
                0x2BF130, 0x2BF0F4, 0x2BF1E8, 0x134040, 0x13423C,
                0x134B5C, 0x138D0C]
    cases = []
    for flag in (0, 0x40):
        for subcommand in range(128):
            captured = []
            def capture(target):
                def callback(a):
                    captured.append(dict(target=hex(target), registers=[a.get('R'+str(i)) for i in range(4)],
                                         stack_words=list(struct.unpack('<3I', a.uc.mem_read(a.get('SP'), 12)))))
                    return 0
                return callback
            arm.stubs = {t: capture(t) for t in terminal}
            arm.stubs.update({t: lambda a: 0 for t in (0x2B955C, 0x2B931C, 0x2B95A0, 0x2B947C, 0x2B95C0, 0x40C10)})
            arm.stubs.update({0x2BCC50: lambda a: 0x11015000, 0x2BCCD4: lambda a: 1})
            arm.uc.mem_write(PACKET, bytes([0x72, subcommand, 0, 7, flag, 0])+bytes(250))
            arm.uc.mem_write(CONTEXT, bytes(0x100))
            arm.write(BASE+0x1747538+8, 1)  # synthetic registered bank for guarded requests
            arm.call(0x2C11A0, PACKET, CONTEXT, 0x72, count=10000)
            assert len(captured) == 1, (subcommand, flag, captured)
            cases.append(dict(subcommand=subcommand, field4=flag, terminal=captured[0]))
    for flag in (0, 0x40):
        case = cases[(128 if flag else 0)+0x14]
        assert case['terminal']['target'] == '0x13423c'
        assert case['terminal']['registers'][2] == flag >> 6
        case = cases[(128 if flag else 0)+0x15]
        assert case['terminal']['target'] == '0x134b5c'
        assert case['terminal']['registers'][2] == flag >> 6
    for case in cases:
        if case['subcommand'] >= 29: assert case['terminal']['target'] == '0x138d0c'
    return cases


def diagnostic_dispatch(fw):
    """Capture service handlers, including the identity writer, before entry."""
    arm = Arm(fw)
    leaves = [0x4BAD0, 0x4B66C, 0x4B894, 0x4B7C8, 0x4BD54, 0x4B588, 0x4B60C]
    cases = []
    fixtures = [('start', [7, 3, 0], 0x4BAD0), ('run', [7, 3, 1], 0x4B66C),
                ('next', [7, 3, 2], 0x4B894), ('previous', [7, 3, 3], 0x4B7C8),
                ('parameter', [7, 3, 0x11, 0, 2, 0], 0x4BD54),
                ('ack', [7, 0x70, 1], 0x4B588),
                ('identity_update_NOT_EXECUTED', [7, 8, 0], 0x4B60C),
                ('unknown', [7, 0x7F, 0], None)]
    for name, packet, expected in fixtures:
        captured = []
        def capture(target):
            def callback(a):
                captured.append(dict(target=hex(target), registers=[a.get('R'+str(i)) for i in range(3)]))
                return 0
            return callback
        arm.stubs = {target: capture(target) for target in leaves}
        arm.write(BASE+0xFE9888, CONTEXT)
        arm.uc.mem_write(BASE+0x1B571B6, struct.pack('<h', 5))
        arm.uc.mem_write(PACKET, bytes(packet)+bytes(32-len(packet)))
        arm.call(0x2BD190, PACKET, count=10000)
        assert [c['target'] for c in captured] == ([] if expected is None else [hex(expected)])
        cases.append(dict(name=name, synthetic_event_hex=bytes(packet).hex(), captured=captured,
                          handler_body_executed=False))
    return cases


def metadata_record(fw):
    """Run the original name-record constructor with a one-item fake library."""
    arm = Arm(fw)
    sender, context, allocated, name = 0x11010000, 0x11011000, 0x11012000, 0x11013000
    manager, bank = 0x11020000, 0x11021000
    arm.write(BASE+0x199BD88, manager)
    arm.write(manager+0x400, bank)
    arm.write(bank, 0, 1)
    arm.uc.mem_write(name, b'SYNTHETIC ROM NAME\0')
    output = []
    def emit(label):
        def callback(a):
            length = a.get('R2')
            assert length in (12, 28)
            output.append(dict(kind=label, bytes=length, hex=bytes(a.uc.mem_read(a.get('R1'), length)).hex()))
            return 0
        return callback
    def reject(a): raise AssertionError('Metadata constructor reached a TG read/write leaf')
    arm.stubs = {t: lambda a: 0 for t in (0x2DC184, 0x2DC1BC, 0x1394B4, 0x1394D4,
                                         0x14E760, 0x36E74, 0x36984, 0x36A00,
                                         0x2857B8, 0x2856F4)}
    arm.stubs.update({0x2BCC50: lambda a: 0x11015000, 0x2C1C08: lambda a: 1,
                      0x14E730: lambda a: allocated, 0x28561C: lambda a: name,
                      0x138240: emit('header'), 0x138680: emit('unpacked_name_record'),
                      0x138178: lambda a: 0})
    for target in (0x12E1C0, 0x12E210, 0x12E264, 0x11C90C, 0x11C9E0): arm.stubs[target] = reject
    arm.call(0x134B5C, sender, context, 0, 0, stack=(1,), count=20000)
    assert len(output) == 2
    header, payload = [bytes.fromhex(p['hex']) for p in output]
    assert header[:8] == bytes.fromhex('f0 42 30 00 01 49 73 15')
    expected_name = b'SYNTHETIC ROM NAME\0'
    assert payload[:2] == bytes(2) and payload[2:2+len(expected_name)] == expected_name
    assert len(payload) == 28 and payload[26:] == bytes(2)
    return dict(source_kind='Synthetic one-item library; not real hardware or ROM payload',
                original_function='0x134b5c', captures=output,
                getters_stubbed=['0x28561c (name)', '0x2857b8 (flag)', '0x2856f4 (flag)'],
                emitter_scope='Captured constructor arguments before MIDI packing/transport', TG_reads=0)


def diagnostic_checksum(fw):
    arm = Arm(fw)
    manager, hardware = 0x11010000, 0x60000000
    arm.write(manager, hardware)
    indices = list(range(65536))+[(block << 16)+65535 for block in range(1, 255)]
    def value(index, half): return ((index*17) ^ (index >> 9) ^ (half*0xB527)) & 65535
    sums = [sum(value(i, half) for i in indices) & 65535 for half in (0, 1)]
    cases = []
    for fail_half, expected in [(None, 0), (0, 1), (1, 2)]:
        reads = [[], []]
        def read(a):
            assert a.get('R0') == hardware
            index, half = a.get('R1'), a.get('R2')
            assert half in (0, 1)
            reads[half].append(index)
            if index == 0xFFFFFF: return sums[half] ^ (1 if fail_half == half else 0)
            return value(index, half)
        arm.stubs = {0x11C888: lambda a: 0, 0x11C8CC: lambda a: 0, 0x12E1C0: read}
        result = arm.call(0x11CC88, manager, count=12000000)
        assert result == expected
        for half in (0, 1):
            expected_indices = indices+[0xFFFFFF] if half == 0 or fail_half != 0 else []
            assert reads[half] == expected_indices
        cases.append(dict(failing_half=fail_half, result=result,
                          read_counts=list(map(len, reads)), all_read_addresses_match=True,
                          per_half_sum16=sums, source='synthetic TG u16 values'))
    # Verify the diagnostic consumer returns only the status and emits a fixed
    # diagnostic report, without exporting the words it read.
    consumer = []
    for status in (0, 1, 2):
        wire = []
        arm.write(CONTEXT+0x38, 0x11014000)
        arm.uc.mem_write(0x11014000+0x28, bytes.fromhex('f0 42 20 00 01 49'))
        def send(a):
            assert a.get('R0') == BASE+0x10478E8 and a.get('R2') == 1
            wire.append(a.get('R1')); return 0
        arm.stubs = {0x11C860: lambda a: manager,
                     0x138178: send, 0x11C888: lambda a: 0, 0x11C8CC: lambda a: 0,
                     0x11CC88: lambda a: status}
        arm.call(0x4D480, CONTEXT, count=10000)
        stored = struct.unpack('<I', arm.uc.mem_read(CONTEXT+0x1C, 4))[0]
        expected = bytes.fromhex('f0 42 20 00 01 49 6e 06 f7 f0 42 20 00 01 49 6c')
        expected += bytes([status, int(status != 0), 0xF7])
        assert bytes(wire) == expected and stored == status
        consumer.append(dict(injected_status=status, output_hex=bytes(wire).hex(), stored_status=stored,
                             emitter_scope='Original diagnostic sender through final byte-output boundary'))
    return dict(original_checksum_function='0x11cc88', per_half_helper='0x11cbc4',
                read_addresses_per_half=dict(first_block=[0, 65535],
                                             remaining='(block<<16)+65535, block=1..254',
                                             expected_checksum_word=0xFFFFFF),
                checksum_cases=cases, original_consumer='0x4d480', consumer_cases=consumer,
                limitation='TG read is synthetic; checksum is a fixed address summary, not a PCM export')


def localized_read_boundary(fw):
    """Verify the existing localized-PCM reader does not map to factory blocks."""
    arm = Arm(fw)
    context, manager, block_buffer, output = 0x11010000, 0x11011000, 0x11050000, 0x110A0000
    arm.write(context+0x1E4, block_buffer)
    cases = []
    for index, count, block in [(0, 1, 0x100), (0x1FFFF, 2, 0x100),
                                (0x20000, 1, 0x101), (0x1FE0000, 0x20000, 0x1FF),
                                (0x1FFFFFF, 1, 0x1FF), (0x2000000, 1, None),
                                (0xFFFFFFFF, 1, None)]:
        reads, assertions = [], []
        def read(a):
            assert a.get('R0') == manager
            b = a.get('R1')
            assert 0x100 <= b <= 0x1FF
            reads.append(b)
            arm.uc.mem_write(a.get('R2'), bytes((b+i*13) & 255 for i in range(0x40000)))
            return 0
        def reject(a):
            assertions.append(dict(line=a.get('R2'), file_pointer=a.get('R1')))
            raise ValueError('Expected localized-PCM range assertion')
        arm.stubs = {0x11C860: lambda a: manager, 0x11C90C: read, 0x2C5220: reject}
        arm.uc.mem_write(output, b'\xcc'*0x40010)
        try:
            returned = arm.call(0x1ED388, context, index, count, output, count=2000000)
        except RuntimeError:
            assert block is None and assertions and not reads
            cases.append(dict(index=index, requested_u16=count, range_assertion=assertions,
                              TG_block_reads=[], factory_region_reached=False))
            continue
        assert block is not None and reads == [block]
        expected_count = min(count, 0x20000-(index & 0x1FFFF))
        assert returned == expected_count and not assertions
        offset = (index & 0x1FFFF)*2
        expected = bytes((block+i*13) & 255 for i in range(offset, offset+returned*2))
        assert bytes(arm.uc.mem_read(output, returned*2)) == expected
        assert bytes(arm.uc.mem_read(output+returned*2, 16)) == b'\xcc'*16
        cases.append(dict(index=index, requested_u16=count, returned_u16=returned,
                          TG_block_reads=reads, all_synthetic_bytes_match=True,
                          factory_region_reached=False))
    return dict(entry='0x1ed388', original_range_wrapper='0x11c994',
                block_formula='(u32_index >> 17) + 0x100', cases=cases,
                limitation='Internal helper boundary only; no MIDI export entry or real PCM bytes established')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    fw = Firmware(); edges = branches(fw)
    OUT.mkdir(parents=True, exist_ok=True)
    ranges = [(0x2C11A0, 0x2C1AB0), (0x2BF1F4, 0x2BF4DC), (0x134B5C, 0x1351BC),
              (0x2C2E90, 0x2C4474), (0x2BD190, 0x2BD2A8),
              (0x4D480, 0x4D4DC), (0x11CBC4, 0x11CCDC), (0x138C68, 0x138D0C),
              (0x4D1B8, 0x4D1E0), (0x4A730, 0x4A950), (0x4B60C, 0x4B66C),
              (0x1ED388, 0x1ED42C), (0x11C994, 0x11C9E0)]
    for start, end in ranges:
        text = io.StringIO()
        with contextlib.redirect_stdout(text): inspect(fw.data, start, end)
        (OUT / f'{start:06x}-{end:06x}.asm.txt').write_text(text.getvalue())
    targets = [0x12E1C0, 0x11C90C, 0x11C994, 0x11CBC4, 0x11CC88, 0x11CCDC,
               0x11CD00, 0x13423C, 0x134B5C, 0x2BF1F4, 0x2C11A0, 0x4B60C]
    report = dict(firmware_sha256=FW_SHA, tool_sha256=sha(Path(__file__).read_bytes()),
                  helper_tool_sha256={name: sha((ROOT/'tools'/name).read_bytes()) for name in
                                      ('program_firmware.py', 'firmware_inspect.py', 'decode_korg_pcm.py')},
                  excerpts_sha256={f'{start:06x}-{end:06x}.asm.txt': sha((OUT/f'{start:06x}-{end:06x}.asm.txt').read_bytes())
                                   for start, end in ranges},
                  coordinates='Decompressed v1.2.4 file offsets; virtual base 0xc0000000',
                  request_family=0x72, reply_family=0x73,
                  request_subcommand_jump_table=[dict(subcommand=i, target=hex(fw.pointer(0x2BF228+i*4))) for i in range(29)],
                  incoming_edges={hex(t): [e for e in edges if e['target'] == t] for t in targets},
                  pointer_reference_counts={hex(t): sum(1 for offset in range(0, len(fw.data)-3, 4)
                                                       if fw.u32(offset) == BASE+t) for t in targets},
                  limitations=['Direct B/BL and pointer scans are candidates, not a complete recovered call graph',
                               'Synthetic state/observer gates do not prove a hardware mode is enabled',
                               'No MIDI or USB was sent and no real ROM bytes were read'])
    if args.verify_arm:
        report['byte_parser_cases'] = parser_cases(fw)
        print('Original byte parser cases passed', flush=True)
        report['request_dispatch_cases'] = request_dispatch(fw)
        print('Original request dispatch cases passed', flush=True)
        report['diagnostic_dispatch_cases'] = diagnostic_dispatch(fw)
        print('Original diagnostic dispatch cases passed', flush=True)
        report['metadata_record_case'] = metadata_record(fw)
        print('Original metadata record constructor passed', flush=True)
        report['diagnostic_checksum'] = diagnostic_checksum(fw)
        print('Original diagnostic checksum/consumer cases passed', flush=True)
        report['localized_read_boundary'] = localized_read_boundary(fw)
        print('Original localized read boundary cases passed', flush=True)
    report['host_callable_TG_PCM_export_found'] = False
    report['findings'] = dict(
        metadata='0x72/0x14 and 0x72/0x15 request bank/name information; responses use 0x73',
        diagnostic='Fixed address checksum reaches TG reads; replies contain status, not PCM words',
        localized='Original wrapper maps into blocks 0x100..0x1ff; tested overflow-like indices assert',
        identity='Service event 07/08 reaches 0x4b60c, an identity update path; intercepted before handler body',
        remaining='Other families, unresolved indirect dispatch and absent boot code are not exhaustively ruled out')
    report['physical_device_access'] = False
    filename = 'dispatch-check-arm.json' if args.verify_arm else 'dispatch-static.json'
    (OUT / filename).write_text(json.dumps(report, indent=2)+'\n')
    print('Saved', (OUT / filename).relative_to(PRODUCT_ROOT))


if __name__ == '__main__': main()
