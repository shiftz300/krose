#!/usr/bin/env python3
"""Recover complete built-in PCM metadata, not missing ROM audio.

Optional ARM checks use only synthetic RAM and mocked storage reads. No OS,
flash programming, USB/MIDI, product resources or keyboard are touched.
"""
import argparse
import collections
import contextlib
import hashlib
import io
import json
import struct
from pathlib import Path

from firmware_inspect import inspect
from program_firmware import Arm, BASE, Firmware, ROOT, FW_SHA

TABLES = {
    'sample_descriptors': (0x410ABC, 4070, 64, 0x20DEFC, 0x20DF08),
    'key_regions': (0x492C28, 5570, 20, 0x20DF14, 0x20DF20),
    'multisamples': (0x48F5CC, 497, 28, 0x20CF34, 0x20CF40),
    'drumsamples': (0x408BFC, 1014, 32, 0x20CCA0, 0x20CCAC),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    fw = Firmware()
    folder = ROOT / 'research/derived/firmware/KROSS2_V124/rom/catalog'
    folder.mkdir(parents=True, exist_ok=True)
    samples, regions, multisamples, drums = [], [], [], []
    table_records = {}
    for name, (offset, count, stride, getter, counter) in TABLES.items():
        assert fw.u32(getter + 8) == BASE + offset
        assert fw.u32(counter + 8) == count
        raw = fw.data[offset:offset + count * stride]
        (folder / (name + '.bin')).write_bytes(raw)
        table_records[name] = dict(offset=hex(offset), count=count, stride=stride,
                                   sha256=sha(raw), getter=hex(getter), count_getter=hex(counter))
    for i in range(4070):
        offset = 0x410ABC + i * 64
        raw = fw.data[offset:offset + 64]
        values = struct.unpack('<16I', raw)
        pitch, = struct.unpack_from('<h', raw)
        coefficients = list(struct.unpack_from('<hh', raw, 8))
        flags = raw[7]
        unit = 1 if flags & 1 else 2
        start, loop, end = values[3], values[5], values[6]
        assert start <= loop <= end
        assert (end + 1) * unit <= 0x4000000
        samples.append(dict(index=i, offset=hex(offset), raw_hex=raw.hex(),
                            pitch_field=pitch, flags=flags, coefficients_q14=coefficients,
                            start=start, start2=values[4], loop_start=loop, end_inclusive_candidate=end,
                            address_unit_bytes=unit, byte_start_candidate=start * unit,
                            byte_end_exclusive_candidate=(end + 1) * unit,
                            role='diagnostic descriptor' if i >= 4068 else 'factory descriptor',
                            interpretation='Address scaling supported by original relocation code; format flags and end convention need real payload validation'))
    for i in range(5570):
        offset = 0x492C28 + i * 20
        raw = fw.data[offset:offset + 20]
        sample, = struct.unpack_from('<H', raw)
        assert sample < len(samples) and raw[3] <= 127 and raw[4] <= 127
        regions.append(dict(index=i, offset=hex(offset), sample_index_raw=sample,
                            sample_index_after_diagnostic_init=4068 + i - 5568 if i >= 5568 else sample,
                            top_key=raw[3], root_key_candidate=raw[4], raw_hex=raw.hex()))
    for i in range(497):
        offset = 0x48F5CC + i * 28
        raw = fw.data[offset:offset + 28]
        first, count, flags = struct.unpack_from('<HBB', raw)
        name = raw[4:28].decode('ascii').rstrip(' \0')
        assert first + count <= 5568
        if i < 496:
            selected = regions[first:first + count]
            assert [r['top_key'] for r in selected] == sorted(r['top_key'] for r in selected)
        multisamples.append(dict(index=i, name=name, first_region=first, region_count=count,
                                 flags=flags, role='diagnostic' if i == 496 else 'factory multisample',
                                 scope='Raw diagnostic first-region field is not treated as factory mapping' if i == 496 else 'factory key region slice'))
    for i in range(1014):
        offset = 0x408BFC + i * 32
        raw = fw.data[offset:offset + 32]
        sample, = struct.unpack_from('<H', raw)
        assert sample < 4068
        drums.append(dict(index=i, name=raw[4:28].decode('ascii').rstrip(' \0'),
                          sample_index=sample, raw_hex=raw.hex(), offset=hex(offset),
                          flags_raw=list(raw[2:4]), tail_raw=raw[28:].hex()))
    for name, values in [('sample-descriptors',samples), ('key-regions',regions),
                         ('multisamples',multisamples), ('drumsamples',drums)]:
        (folder / (name + '.json')).write_text(json.dumps(values, ensure_ascii=False, indent=2) + '\n')
    used = {r['sample_index_raw'] for r in regions[:5568]} | {r['sample_index'] for r in drums}
    arm_checks = {}
    if args.verify_arm:
        arm = Arm(fw)
        getters = []
        for name, (offset, count, stride, getter, counter) in TABLES.items():
            assert arm.call(getter) & 0xFFFFFFFF == BASE + offset
            assert arm.call(counter) == count
            getters.append(dict(table=name, pointer=hex(BASE + offset), count=count))
        arm.call(0x20DF2C)
        diagnostic_ids = [struct.unpack('<H', arm.uc.mem_read(BASE + 0x492C28 + i * 20, 2))[0] for i in (5568,5569)]
        assert diagnostic_ids == [4068,4069]
        relocations = []
        for flag in (0x10, 0x11):
            obj, sample = 0x11002000, 0x11004000
            arm.uc.mem_write(obj, bytes(0x100))
            arm.uc.mem_write(sample, bytes(64))
            arm.uc.mem_write(obj + 0x5C, struct.pack('<H', 1))
            arm.write(obj + 0x6C, sample)
            arm.write(obj + 0x88, 0x200)
            arm.uc.mem_write(sample + 7, bytes([flag]))
            for field in range(0x0C, 0x40, 4):
                arm.write(sample + field, 0x1000 + field)
            arm.call(0x12B828, obj)
            delta = 0x200 if flag & 1 else 0x100
            for field in range(0x0C, 0x40, 4):
                assert struct.unpack('<I',arm.uc.mem_read(sample+field,4))[0] == 0x1000 + field - delta
            relocations.append(dict(flags=flag, byte_offset=0x200, descriptor_address_delta=delta))
        # Execute the complete original reader, with synthetic flash words.
        # The read command itself was separately checked in probe_rom_storage.py.
        blocks = []
        for block in (0, 0xFF, 0x100):
            obj, target = 0x11002000, 0x11010000
            arm.write(obj, 0x60000000)
            count = [0]
            endpoints = []
            def read(machine):
                index, half = machine.get('R1'), machine.get('R2')
                assert index == (block << 16) + count[0] // 2 and half == count[0] % 2
                if count[0] < 2 or count[0] >= 131070:
                    endpoints.append([index,half])
                count[0] += 1
                return ((index * 131) ^ (index >> 16) ^ (half * 0xA55A)) & 0xFFFF
            arm.stubs = {0x11C888: lambda _: 0, 0x11C8CC: lambda _: 0, 0x12E1C0: read}
            arm.call(0x11C90C, obj, block, target, count=2500000)
            actual = bytes(arm.uc.mem_read(target, 0x40000))
            expected = b''.join(struct.pack('<H', ((index*131) ^ (index>>16) ^ (half*0xA55A)) & 0xFFFF)
                                for index in range(block << 16,(block << 16)+65536) for half in (0,1))
            assert count[0] == 131072 and actual == expected
            blocks.append(dict(block=block, output_bytes=len(actual), mocked_u16_reads=count[0],
                               endpoint_indices=endpoints, synthetic_output_sha256=sha(actual)))
        obj = 0x11002000
        arm.uc.mem_write(obj, bytes(64))
        arm.write(obj, 0x60000000)
        footer = b'KORG\x01\x02\x04\x00' + bytes(range(8))
        footer_calls = []
        def read_footer(machine):
            index, half = machine.get('R1'), machine.get('R2')
            position = (index - 0xFFFFFC) * 2 + half
            assert 0 <= position < 8
            footer_calls.append([index, half])
            return struct.unpack_from('<H', footer, position * 2)[0]
        arm.stubs = {0x11C888:lambda _:0, 0x11C8CC:lambda _:0, 0x12E1C0:read_footer}
        assert arm.call(0x11CD00,obj) == obj + 4
        assert bytes(arm.uc.mem_read(obj + 4,16)) == footer
        assert footer_calls == [[index,half] for index in range(0xFFFFFC,0x1000000) for half in (0,1)]
        arm_checks = dict(getters=getters, diagnostic_sample_ids=diagnostic_ids,
                          address_unit_relocations=relocations, full_block_readers=blocks,
                          footer_reader=dict(mocked_u16_reads=footer_calls, returned_bytes=footer.hex(),
                                             candidate_byte_interval=[0x3FFFFF0,0x4000000]),
                          scope='Original ARM against synthetic RAM/register data; no actual ROM byte obtained')
    output = folder / ('layout-check-arm.json' if args.verify_arm else 'layout-check.json')
    report = dict(firmware_sha256=FW_SHA, tool_sha256=sha(Path(__file__).read_bytes()), tables=table_records,
                  factory_multisamples=496, diagnostic_multisamples=1, factory_drumsamples=1014,
                  referenced_factory_descriptors=len(used), unreferenced_factory_descriptors=sorted(set(range(4068))-used),
                  reference_scope='Direct region/drum index references only; missing direct references do not establish unused audio (implicit stereo/other paths unresolved)',
                  descriptor_flags=dict(sorted(collections.Counter(hex(s['flags']) for s in samples).items())),
                  candidate_factory_PCM_byte_span=[0,0x4000000],
                  span_basis='Every descriptor fits lower64MiB after original address-unit scaling; footer reader targets final16bytes there; expansion reader adds block0x100 (=64MiB)',
                  largest_descriptor_byte_end=max(s['byte_end_exclusive_candidate'] for s in samples),
                  missing='Actual PCM audio payload is absent; metadata extraction does not create playable factory samples',
                  ARM=arm_checks,
                  outputs_sha256={p.name:sha(p.read_bytes()) for p in folder.iterdir() if p.suffix in ('.bin','.json') and not p.name.startswith('layout-check')})
    output.write_text(json.dumps(report,indent=2)+'\n')
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream):
        for start,end in ((0x20CCA0,0x20CCB8),(0x20CF34,0x20CF4C),(0x20DEFC,0x20DF6C),
                          (0x12B828,0x12B8D4),(0x1ED3B0,0x1ED424),(0x11CD00,0x11CDDC)):
            print(f'\nBounded static excerpt [{start:#x},{end:#x})')
            inspect(fw.data,start,end)
    (folder/'layout-evidence.arm.txt').write_text(stream.getvalue())
    print(f'Recovered 4070 sample descriptors, 5570 regions, 497 multisample names and 1014 drumsample names; referenced factory samples: {len(used)}; ARM checks: {bool(arm_checks)}')


if __name__=='__main__':
    main()
