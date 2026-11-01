#!/usr/bin/env python3
"""Build an experimental identity-only application patch, entirely offline.

No connected disk discovery, mounting, installation or MIDI. Always require the
exact official v1.2.4 input. Generated files remain in research/derived/.
"""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

from program_firmware import BASE, FW_SHA, Firmware, ROOT

OUT = ROOT / 'research/derived/firmware/KROSS2_V124/rom/injection/stage-a'
SOURCE = ROOT / 'tools/kross_probe_injection.S'
SLOT = 0x500000
TABLE = 0x2BF228 + 0x18 * 4
OLD_TARGET = BASE + 0x2BF4B4
IMAGE_BYTES = 0x600000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def text_section(path):
    data = path.read_bytes()
    if data[:7] != b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H', data, 18)[0] != 40:
        raise ValueError('Expected little-endian ARM ELF32')
    start = struct.unpack_from('<I', data, 32)[0]
    size, count, names = struct.unpack_from('<3H', data, 46)
    sections = [struct.unpack_from('<10I', data, start + i*size) for i in range(count)]
    def body(s): return data[s[4]:s[4]+s[5]]
    strings = body(sections[names])
    def name(i): return strings[i:strings.index(0, i)].decode()
    index = next(i for i, s in enumerate(sections) if name(s[0]) == '.text')
    if any(s[1] in (4, 9) and s[7] == index and s[5] for s in sections):
        raise ValueError('Unresolved relocation in injected code')
    entries = []
    for s in sections:
        if s[1] != 2: continue
        symbols, labels = body(s), body(sections[s[6]])
        for offset in range(0, len(symbols), s[9]):
            label, value, length, info, other, section = struct.unpack_from('<IIIBBH', symbols, offset)
            if labels[label:labels.index(0, label)] == b'k2_probe_entry':
                entries.append((section, value))
    if entries != [(index, 0)]:
        raise ValueError('Injection entry must be first instruction of .text')
    return body(sections[index])


def sum16(data):
    return sum(data[:-2]) & 0xffff


def build():
    original = Firmware().data
    if len(original) != IMAGE_BYTES or struct.unpack_from('<H', original, len(original)-2)[0] != sum16(original):
        raise ValueError('Unexpected original image size/checksum')
    if struct.unpack_from('<I', original, TABLE)[0] != OLD_TARGET:
        raise ValueError('Original unused-command pointer mismatch')
    obj = ROOT / 'build/kross-probe-injection.o'
    obj.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['clang', '-target', 'armv5te-none-eabi', '-march=armv5te', '-marm',
                    '-c', str(SOURCE), '-o', str(obj)], check=True)
    code = text_section(obj)
    if len(code) > 4096 or original[SLOT:SLOT+len(code)] != b'\xff' * len(code):
        raise ValueError('Injection slot is not unchanged erased padding')
    image = bytearray(original)
    struct.pack_into('<I', image, TABLE, BASE + SLOT)
    image[SLOT:SLOT+len(code)] = code
    struct.pack_into('<H', image, len(image)-2, sum16(image))
    allowed = [(TABLE, TABLE+4), (SLOT, SLOT+len(code)), (len(image)-2, len(image))]
    changed = [i for i, (a, b) in enumerate(zip(original, image)) if a != b]
    if not all(any(lo <= i < hi for lo, hi in allowed) for i in changed):
        raise ValueError('Unexpected patch outside declared regions')
    OUT.mkdir(parents=True, exist_ok=True)
    for directory, data in [('candidate', image), ('restore', original)]:
        target = OUT / directory / 'KROSSAPP.BIN'
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
    (OUT/'probe-arm.text.bin').write_bytes(code)
    # MIDI channel 1 fixture, not automatically transmitted.
    (OUT/'probe-channel-1.syx').write_bytes(bytes.fromhex('f0 42 30 00 01 49 72 18 00 00 00 f7'))
    manifest = dict(stage='A: identity-only experimental injection; NO ROM reader installed',
                    hardware_tested=False, recovery_guaranteed=False,
                    original_sha256=FW_SHA, candidate_sha256=sha(image),
                    image_bytes=len(image), code_bytes=len(code), code_sha256=sha(code),
                    source_sha256=sha(SOURCE.read_bytes()), builder_sha256=sha(Path(__file__).read_bytes()),
                    changes=[dict(offset=hex(lo), bytes=hi-lo) for lo, hi in allowed],
                    changed_byte_count=len(changed), checksum_u16le=hex(sum16(image)),
                    startup_hook=False, TG_reading=False, flash_programming=False,
                    deployment='Manual USB file replacement only, NOT performed by this tool',
                    request_channel_1='f0 42 30 00 01 49 72 18 00 00 00 f7',
                    expected_reply_channel_1='f0 42 30 00 01 49 7d 4b 52 4f 53 45 01 f7',
                    unknowns=['Bootloader acceptance/loading range of modified application',
                              'Real task stack, MMU permissions and runtime use of padding slot',
                              'USB MIDI ring transport/locking on the instrument',
                              'Recovery USB mode after arbitrary application failure'])
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (OUT/'SHA256SUMS').write_text(''.join(f'{sha(data)}  {directory}/KROSSAPP.BIN\n'
                                       for directory, data in [('candidate', image), ('restore', original)]))
    return manifest


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(build(), indent=2))
