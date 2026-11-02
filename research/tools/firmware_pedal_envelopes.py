#!/usr/bin/env python3
"""Native CC64 release scaling and pedal auxiliary-envelope request flow."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_envelopes import Core as BaseCore,Envelope as BaseEnvelope,Rig as BaseRig,OFFSETS,example_program,q64,pq
from firmware_lfo_targets import div
from firmware_voice_lfo import h,sh,w,ph,pw,s32,sha,OUT,PRELOAD
from firmware_inspect import inspect
from program_firmware import Firmware,FW_SHA
from layout import PRODUCT_ROOT as ROOT

class Core(BaseCore):
    def __init__(self,f):
        super().__init__(f);self.normal=list(struct.unpack_from('<128h',f.data,0x405530));self.special=list(struct.unpack_from('<128I',f.data,0x405630))
    def step(self,b,pedal_scale=None,curve=0):
        progress=(w(b,32)+((s32(w(b,12))*((w(b,8)-(w(b,32)>>2))&0xFFFFFFFF))>>29))&0xFFFFFFFF
        if w(b,24)==(q64(b,16)&0xFFFFFFFF):pw(b,28,w(b,24))
        pw(b,32,progress)
        if pedal_scale is not None and pedal_scale!=w(b,40):
            scaled=min(0x7FFFFFFF,w(b,24)*pedal_scale>>8)
            pq(b,16,div(q64(b,16)*pedal_scale,w(b,40)));pw(b,40,pedal_scale)
            pw(b,12,self.math.eg_curve_coefficient(curve,scaled//24))
        pq(b,16,q64(b,16)-24);value=min(progress,0x80000000)
        if b[6]<=9:
            if b[6]&1:value=0x80000000-value
            ph(b,0,h(b,2)+(value*h(b,4)>>31))
        return q64(b,16)<=0

class Envelope(BaseEnvelope):
    def __init__(self,*args,owner):super().__init__(*args);self.owner=owner
    def start(self,advance=True):
        if self.kind!=2:return super().start(advance)
        self.b[50]=self.b[51]=0;aux=memoryview(self.b)[52:];ph(aux,0,32767 if self.owner.pedal_enabled and self.owner.pedal_value>80 else 0)
        aux[6]=7;pw(aux,44,32767);self.setup(0)
        if advance:self.core.step(self.b)
    def aux_on(self):
        aux=memoryview(self.b)[52:];target=s32(w(aux,44)*16055)>>15;aux[6]=0
        self.core.target(aux,target);self.core.segment(aux,52,0,0);pw(aux,44,target)
    def aux_off(self):
        aux=memoryview(self.b)[52:];aux[6]=8;self.core.target(aux,0);self.core.segment(aux,62,10,0)
    def refresh(self):
        if self.kind!=2:return super().refresh()
        b,p=self.b,self.p;source,threshold=self.trigger_fields()
        if not b[49] and p[source]:
            current=s32(99*self.source(p[source]));previous=s32(w(b,36));limit=struct.unpack_from('<b',p,threshold)[0]*4096
            triggered=current>=limit and previous<limit if limit>=0 else current<=limit and previous>limit
            pw(b,36,current)
            if triggered:self.initialize();self.setup(0)
        if b[50]:self.aux_on();b[50]=0
        if b[51]:self.aux_off();b[51]=0
    def advance(self):
        if self.kind!=2:return super().advance()
        b=self.b;stage=b[6];aux=memoryview(b)[52:]
        if aux[6] in [0,9] and self.core.step(aux):aux[6]=7
        if stage>9:return
        if stage==6:pw(b,28,24);return
        if stage==7:return
        scale=self.owner.release_scale() if stage==9 and self.owner.record[0x509]&64 and self.owner.pedal_enabled else None
        if not self.core.step(b,pedal_scale=scale,curve=b[48]):return
        if stage<=1:self.setup(1)
        elif stage<=3:self.setup(2)
        elif stage<=5:
            if self.p[6]:b[6]=6
            else:ph(b,0,0);b[6]=7
        else:ph(b,0,0);b[6]=7

class Rig(BaseRig):
    def __init__(self,f):self.pedal_core=Core(f);super().__init__(f)
    def prepare(self,record,osc):
        self.pedal_value=0;self.pedal_enabled=False;self.pedal_special=False;super().prepare(record,osc);self.core=self.pedal_core
        self.envelopes=[Envelope(e.kind,self.core,e.b,e.p,e.address,self.source,owner=self) for e in self.envelopes]
        self.a.write(self.oscruntime+8,self.program+0x564+380*osc)
        self.node=0x11040000;head=self.oscruntime+0x490
        self.a.write(head,self.node,self.node,0);self.a.write(self.node,head,head,self.voice)
    def pedal(self,value,enabled=True,special=False):
        self.pedal_value=value;self.pedal_enabled=enabled;self.pedal_special=special
        self.a.uc.mem_write(self.controls+64,bytes([value]));self.a.uc.mem_write(self.part+0x19,bytes([4 if enabled else 0]))
        self.a.uc.mem_write(self.oscruntime+0x4A3,bytes([int(special)]));self.a.write(self.context+0x3C,int(enabled))
        if enabled:self.cc[64]=value
        else:self.cc.pop(64,None)
    def release_scale(self):
        value=self.pedal_value
        if self.pedal_special:return self.core.special[value]
        if self.envelopes[2].p[6]:value=min(value,64)
        return self.core.normal[value]
    def pedal_request(self,on):
        self.a.call(0x1F5E44 if on else 0x1F5E98,self.oscruntime)
        if self.osc_bytes()[0x2C]&128:
            if on:
                if not self.voice_bits&1:self.eg_states[2][50]=1
            else:self.eg_states[2][51]=1  # release permission stays zero in this fixture
        self.compare_egs()
    def release_egs(self):
        self.voice_bits|=1;self.a.uc.mem_write(self.voice+0x10,struct.pack('<H',self.voice_bits));super().release_egs()
    def frame(self,*args,**kwargs):
        result=super().frame(*args,**kwargs);aux=memoryview(self.eg_states[2])[52:]
        return dict(cc64=self.pedal_value,aux_level=sh(aux,0),aux_stage=aux[6],aux_target=w(aux,44),release_scale=w(self.eg_states[2],40),**result)

def program(sustain=40,auxiliary=True,release_scaling=True):
    record=example_program(time=50);record[0x509]|=64 if release_scaling else 0
    for osc in range(2):
        base=0x564+380*osc;record[base+0x11E]=sustain
        if auxiliary:record[base+0x2C]|=128
    return record

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args();f=Firmware()
    for name,lo,hi in [('pedal-envelope-core',0x1FAC24,0x1FAE60),('pedal-envelope-auxiliary',0x1FA380,0x1FA4B4),
                       ('pedal-envelope-requests',0x1F5E44,0x1F5F4C),('pedal-envelope-consumer',0x1FA9C4,0x1FAA98)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);cell=0x11050000;core_cases=[]
    for special,sustain,value,curve,time in itertools.product(range(2),[0,40],range(128),[0,3,10],[0,50,99]):
        r.prepare(program(sustain=sustain),0);r.pedal(value,special=bool(special));b=bytearray(48);ph(b,0,32767);b[6]=8
        r.a.uc.mem_write(cell,bytes(b));r.a.call(0x1FAF3C,cell,0);r.core.target(b,0)
        r.a.call(0x1FB0AC,cell,time,0,curve);r.core.segment(b,time,curve,0)
        result=r.a.call(0x1FAC24,cell,r.voice,curve);done=r.core.step(b,r.release_scale(),curve)
        actual=bytes(r.a.uc.mem_read(cell,48));assert actual==bytes(b),(special,sustain,value,curve,time,actual.hex(),bytes(b).hex())
        assert result==int(done)
        core_cases.append(dict(special=special,sustain=sustain,cc64=value,curve=curve,time=time,scale=w(b,40),remaining=q64(b,16),coefficient=w(b,12)))
    initialization=[]
    for enabled,value in itertools.product(range(2),range(128)):
        r.prepare(program(),0);r.pedal(value,enabled=bool(enabled));r.initialize_all()
        initialization.append(dict(enabled=enabled,cc64=value,aux_level=sh(r.eg_states[2],52)))
    transitions=[]
    for special,sustain,scaling,enabled in itertools.product(range(2),[0,40],range(2),range(2)):
        r.prepare(program(sustain,release_scaling=bool(scaling)),0);r.pedal(0,enabled=bool(enabled),special=bool(special));r.initialize_all();steps=[]
        schedule=[0,63,64,65,80,81,100,127,80,64,32,0]
        for update in range(192):
            r.pedal(schedule[min(len(schedule)-1,update//16)],enabled=bool(enabled),special=bool(special))
            state=r.frame(update*20,release=update==16);steps.append(dict(update=update,**state))
        transitions.append(dict(special=special,sustain=sustain,scaling=scaling,enabled=enabled,steps=steps))
    requests=[]
    for enabled,initial_cc,special in itertools.product(range(2),[0,80,81,127],range(2)):
        r.prepare(program(auxiliary=bool(enabled)),0);r.pedal(initial_cc,special=bool(special));r.initialize_all();steps=[]
        for update in range(320):
            if update in [0,128]:r.pedal(127,special=bool(special));r.pedal_request(True)
            if update in [64,192]:r.pedal(0,special=bool(special));r.pedal_request(False)
            steps.append(dict(update=update,**r.frame(update*20)))
        requests.append(dict(auxiliary_enabled=enabled,initial_cc=initial_cc,special=special,steps=steps))
    both=[]
    for first,second in itertools.product(range(2),range(2)):
        r.prepare(program(),0);r.initialize_all();r.pedal_request(True) if first else None;r.pedal_request(False) if second else None
        r.refresh_egs();both.append(dict(on=first,off=second,aux_level=sh(r.eg_states[2],52),aux_stage=r.eg_states[2][58],aux_target=w(r.eg_states[2],96)))
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    release_flags=[];auxiliary_flags=[]
    for index in range(768):
        offset=0x1EF220+2140*index;record=raw[offset:offset+2140];name=chr(65+index//128)+str(index%128).zfill(3)
        if record[0x509]&64:release_flags.append(name)
        for osc in range(2):
            if record[0x564+380*osc+0x2C]&128:auxiliary_flags.append(dict(index=index,program=name,oscillator=osc+1,name=record[:24].decode('ascii').rstrip(),source_offset=offset))
    factory=[]
    for item,special in itertools.product(auxiliary_flags,range(2)):
        offset=item['source_offset'];record=raw[offset:offset+2140];r.prepare(record,item['oscillator']-1);r.pedal(0,special=bool(special));r.initialize_all();steps=[]
        for update in range(320):
            if update==64:r.pedal(127,special=bool(special));r.pedal_request(True)
            if update==192:r.pedal(0,special=bool(special));r.pedal_request(False)
            steps.append(dict(update=update,**r.frame(update*20,release=update==128)))
        factory.append(dict(**item,special=special,source_sha256=hashlib.sha256(record).hexdigest(),steps=steps))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
                additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['voice_math.py','firmware_voice_lfo.py','firmware_voice_lfo_integration.py','firmware_lfo_targets.py','firmware_ams_mixers.py','firmware_envelopes.py']},
                inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],
                core_cases=core_cases,initialization=initialization,transitions=transitions,requests=requests,both_requests=both,
                factory_usage=dict(release_scaling_programs=release_flags,auxiliary_oscillators=auxiliary_flags),factory=factory,
                normal_scale_table=r.core.normal,special_scale_table=r.core.special,
                boundaries=['Original CC64 release scaling, auxiliary initialization, oscillator pedal request writers and envelope consumers execute in private memory',
                            'All 128 CC64 values, both curve-table selectors and sustain cap branches compare full native envelope state with independent integer models',
                            'Controller state and one-voice oscillator list are synthetic; manager release/classification paths and physical MIDI input are not executed',
                            'Controlled fixtures explicitly enable branch combinations; separate factory traces use all16 stored auxiliary-flag OSCs with controlled runtime table selector and release permission0',
                            'Factory flag counts describe stored fields only; oscillator activation, sample selection and audible contribution are not asserted',
                            'LFO/mixers/targets use previous independent models; no OS, MMIO, hardware, TG audio or product code executes'])
    (OUT/'pedal-envelopes-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,core_cases=len(core_cases),initialization_cases=len(initialization),transition_traces=len(transitions),
                          transition_updates=192*len(transitions),request_traces=len(requests),request_updates=320*len(requests),both_request_cases=len(both),
                          factory_release_flags=len(release_flags),factory_auxiliary_flags=len(auxiliary_flags),factory_traces=len(factory),factory_updates=320*len(factory)),indent=2))
if __name__=='__main__':main()
