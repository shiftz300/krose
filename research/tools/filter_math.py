#!/usr/bin/env python3
"""Independent factory Concert filter control port, zero external controllers.

Outputs are TG control words, not Hz/Q. No silicon transfer law is assumed.
"""
import struct
from voice_math import VoiceMath, EnvelopeSegment, clamp


def s8(value):return value if value<128 else value-256


class FilterMath:
    def __init__(self, firmware, program):
        self.math=VoiceMath(firmware);self.program=program

    def start(self,note,velocity,oscillator):
        self.osc=self.program[0x564+380*oscillator:0x564+380*(oscillator+1)]
        p=self.osc;m=self.math
        self.velocity=velocity
        self.sources={14:(129*velocity+1)>>2,
                      15:(struct.unpack_from('<h',m.firmware.data,0x405F08+velocity*2)[0]+1)>>3,
                      9:m.keyboard_tracking(p[0xFC:],note),
                      10:m.keyboard_tracking(p[0x13C:],note,amp=True),
                      11:m.keyboard_tracking(self.program[0x554:],note),
                      12:m.keyboard_tracking(self.program[0x55C:],note)}
        self.sources[1]=m.basic_mixer(p[0x14C:],self.sources)
        self.sources[2]=m.basic_mixer(p[0x164:],self.sources)
        eg=p[0xD8:]
        current=m.eg_level(s8(eg[4]),s8(eg[14]),self.source(eg[13]),minimum=-32767)
        self.prepare(0,current)
        self.advance_eg()
        return self.snapshot()

    def source(self,index):return self.sources.get(index,0)

    def prepare(self,phase,current):
        p=self.osc[0xD8:];m=self.math
        level_offset=[6,8,10,12][phase]
        depth=[s8(p[15]),s8(p[16]),0,0][phase]
        target=m.eg_level(s8(p[level_offset]),depth,self.source(p[13]),minimum=-32767)
        modulation=sum(12*m.modulation_product(s8(p[18+5*i+phase]),self.source(p[17+5*i])) for i in range(3))
        self.eg=EnvelopeSegment(m,current,target,p[5+phase*2],modulation,p[phase],stage=phase*2 if phase<3 else 8)

    def advance_eg(self):
        e=self.eg
        if e.stage==6:return
        e.step()
        if e.remaining<=0:
            if e.stage<=1:self.prepare(1,e.level)
            elif e.stage<=3:self.prepare(2,e.level)
            else:e.stage=6

    def advance(self):self.advance_eg();return self.snapshot()
    def release(self):self.prepare(3,self.eg.level);return self.snapshot()

    def snapshot(self):
        self.sources[4]=(self.eg.level*32770)>>18
        return {'A':self.branch(0x90),'B':self.branch(0xB4),
                'eg_level':self.eg.level,'eg_stage':self.eg.stage,'eg_duration':self.eg.total,
                'mixers':[self.source(1),self.source(2)]}

    def branch(self,offset):
        p=self.osc[offset:];m=self.math
        # Native per-filter keytracking offset; extra sample/tone offsets zero.
        tracking=(self.source(9)*s8(p[21]))>>5
        eg_depth=s8(p[22])*63+((self.velocity*s8(p[23]))>>1)
        raw=p[19]*32767+((eg_depth*self.eg.level)>>6)+(tracking<<8)
        for source,depth in ((p[8],s8(p[9])),(p[12],s8(p[13]))):
            raw+=8*depth*self.source(source)
        cutoff=min(31744,((max(raw,0)>>2)*317)>>13)
        resonance=clamp(p[20]*321+8*m.modulation_product(s8(p[5]),self.source(p[4])),0,31744)
        trim=32767 if p[17]==99 else p[17]*331
        output=32767 if p[18]>=99 else p[18]*331
        output=clamp(output+8*m.modulation_product(s8(p[1]),self.source(p[0])),0,32767)
        return [trim,cutoff,resonance,output]
