#!/usr/bin/env python3
"""Compare the KROSS firmware's Blowfish implementation with a local port."""
import struct
import sys
from pathlib import Path

from layout import ROOT
sys.path.insert(0, str(ROOT / "research/python-deps"))
FIRMWARE = ROOT / "research/derived/firmware/KROSS2_V124/KROSSAPP.bin"


class KorgBlowfish:
    def __init__(self, firmware, key):
        self.p = list(struct.unpack_from("<18I", firmware, 0x340958))
        self.s = list(struct.unpack_from("<1024I", firmware, 0x33F958))
        for i in range(18):
            self.p[i] ^= int.from_bytes(bytes(key[(i * 4 + j) % len(key)] for j in range(4)), "little")
        left = right = 0
        for table in (self.p, self.s):
            for i in range(0, len(table), 2):
                left, right = self.block(left, right)
                table[i:i + 2] = left, right

    def block(self, left, right, decrypt=False):
        p = self.p[::-1] if decrypt else self.p
        s = self.s
        for i in range(16):
            left ^= p[i]
            f = (((s[left & 255] + s[256 + ((left >> 8) & 255)]) ^
                  s[512 + ((left >> 16) & 255)]) + s[768 + (left >> 24)]) & 0xFFFFFFFF
            right ^= f
            left, right = right, left
        left, right = right, left
        return left ^ p[17], right ^ p[16]

    def decrypt(self, data):
        if len(data) % 8:
            raise ValueError("Blowfish input must be a multiple of 8 bytes")
        return b"".join(struct.pack("<II", *self.block(*struct.unpack_from("<II", data, i), True))
                        for i in range(0, len(data), 8))


def firmware_probe(firmware, key, data):
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
    from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_PC
    base = 0xC0000000
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(base, 0x2000000)
    uc.mem_write(base, firmware)
    uc.mem_map(0x10000000, 0x1000)
    uc.mem_map(0x11000000, 0x20000)
    uc.mem_map(0x12000000, 0x10000)
    ctx, p, s, kp, dp = 0x12000000, 0x12000100, 0x12001000, 0x12003000, 0x12004000
    uc.mem_write(ctx, struct.pack("<II", p, s))
    uc.mem_write(kp, key)
    uc.mem_write(dp, data)

    def call(offset, *args):
        uc.reg_write(UC_ARM_REG_SP, 0x1101F000)
        uc.reg_write(UC_ARM_REG_LR, 0x10000000)
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), args):
            uc.reg_write(reg, value)
        uc.emu_start(base + offset, 0x10000000, count=5000000)
        if uc.reg_read(UC_ARM_REG_PC) != 0x10000000:
            raise RuntimeError("Instruction budget exhausted")

    call(0x61F54, ctx, kp, len(key))
    context = bytes(uc.mem_read(p, 72)) + bytes(uc.mem_read(s, 4096))
    call(0x62178, ctx, dp, len(data))
    return bytes(uc.mem_read(dp, len(data))), context


if __name__ == "__main__":
    fw = FIRMWARE.read_bytes()
    encrypted = (ROOT / "EXPCM001/EXPCM001.KEP").read_bytes()[:256]
    for suffix in (b"ABCDEFGHIJKLMNOP", fw[0x48EE54:0x48EE64], b" " * 16, bytes(16)):
        key = b"KORG0002" + suffix
        port = KorgBlowfish(fw, key)
        out = port.decrypt(encrypted)
        print("port", key.hex(), repr(out[:64]), flush=True)
        if "--emulate" in sys.argv:
            machine, context = firmware_probe(fw, key, encrypted)
            native_context = struct.pack("<18I", *port.p) + struct.pack("<1024I", *port.s)
            print("firmware", repr(machine[:64]), "context matches", context == native_context, flush=True)
            for i in range(0, len(context), 4):
                if context[i:i+4] != native_context[i:i+4]:
                    print("first context mismatch", i, context[i:i+4].hex(), native_context[i:i+4].hex(), flush=True)
                    break
            if b"KORG" in machine[:64]:
                (ROOT / "research/derived/kep").mkdir(parents=True, exist_ok=True)
                (ROOT / "research/derived/kep/KEP-header-decoded.bin").write_bytes(machine)
                (ROOT / "research/derived/kep/KEP-blowfish-context.bin").write_bytes(context)
