#!/usr/bin/env python3
"""All seven native AMS mixer modes, state transitions and LFO target flow."""
import argparse,collections,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_lfo_targets import Rig as TargetRig,synthetic,modulation
from firmware_voice_lfo import h,sh,ph,pw,s32,clamp,sha,OUT,PRELOAD
from firmware_inspect import inspect
from program_firmware import Firmware,FW_SHA
from layout import PRODUCT_ROOT as ROOT
NAMES=['A+B','Amt A x B','Offset','Smoothing','Shape','Quantize','Gate Control']
def sb(b,o):return struct.unpack_from('<b',b,o)[0]
def scale(amount,value):return s32(amount*value*331)>>15

class MixModel:
    def __init__(self,f):
        self.smoothing=list(struct.unpack_from('<100I',f.data,0x407968))
        self.quantize=list(struct.unpack_from('<33I',f.data,0x407AF8))
        assert all(self.quantize[n]==4096//n for n in range(2,33))
    def update(self,b,p,source,initial=False):
        kind=p[0]&7;value=0
        if kind==0:value=scale(sb(p,2),source(p[1]))+scale(sb(p,4),source(p[3]))
        elif kind==1:
            amount=sb(p,2)+(s32(99*scale(sb(p,4),source(p[3])))>>12)
            value=scale(amount,source(p[1]))
        elif kind==2:value=scale(sh(p,6),source(p[1]))+(s32(sh(p,8)*165)>>2)
        elif kind==3:
            target=scale(99,source(p[1]));old=sh(b,6);coefficient=self.smoothing[p[10] if target>=old else p[11]]
            value=old+(s32(coefficient*(target-old))>>16)
        elif kind==4:
            x=source(p[1]);amount=sb(p,12)*331
            if p[13]:value=x+(s32((4096-(s32(x*x)>>12))*amount)>>16)
            else:
                v=2*abs(x)-4096;v+=s32((4096-(s32(v*v)>>12))*amount)>>16
                value=((v+4096)>>1)*(1 if x>=0 else -1)
        elif kind==5:
            x=source(p[1]);steps=p[5];index=s32(abs(x)*(steps+1))>>12
            value=(s32(index*self.quantize[steps]) if index<steps else 4096)*(1 if x>=0 else -1)
        elif kind==6:
            flags=p[16];gate=int(source(p[17])>=modulation(sb(p,18),4096)) if p[17] else 0
            if initial:b[4]=gate
            elif flags&1:gate=b[4]
            if p[17]:
                if gate:value=scale(99,source(p[3])) if flags&4 else modulation(sb(p,20),4096)
                else:value=scale(99,source(p[1])) if flags&2 else modulation(sb(p,19),4096)
        ph(b,6,clamp(value,-24576,24576))
    def initialize(self,b,address,p,source):
        pw(b,0,address);ph(b,6,scale(99,source(p[1])) if p[0]&7==3 else 0)
        self.update(b,p,source,True)

class Rig(TargetRig):
    def __init__(self,f):self.mix_model=MixModel(f);super().__init__(f)
    def prepare(self,record,osc):
        self.mixer_states=[bytearray(8),bytearray(8)];self.probes=[0,0,0]
        super().prepare(record,osc)
    def source(self,number):
        if number in [1,2]:return sh(self.mixer_states[number-1],6)
        if number in [9,10,11]:return self.probes[number-9]
        return super().source(number)
    def set_probe(self,first,second=0,gate=0):
        self.probes=[first,second,gate]
        for off,value in zip([0x204,0x206,0x212],self.probes):self.a.uc.mem_write(self.voice+off,struct.pack('<h',value))
    def mixer_address(self,slot):return self.voice+0x1F0+8*slot
    def mixer_parameter_address(self,slot):return self.program+0x564+380*self.osc+0x14C+24*slot
    def mixer_params(self,slot):
        off=0x564+380*self.osc+0x14C+24*slot;return self.record[off:off+24]
    def set_mixer_params(self,slot,p):
        off=0x564+380*self.osc+0x14C+24*slot;self.record[off:off+24]=p
        self.a.uc.mem_write(self.mixer_parameter_address(slot),bytes(p))
    def compare_mixers(self):
        for slot,b in enumerate(self.mixer_states):
            actual=bytes(self.a.uc.mem_read(self.mixer_address(slot),8));assert actual==bytes(b),(slot,actual.hex(),bytes(b).hex())
    def initialize_mixer(self,slot):
        self.a.call(0x201434,self.mixer_address(slot),self.voice,self.mixer_parameter_address(slot))
        self.mix_model.initialize(self.mixer_states[slot],self.mixer_parameter_address(slot),self.mixer_params(slot),self.source);self.compare_mixers()
    def update_mixer(self,slot,initial=False):
        self.a.call(0x20119C,self.mixer_address(slot),self.voice,int(initial))
        self.mix_model.update(self.mixer_states[slot],self.mixer_params(slot),self.source,initial);self.compare_mixers()
        return sh(self.mixer_states[slot],6)

def parameters(kind):
    p=bytearray(24);p[0]=kind;p[1]=9;p[2]=99;p[3]=10;p[4]=99;p[5]=12;p[10]=80;p[11]=50
    ph(p,6,99);ph(p,8,0);p[17]=11;p[19]=(-37)&255;p[20]=57;return p

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args();f=Firmware()
    for name,lo,hi in [('ams-mixers-update',0x201120,0x201490),('ams-mixers-initialize-order',0x1F73F8,0x1F7448),
                       ('ams-mixers-refresh-order',0x1FE554,0x1FE6B4)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);arithmetic=[]
    for kind,a,b,amount_a,amount_b in itertools.product(range(3),[-24576,-4096,0,4096,24576],[-24576,-4096,0,4096,24576],[-99,0,99],[-99,0,99]):
        r.prepare(synthetic(),0);p=parameters(kind);p[2]=amount_a&255;p[4]=amount_b&255;ph(p,6,2*amount_a);ph(p,8,2*amount_b)
        r.set_mixer_params(0,p);r.set_probe(a,b);r.initialize_mixer(0)
        arithmetic.append(dict(mode=kind,a=a,b=b,amount_a=amount_a,amount_b=amount_b,output=sh(r.mixer_states[0],6)))
    offset_edges=[]
    for amount,offset,value in itertools.product([-199,-198,-1,0,1,198,199],[-199,0,199],[-24576,-4096,0,4096,24576]):
        r.prepare(synthetic(),0);p=parameters(2);ph(p,6,amount);ph(p,8,offset);r.set_mixer_params(0,p);r.set_probe(value);r.initialize_mixer(0)
        offset_edges.append(dict(amount=amount,offset=offset,input=value,output=sh(r.mixer_states[0],6)))
    smoothing=[]
    for up in range(100):
        r.prepare(synthetic(),0);p=parameters(3);p[10]=up;p[11]=99-up;r.set_mixer_params(0,p);r.set_probe(0);r.initialize_mixer(0);steps=[]
        for update in range(192):
            value=4096 if update<64 else -4096 if update<128 else 0;r.set_probe(value);result=r.update_mixer(0)
            steps.append(dict(update=update,input=value,output=result))
        smoothing.append(dict(up=up,down=99-up,steps=steps))
    extreme=[]
    for rate,old,new in itertools.product([0,50,99],[-24576,-4096,0,4096,24576],[-24576,-4096,0,4096,24576]):
        r.prepare(synthetic(),0);p=parameters(3);p[10]=p[11]=rate;r.set_mixer_params(0,p);r.set_probe(old);r.initialize_mixer(0)
        r.set_probe(new);result=r.update_mixer(0);extreme.append(dict(rate=rate,old=old,new=new,output=result))
    shapes=[]
    for asymmetric,amount,value in itertools.product(range(2),[-99,0,99],range(-4096,4097,64)):
        r.prepare(synthetic(),0);p=parameters(4);p[12]=amount&255;p[13]=asymmetric;r.set_mixer_params(0,p);r.set_probe(value);r.initialize_mixer(0)
        shapes.append(dict(asymmetric=asymmetric,amount=amount,input=value,output=sh(r.mixer_states[0],6)))
    quantized=[]
    for count in range(2,33):
        points={-24576,-4096,-1,0,1,4096,24576}
        for index in range(count+2):
            edge=(4096*index+count)//(count+1)
            for delta in [-1,0,1]:points.add(edge+delta);points.add(-edge+delta)
        r.prepare(synthetic(),0);p=parameters(5);p[5]=count;r.set_mixer_params(0,p);r.set_probe(0);r.initialize_mixer(0)
        for value in sorted(points):
            r.set_probe(value);result=r.update_mixer(0);quantized.append(dict(count=count,input=value,output=result))
    gates=[]
    for flags,threshold,control,start_high in itertools.product(range(8),[-99,0,99],[0,11],range(2)):
        r.prepare(synthetic(),0);p=parameters(6);p[16]=flags;p[17]=control;p[18]=threshold&255;r.set_mixer_params(0,p)
        boundary=modulation(threshold,4096);r.set_probe(-2048,3072,boundary+(1 if start_high else -1));r.initialize_mixer(0);steps=[]
        for update in range(12):
            gate=boundary+[-1,0,1][update%3];r.set_probe(-2048 if update<6 else 2048,3072 if update<6 else -3072,gate)
            result=r.update_mixer(0,initial=update==6)
            steps.append(dict(update=update,gate_input=gate,reinitialize=update==6,latched=r.mixer_states[0][4],output=result))
        gates.append(dict(flags=flags,threshold=threshold,control_source=control,start_high=start_high,steps=steps))
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b';factory=[];counts=collections.Counter();representatives={}
    for program,osc in itertools.product(range(768),range(2)):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140];r.prepare(record,osc)
        r.initialize(1,seed=0x12345678);r.initialize(0)
        for slot in range(2):
            kind=r.mixer_params(slot)[0]&7;assert kind<=6;counts[kind]+=1;representatives.setdefault(kind,(program,osc));r.initialize_mixer(slot)
        steps=[]
        for clock in [0,1,15,60,240,480,960,1920]:
            for slot in [1,0]:r.advance(slot,clock)
            values=[0,0]
            for slot in [1,0]:values[slot]=r.wave(slot)
            for slot in range(2):r.update_mixer(slot)
            state=r.targets(values);steps.append(dict(clock=clock,mixers=[sh(b,6) for b in r.mixer_states],**state))
        factory.append(dict(program=chr(65+program//128)+str(program%128).zfill(3),oscillator=osc+1,source_offset=offset,
                            source_sha256=hashlib.sha256(record).hexdigest(),parameters=[list(r.mixer_params(i)) for i in range(2)],steps=steps))
    continuous=[]
    for kind,(program,osc) in sorted(representatives.items()):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140];r.prepare(record,osc);r.initialize(1,seed=0x12345678);r.initialize(0)
        for slot in range(2):r.initialize_mixer(slot)
        steps=[]
        for update in range(256):
            r.inputs(note=[36,60,84,108][update//64],vel=[32,64,100,127][update//64])
            for slot in [1,0]:r.advance(slot,update*20)
            values=[0,0]
            for slot in [1,0]:values[slot]=r.wave(slot)
            for slot in range(2):r.update_mixer(slot)
            state=r.targets(values)
            if update%4==0 or update in [63,64,127,128,191,192,255]:steps.append(dict(update=update,mixers=[sh(b,6) for b in r.mixer_states],**state))
        continuous.append(dict(selected_mode=kind,program=chr(65+program//128)+str(program%128).zfill(3),oscillator=osc+1,compared_updates=256,steps=steps))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
                additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_voice_lfo.py','firmware_voice_lfo_integration.py','firmware_lfo_targets.py']},
                inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],names=NAMES,arithmetic=arithmetic,offset_edges=offset_edges,smoothing=smoothing,smoothing_extreme=extreme,
                shapes=shapes,quantized=quantized,gates=gates,factory=factory,factory_mode_counts=dict(counts),continuous=continuous,
                smoothing_coefficients=r.mix_model.smoothing,quantize_coefficients=r.mix_model.quantize,
                boundaries=['All seven original mixer branches, initializer and native voice AMS getter execute; full 8-byte states compare with an independent integer model',
                            'Isolated probes place known AMS values in native tracking fields read through original source IDs9/10/11; source functions are not substituted',
                            'Factory LFO initialization/wave order is LFO2 then LFO1; mixer initialization/update is Mixer1 then Mixer2, followed by native targets',
                            'Factory flow reuses controlled EG, synthetic sample/pitch contexts and neutral controllers from the LFO-target fixture; complete envelope scheduling remains pending',
                            'Seven representative traces change note/velocity directly in private control state; no physical keyboard or MIDI task executes',
                            'Only firmware assertion failure is trapped; no algorithm getter or calculation is replaced; no device/OS/TG audio/product code executes'])
    (OUT/'ams-mixers-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,arithmetic_cases=len(arithmetic),offset_edge_cases=len(offset_edges),smoothing_traces=len(smoothing),smoothing_extreme_cases=len(extreme),shape_cases=len(shapes),
                          quantize_cases=len(quantized),gate_traces=len(gates),factory_mixers=sum(counts.values()),factory_mode_counts=dict(counts),
                          factory_updates=8*len(factory),continuous_updates=256*len(continuous)),indent=2))
if __name__=='__main__':main()
