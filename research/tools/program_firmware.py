#!/usr/bin/env python3
"""Version-locked KROSS 2 Program metadata and isolated ARM research helpers."""
import hashlib
import struct
import sys

from decode_korg_pcm import ROOT, FW, FW_SHA

BASE = 0xC0000000
PROGRAM_RAM = 0xC1666C88
PARAMETER_GROUPS = 0x407BD0
EFFECT_TABLE = 0x336D6C
EFFECT_COUNT = 135  # ID 0 (No Effect), plus 134 effects in this firmware.


class Firmware:
    def __init__(self):
        self.data = FW.read_bytes()
        if hashlib.sha256(self.data).hexdigest() != FW_SHA:
            raise ValueError("Unsupported firmware version")

    def u32(self, offset):
        return struct.unpack_from("<I", self.data, offset)[0]

    def pointer(self, offset):
        result = self.u32(offset) - BASE
        if not 0 <= result < len(self.data):
            raise ValueError(f"Not an image pointer at {offset:#x}")
        return result

    def string(self, offset):
        return self.data[offset:self.data.index(b"\0", offset)].decode("ascii")

    def phase_increment(self, exponent):
        """Integer port of 0x1ff348; 3072 exponent units per octave.

        Caller must supply the lower bound enforced by the voice control path.
        The original helper itself only clamps the upper bound.
        """
        if exponent < -0x8000:
            raise ValueError("Exponent below table range")
        index = min(exponent, 0x5FFF) + 0x8000
        base = self.u32(0x405B88 + (index >> 8) * 4)
        fraction = struct.unpack_from("<H", self.data, 0x405984 + (index & 255) * 2)[0]
        return (base + (((base * fraction) & 0xFFFFFFFF) >> 16)) & 0xFFFFFFFF

    def descriptor(self, offset):
        kind, display, shift, width, flags, low, high = struct.unpack_from("<BBBBIii", self.data, offset)
        if kind > 6 or width > 32:
            raise ValueError("Invalid parameter descriptor")
        return {"firmware_offset": offset, "raw_hex": self.data[offset:offset + 20].hex(),
                "type": kind, "display_format": display, "shift": shift, "width": width,
                "flags": flags, "minimum": low, "maximum": high,
                "callback": self.u32(offset + 16) - BASE if self.u32(offset + 16) else None}

    def read_value(self, data, offset, descriptor):
        kind = descriptor["type"]
        if kind == 6:
            raise ValueError("String parameter not supported here")
        size = (1, 2, 4, 1, 2, 4)[kind]
        raw = data[offset:offset + size]
        if len(raw) != size:
            raise ValueError("Truncated parameter")
        value = int.from_bytes(raw, "little", signed=kind < 3)
        width = descriptor["width"]
        if width:
            value = (value >> descriptor["shift"]) & ((1 << width) - 1)
            if kind < 3 and value & (1 << (width - 1)):
                value -= 1 << width
        return value

    def group(self, namespace, program):
        group = self.pointer(PARAMETER_GROUPS + namespace * 4)
        count = self.u32(group)
        table = self.pointer(group + 4)
        if count > 512:
            raise ValueError("Invalid group length")
        result = []
        for index in range(count):
            cell = self.pointer(table + index * 4)
            address = self.u32(cell)
            if not PROGRAM_RAM <= address < PROGRAM_RAM + len(program):
                continue
            descriptor = self.descriptor(self.pointer(cell + 4))
            if descriptor["type"] == 6:
                continue
            offset = address - PROGRAM_RAM
            result.append({"namespace": namespace, "index": index, "program_offset": offset,
                           "cell_offset": cell, "descriptor": descriptor,
                           "value": self.read_value(program, offset, descriptor)})
        return result

    def effect(self, effect_id):
        if not 0 <= effect_id < EFFECT_COUNT:
            raise ValueError("Effect ID outside v1.2.4 table")
        definition = self.pointer(EFFECT_TABLE + effect_id * 4)
        parameter_count, code_count, constant_count, aux = struct.unpack_from("<4H", self.data, definition + 28)
        parameter_table = self.pointer(definition + 36)
        parameters = []
        for index in range(parameter_count):
            record = self.pointer(parameter_table + index * 4)
            packed = self.u32(record + 16)
            parameters.append({"index": index, "label": self.string(self.pointer(record + 12)),
                               "record_offset": record, "payload_offset": packed & 255,
                               "ui_flags": (packed >> 8) & 255,
                               "display_function": self.u32(record + 20) - BASE if self.u32(record + 20) else None,
                               "active_ui_descriptor": self.u32(record + 24) != 0xFFFFFFFF,
                               "descriptor": self.descriptor(self.pointer(record + 8))})
        return {"id": effect_id, "name": self.string(self.pointer(definition)),
                "short_name": self.string(self.pointer(definition + 4)), "definition_offset": definition,
                "code_offset": self.pointer(definition + 8) if self.u32(definition + 8) else None,
                "code_words_64": code_count,
                "constants_offset": self.pointer(definition + 12), "constant_words_32": constant_count,
                "aux_count_unresolved": aux,
                "arm_functions": [self.pointer(definition + i) for i in (16, 20, 24)],
                "parameters": parameters}


class Arm:
    """Pure memory computation only. Never starts the OS or accesses a device."""
    def __init__(self, firmware):
        sys.path.insert(0, str(ROOT / "research/python-deps"))
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
        from unicorn import arm_const
        self.constants = arm_const
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.uc.mem_map(BASE, 0x2000000)
        self.uc.mem_write(BASE, firmware.data)
        self.uc.mem_map(0x10000000, 0x1000)
        self.uc.mem_map(0x11000000, 0x200000)
        self.stack = 0x111F0000
        self.stubs = {}
        self.memory_fault = None

        def hook(uc, address, size, user):
            function = self.stubs.get(address - BASE)
            if function:
                value = function(self)
                if value is not None:
                    self.set("R0", value)
                self.set("PC", self.get("LR"))
        self.uc.hook_add(UC_HOOK_CODE, hook)
        def fault(uc, access, address, size, value, user):
            self.memory_fault = {'access': access, 'address': hex(address),
                                 'bytes': size, 'pc': hex(self.get('PC'))}
            return False
        self.uc.hook_add(UC_HOOK_MEM_INVALID, fault)

    def set(self, register, value):
        self.uc.reg_write(getattr(self.constants, "UC_ARM_REG_" + register), value & 0xFFFFFFFF)

    def get(self, register):
        return self.uc.reg_read(getattr(self.constants, "UC_ARM_REG_" + register))

    def write(self, address, *values):
        self.uc.mem_write(address, struct.pack("<" + "I" * len(values), *[v & 0xFFFFFFFF for v in values]))

    def call(self, offset, *arguments, stack=(), count=1000000):
        if len(arguments)>4:
            raise ValueError('AAPCS register arguments are R0..R3; pass remaining values via stack=')
        self.memory_fault = None
        for n in range(13):
            self.set("R" + str(n), 0)
        self.set("SP", self.stack)
        self.set("LR", 0x10000000)
        for i, value in enumerate(arguments):
            self.set("R" + str(i), value)
        if stack:
            self.write(self.stack, *stack)
        try:
            self.uc.emu_start(BASE + offset, 0x10000000, count=count)
        except Exception as error:
            raise RuntimeError(f'ARM call {offset:#x} failed; memory fault={self.memory_fault}') from error
        if self.get("PC") != 0x10000000:
            raise RuntimeError(f"Instruction budget exhausted at {self.get('PC'):#x}")
        value = self.get("R0")
        return value - 2**32 if value & 2**31 else value

    def parameter(self, value_bytes, descriptor):
        obj, data, desc = 0x11000000, 0x11001000, 0x11002000
        self.uc.mem_write(data, value_bytes + bytes(8))
        self.uc.mem_write(desc, bytes.fromhex(descriptor["raw_hex"]))
        self.write(obj, 0, data, desc, 0, 0, 0)
        return self.call(0x20AF84, obj)

    def pitch_rate(self, pitch):
        """Run original pitch setup + increment update, zeroing unrelated modulation.

        Stubs are external MIDI/tone-adjust getters and pitch-EG update, all zero.
        Sample pitch, base-pitch correction, exp LUT and increment clamp run
        as original instructions. The sample descriptor and contexts are synthetic.
        """
        voice, context, osc, part, controls, oscruntime, sample, pitchctx = [0x11010000 + i * 0x2000 for i in range(8)]
        self.uc.mem_write(voice, bytes(0x10000))
        self.write(voice + 4, oscruntime, context)
        self.write(voice + 0x20, sample)
        self.write(voice + 0x21C, part, 0, osc)
        self.write(context + 4, part)
        self.write(context + 0x8C, controls)
        self.uc.mem_write(oscruntime + 0x4A2, b"\xff")
        self.uc.mem_write(sample, struct.pack("<h", pitch))
        self.uc.mem_write(sample + 7, b"\x11")
        self.write(sample + 0x14, 0, 4095)
        self.stubs = {offset: lambda arm: 0 for offset in (0x2753DC, 0x2754AC, 0x275688, 0x274DC4, 0x1F8A64, 0x1FFDE8)}
        self.call(0x1FF764, pitchctx, voice, 60 * 256, 0,
                  stack=(sample, 60 * 256, 0, 0))
        increment = struct.unpack("<I", self.uc.mem_read(pitchctx + 0x18, 4))[0]
        self.stubs = {}
        return increment
