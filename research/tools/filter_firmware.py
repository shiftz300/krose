#!/usr/bin/env python3
"""Synthetic factory Concert filter contexts; isolated original ARM controls.

Inherits the three external gates from VoiceOracle. No TG audio is executed.
"""
import struct
from voice_firmware import VoiceOracle


class FilterOracle(VoiceOracle):
    def initialize_filter(self, note=60, velocity=100, oscillator=0):
        self.initialize(note, velocity, oscillator, 119 if velocity < 107 else 127)
        a=self.arm;v=self.voice
        a.call(0x1FB8C4,v+0x120,v)
        a.call(0x1FB79C,v+0xEC,v,self.s16(v+0x204),0,stack=(0,))
        return self.filter_snapshot()

    def filter_snapshot(self):
        v=self.voice;e=v+0x120
        return {'A':list(struct.unpack('<4H',self.arm.uc.mem_read(v+0xEC,8))),
                'B':list(struct.unpack('<4H',self.arm.uc.mem_read(v+0x100,8))),
                'routing':self.byte(v+0x116),'types':[self.byte(v+0xFC),self.byte(v+0x110)],
                'eg_level':self.s16(e),'eg_stage':self.byte(e+6),'eg_duration':self.u32(e+0x18),
                'mixers':[self.s16(v+0x1F6),self.s16(v+0x1FE)]}

    def advance_filter(self):
        a=self.arm;v=self.voice
        a.call(0x1FBBE0,v+0x120,v)
        a.call(0x1FB4B0,v+0xEC,v,0,0)
        return self.filter_snapshot()

    def release_filter(self):
        self.arm.call(0x1FBAA0,self.voice+0x120,self.voice)
        return self.filter_snapshot()
