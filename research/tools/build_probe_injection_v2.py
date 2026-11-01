#!/usr/bin/env python3
"""Offline stage-A revision 2: use only the real eight-byte event ABI.

Preserves the complete stage-a v1 bundle and official image. Does not contact
the instrument. Revision 2 replies with marker version 02, and still reads no TG.
"""
import hashlib
import json
import struct
import subprocess

from build_probe_injection import OUT as OLD_OUT, SLOT, TABLE, IMAGE_BYTES, text_section, sum16
from program_firmware import BASE, FW_SHA, Firmware, ROOT

OUT = OLD_OUT.with_name('stage-a-v2')
SOURCE = ROOT/'tools/kross_probe_injection_v2.S'


def sha(data): return hashlib.sha256(data).hexdigest()


def build():
    original = Firmware().data
    obj = ROOT/'build/kross-probe-injection-v2.o'
    subprocess.run(['clang', '-target', 'armv5te-none-eabi', '-march=armv5te', '-marm',
                    '-c', str(SOURCE), '-o', str(obj)], check=True)
    code = text_section(obj)
    assert len(original) == IMAGE_BYTES and original[SLOT:SLOT+len(code)] == b'\xff'*len(code)
    assert 0 < len(code) <= 4096
    candidate = bytearray(original)
    struct.pack_into('<I', candidate, TABLE, BASE+SLOT)
    candidate[SLOT:SLOT+len(code)] = code
    struct.pack_into('<H', candidate, len(candidate)-2, sum16(candidate))
    OUT.mkdir(parents=True, exist_ok=True)
    for label, data in [('candidate', candidate), ('restore', original)]:
        (OUT/label).mkdir(exist_ok=True)
        (OUT/label/'KROSSAPP.BIN').write_bytes(data)
    (OUT/'probe-arm.text.bin').write_bytes(code)
    manifest = dict(stage='A revision 2: identity only; real 8-byte MIDI event ABI',
                    revision=2, original_sha256=FW_SHA, candidate_sha256=sha(candidate),
                    previous_candidate_sha256=sha((OLD_OUT/'candidate/KROSSAPP.BIN').read_bytes()),
                    source_sha256=sha(SOURCE.read_bytes()), code_bytes=len(code), code_sha256=sha(code),
                    image_bytes=len(candidate), TG_reading=False, flash_programming=False,
                    hardware_tested=False, recovery_guaranteed=False,
                    request_channel_1='f042300001497218000000f7',
                    expected_reply_channel_1='f042300001497d4b524f534502f7',
                    fix='Do not read parser scratch at event+8; real FIFO copies two u32 only',
                    index_scope='Only event byte 5 remains: 14-bit wire indices are truncated to 8 bits by original parser/FIFO; identity aliases are harmless',
                    unknowns=['Actual v2 execution/reply on owned keyboard',
                              'Cause of no original 72/15 name-query reply',
                              'Recoverability after arbitrary application failure'])
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (OUT/'SHA256SUMS').write_text(''.join(f'{sha(data)}  {label}/KROSSAPP.BIN\n'
                                       for label, data in [('candidate', candidate), ('restore', original)]))
    return manifest


if __name__ == '__main__': print(json.dumps(build(), indent=2))
