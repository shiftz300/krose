#!/usr/bin/env python3
"""Native pitch/filter/amp envelope lifecycle and independent integer states."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_ams_mixers import Rig as MixerRig
from firmware_lfo_targets import synthetic,modulation
from firmware_voice_lfo import h,sh,w,ph,pw,s32,clamp,sha,OUT,PRELOAD
from voice_math import VoiceMath
from program_firmware import Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OFFSETS=[0xBC,0x120,0x15C]
PARAMS=[0x520,0x564+0xD8,0x564+0x118]
INIT=[0x1FF9B4,0x1FB8C4,0x1FA300]
START=[0x1FFDE8,0x1FBD70,0x1FAA50]
ADVANCE=[0x1FFC54,0x1FBBE0,0x1FA828]
RELEASE=[0x1FFD34,0x1FBAA0,0x1FA664]
REFRESH=[0x1FFDA0,0x1FBD28,0x1FA9C4]
def sb(b,o):return struct.unpack_from('<b',b,o)[0]
def q64(b,o):return struct.unpack_from('<q',b,o)[0]
def pq(b,o,v):struct.pack_into('<q',b,o,v)
def example_program(time=50,curves=(0,3,7,10),threshold=None,time_amount=0):
    record=synthetic();p=bytearray(26);p[:12]=bytes([(-20)&255,time,70,time,(-40)&255,time,time,(-10)&255,*curves])
    p[20]=9;p[21:24]=bytes([time_amount&255]*3)
    if threshold is not None:p[24]=9;p[25]=threshold&255
    record[0x520:0x53A]=p
    for osc in range(2):
        base=0x564+380*osc;p=bytearray(34);p[:13]=bytes([*curves,(-20)&255,time,70,time,(-40)&255,time,10,time,(-10)&255])
        p[17]=9;p[18:22]=bytes([time_amount&255]*4)
        if threshold is not None:p[32]=9;p[33]=threshold&255
        record[base+0xD8:base+0xFA]=p
        p=bytearray(33);p[:12]=bytes([0,time,99,time,70,time,40,time,*curves]);p[16]=9;p[17:21]=bytes([time_amount&255]*4)
        if threshold is not None:p[31]=9;p[32]=threshold&255
        record[base+0x118:base+0x139]=p;record[base+0x7D]=50;record[base+0xA6]=30;record[base+0xCA]=30
    return record

class Core:
    def __init__(self,f):self.math=VoiceMath(f)
    def segment(self,b,time,curve,amount):
        duration=self.math.eg_duration(self.math.firmware.u32(0x3FD5A4+4*time),amount)
        pq(b,16,duration);pw(b,24,duration);pw(b,32,0);pw(b,8,self.math.firmware.u32(0x405830+4*curve))
        pw(b,40,256);pw(b,12,self.math.eg_curve_coefficient(curve,duration//24))
    def target(self,b,value):
        current=sh(b,0)
        if value<=current:b[6]=(b[6]+1)&255;ph(b,2,value);ph(b,4,current-value)
        else:ph(b,2,current);ph(b,4,value-current)
    def step(self,b):
        progress=(w(b,32)+((s32(w(b,12))*((w(b,8)-(w(b,32)>>2))&0xFFFFFFFF))>>29))&0xFFFFFFFF
        if w(b,24)==(q64(b,16)&0xFFFFFFFF):pw(b,28,w(b,24))
        pw(b,32,progress);pq(b,16,q64(b,16)-24);value=min(progress,0x80000000)
        if b[6]<=9:
            if b[6]&1:value=0x80000000-value
            ph(b,0,h(b,2)+(value*h(b,4)>>31))
        return q64(b,16)<=0

class Envelope:
    def __init__(self,kind,core,b,parameters,address,source):
        self.kind,self.core,self.b,self.p,self.address,self.source=kind,core,b,parameters,address,source
    def mod(self,amount,source):return modulation(amount,self.source(source)) if amount else 0
    def trigger_fields(self):return (24,25) if self.kind==0 else (32,33) if self.kind==1 else (31,32)
    def initialize(self):
        b,p=self.b,self.p;pw(b,44,self.address);src,_=self.trigger_fields();pw(b,36,99*self.source(p[src]))
        if self.kind==0:value=330*sb(p,0)+12*self.mod(sb(p,13),p[12])+12*self.mod(sb(p,17),p[16]);value=clamp(value,-32767,32767)
        elif self.kind==1:value=clamp(330*sb(p,4)+12*self.mod(sb(p,14),p[13]),-32767,32767)
        else:
            b[49]=0;ph(b,52,0);value=clamp(330*p[0]+12*self.mod(sb(p,13),p[12]),0,32767)
        ph(b,0,value)
    def setup(self,phase):
        b,p=self.b,self.p;b[6]=[0,2,4,8][phase]
        if self.kind==0:
            time=[p[1],p[3],p[5],p[6]][phase];level=[sb(p,2),sb(p,4),0,sb(p,7)][phase]
            a=[sb(p,14),sb(p,15),0,0][phase];c=[sb(p,18),sb(p,19),0,0][phase]
            target=clamp(level*330+12*self.mod(a,p[12])+12*self.mod(c,p[16]),-32767,32767)
            amount=12*self.mod([sb(p,21),sb(p,22),sb(p,23),0][phase],p[20]);curve=p[8+phase]
        elif self.kind==1:
            time=p[5+2*phase];level=sb(p,6+2*phase);intensity=[sb(p,15),sb(p,16),0,0][phase]
            target=clamp(level*330+12*self.mod(intensity,p[13]),-32767,32767)
            amount=12*sum(self.mod(sb(p,18+5*i+phase),p[17+5*i]) for i in range(3));curve=p[phase]
        else:
            time=[p[1],p[3],p[5],p[7]][phase];level=[p[2],p[4],p[6],0][phase];intensity=[sb(p,14),sb(p,15),0,0][phase]
            target=clamp(level*330+12*self.mod(intensity,p[12]),0,32767)
            amount=(6 if phase==1 else 12)*sum(self.mod(sb(p,17+5*i+phase),p[16+5*i]) for i in range(3));curve=p[8+phase]
            if phase==3:b[48]=curve
        self.core.target(b,target);self.core.segment(b,time,curve,amount)
    def start(self,advance=True):
        if self.kind==2:
            self.b[50]=self.b[51]=0;aux=memoryview(self.b)[52:];ph(aux,0,0);aux[6]=7;pw(aux,44,32767)
        self.setup(0)
        if advance:self.core.step(self.b)
    def release(self):
        if self.kind==0 and self.b[6]>7:return
        if self.kind==2:self.b[49]=1
        self.setup(3)
    def advance(self):
        b=self.b;stage=b[6]
        if self.kind==2:
            aux=memoryview(b)[52:]
            if aux[6] in [0,9] and self.core.step(aux):aux[6]=7
        if stage>9:return
        if self.kind<2:
            if stage in [6,7]:pw(b,28,24);return
            if not self.core.step(b):return
            if stage<=1:self.setup(1)
            elif stage<=3:self.setup(2)
            else:b[6]=6
        else:
            if stage==6:pw(b,28,24);return
            if stage==7:return
            if not self.core.step(b):return
            if stage<=1:self.setup(1)
            elif stage<=3:self.setup(2)
            elif stage<=5:
                if self.p[6]:b[6]=6
                else:ph(b,0,0);b[6]=7
            else:ph(b,0,0);b[6]=7
    def refresh(self):
        b,p=self.b,self.p
        if self.kind==2 and b[49]:return
        source,threshold=self.trigger_fields()
        if not p[source]:return
        current=s32(99*self.source(p[source]));previous=s32(w(b,36));limit=sb(p,threshold)*4096
        triggered=current>=limit and previous<limit if limit>=0 else current<=limit and previous>limit
        pw(b,36,current)
        if triggered:self.initialize();self.start(advance=False)

class Rig(MixerRig):
    def __init__(self,f):self.core=Core(f);super().__init__(f)
    def prepare(self,record,osc):
        self.eg_states=[bytearray(48),bytearray(48),bytearray(100)];super().prepare(record,osc)
        self.envelopes=[];self.voice_bits=0;self.a.write(self.voice+0x240,0xFFFFFFFF)
        for kind,b in enumerate(self.eg_states):
            off=PARAMS[kind]+(380*osc if kind else 0);p=bytearray(record[off:off+(26 if kind==0 else 34 if kind==1 else 33)])
            self.envelopes.append(Envelope(kind,self.core,b,p,self.program+off,self.source));self.a.uc.mem_write(self.voice+OFFSETS[kind],bytes(b))
        self.eg_levels=[0,0,0]
    def source(self,number):
        if number in [3,4,5]:return sh(self.eg_states[number-3],0)*32770>>18
        return super().source(number)
    def compare_egs(self):
        for kind,b in enumerate(self.eg_states):
            actual=bytes(self.a.uc.mem_read(self.voice+OFFSETS[kind],len(b)))
            assert actual==bytes(b),(getattr(self,'case',None),kind,[(i,x,y) for i,(x,y) in enumerate(zip(actual,b)) if x!=y],self.envelopes[kind].p.hex())
        actual=h(bytes(self.a.uc.mem_read(self.voice+0x10,2)),0);assert actual==self.voice_bits,(actual,self.voice_bits)
    def initialize_egs(self):
        for kind,e in enumerate(self.envelopes):
            self.a.call(INIT[kind],self.voice+OFFSETS[kind],self.voice);e.initialize();self.compare_egs()
        for kind,e in enumerate(self.envelopes):
            self.a.call(START[kind],self.voice+OFFSETS[kind],self.voice);e.start();self.compare_egs()
    def advance_egs(self):
        for kind,e in enumerate(self.envelopes):
            stage=e.b[6];self.a.call(ADVANCE[kind],self.voice+OFFSETS[kind],self.voice);e.advance()
            if kind==2 and stage==7 and (not self.osc_bytes()[0x2C]&128 or self.voice_bits&1):
                e.b[6]=6;self.voice_bits|=32
            self.compare_egs()
    def refresh_egs(self):
        for kind,e in enumerate(self.envelopes):
            self.a.call(REFRESH[kind],self.voice+OFFSETS[kind],self.voice);e.refresh();self.compare_egs()
    def release_egs(self):
        for kind,e in enumerate(self.envelopes):
            self.a.call(RELEASE[kind],self.voice+OFFSETS[kind],self.voice);e.release();self.compare_egs()
    def model_amp(self,values):
        gain=super().model_amp(values);level=sh(self.eg_states[2],0)
        if self.osc_bytes()[0x2C]&128:level=level*sh(self.eg_states[2],52)>>15
        ph(self.amp,0,min(h(self.amp,8),gain*level>>14));return gain
    def frame(self,clock,release=False):
        if release:self.release_egs()
        self.advance_egs()
        for slot in [1,0]:self.advance(slot,clock)
        values=[0,0]
        for slot in [1,0]:values[slot]=self.wave(slot)
        self.refresh_egs()
        for slot in range(2):self.update_mixer(slot)
        self.eg_levels=[sh(b,0) for b in self.eg_states];state=self.targets(values);self.compare_egs()
        return dict(eg_levels=list(self.eg_levels),eg_stages=[b[6] for b in self.eg_states],eg_remaining=[q64(b,16) for b in self.eg_states],voice_status=self.voice_bits,
                    mixers=[sh(b,6) for b in self.mixer_states],**state)
    def initialize_all(self):
        self.initialize(1,seed=0x12345678);self.initialize(0)
        for slot in range(2):self.initialize_mixer(slot)
        self.initialize_egs()
    def prepare_segment(self,kind,phase):
        e=self.envelopes[kind];p=e.p;e.b[6]=[0,2,4,8][phase]
        self.a.uc.mem_write(self.voice+OFFSETS[kind]+6,bytes([e.b[6]]))
        time=([p[1],p[3],p[5],p[6]] if kind==0 else [p[5],p[7],p[9],p[11]] if kind==1 else [p[1],p[3],p[5],p[7]])[phase]
        target=([sb(p,2),sb(p,4),0,sb(p,7)] if kind==0 else [sb(p,6),sb(p,8),sb(p,10),sb(p,12)] if kind==1 else [p[2],p[4],p[6],0])[phase]
        kw={} if kind==0 else {'stack':(0,)}
        self.a.call([0x1FFA44,0x1FB928,0x1FA4B4][kind],self.voice+OFFSETS[kind],self.voice,time,target,**kw)
        e.setup(phase);self.compare_egs()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args();f=Firmware()
    for name,lo,hi in [('envelope-core',0x1FAB3C,0x1FB1C4),('envelope-amplitude',0x1FA300,0x1FAA98),
                       ('envelope-filter',0x1FB8C4,0x1FBD98),('envelope-pitch',0x1FF9B4,0x1FFDE8)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);core_cases=[];cell=0x11050000
    for curve,time,current,target,amount in itertools.product(range(11),[0,1,7,50,99],[-32767,0,32767],[-32767,0,32767],[-20000,0,20000]):
        b=bytearray(48);ph(b,0,current);r.a.uc.mem_write(cell,bytes(b));r.a.call(0x1FAF3C,cell,target);r.core.target(b,target)
        r.a.call(0x1FB0AC,cell,time,amount,curve);r.core.segment(b,time,curve,amount)
        assert bytes(r.a.uc.mem_read(cell,48))==bytes(b)
        for step in range(10):
            result=r.a.call(0x1FAC24,cell,0,0);done=r.core.step(b);assert result==int(done)
            assert bytes(r.a.uc.mem_read(cell,48))==bytes(b),(curve,time,current,target,amount,step)
        core_cases.append(dict(curve=curve,time=time,current=current,target=target,modulation=amount,final_level=sh(b,0),remaining=q64(b,16)))
    duration_cases=[]
    for amount,source,kind,phase in itertools.product([-99,0,99],[-4096,0,4096],range(3),range(4)):
        r.prepare(example_program(time_amount=amount),0);r.set_probe(source);r.initialize_all();r.prepare_segment(kind,phase)
        duration_cases.append(dict(amount=amount,source=source,kind=kind,phase=phase,duration=w(r.eg_states[kind],24)))
    lifecycle=[]
    for time,curves in itertools.product([0,7,50,99],[(0,0,0,0),(0,3,7,10),(10,7,3,0)]):
        r.prepare(example_program(time,curves),0);r.initialize_all();steps=[]
        for update in range(256):steps.append(dict(update=update,release=update==128,**r.frame(20*update,release=update==128)))
        lifecycle.append(dict(time=time,curves=curves,steps=steps))
    retriggers=[]
    for threshold in [-99,-1,0,1,99]:
        record=example_program(threshold=threshold);r.prepare(record,0);boundary=threshold*4096
        floor=boundary//99;ceil=-(-boundary//99);r.set_probe(floor-1 if threshold>=0 else ceil+1);r.initialize_all();steps=[]
        for update in range(16):
            source=[floor-1,floor,ceil,ceil+1,ceil, floor,floor-1,ceil+1][update%8]
            if update==8:r.release_egs()
            r.set_probe(source);r.advance_egs();before=[b[6] for b in r.eg_states];progress=[w(b,32) for b in r.eg_states];r.refresh_egs()
            steps.append(dict(update=update,source=source,released=update>=8,before=before,stages=[b[6] for b in r.eg_states],
                              levels=[sh(b,0) for b in r.eg_states],previous=[s32(w(b,36)) for b in r.eg_states],
                              reset=[w(b,32)==0 and progress[i]!=0 for i,b in enumerate(r.eg_states)]))
        retriggers.append(dict(threshold=threshold,steps=steps))
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory=[];parameter_locations=set()
    for program,osc in itertools.product(range(768),range(2)):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140];r.prepare(record,osc);r.initialize_all();steps=[]
        for kind in range(3):parameter_locations.add(offset+PARAMS[kind]+(380*osc if kind else 0))
        for update in range(8):
            r.case=(program,osc,update,[b[6] for b in r.eg_states]);steps.append(dict(update=update,**r.frame(update*20,release=update==4)))
        factory.append(dict(program=chr(65+program//128)+str(program%128).zfill(3),oscillator=osc+1,source_offset=offset,
                            source_sha256=hashlib.sha256(record).hexdigest(),parameters=[list(e.p) for e in r.envelopes],steps=steps))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
                additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['voice_math.py','firmware_voice_lfo.py','firmware_voice_lfo_integration.py','firmware_lfo_targets.py','firmware_ams_mixers.py']},
                inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],core_cases=core_cases,duration_cases=duration_cases,lifecycle=lifecycle,retriggers=retriggers,factory=factory,
                factory_envelope_contexts=3*len(factory),factory_parameter_locations=len(parameter_locations),
                boundaries=['Original pitch/filter/amp envelope initialization, attack, advance, release and retrigger refresh execute against independent packed state models',
                            'Native LFO, both native mixers and all three native target functions are connected in observed single-voice ordering',
                            'Tone Adjust neutral and external MIDI controllers disabled; half-pedal and auxiliary envelope requests remain separate work',
                            'Synthetic sample/pitch/control contexts retained from previous target fixture; no actual sample-region assembly, OS, device or TG audio executes'])
    (OUT/'envelopes-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,core_segments=len(core_cases),core_steps=10*len(core_cases),duration_cases=len(duration_cases),lifecycle_traces=len(lifecycle),
                          lifecycle_updates=256*len(lifecycle),retrigger_traces=len(retriggers),factory_oscillators=len(factory),factory_envelope_contexts=3*len(factory),
                          factory_parameter_locations=len(parameter_locations),factory_updates=8*len(factory)),indent=2))
if __name__=='__main__':main()
