#!/usr/bin/env python3
"""Recover original Hall controls, four decay tables and delay intervals."""
import argparse,contextlib,hashlib,io,itertools,json,math,struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from firmware_chorus import mix,shelf_table,shelf_decode,shelf_reference
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
PRELOAD=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
Q23=0x7FFFFF
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def u32(v):return v&0xFFFFFFFF
def trunc(v,d):return (abs(v)//d)*(1 if v>=0 else -1)

class HallRig:
    def __init__(self,f):
        self.f=f;self.a=Arm(f);self.ctx,self.request=0x11008000,0x11009000;self.slot=0;self.params={};self.queries=[]
        self.definition=f.effect(105);self.initial=[f.u32(self.definition['constants_offset']+4*i) for i in range(61)]
        self.intervals=[(22,5),(23,8),(24,11),(25,14)]
        self.lengths=[self.initial[end]-self.initial[start] for start,end in self.intervals]
        self.time_pointers=[f.u32(0x4842C4+4*i)-0xC0000000 for i in range(4)]
        self.time_tables=[list(struct.unpack_from('<100h',f.data,p)) for p in self.time_pointers]
        self.damp_weights=[f.u32(0x35DF00+4*i) for i in range(4)]
        assert self.damp_weights==[v//2 for v in self.lengths]
        def getter(a):
            assert a.get('R0')==777 and a.get('R2')==a.get('R3')==0
            i=a.get('R1');self.queries.append(i);return self.params[i]
        self.a.stubs[0xD5AC4]=getter
    def words(self):return list(struct.unpack('<80I',self.a.uc.mem_read(0xC0FE9DC8+320*self.slot,320)))
    def reset(self,load=False,slot=0):
        self.slot=slot;self.a.uc.mem_write(self.ctx,b'\x01\x01'+bytes(30));self.a.uc.mem_write(0xC0FE9DC8,bytes(2560));self.queries.clear()
        if load:
            self.a.call(0x5A51C,self.ctx,slot,2,0xC0000000+self.definition['definition_offset'])
            assert self.words()==self.initial+[0]*19
    def callback(self,index,value,enabled=1):
        self.a.uc.mem_write(self.request,bytes(40));self.a.write(self.request,777,0,value,self.slot,self.ctx,enabled)
        self.a.call(self.definition['parameters'][index]['descriptor']['callback'],20,self.request)
    def time_words(self,raw):return [u32(self.time_tables[i][raw-1]*256*(1 if i%2==0 else -1)) for i in range(4)]
    def damp_words(self,raw):
        scale=raw*Q23//100;return [scale*v//self.damp_weights[0] for v in self.damp_weights]
    def scalar(self,index,value,expected,enabled=1):
        self.reset();self.callback(index,value,enabled);want=[0]*80
        for k,v in expected.items():want[k]=u32(v)
        assert self.words()==want,(index,value,[(i,x,y) for i,(x,y) in enumerate(zip(self.words(),want)) if x!=y])
        return dict(parameter=index,value=value,enabled=enabled,writes={str(k):u32(v) for k,v in expected.items()})
    def static_expected(self,p,baseline):
        w=baseline.copy();w[0]=self.f.u32(0x38CCE8+4*self.slot)+1;w[26]=p[4]*Q23//200
        w[31:35]=self.time_words(p[0]);w[35:39]=self.damp_words(p[1]);w[40],w[39]=map(u32,mix(p[7]));w[42]=p[3]*Q23//100
        w[43:46]=shelf_table(self.f,0,p[5],p[10]);w[46:49]=shelf_table(self.f,1,p[6],p[11])
        return w

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('hall-parameters-and-init',0x7ADA4,0x7B278),('hall-shared-parameters',0x73A2C,0x73BD4),('hall-time-damping',0x9D014,0x9D1C0),
                       ('hall-constant-relocation',0x9B510,0x9B8B8)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    r=HallRig(f);a=r.a;scalar=[];decays=[]
    assert r.lengths==[5450,5278,4846,4798]
    for raw in range(1,101):
        scalar.append(r.scalar(0,raw,{31+i:v for i,v in enumerate(r.time_words(raw))}))
        for i,length in enumerate(r.lengths):
            reference=32767*10**(-30*length/(48000*raw));native=r.time_tables[i][raw-1]
            assert native==math.floor(reference),(raw,i,native,reference)
            gain=native/32768;fitted=-3*length/(48000*math.log10(gain))
            decays.append(dict(time_raw=raw,seconds=raw/10,line=i,length=length,table_value=native,
                               signed_gain=gain*(1 if i%2==0 else -1),analytic_value=reference,
                               isolated_loop_t60=fitted,relative_t60_quantization_error=abs(fitted-raw/10)/(raw/10)))
    for raw in range(101):
        scalar.append(r.scalar(1,raw,{35+i:v for i,v in enumerate(r.damp_words(raw))}))
        scalar.append(r.scalar(3,raw,{42:raw*Q23//100}));scalar.append(r.scalar(4,raw,{26:raw*Q23//200}))
        for enabled in range(2):
            wet,dry=mix(raw if enabled else 0);scalar.append(r.scalar(7,raw,{40:wet,39:dry},enabled))
    # Pre-delay is fixed at zero in this definition, but its original callback
    # still adds the physical slot's base and the guard offset.
    initialized=[]
    for slot in [0,1,4,5,6]:
        r.reset(True,slot);baseline=r.words();code_address=0xC0FEB1C8+8*(32+124*slot)
        before=bytes(a.uc.mem_read(code_address,121*8));assert before==f.data[r.definition['code_offset']:r.definition['code_offset']+121*8]
        a.call(0x7ADE0,r.ctx,slot);base=f.u32(0x38CCE8+4*slot);want=baseline.copy()
        for i in range(1,26):want[i]+=base
        assert r.words()==want
        r.callback(2,0);want[0]=base+1;assert r.words()==want
        after=bytes(a.uc.mem_read(code_address,121*8));references=[]
        for pc,((lo,hi),(new_lo,new_hi)) in enumerate(zip(struct.iter_unpack('<II',before),struct.iter_unpack('<II',after))):
            index=(hi>>19)&1023
            if 31<=index<=38:
                relocated=(new_hi>>19)&1023;assert relocated==index+80*slot,(slot,pc,index,relocated)
                references.append(dict(instruction=pc,local_index=index,relocated_index=relocated,original=[lo,hi],relocated=[new_lo,new_hi]))
        assert {v['local_index'] for v in references}==set(range(31,39))
        initialized.append(dict(slot=slot,base=base,address_words=want[:26],decay_damping_references=references))
    eq=[];r.params.update({i:0 for i in range(12)})
    for band,gain,fc in itertools.product(range(2),range(-30,31),range(2)):
        words=shelf_table(f,band,gain,fc);coeff=shelf_decode(words,band);reference=shelf_reference(band,gain,fc)
        error=max(abs(x-y) for x,y in zip(coeff,reference));assert error<0.000003 and abs(coeff[2])<1
        r.params[10+band]=fc;r.reset();r.callback(5+band,gain);want=[0]*80;start=43+3*band;want[start:start+3]=words;assert r.words()==want
        r.params[5+band]=gain;r.reset();r.callback(10+band,fc);assert r.words()==want
        eq.append(dict(band=band,gain_raw=gain,fc=fc,native=words,coefficients=coeff,max_error=error))
    dynamic=[]
    for wet,amount,value,source,enabled in itertools.product([0,16,50,100],[-100,-1,0,1,100],[-127,-64,0,64,127],[11,37],range(2)):
        r.params.update({7:wet,8:11,9:amount});r.reset();a.call(0x7B1B4,r.ctx,0,enabled,777,stack=(source,value));want=[0]*80
        if enabled and source==11:
            adjusted=max(0,min(100,wet+trunc(value*amount,127)));want[40],want[39]=map(u32,mix(adjusted))
        assert r.words()==want,(wet,amount,value,source,enabled,r.words(),want)
        dynamic.append(dict(wet=wet,amount=amount,value=value,source=source,enabled=enabled,wet_word=want[40],dry_word=want[39]))
    r.params.update({7:16,8:11,9:100});r.reset(True);r.callback(7,16);previous=r.words();trajectory=[]
    for source,value,enabled in [(11,-127,1),(11,-1,1),(37,127,1),(11,64,0),(11,64,1),(11,127,1),(11,0,1)]:
        a.call(0x7B1B4,r.ctx,0,enabled,777,stack=(source,value));want=previous.copy()
        if enabled and source==11:want[40],want[39]=map(u32,mix(max(0,min(100,16+trunc(value*100,127)))))
        assert r.words()==want;trajectory.append(dict(source=source,value=value,enabled=enabled,wet_word=want[40],dry_word=want[39]));previous=want
    # Host reference for each isolated recurrence only. This is NOT the Hall
    # network: diffusion, damping, coupling and output mix do not execute here.
    impulses=[]
    for raw,line in itertools.product([1,18,100],range(4)):
        length=r.lengths[line];g=r.time_tables[line][raw-1]/32768*(1 if line%2==0 else -1)
        frames=math.ceil(48000*raw/10*1.1)+length;ring=[0.]*length;events=[]
        for n in range(frames):
            y=(1. if n==0 else 0.)+g*ring[n%length];ring[n%length]=y
            if n%length:
                assert y==0
            else:
                expect=g**(n//length);assert abs(y-expect)<=1e-13*max(abs(expect),1e-30);events.append([n,y])
        fit=-3*length/(48000*math.log10(abs(events[1][1]/events[0][1])))
        assert abs(fit-next(d['isolated_loop_t60'] for d in decays if d['time_raw']==raw and d['line']==line))<1e-12
        impulses.append(dict(time_raw=raw,line=line,length=length,frames=frames,events=events,isolated_loop_t60=fit))
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b';factory=[]
    for program in range(768):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140]
        for slot in range(7):
            payload=0x18+76*slot if slot<5 else 0x194+68*(slot-5)
            if record[payload+64]!=105 or not record[payload+65]&64:continue
            params=[f.read_value(record,payload+p['payload_offset'],p['descriptor']) for p in r.definition['parameters']]
            assert all(p['descriptor']['minimum']<=v<=p['descriptor']['maximum'] for p,v in zip(r.definition['parameters'],params))
            r.params.clear();r.params.update(enumerate(params));r.reset(True,slot);a.call(0x7ADE0,r.ctx,slot);baseline=r.words()
            for i,value in enumerate(params):r.callback(i,value)
            expected=r.static_expected(params,baseline);assert r.words()==expected,(program,slot,[(i,x,y) for i,(x,y) in enumerate(zip(r.words(),expected)) if x!=y])
            factory.append(dict(program=chr(65+program//128)+str(program%128).zfill(3),slot='IFX'+str(slot+1) if slot<5 else 'MFX'+str(slot-4),
                                source_offset=offset,source_sha256=hashlib.sha256(record).hexdigest(),payload_offset=payload,parameters=params,words=r.words()[:61]))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={'firmware_chorus.py':sha(ROOT/'research/tools/firmware_chorus.py')},inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],
        initial_constants=r.initial,delay_intervals=[dict(start_index=s,end_index=e,length=r.lengths[i]) for i,(s,e) in enumerate(r.intervals)],
        time_table_offsets=r.time_pointers,time_tables=r.time_tables,damp_weights=r.damp_weights,decays=decays,scalars=scalar,initialized=initialized,
        pre_eq=eq,dynamic=dynamic,continuous_updates=trajectory,isolated_loop_impulses=impulses,factory=factory,
        max_t60_quantization_error=max(d['relative_t60_quantization_error'] for d in decays),max_eq_error=max(d['max_error'] for d in eq),
        boundaries=['Original Hall buffered loader, initializer and static/dynamic parameter callbacks execute; only parameter getter 0xD5AC4 supplies decoded values',
                    'Four feedback coefficient tables exactly equal floor(32767*10^(-3*L/(48000*T))) for all 100 time values; L matches original address-interval differences',
                    'Four damping coefficients are original percent scale times interval-length ratios; this does not determine their audio transfer functions',
                    'Bits 19..28 of the high program word carry the tested decay/damping constant indices; original slot relocation adds 80*slot at every observed use',
                    'Full 80-word buffers compare scalar, shelf, dynamic and factory settings; all enabled Hall slots in A-F Programs initialize at their actual slot',
                    'Twelve host impulse checks execute isolated signed delay-feedback recurrences using native gains, not the original complete Hall diffusion/coupling/damping network',
                    'No TG audio instruction, MMIO, OS, physical device or product code executes; full reverb topology and physical audio remain unresolved'])
    (OUT/'hall-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,scalar_cases=len(scalar),decay_coefficients=len(decays),delay_lengths=r.lengths,pre_eq_cases=len(eq),dynamic_cases=len(dynamic),
                         continuous_updates=len(trajectory),initializer_slots=len(initialized),isolated_loop_impulses=len(impulses),factory_slots=len(factory),
                         max_t60_quantization_error=result['max_t60_quantization_error'],max_eq_error=result['max_eq_error']),indent=2))
if __name__=='__main__':main()
