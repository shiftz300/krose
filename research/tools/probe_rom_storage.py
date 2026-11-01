#!/usr/bin/env python3
"""Trace KROSS 2 PCM storage without contacting a keyboard.

Default: version-locked static references and annotated ARM excerpts.
--verify-arm: execute only the tiny read command with mocked register I/O.
Never run a file loader, flash writer, OS entry point, USB, MIDI, or hardware.
"""
import argparse
import contextlib
import hashlib
import io
import json
import zipfile
from pathlib import Path

from firmware_inspect import inspect
from index_firmware import scan
from program_firmware import Arm, Firmware, ROOT, FW_SHA


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args()
    fw = Firmware()
    calls, literals = scan(fw.data)
    folder = ROOT / 'research/derived/firmware/KROSS2_V124/rom'
    folder.mkdir(parents=True, exist_ok=True)
    offsets = {'PCM_image_filename': 0x462D7C, 'PCM_manager_debug_path': 0x45CE9C,
               'NAND_manager_debug_path': 0x45CDA8, 'PCM_voice_ROM_debug_path': 0x45CF3C}
    references = {name: dict(offset=hex(offset), value=fw.string(offset),
                            candidate_literal_refs=[[hex(a), hex(b)] for a,b in literals[offset]])
                  for name, offset in offsets.items()}
    assert references['PCM_image_filename']['value'] == 'KROSSPCM.BIN'
    assert [0x1E9B40, 0x1E9C8C] in literals[0x462D7C]
    assert fw.string(fw.pointer(0x4846C8)) == 'A:'
    assert fw.u32(0x11C878) == 0xE1A00881  # lsl r0,r1,#17
    assert fw.u32(0x11C880) == 0xE3A00802  # mov r0,#0x20000
    archive = ROOT / 'research/downloads/KROSS2_V124.zip'
    with zipfile.ZipFile(archive) as zipped:
        members = [dict(file=p.filename, bytes=p.file_size) for p in zipped.infolist() if not p.is_dir()]
    assert not any(p['file'].split('/')[-1] == 'KROSSPCM.BIN' for p in members)
    ranges = [('image_file_loader', 0x1E9AAC, 0x1E9C9C),
              ('PCM_manager_read_and_write', 0x11C860, 0x11CBC4),
              ('TG_storage_read_command', 0x12E1A8, 0x12E210),
              ('TG_storage_write_command_NOT_EXECUTED', 0x12E210, 0x12E2B4),
              ('NOR_style_program_sequence_NOT_EXECUTED', 0x12E494, 0x12E5E0)]
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        for name, start, end in ranges:
            print(f'\n{name} [{start:#x},{end:#x}); bounded static excerpt, not automatic function recovery')
            inspect(fw.data, start, end)
    (folder / 'storage-path.arm.txt').write_text(stream.getvalue())
    captures = []
    if args.verify_arm:
        arm = Arm(fw)
        hardware = 0x60000000
        for index in (0, 0x10000, 0x1FF0000):
            for half in (0, 1):
                writes, reads = [], []
                busy = [2, 0]
                def write(machine):
                    writes.append([machine.get('R0') - hardware, machine.get('R1')])
                    return 0
                def read(machine):
                    register = machine.get('R0') - hardware
                    reads.append(register)
                    if register == 0x338:
                        return busy.pop(0)
                    assert register == 0x334
                    return 0xFACEA55A  # test the original low-16-bit truncation
                arm.stubs = {0x132690: write, 0x1326B4: read}
                result = arm.call(0x12E1C0, hardware, index, half, count=1000)
                assert writes == [[0x330, index * 2 + half], [0x338, 0xFE]]
                assert reads == [0x338, 0x338, 0x334] and result == 0xA55A
                captures.append(dict(index=index, half=half, writes=writes, reads=reads, returned=result))
    result = dict(firmware_sha256=FW_SHA, tool_sha256=sha(Path(__file__)),
                  coordinate_system='Offsets in decompressed v1.2.4 KROSSAPP.bin; virtual base 0xc0000000',
                  references=references, update_archive_sha256=sha(archive), update_members=members,
                  static_findings=[
                      dict(entry='0x1e9aac', role='Reads A:/KROSSPCM.BIN in at most 0x40000-byte buffers, calls 0x11c9e0 with increasing block index; image programming, NOT export'),
                      dict(entry='0x11c90c', role='PCM storage block reader; 65536 iterations, two u16 reads per iteration; 262144 output bytes'),
                      dict(entry='0x11c994', role='Guarded wrapper for block reader, accepts block indices 0x100..0x1ff; this range alone does not locate factory PCM'),
                      dict(entry='0x12e1c0', role='TG storage read: address=(index<<1)+half at TG+0x330; command0xfe at TG+0x338; poll bit1 clear, return low16 from TG+0x334'),
                      dict(entry='0x12e494', role='Write path has 0x555/0x2aa unlock offsets with 0xaa/0x55 and 0x25/0x29 program commands; NOR-style protocol evidence, NOT a chip identification')],
                  direct_call_candidates={hex(target): [hex(a) for a,b in calls if b==target]
                                          for target in (0x1E9AAC,0x11C90C,0x11C994,0x11C9E0,0x12E1C0)},
                  original_ARM_read_command_captures=captures,
                  ARM_scope='Only original read command with synthetic busy/data registers; no physical flash data and no I/O to a device' if captures else 'Static analysis only; ARM was not executed',
                  unresolved=['Actual factory ROM image bytes absent', 'Factory PCM physical chip and region boundaries unverified',
                              'Availability of a safe stock-firmware export/debug interface unverified',
                              'KROSSPCM.BIN service image layout and compatibility not validated',
                              'Native ROM sample descriptors/decoder may differ from EXPCM and require confirmation'])
    output = folder / ('storage-probe-arm.json' if args.verify_arm else 'storage-probe.json')
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('Recorded PCM storage path; original ARM captures:', len(captures), '; no keyboard accessed')


if __name__ == '__main__':
    main()
