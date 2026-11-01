#!/usr/bin/env python3
"""Local KROSS 2 firmware inspection helpers. Never execute device firmware."""
import argparse
import struct
import sys
from pathlib import Path

from layout import ROOT
sys.path.insert(0, str(ROOT / "research/python-deps"))
BASE = 0xC0000000


def decompress_cmp(source):
    data = source.read_bytes()
    expected, checksum = struct.unpack_from("<II", data)
    if not 0 < expected <= 64 * 1024 * 1024:
        raise ValueError("Implausible CMP output size")
    ring = bytearray(4096)
    write = 4096 - 18
    output = bytearray()
    pos = 8
    while len(output) < expected:
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if len(output) == expected:
                break
            if flags & (1 << bit):
                decoded = bytes([data[pos]])
                pos += 1
            else:
                low, high = data[pos:pos + 2]
                pos += 2
                offset = low | ((high & 0xF0) << 4)
                decoded = None
                count = (high & 15) + 3
            for i in range(1 if decoded is not None else count):
                value = decoded[0] if decoded is not None else ring[(offset + i) & 4095]
                output.append(value)
                ring[write] = value
                write = (write + 1) & 4095
    if pos != len(data):
        raise ValueError(f"CMP trailing bytes: consumed {pos}/{len(data)}")
    actual_sum = sum(output) & 0xFFFFFFFF
    if actual_sum != checksum:
        raise ValueError(f"CMP checksum mismatch: {actual_sum:08x} != {checksum:08x}")
    print(f"CMP size={expected}, byte-sum checksum={actual_sum:08x}: PASS")
    return output


def inspect(data, start, end):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    md.skipdata = True
    for ins in md.disasm(data[start:end], BASE + start):
        comment = ""
        word = int.from_bytes(ins.bytes, "little")
        # ARM immediate LDR from the PC: annotate literal and nearby string.
        if word & 0x0F7F0000 == 0x051F0000:
            literal = ins.address - BASE + 8 + ((1 if word & (1 << 23) else -1) * (word & 4095))
            if 0 <= literal <= len(data) - 4:
                value = struct.unpack_from("<I", data, literal)[0]
                comment = f" ; [{literal:06x}]={value:08x}"
                if BASE <= value < BASE + len(data):
                    s = data[value-BASE:value-BASE+80].split(b"\0")[0]
                    if s and all(32 <= c < 127 for c in s):
                        comment += " " + repr(s.decode())
        print(f"{ins.address - BASE:06x}: {ins.mnemonic:8} {ins.op_str}{comment}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decompress", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--file", type=Path, default=ROOT / "research/derived/firmware/KROSS2_V124/KROSSAPP.bin")
    parser.add_argument("--range", nargs=2, type=lambda v: int(v, 0))
    parser.add_argument("--calls", nargs="+", type=lambda v: int(v, 0))
    args = parser.parse_args()
    if args.decompress:
        output = decompress_cmp(args.decompress)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(output)
        return
    data = args.file.read_bytes()
    if args.range:
        inspect(data, *args.range)
    if args.calls:
        targets = set(args.calls)
        for offset in range(0, min(0x330000, len(data)-3), 4):
            word = struct.unpack_from("<I", data, offset)[0]
            if (word & 0x0F000000) != 0x0B000000:
                continue
            rel = word & 0xFFFFFF
            if rel & 0x800000:
                rel -= 0x1000000
            dest = offset + 8 + rel * 4
            if dest in targets:
                print(f"{offset:06x} -> {dest:06x}")


if __name__ == "__main__":
    main()
