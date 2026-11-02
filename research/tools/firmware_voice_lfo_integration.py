#!/usr/bin/env python3
"""Run native voice LFO wrappers, parameter getters and AMS routing offline."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from firmware_voice_lfo import Model,h,sh,w,ph,pw,clamp,s16,s32,ams_value,sha,OUT,PRELOAD
from layout import PRODUCT_ROOT as ROOT

TA=0xC1439F10
def sb(b,o):return struct.unpack_from('<b',b,o)[0]
def adjust(value,amount):
    return value+((99-value)*amount*331>>15) if amount>0 else value-((value*-amount*331)>>15)
def cc_adjust(value,cc):
    delta=cc-64;amount=(delta*403>>8) if delta>0 else (delta*99>>6)
    return adjust(value,amount)
def note_adjust(note,amount):
    return min(9,note+((10-note)*-amount*331>>15)) if amount<0 else max(0,note-(amount*331*(note+1)>>15))
def velocity(value):return (129*value+1)>>2

class VoiceModel(Model):
    def __init__(self,f):
        super().__init__(f);self.gain=list(struct.unpack_from('<256H',f.data,0x4062EA))
        self.velocity_curve=list(struct.unpack_from('<128h',f.data,0x405F08))
    def factor(self,amount,source,secondary_amount=0,secondary_source=0):
        delta=secondary_amount*secondary_source>>12
        if amount==0 and delta==0:return 256
        product=clamp((amount+delta)*source*331>>15,-32768,32767)
        index=clamp(product*3>>7,-128,255)+128
        return self.gain[index] if index<=255 else self.gain[index-128]<<8
    def speed(self,b,freq,scale,sync,note,multiple,clock):
        if not sync:return clamp(s32(self.rate[freq]*scale>>8),1,27525)
        return super().speed(b,freq,scale,sync,note,multiple,clock)

class Rig:
    def __init__(self,f):
        self.a=Arm(f);self.m=VoiceModel(f)
        self.voice,self.context,self.oscruntime,self.program,self.part,self.controls,self.clock,self.donor=range(0x11010000,0x11020000,0x2000)
        self.a.write(0xC1B5720C,self.clock)
        def fail(a):raise AssertionError('Firmware assertion '+hex(a.get('LR')))
        self.a.stubs[0x2C5220]=fail
        self.ta={i:0 for i in range(1,51)};self.ta[25]=self.ta[29]=-1;self.cc={};self.common_lfo=0;self.note=60;self.vel=100
        self.a.uc.mem_write(TA,bytes(48));self.a.uc.mem_write(TA+31,b'\xff');self.a.uc.mem_write(TA+35,b'\xff')
        self.a.write(self.context+4,self.part);self.a.write(self.context+0x8C,self.controls)
        self.record=bytearray(2140);self.states=[bytearray(44),bytearray(44)];self.osc=0
        self.mixers=[0,0]
        self.prepare(bytes(2140),0)
    def set_ta(self,slot,role,value):
        selector=22+4*slot+role;self.ta[selector]=value
        self.a.uc.mem_write(TA+28+4*slot+role,bytes([value&255]))
    def inputs(self,note=60,vel=100,common=0,cc=None):
        self.note,self.vel,self.common_lfo=note,vel,common;self.cc=cc or {}
        self.a.uc.mem_write(self.voice+0x12,bytes([note,0,vel]));self.a.uc.mem_write(self.context+0x44,bytes([note,vel]))
        self.a.uc.mem_write(self.context+0x58,struct.pack('<h',common));mask=[0,0,0]
        self.a.uc.mem_write(self.controls,bytes(128))
        for number,value in self.cc.items():mask[number//32]|=1<<(number%32);self.a.uc.mem_write(self.controls+number,bytes([value]))
        self.a.write(self.context+0x34,*mask)
    def prepare(self,record,osc):
        self.record=bytearray(record);self.osc=osc;self.a.uc.mem_write(self.program,bytes(record))
        self.a.uc.mem_write(self.voice,bytes(0x240));self.a.write(self.voice+4,self.oscruntime,self.context)
        self.a.write(self.voice+0x21C,self.program);self.a.uc.mem_write(self.oscruntime+4,bytes([osc]))
        self.states=[bytearray(44),bytearray(44)];self.mixers=[0,0];self.inputs()
    def set_mixers(self,first,second):
        self.mixers=[first,second]
        self.a.uc.mem_write(self.voice+0x1F6,struct.pack('<h',first));self.a.uc.mem_write(self.voice+0x1FE,struct.pack('<h',second))
    def params(self,slot):return self.record[0x564+380*self.osc+0x30+28*slot:0x564+380*self.osc+0x30+28*(slot+1)]
    def address(self,slot):return self.voice+0x2C+44*slot
    def param_address(self,slot):return self.program+0x564+380*self.osc+0x30+28*slot
    def set_params(self,slot,params):
        offset=0x564+380*self.osc+0x30+28*slot;self.record[offset:offset+28]=params
        self.a.uc.mem_write(self.param_address(slot),bytes(params))
    def compare(self):
        for slot,b in enumerate(self.states):
            actual=bytes(self.a.uc.mem_read(self.address(slot),44))
            assert actual==bytes(b),(slot,[(i,x,y) for i,(x,y) in enumerate(zip(actual,b)) if x!=y])
        assert w(bytes(self.a.uc.mem_read(0xC1B5848C,4)),0)==self.m.seed
    def source(self,number):
        if number==0:return 0
        if number in [1,2]:return self.mixers[number-1]
        if number in [3,4,5,9,10,11,12]:return 0  # explicit zero EG/tracking fields
        if number in [6,7]:return ams_value(self.states[number-6])
        if number==8:return self.common_lfo*16387>>16
        if number==13:return (min(self.note-60,60)*8739)>>7
        if number==14:return velocity(self.vel)
        if number==15:return (self.m.velocity_curve[self.vel]+1)>>3
        if number in [16,17,21,22]:return 0  # corresponding part enable flags are zero
        cc_unipolar={19:1,20:2,23:4,25:18,30:17,31:19,32:20,33:21,34:64,35:65,36:66,37:67,38:80,39:81,40:82,41:83,42:85,43:86,44:87,45:88}
        cc_bipolar={24:16,26:17,27:19,28:20,29:21}
        if number in cc_unipolar:
            value=self.cc.get(cc_unipolar[number]);return 0 if value is None or value==255 else velocity(value)
        if number in cc_bipolar:
            value=self.cc.get(cc_bipolar[number])
            if value is None or value==255:return 0
            centered=(value-64)*2
            return centered*32 if centered<0 else velocity(centered+int(centered>0))
        if number==18:return 0  # disabled pitch controller
        raise ValueError('Unmodeled AMS source '+str(number))
    def scalar(self,slot,value,role):
        result=adjust(value,self.ta[22+4*slot+role])
        cc_number={0:76,2:78}.get(role) if slot==0 else None
        return cc_adjust(result,self.cc[cc_number]) if cc_number in self.cc else result
    def factor(self,slot,offset,secondary=None):
        p=self.params(slot);amt=sb(p,offset+1);depth=sb(p,secondary+1) if secondary is not None else 0
        src=self.source(p[offset]) if amt or depth else 0
        depth_src=self.source(p[secondary]) if depth else 0
        return self.m.factor(amt,src,depth,depth_src)
    def initialize(self,slot,clock=0,seed=None,donor=None):
        p=self.params(slot);b=self.states[slot];kind=p[0]&63
        if seed is not None:self.m.seed=seed;self.a.write(0xC1B5848C,seed)
        self.a.write(self.clock+4,clock)
        if donor is not None:self.a.uc.mem_write(self.donor,bytes(donor))
        value=self.a.call(0x1FBDE8,self.address(slot),self.voice,self.param_address(slot),self.donor if donor is not None else 0)
        pw(b,40,self.param_address(slot));effective_donor=None if p[0]&128 else donor
        self.m.initialize(b,kind,sb(p,3),self.scalar(slot,p[6],2),self.scalar(slot,p[7],1),clock,self.context,self.param_address(slot)+12,effective_donor)
        pw(b,32,self.voice)
        expected=self.m.waveform(b,kind,sb(p,4),sb(p,5),sb(p,9),self.source(p[8]) if sb(p,9) else 0)
        assert value==expected,(slot,value,expected);self.compare();return value
    def wave(self,slot):
        p=self.params(slot);value=self.a.call(0x1FBD98,self.address(slot))
        expected=self.m.waveform(self.states[slot],p[0]&63,sb(p,4),sb(p,5),sb(p,9),self.source(p[8]) if sb(p,9) else 0)
        assert value==expected,(value,expected);self.compare();return value
    def advance(self,slot,clock):
        p=self.params(slot);scale=min(0x7FFFFFFF,self.factor(slot,16,20)*self.factor(slot,24)>>8)
        frozen=self.ta[25+4*slot];frozen=bool(frozen if frozen>=0 else p[0]&64)
        note=note_adjust(p[12]&15,self.ta[22+4*slot])
        self.a.write(self.clock+4,clock);self.a.call(0x1FBE74,self.address(slot))
        self.m.advance(self.states[slot],p[0]&63,scale,frozen,self.scalar(slot,p[1],0),p[12]>>7,note,p[13],clock)
        self.compare();return scale

def params(kind=3,sync=False):
    p=bytearray(28);p[0]=kind;p[1]=50;p[6]=1;p[7]=50;p[12]=128*sync+6;p[13]=1;return p

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args();f=Firmware()
    for name,lo,hi in [('voice-lfo-input-getters',0x2746C8,0x2747DC),('voice-lfo-sync-getter',0x274CC4,0x274D44),
                       ('voice-lfo-tone-getters',0x275310,0x275688),('voice-lfo-voice-getter',0x1F8608,0x1F8784),
                       ('voice-lfo-native-source',0x273E30,0x2741EC),('voice-lfo-rate-table',0x1FFE10,0x1FFE38),
                       ('voice-lfo-call-order',0x1F8170,0x1F81D0),('voice-lfo-wave-order',0x1FE554,0x1FE58C)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);a=r.a;m=r.m
    factor_cases=[];b=r.states[0];pw(b,28,r.context);pw(b,32,r.voice);a.uc.mem_write(r.address(0),bytes(b))
    primary,secondary=r.param_address(0)+16,r.param_address(0)+20
    for amount,depth,source,depth_source in itertools.product([-99,-1,0,1,99],[-99,0,99],[-24576,-4096,0,4096,24576],[-24576,-4096,0,4096,24576]):
        a.uc.mem_write(r.voice+0x1F6,struct.pack('<h',source));a.uc.mem_write(r.voice+0x1FE,struct.pack('<h',depth_source))
        a.uc.mem_write(primary,bytes([1,amount&255]));a.uc.mem_write(secondary,bytes([2,depth&255]))
        value=a.call(0x200E20,r.address(0),primary,secondary);expected=m.factor(amount,source,depth,depth_source)
        assert value==expected,(amount,depth,source,depth_source,value,expected)
        factor_cases.append(dict(amount=amount,amount_modulation=depth,source=source,amount_source=depth_source,factor=value))
    factor_sweeps=[]
    for amount,source in itertools.product([-99,50,99],range(-4096,4097,64)):
        a.uc.mem_write(r.voice+0x1F6,struct.pack('<h',source));a.uc.mem_write(primary,bytes([1,amount&255]))
        value=a.call(0x200E20,r.address(0),primary,0);assert value==m.factor(amount,source)
        factor_sweeps.append(dict(amount=amount,source=source,factor=value))
    scalar_cases=[]
    for slot,role,value,tone,cc_value in itertools.product(range(2),range(3),[0,1,50,98,99],[-99,-50,0,50,99],[None,0,64,127]):
        r.set_ta(slot,role,tone);number=76 if role==0 else 78;r.inputs(cc={} if cc_value is None else {number:cc_value})
        actual=a.call(0x27473C,r.context,value,number if slot==0 and role!=1 else 120,22+4*slot+role,stack=(-1,))
        expected=r.scalar(slot,value,role);assert actual==expected,(slot,role,value,tone,cc_value,actual,expected)
        scalar_cases.append(dict(slot=slot+1,role=role,value=value,tone=tone,cc_value=cc_value,result=actual))
    note_cases=[]
    for slot,note,tone in itertools.product(range(2),range(10),[-99,-50,0,50,99]):
        r.set_ta(slot,0,tone);value=a.call(0x274CC4,r.context,note,22+4*slot);assert value==note_adjust(note,tone)
        note_cases.append(dict(slot=slot+1,note=note,tone=tone,result=value))
    for slot,role in itertools.product(range(2),range(3)):r.set_ta(slot,role,0)
    r.inputs();donors=[]
    for kind,slot,reset,inherit in itertools.product(range(18),range(2),range(2),range(2)):
        r.prepare(bytes(2140),slot);p=params(kind);p[0]|=reset*128;p[3]=37;r.set_params(slot,p)
        old=bytearray(44);ph(old,6,777);ph(old,36,1234);pw(old,20,99)
        r.states[slot]=old;a.uc.mem_write(r.address(slot),bytes(old))
        donor=bytearray(44);ph(donor,4,123);ph(donor,8,23456);ph(donor,10,45678);donor[18]=3;pw(donor,20,17)
        value=r.initialize(slot,clock=321,seed=0x12345678,donor=donor if inherit else None)
        donors.append(dict(wave=kind,slot=slot+1,reset=reset,donor_present=inherit,output=value,state=list(struct.unpack('<22H',r.states[slot]))))
    traces=[]
    for kind,sync,override in itertools.product(range(18),range(2),[-1,0,1]):
        r.prepare(bytes(2140),kind%2)
        for slot in range(2):
            r.set_ta(slot,3,override);p=params(kind,bool(sync));p[0]|=64 if kind%2 else 0
            p[8:10]=bytes([19,33]);p[16:18]=bytes([14,60]);p[20:22]=bytes([13,40]);p[24:26]=bytes([8,230]);r.set_params(slot,p)
        r.inputs(note=48,vel=100,common=8192,cc={1:96,76:80,78:64})
        r.initialize(1,seed=0x12345678);r.initialize(0);steps=[]
        for update in range(32):
            r.inputs(note=[48,60,84,127][update//8],vel=[1,64,100,127][update//8],common=8192,cc={1:[0,64,96,127][update//8],76:80,78:64})
            scales=[0,0]
            for slot in [1,0]:scales[slot]=r.advance(slot,update*40)
            values=[0,0]
            for slot in [1,0]:values[slot]=r.wave(slot)
            steps.append(dict(update=update,clock=update*40,scales=scales,outputs=values,phases=[h(b,10) for b in r.states],fades=[h(b,8) for b in r.states]))
        traces.append(dict(wave=kind,sync=sync,override=override,steps=steps))
    # Restore the neutral Tone Adjust default; execute real getters for factory Programs.
    for slot,role in itertools.product(range(2),range(4)):r.set_ta(slot,role,-1 if role==3 else 0)
    saturation=[]
    for freq,source,amount,secondary_enabled in itertools.product([0,50,99],[-24576,0,24576],[-99,99],range(2)):
        r.prepare(bytes(2140),0);p=params();p[1]=freq;p[6]=p[7]=0
        p[16:18]=bytes([1,amount&255]);p[20:22]=bytes([2,99 if secondary_enabled else 0]);p[24:26]=bytes([1,amount&255])
        r.set_params(0,p);r.set_mixers(source,24576);r.initialize(0,seed=1)
        scale=r.advance(0,1);saturation.append(dict(frequency=freq,source=source,amount=amount,secondary_enabled=secondary_enabled,
                                                   scale=scale,phase=h(r.states[0],10),fade=h(r.states[0],8)))
    feedback=[];r.prepare(bytes(2140),0)
    for slot in range(2):
        p=params(0 if slot==0 else 3);p[6]=p[7]=0;p[8:10]=bytes([7-slot,35]);p[16:18]=bytes([7-slot,45]);r.set_params(slot,p)
    r.initialize(1,seed=1);r.initialize(0)
    for update in range(128):
        scales=[0,0]
        for slot in [1,0]:scales[slot]=r.advance(slot,update)
        values=[0,0]
        for slot in [1,0]:values[slot]=r.wave(slot)
        feedback.append(dict(update=update,scales=scales,outputs=values,phases=[h(b,10) for b in r.states]))
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b';factory=[]
    for program,osc in itertools.product(range(768),range(2)):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140];r.prepare(record,osc)
        r.initialize(1,seed=0x12345678);r.initialize(0);steps=[]
        for clock in [0,1,15,60,240,480,960,1920]:
            scales=[0,0]
            for slot in [1,0]:scales[slot]=r.advance(slot,clock)
            for slot in [1,0]:r.wave(slot)
            steps.append(dict(clock=clock,scales=scales,outputs=[sh(b,0) for b in r.states],phases=[h(b,10) for b in r.states]))
        factory.append(dict(program=chr(65+program//128)+str(program%128).zfill(3),oscillator=osc+1,source_offset=offset,
                            source_sha256=hashlib.sha256(record).hexdigest(),steps=steps))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
                additional_helpers={'firmware_voice_lfo.py':sha(ROOT/'research/tools/firmware_voice_lfo.py')},inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],
                factor_cases=factor_cases,factor_sweeps=factor_sweeps,scalar_cases=scalar_cases,note_cases=note_cases,donor_cases=donors,traces=traces,
                saturation=saturation,feedback=feedback,factory=factory,rate_factor_table=m.gain,
                boundaries=['Original voice initializer, wave wrapper, rate wrapper, Tone Adjust getters and AMS getters execute; no computation helper is substituted',
                            'Only assertion failure entry is intercepted to fail the experiment; no assertion call is expected',
                            'Core integer model is reused; wrapper model supplies independently decoded parameters, AMS sources and Tone Adjust/CC transforms',
                            'Both LFOs are initialized, advanced and evaluated in LFO2-then-LFO1 order found in the original voice code',
                            'Factory checks use note 60, velocity 100, neutral Tone Adjust, zero EG/mixer/tracking/common-LFO states and disabled external controllers',
                            'Donor pointer inputs are controlled; selection of a stereo donor by the full voice allocator is not executed',
                            'No complete voice update, TG audio, device, OS or product code executes'])
    (OUT/'voice-lfo-integration-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,factor_cases=len(factor_cases),scalar_cases=len(scalar_cases),note_cases=len(note_cases),donor_cases=len(donors),
                          factor_sweep_cases=len(factor_sweeps),saturation_cases=len(saturation),feedback_updates=len(feedback),
                          continuous_traces=len(traces),factory_oscillators=len(factory),factory_lfo_blocks=2*len(factory)),indent=2))
if __name__=='__main__':main()
