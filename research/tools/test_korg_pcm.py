#!/usr/bin/env python3
"""Verify the reconstruction against C, Python, and optionally original ARM code.

--firmware executes two isolated instruction ranges in Unicorn, without a
device, OS startup, firmware changes, or MIDI. It tests the encoder feedback
path; it cannot establish identity with the separate TG01 hardware decoder.
"""
import argparse
import array
import hashlib
import json
import random
import struct
import sys
from pathlib import Path

from decode_korg_pcm import ROOT, FW, SOURCE, Decoder, decode_reference, load_lut, write_wav


class FirmwareFeedback:
    def __init__(self):
        sys.path.insert(0, str(ROOT / "research/python-deps"))
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
        from unicorn import arm_const
        self.registers = arm_const
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.base, self.fp, self.ctx = 0xC0000000, 0x11010000, 0x12000000
        self.history, self.coefficients = self.ctx + 0x1000, self.ctx + 0x2000
        self.uc.mem_map(self.base, 0x600000)
        self.uc.mem_write(self.base, FW.read_bytes())
        self.uc.mem_map(0x11000000, 0x20000)
        self.uc.mem_map(self.ctx, 0x10000)

    def reg(self, name, value):
        self.uc.reg_write(getattr(self.registers, "UC_ARM_REG_" + name), value & 0xFFFFFFFF)

    def write(self, address, *words):
        self.uc.mem_write(address, struct.pack("<" + "I" * len(words), *[w & 0xFFFFFFFF for w in words]))

    def step(self, code, a1, a2, previous, older):
        self.reg("SP", self.fp - 0x1000)
        self.reg("FP", self.fp)
        self.reg("R9", self.ctx)
        self.write(self.ctx + 0x18, self.history)
        self.write(self.ctx + 0x20, 0)
        self.write(self.history, previous, older, 0)
        self.uc.mem_write(self.coefficients, struct.pack("<2h", a1, a2))
        self.write(self.fp + 0xC, self.coefficients)
        self.uc.emu_start(self.base + 0x1F5218, self.base + 0x1F5308, count=2000)
        if self.uc.reg_read(self.registers.UC_ARM_REG_PC) != self.base + 0x1F5308:
            raise RuntimeError("Prediction did not reach boundary")
        self.reg("R1", code << 24)
        self.write(self.fp - 0x50, 0)
        self.uc.emu_start(self.base + 0x1F55B0, self.base + 0x1F569C, count=2000)
        if self.uc.reg_read(self.registers.UC_ARM_REG_PC) != self.base + 0x1F569C:
            raise RuntimeError("Feedback did not reach boundary")
        return struct.unpack("<i", self.uc.mem_read(self.history + 8, 4))[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", action="store_true")
    args = parser.parse_args()
    lut = load_lut()
    decoder = Decoder(lut, ROOT / "build")
    samples = json.loads((SOURCE / "samples.json").read_text())
    rng = random.Random(20261031)
    cases = [("all_codes_no_prediction", bytes(range(256)), 0, 0),
             ("silence", bytes(2048), 30945, -14674),
             ("saturation", bytes(rng.randrange(256) for _ in range(2048)), 32767, 32767),
             ("negative_coefficients", bytes(rng.randrange(256) for _ in range(2048)), -32768, -32768)]
    for i in [56, 70, 80, 84, 110, 112, 140, 166, 168, 196, 222]:
        descriptor = samples[i]
        coefficients = struct.unpack_from("<2h", bytes.fromhex(descriptor["descriptor_hex"]), 8)
        cases.append((f"native_{i:03d}", (SOURCE / descriptor["native_file"]).read_bytes()[:2048], *coefficients))
    firmware = FirmwareFeedback() if args.firmware else None
    rows = []
    for name, source, a1, a2 in cases:
        expected, counts = decode_reference(source, a1, a2, lut)
        actual, c_counts = decoder.decode(source, a1, a2)
        assert expected == actual and counts == c_counts, name
        if firmware:
            previous = older = 0
            for code, value in zip(source, expected):
                native = firmware.step(code, a1, a2, previous, older)
                assert native == value, (name, code, native, value, previous, older)
                older, previous = previous, native
        rows.append({"case": name, "frames": len(source), "c_python_equal": True,
                     "arm_firmware_equal": True if firmware else None, "saturations": counts})
        print(f"PASS {name}: {len(source)} frames" + (" C = Python = ARM firmware" if firmware else " C = Python"), flush=True)
    # Container verification includes exact byte order and negative full-scale.
    temporary = ROOT / "build/test_pcm24.wav"
    write_wav(temporary, array.array("i", [0, 256, -256, 2147483647, -2147483647, 0]), 2, 42017, 60, [0, 2])
    data = temporary.read_bytes()
    assert data[:4] == b"RIFF" and len(data) == struct.unpack_from("<I", data, 4)[0] + 8
    pos = data.index(b"data")
    assert data[pos + 8:pos + 23] == bytes.fromhex("000000010000ffffff ffff7f000080".replace(" ", ""))
    report = {"firmware_sha256": hashlib.sha256(FW.read_bytes()).hexdigest(),
              "oracle": "Original ARM encoder prediction + inverse quantizer + saturated feedback" if firmware else "Python reference",
              "oracle_scope": "Does not execute or validate TG01 hardware, rate interpretation or complete Program",
              "total_frames": sum(r["frames"] for r in rows), "cases": rows, "wav_container_pass": True}
    path = ROOT / ("research/derived/verification/pcm-arm-comparison.json" if firmware else "build/pcm-c-python-comparison.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS PCM24 RIFF and smpl container; report: {path}")


if __name__ == "__main__":
    main()
