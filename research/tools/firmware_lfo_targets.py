#!/usr/bin/env python3
"""Independent LFO-to-pitch/filter/amplitude controls, compared to native ARM."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_voice_lfo_integration import Rig as LfoRig,sb,TA
from firmware_voice_lfo import h,sh,w,ph,pw,clamp,s16,s32,sha,OUT,PRELOAD
from program_firmware import Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
MASK=0xFFFFFFFF
def u32(v):return v&MASK
def div(n,d):return (abs(n)//abs(d))*(-1 if (n<0)^(d<0) else 1)
def depth(value):
    v=abs(value);q=21*v if v<=50 else 1024+103*(v-50) if v<=60 else 2048+410*(v-60)
    return (q>>3)*(-1 if value<0 else 1)
def modulation(amount,source):return clamp(amount*source*331>>15,-32768,32767)

class Rig(LfoRig):
    def __init__(self,f):self.f=f;super().__init__(f)
    def prepare(self,record,osc):
        super().prepare(record,osc);a=self.a;v=self.voice;o=self.program+0x564+380*osc
        a.write(v+0x220,self.program+0x520,o);a.write(v+0x20,0x11030000)
        self.sample=bytearray(64);self.sample[7]=32;pw(self.sample,20,0);pw(self.sample,24,512)
        a.uc.mem_write(0x11030000,bytes(self.sample))
        a.write(0xC199BD3C,0x11034000);a.write(0x11034000,3)
        a.write(0xC1743270,0x11036000);a.write(0x11036030,0)
        a.uc.mem_write(self.part+5,b'\x7f');a.write(self.context+0x30,0xFFFFFFFF)
        self.pitch=bytearray(56);ph(self.pitch,18,69*256);pw(self.pitch,24,8192)
        for at,offset in [(28,0x68),(32,0x6C),(36,0x70),(40,0x74)]:pw(self.pitch,at,o+offset)
        self.pitch[44]=self.pitch[52]=255;a.uc.mem_write(v+0x84,bytes(self.pitch))
        self.filter=bytearray(52)
        for bank in range(2):
            for at,value in [(0,32767),(2,5000),(4,1000),(6,20000)]:ph(self.filter,20*bank+at,value)
        self.filter[42]=record[0x564+380*osc+0x88]&3;a.uc.mem_write(v+0xEC,bytes(self.filter))
        self.amp=bytearray(12)
        for at,value in [(0,1000),(2,999),(4,17000),(6,16000),(8,32767)]:ph(self.amp,at,value)
        a.uc.mem_write(v+0x150,bytes(self.amp));self.flags=0
        self.levels(0,0,24576)
    def levels(self,pitch,fil,amp):
        self.eg_levels=[pitch,fil,amp]
        for at,value in [(0xBC,pitch),(0x120,fil),(0x15C,amp),(0x190,32767)]:self.a.uc.mem_write(self.voice+at,struct.pack('<h',value))
    def source(self,number):
        if number in [3,4,5]:return self.eg_levels[number-3]*32770>>18
        return super().source(number)
    def osc_bytes(self):return self.record[0x564+380*self.osc:0x564+380*(self.osc+1)]
    def values(self,first,second,fades=(65535,65535),change=True):
        for slot,(value,fade) in enumerate(zip([first,second],fades)):
            ph(self.states[slot],0,value);ph(self.states[slot],8,fade);self.states[slot][18]=4 if change else 0
            self.a.uc.mem_write(self.address(slot),bytes(self.states[slot]))
    def rate(self,value):
        value=min(0x5FFF,value);assert value>=-32768,value
        index,fraction=divmod(value+32768,256);base=self.f.u32(0x405B88+index*4);fine=h(self.f.data,0x405984+fraction*2)
        return u32(base+(u32(base*fine)>>16))
    def model_pitch(self,values):
        p=self.osc_bytes()[0x68:];b=self.pitch;flags=self.flags;total=0
        for slot in range(2):
            variable=depth(sb(p,9+4*slot))
            variable=s32((self.source(p[8+4*slot])<<4)*variable)>>16 if variable else 0
            if variable:self.states[slot][18]|=1
            base=depth(sb(p,22+slot))*h(self.states[slot],8)>>16
            amount=variable+base
            if amount and self.states[slot][18]&4:flags|=1
            total+=s32(amount*values[slot])>>14
        eg=depth(sb(p,21))
        if sb(p,5):eg+=s32((self.source(p[4])<<4)*depth(sb(p,5)))>>16
        if eg:flags|=16
        pitch=s32(eg*self.eg_levels[0])>>15
        if sb(p,1):pitch+=s32((self.source(p[0])<<4)*depth(sb(p,1)))>>16
        offset=pitch-sh(b,2)+total+(s32(w(b,4))>>8)
        ph(b,16,h(b,18)+offset)
        increment=self.rate(offset);absolute=u32(self.rate(sh(b,16)-0x4500)<<3)
        correction=div(sb(p,29)*65536,4400);correction=div(s32(correction<<16),s32(absolute))
        increment+=correction*increment>>16
        sample=self.sample;mode=sample[7];length=s32(w(sample,24)-w(sample,20))
        maximum=32768 if mode&1 else 0x1FFFFF
        if not mode&33 and length<=255:
            maximum=65536 if length<=15 else 131072 if length<=31 else 262144 if length<=63 else 524288 if length<=127 else 1048576
        pw(b,20,w(b,24));pw(b,24,min(increment,maximum));pw(b,48,maximum);self.flags=flags
    def cutoff(self,raw):return min(31744,s32((max(s32(raw),0)>>2)*317)>>13)
    def model_filter(self,values):
        p=self.osc_bytes();b=self.filter;routing=b[42]
        sources=[self.source(p[0x8A+i]) for i in range(3)];egsource=self.source(p[0x89])
        if routing==3:ph(b,6,h(b,26))
        for bank in range(2):
            at=20*bank;q=p[0x90+36*bank:]
            if bank and routing==3:
                b[28:36]=b[8:16];b[20:28]=b[0:8];ph(b,24,h(b,24)*115>>8);ph(b,32,h(b,32)*115>>8);ph(b,20,32767);continue
            lfo_sum=0
            for slot in range(3):
                variable=s32(sources[slot]*sb(q,31+slot))>>5 if sources[slot] else 0
                amount=variable>>2
                if slot<2:
                    if amount:self.states[slot][18]|=1
                    amount+=sb(q,25+slot)*h(self.states[slot],8)>>11
                    changed=self.states[slot][18]&4
                else:amount+=sb(q,27)<<5;changed=False
                if amount and changed:self.flags|=1<<(bank+1)
                lfo_sum=s32(lfo_sum+(s32(amount*values[slot])>>4))
            raw=s32(sh(b,40)*198+lfo_sum+(sh(b,44+2*bank)<<8))
            eg_depth=sb(q,22)*63+(self.vel*sb(q,23)>>1)+(s32(egsource*sb(q,24))>>6)
            raw=s32(raw+q[19]*32767+(s32(eg_depth*self.eg_levels[1])>>6))
            for off in [8,12]:raw=s32(raw+s32(8*sb(q,off+1)*self.source(q[off])))
            b[at+8:at+16]=b[at:at+8];ph(b,at+2,self.cutoff(raw))
            resonance=clamp((q[20]+sb(b,50))*321+8*modulation(sb(q,5),self.source(q[4])),0,31744)
            trim=32767 if q[17]==99 else q[17]*331
            output=32767 if q[18]>=99 else q[18]*331
            output=clamp(output+8*modulation(sb(q,1),self.source(q[0])),0,32767)
            ph(b,at,trim);ph(b,at+4,resonance);ph(b,at+6,output)
            if eg_depth:self.flags|=1<<(bank+5)
        if routing==3:ph(b,6,32767);ph(b,14,32767)
    def model_amp(self,values):
        p=self.osc_bytes();q=p[0x104:];b=self.amp;total=0
        for slot in range(2):
            amount=modulation(sb(q,13+4*slot),self.source(q[12+4*slot])) if sb(q,13+4*slot) else 0
            amount+=s32(sb(q,8+slot)*h(self.states[slot],8)*330)>>19
            total+=s32(values[slot]*amount)>>11
            if amount and self.states[slot][18]&4:self.flags|=8
        ph(b,2,h(b,0));mix=self.record[0x51C+self.osc]&127
        gain=u32(u32(mix*mix*q[0])*131)>>14;gain=u32(h(b,4)*gain)>>14
        volume=min(65535,u32((127*127*127)*525)>>14);volume=u32(volume*volume)>>16;gain=u32(gain*volume)>>16
        if sb(q,5):
            amount=modulation(sb(q,5),self.source(q[4]))
            if amount:
                factor=clamp(amount+4096,0,32767);gain=(u32(gain*factor)*factor*factor>>36)&0x0FFFFFFF
        gain=min(65535,gain*max(0,32768+total)>>15)
        if self.record[0x51C+self.osc]&128:gain=0
        level=self.eg_levels[2]
        if p[0x2C]&128:level=level*32767>>15
        ph(b,0,min(h(b,8),gain*level>>14));return gain
    def check(self):
        self.compare()
        for at,expected in [(0x84,self.pitch),(0xEC,self.filter),(0x150,self.amp)]:
            actual=bytes(self.a.uc.mem_read(self.voice+at,len(expected)))
            assert actual==bytes(expected),(hex(at),[(i,x,y) for i,(x,y) in enumerate(zip(actual,expected)) if x!=y])
        assert bytes(self.a.uc.mem_read(self.voice+0x13,1))[0]==self.flags,(self.osc,bytes(self.a.uc.mem_read(self.voice+0x13,1))[0],self.flags)
    def targets(self,values):
        a=self.a;v=self.voice
        self.flags=0;a.uc.mem_write(v+0x13,b'\x00')
        self.model_pitch(values);a.call(0x1FF38C,v+0x84,v,0,values[0],stack=(values[1],));self.check()
        self.model_filter([*values,self.common_lfo]);a.call(0x1FB4B0,v+0xEC,v,*values);self.check()
        gain=self.model_amp(values);assert a.call(0x1F9DD4,v+0x150,v,*values)==gain;self.check()
        return dict(lfo=list(values),fades=[h(b,8) for b in self.states],pitch_word=h(self.pitch,16),increment=w(self.pitch,24),
                    filters=[list(struct.unpack_from('<4H',self.filter,20*bank)) for bank in range(2)],amp=h(self.amp,0),amp_before_eg=gain,flags=self.flags)

def synthetic():
    p=bytearray(2140);p[0x51C:0x51E]=bytes([103,103])
    for osc in range(2):
        base=0x564+380*osc;p[base+0x104]=106
        for bank in range(2):p[base+0x90+36*bank+17:base+0x90+36*bank+21]=bytes([99,99,50,10])
        for slot in range(2):
            at=base+0x30+28*slot;p[at]=3;p[at+1]=50;p[at+13]=1
    return p

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args();f=Firmware()
    for name,lo,hi in [('lfo-target-pitch-depth',0x1FF1A0,0x1FF250),('lfo-target-pitch',0x1FF38C,0x1FF764),
                       ('lfo-target-filter',0x1FB250,0x1FB79C),('lfo-target-amplitude',0x1F9DD4,0x1FA1A0),
                       ('lfo-target-batch-order',0x1FE554,0x1FE798)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);depth_cases=[]
    for amount in range(-99,100):
        value=r.a.call(0x1FF1A0,amount);assert value==depth(amount);depth_cases.append([amount,value])
    matrix=[]
    for amount,first,second,fades,routing in itertools.product([-99,0,99],[-32768,-16384,0,16384,32767],[-32768,-16384,0,16384,32767],
                                                            [(0,0),(0,65535),(32768,32768),(65535,0),(65535,65535)],range(4)):
        record=synthetic();base=0x564;record[base+0x7E:base+0x80]=bytes([amount&255,amount&255]);record[base+0x10C:base+0x10E]=bytes([amount&255,amount&255])
        record[base+0x88]=routing
        for bank in range(2):record[base+0xA9+36*bank:base+0xAB+36*bank]=bytes([amount&255,amount&255])
        r.prepare(record,0);r.values(first,second,fades);r.m.seed=1;r.a.write(0xC1B5848C,1)
        state=r.targets([first,second]);matrix.append(dict(amount=amount,routing=routing,**state))
    # Dynamic depth remains separate from base-depth fade; use original velocity AMS.
    dynamic=[]
    for amount,signal,fade in itertools.product([-99,0,99],[-16384,0,16384],[0,32768,65535]):
        record=synthetic();base=0x564;record[base+0x70:base+0x72]=bytes([14,amount&255]);record[base+0x110:base+0x112]=bytes([14,amount&255])
        record[base+0x8A]=14;record[base+0xAF]=amount&255
        r.prepare(record,0);r.values(signal,0,(fade,65535));r.m.seed=1;r.a.write(0xC1B5848C,1)
        dynamic.append(dict(amount=amount,**r.targets([signal,0])))
    fade_sweep=[]
    for mode,index in itertools.product(['base','velocity_ams'],range(101)):
        record=synthetic();base=0x564
        if mode=='base':record[base+0x7E]=record[base+0x10C]=record[base+0xA9]=99
        else:
            record[base+0x70:base+0x72]=bytes([14,99]);record[base+0x110:base+0x112]=bytes([14,99])
            record[base+0x8A]=14;record[base+0xAF]=99
        r.prepare(record,0);fade=index*65535//100;r.values(16384,0,(fade,65535));r.m.seed=1;r.a.write(0xC1B5848C,1)
        fade_sweep.append(dict(mode=mode,fade_index=index,**r.targets([16384,0])))
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b';factory=[];representatives={}
    for program,osc in itertools.product(range(768),range(2)):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140];r.prepare(record,osc)
        for slot in range(2):representatives.setdefault(r.params(slot)[0]&63,(program,osc))
        r.initialize(1,seed=0x12345678);r.initialize(0);steps=[]
        for clock in [0,1,15,60,240,480,960,1920]:
            for slot in [1,0]:r.advance(slot,clock)
            values=[0,0]
            for slot in [1,0]:values[slot]=r.wave(slot)
            steps.append(dict(clock=clock,**r.targets(values)))
        factory.append(dict(program=chr(65+program//128)+str(program%128).zfill(3),oscillator=osc+1,source_offset=offset,
                            source_sha256=hashlib.sha256(record).hexdigest(),steps=steps))
    continuous=[]
    for kind,(program,osc) in sorted(representatives.items()):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140];r.prepare(record,osc)
        r.initialize(1,seed=0x12345678);r.initialize(0);steps=[]
        for update in range(512):
            if update==128:r.levels(8192,-16384,16384)
            if update==384:r.levels(0,0,0)
            for slot in [1,0]:r.advance(slot,20*update)
            values=[0,0]
            for slot in [1,0]:values[slot]=r.wave(slot)
            state=r.targets(values)
            if update%4==0 or update in [127,128,383,384,511]:steps.append(dict(update=update,**state))
        continuous.append(dict(selected_wave=kind,program=chr(65+program//128)+str(program%128).zfill(3),oscillator=osc+1,source_offset=offset,
                               compared_updates=512,source_sha256=hashlib.sha256(record).hexdigest(),steps=steps))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
                additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_voice_lfo.py','firmware_voice_lfo_integration.py']},
                inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],depth_cases=depth_cases,matrix=matrix,dynamic=dynamic,fade_sweep=fade_sweep,factory=factory,continuous=continuous,
                boundaries=['Original pitch, two-filter and amplitude update functions execute with native LFO wrappers, Tone Adjust and AMS getters',
                            'Independent models compare pitch/filter/amplitude control blocks, both LFO states, random state and voice update flags after each call',
                            'Private control contexts use zero portamento/bend/tracking and controlled EG values (pitch/filter 0, amp24576); envelopes themselves are not advanced',
                            'Mode3 mute path, part volume127 and disabled external controllers; sample descriptor uses synthetic mode32/length512',
                            'Factory scan includes all stored OSCs, at note60/velocity100 and eight explicit clock visits; OSC audibility is not asserted',
                            'Eighteen representative traces covering all stored wave kinds run 512 consecutive updates each; EG fields are controlled at update128/384 and per-call voice flags are cleared',
                            'No complete voice update, TG audio processing, hardware, OS or product code executes'])
    (OUT/'lfo-targets-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,depth_cases=len(depth_cases),matrix_cases=len(matrix),dynamic_cases=len(dynamic),factory_oscillators=len(factory),
                          fade_sweep_cases=len(fade_sweep),factory_updates=8*len(factory),continuous_traces=len(continuous),continuous_updates=512*len(continuous)),indent=2))
if __name__=='__main__':main()
