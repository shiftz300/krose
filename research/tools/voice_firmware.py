#!/usr/bin/env python3
"""Reusable synthetic voice contexts for original ARM control functions.

Only external Tone Adjust/MIDI-enable and mute gates are replaced. Voice AMS,
mixers, envelope stages, gain tables and arithmetic execute original code.
Results are control-domain values, not TG-rendered audio or real-time traces.
"""
import hashlib
import struct
from program_firmware import Arm, Firmware, ROOT


class VoiceOracle:
    def __init__(self):
        self.firmware=Firmware()
        self.arm=Arm(self.firmware)
        self.program=(ROOT/'output/kep-analysis/Concert_SE_Grand/program.bin').read_bytes()
        if hashlib.sha256(self.program).hexdigest()!='a52ae2deebe0a0997bb50d50b3b26c1e40bd278567068e6afc85ae20e09222e4':
            raise ValueError('Unexpected Concert Program; synthetic context is version locked')
        self.voice,self.context,self.part,self.osc,self.patch,self.runtime,self.controls,self.mode,self.settings=[0x11010000+i*0x2000 for i in range(9)]
        self.arm.stubs={
            0x2753DC:lambda _:0,  # Tone Adjust offsets all zero
            0x2737C8:lambda _:0,  # no external MIDI controller override enabled
            0x2DF2C:lambda _:1,   # track/part mute gate open
        }

    def u16(self,address):return struct.unpack('<H',self.arm.uc.mem_read(address,2))[0]
    def s16(self,address):return struct.unpack('<h',self.arm.uc.mem_read(address,2))[0]
    def u32(self,address):return struct.unpack('<I',self.arm.uc.mem_read(address,4))[0]
    def byte(self,address):return bytes(self.arm.uc.mem_read(address,1))[0]

    def initialize(self,note=60,velocity=100,oscillator=0,level=127):
        if not (0<=note<=127 and 1<=velocity<=127 and oscillator in (0,1) and 0<=level<=127):
            raise ValueError('Invalid synthetic voice input')
        a=self.arm;v=self.voice;c=self.context
        a.uc.mem_write(v,bytes(0x12000))
        a.uc.mem_write(self.osc,self.program[0x564+380*oscillator:0x564+380*(oscillator+1)])
        a.uc.mem_write(self.patch,self.program)
        a.write(v+4,self.runtime,c)
        a.write(v+0x21C,self.patch,self.patch+0x520,self.osc)
        a.write(v+0x240,0xFFFFFFFF)
        a.uc.mem_write(v+0x12,bytes([note,0,velocity]))
        a.write(c+4,self.part)
        a.write(c+0x8C,self.controls)
        a.uc.mem_write(self.part+5,b'\x7f')
        a.uc.mem_write(c+0x30,struct.pack('<2H',65535,65535))
        a.write(0xC199BD3C,self.mode)
        a.write(self.mode,4)
        a.write(0xC1743270,self.settings)
        a.write(0xC0F5389C,self.settings)
        a.write(self.settings+0x30,0)
        for output,function,parameter in [(0x204,0x2913EC,self.osc+0xFC),
                                          (0x206,0x2915A8,self.osc+0x13C),
                                          (0x212,0x2913EC,self.patch+0x554),
                                          (0x214,0x2913EC,self.patch+0x55C)]:
            value=a.call(function,parameter,note)
            a.uc.mem_write(v+output,struct.pack('<h',value))
        # The note-on path prepares two AMS mixers before amplitude/EG setup.
        for offset,param in [(0x1F0,0x14C),(0x1F8,0x164)]:
            a.call(0x201434,v+offset,v,self.osc+param)
            a.call(0x20119C,v+offset,v,1)
        a.call(0x201674,v+0x200,level,0,0)
        a.call(0x1FA300,v+0x15C,v)
        # r2: zero additional amp modulation; stack: zero LFO inputs and
        # zero extra max-level offset (native default is then +99).
        a.call(0x1FA1A0,v+0x150,v,self.s16(v+0x206),velocity,stack=(0,0,0))
        return self.snapshot()

    def snapshot(self):
        v=self.voice;e=v+0x15C
        return {'eg_control_level':self.s16(e),'eg_stage':self.byte(e+6),
                'eg_duration_units':self.u32(e+0x18),'eg_remaining_units':struct.unpack('<q',self.arm.uc.mem_read(e+0x10,8))[0],
                'amp_control_gain':self.u16(v+0x150),'amp_velocity_factor':self.u16(v+0x156),
                'multisample_factor':self.u16(v+0x200),'ams_mixers':[self.s16(v+0x1F6),self.s16(v+0x1FE)],
                'keyboard_tracking':[self.s16(v+offset) for offset in (0x204,0x206,0x212,0x214)]}

    def advance(self):
        v=self.voice
        self.arm.call(0x1FA828,v+0x15C,v)
        self.arm.call(0x1F9DD4,v+0x150,v,0,0)
        return self.snapshot()

    def release(self):
        self.arm.call(0x1FA664,self.voice+0x15C,self.voice)
        return self.snapshot()
