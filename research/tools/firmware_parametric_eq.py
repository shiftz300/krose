#!/usr/bin/env python3
"""Original P4EQ band paths versus independent audio equations and factory data."""
import argparse,cmath,contextlib,hashlib,io,itertools,json,math,struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
PRELOAD=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def response(c,f):
    z=cmath.exp(-2j*math.pi*f/48000)
    return (c[0]+c[1]*z+c[2]*z*z)/(1-c[3]*z-c[4]*z*z)
def radius(c):
    f1,f2=c[3:];return max(abs((f1+s*cmath.sqrt(f1*f1+4*f2))/2) for s in [-1,1])
def frequency(band,index,mode=0):return [20,50,300,500][band]+(20 if band==0 and mode else [10,10,100,100][band])*index
def decode(words,precision,scale):
    raw=[((hi<<8)|(lo>>15))&0xFFFFFFFF for hi,lo in zip(words[::2],words[1::2])] if precision else words
    bits=32 if precision else 24
    return [(v-(1<<bits) if v&(1<<(bits-1)) else v)/(1<<(bits-2))*2**(scale-1) for v in raw]
class EqRig:
    def __init__(self,f):
        self.a=Arm(f);self.ctx,self.info=0x11008000,0x11009000;self.base=0xC0FE9DC8
        self.a.call(0x57C1C,1,0xFFFF);self.a.call(0x60F70,1,0xFFFF)
        self.a.write(self.info+0xC,0,self.ctx)
        def fixed(p):
            sign,whole,frac=struct.unpack('<hHI',self.a.uc.mem_read(p,8));return sign*(whole+frac/2**32)
        self.constants={name:fixed(p) for name,p in [('angle_step',0xC0FEF750),('angle_limit',0xC0FEF748),('tangent_cap',0xC0FEF740)]}
        self.shelf_factors=[fixed(self.a.call(0x980F8,g)&0xFFFFFFFF) for g in range(37)]
    def words(self,start,count):return list(struct.unpack('<'+'I'*count,self.a.uc.mem_read(self.base+4*start,4*count)))
    def band(self,band,index,q,gain,mode=0,delta=0):
        a=self.a;a.uc.mem_write(self.ctx,b'\x01\x01'+bytes(30));a.uc.mem_write(self.base,bytes(200))
        if band==0:
            a.call(0x86B60,self.ctx,0,gain,q,stack=(index,mode));starts=[2];precision,scale=1,1;allowed=set(range(2,12))
        elif band==1:
            a.call(0x86BD4,self.ctx,0,delta,gain,stack=(q,index));starts=[12,22];precision,scale=1,3;allowed=set(range(12,32))
        elif band==2:
            a.call(0x86C54,self.info,gain,q,index);starts=[32];precision=0;scale=self.words(44,1)[0];allowed=set(range(32,37))|{44}
        else:
            a.call(0x86D38,self.ctx,0,gain,q,stack=(index,mode));starts=[37];precision=0;scale=self.words(45,1)[0];allowed=set(range(37,42))|{45}
        hz=frequency(band,index,mode);expected_scale=1 if band==0 else 3 if band==1 else 4 if mode else 1 if hz<1200 else 2 if hz<4900 else 3
        assert scale==expected_scale
        all_words=self.words(0,50);assert all(v==0 for i,v in enumerate(all_words) if i not in allowed)
        native=[self.words(start,10 if precision else 5) for start in starts]
        return dict(band=band,index=index,q=q,gain=gain,mode=mode,delta=delta,hz=hz,precision=precision,scale=scale,
                    native=native,coefficients=[decode(ws,precision,scale) for ws in native])
    def reference(self,band,index,q,gain,mode=0):
        hz=frequency(band,index,mode)
        if not mode:
            angle=hz*self.constants['angle_step']*5/(q+5)
            alpha=self.constants['tangent_cap'] if angle>=self.constants['angle_limit'] else math.tan(angle)
            cosine=math.cos(2*math.pi*hz/48000);g=10**(abs(gain)/40)
            d=1+alpha if gain>=0 else 1+g*alpha
            return [(1+g*alpha)/d if gain>=0 else (1+alpha)/d,-2*cosine/d,
                    (1-g*alpha)/d if gain>=0 else (1-alpha)/d,2*cosine/d,
                    (alpha-1)/d if gain>=0 else (g*alpha-1)/d]
        factor=self.shelf_factors[abs(gain)];amp=10**(abs(gain)/80)
        t=math.tan(math.pi*hz*(factor if band==0 else 1/factor)/48000)
        if band==0:num,den=[1+t,t-1],[1+t/amp,t/amp-1]
        else:num,den=[amp*(1+t),amp*(t-1)],[1+amp*t,amp*t-1]
        if gain<0:num,den=den,num
        b0,b1=num[0]/den[0],num[1]/den[0];a1=den[1]/den[0]
        return [b0*b0,2*b0*b1,b1*b1,-2*a1,-a1*a1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('p4eq-band-programming',0x86B38,0x86E80),('p4eq-peaking-math',0x5E8FC,0x5F290),('p4eq-shelf-factor',0x980F8,0x988B8)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    rig=EqRig(f);cases=[];largest=0;max_pole=0
    scalar=[];control=0x1100A000;a=rig.a
    for value in range(101):
        a.uc.mem_write(rig.ctx,b'\x01\x01'+bytes(30));a.uc.mem_write(rig.base,bytes(200));a.uc.mem_write(control,bytes(0x40))
        a.write(control+8,value,0,rig.ctx);a.call(0x86E80,20,control)
        assert rig.words(0,50)==[value*0x7FFFFF//100]+[0]*49
        scalar.append(dict(trim=value,word=rig.words(0,1)[0]))
    params={};queries=[]
    def getter(m):
        assert m.get('R0')==777 and m.get('R2')==m.get('R3')==0
        index=m.get('R1');queries.append(index);return params[index]
    a.stubs[0xD5AC4]=getter;wet_cases=[];modulation=[]
    for wet,enabled in itertools.product([0,1,37,100],range(2)):
        params.clear();params[17]=wet;queries.clear()
        a.uc.mem_write(rig.ctx,b'\x01\x01'+bytes(30));a.uc.mem_write(rig.base,bytes(200))
        a.call(0x87B2C,rig.ctx,0,777,enabled)
        assert rig.words(0,50)==[0,wet*0x7FFFFF//100 if enabled else 0]+[0]*48
        assert queries==([17] if enabled else [])
        wet_cases.append(dict(wet=wet,enabled=enabled,word=rig.words(1,1)[0]))
    def truncdiv(v,d):return (abs(v)//d)*(1 if v>=0 else -1)
    for wet,amount,value,source,enabled in itertools.product([0,37,100],[-100,0,100],[-127,0,64,127],[6,11,37],range(2)):
        params.clear();params.update({3:6,17:wet,18:11,19:amount});queries.clear()
        a.uc.mem_write(rig.ctx,b'\x01\x01'+bytes(30));a.uc.mem_write(rig.base,bytes(200))
        a.call(0x87A44,rig.ctx,0,enabled,777,stack=(source,value))
        expected=[0]*50
        if enabled and source==6:expected[46]=max(0,min(0x7FFFFF,truncdiv(value*0x7FFFFF,127)))
        if enabled and source==11:
            adjusted=max(0,min(100,wet+truncdiv(value*amount,127)));expected[1]=adjusted*0x7FFFFF//100
        assert rig.words(0,50)==expected,(wet,amount,value,source,enabled,rig.words(0,50),expected)
        modulation.append(dict(wet=wet,amount=amount,value=value,source=source,enabled=enabled,wet_word=expected[1],band2_weight_word=expected[46]))
    del a.stubs[0xD5AC4]
    def check(row):
        nonlocal largest,max_pole
        gains=[row['gain']] if row['band']!=1 else [row['gain'],max(-36,min(36,row['gain']+row['delta']))]
        errors=[]
        for coeff,gain in zip(row['coefficients'],gains):
            expect=rig.reference(row['band'],row['index'],row['q'],gain,row['mode'])
            error=max(abs(a-b) for a,b in zip(coeff,expect));pole=radius(coeff)
            assert error<0.00005,(row,error,expect)
            assert pole<1,(row,pole)
            largest=max(largest,error);max_pole=max(max_pole,pole);errors.append(error)
        row['reference_errors']=errors
        return row
    for band,indices in [(0,[0,1,49,98]),(1,[0,99,500,995]),(2,[0,8,9,45,46,97]),(3,[0,6,7,43,44,114,115,116,195])]:
        for index,q,gain,mode,delta in itertools.product(indices,[0,12,95],[-36,-12,0,12,36],[0,1] if band in [0,3] else [0],[-36,0,36] if band==1 else [0]):
            cases.append(check(rig.band(band,index,q,gain,mode,delta)))
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    definition=f.effect(7);factory=[]
    for program in range(768):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140];assert len(record)==2140
        for slot in range(7):
            payload=0x18+76*slot if slot<5 else [0x194,0x1D8][slot-5];header=payload+64
            if record[header]!=7 or not record[header+1]&64:continue
            values=[f.read_value(record,payload+p['payload_offset'],p['descriptor']) for p in definition['parameters']]
            bands=[]
            for band,idx in enumerate([5,8,11,14]):
                mode=values[1 if band==0 else 2] if band in [0,3] else 0
                bands.append(check(rig.band(band,values[idx],values[idx+1],values[idx+2],mode,values[4] if band==1 else 0)))
            factory.append(dict(program=chr(65+program//128)+str(program%128).zfill(3),slot='IFX'+str(slot+1) if slot<5 else 'MFX'+str(slot-4),
                source_offset=offset,source_sha256=hashlib.sha256(record).hexdigest(),payload_offset=payload,parameters=values,bands=bands))
    # Realize the normalized native coefficients as a host SOS. Check the
    # finite impulse's complex DFT against its analytic transfer function.
    impulses=[]
    for band,index,q,gain,mode in [(0,0,95,36,0),(1,995,0,36,0),(2,97,0,36,0),(3,0,0,36,1),(0,49,0,-36,1)]:
        row=next(r for r in cases if (r['band'],r['index'],r['q'],r['gain'],r['mode'],r['delta'])==(band,index,q,gain,mode,0))
        c=row['coefficients'][0];b0,b1,b2,f1,f2=c;x1=x2=y1=y2=0.;signal=[]
        for n in range(131072):
            x=1. if n==0 else 0.;y=b0*x+b1*x1+b2*x2+f1*y1+f2*y2
            assert math.isfinite(y);signal.append(y);x2,x1,y2,y1=x1,x,y1,y
        errors=[]
        for hz in [20,80,1000,10000]:
            z=cmath.exp(-2j*math.pi*hz/48000);power=1+0j;actual=0j
            for sample in signal:actual+=sample*power;power*=z
            expected=response(c,hz);error=abs(actual-expected)/max(abs(expected),1e-12)
            assert error<1e-5,(row,hz,error)
            errors.append(dict(hz=hz,relative_complex_error=error))
        impulses.append(dict(band=band,index=index,q=q,gain=gain,mode=mode,frames=len(signal),tail_peak=max(map(abs,signal[-4096:])),checks=errors))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],constants=rig.constants,shelf_factors=rig.shelf_factors,
        cases=cases,factory=factory,trim=scalar,wet=wet_cases,modulation=modulation,host_impulses=impulses,max_coefficient_error=largest,max_pole_radius=max_pole,
        boundaries=['Original four-band coefficient programming, dynamic-band endpoint clamp, shelf lookup and buffered coefficient writes execute without stubs',
                    'Independent floating-point peaking/shelf equations compare normalized native coefficients; every checked pole remains inside the unit circle',
                    'Factory scan includes enabled P4EQ slots in all 768 A-F Programs, not signal-path audibility or total effects coverage',
                    '50-word buffer starts at zero for each band; writes outside the intended coefficient/scale locations are checked',
                    'Original trim, static Wet/Dry and dynamic control callbacks execute; scalar cases supply parameter getter values at 0xD5AC4, with all other words checked unchanged',
                    'Five host double-precision SOS impulse responses compare complex frequency response at four frequencies; this validates the reference realization, not silicon audio',
                    'No TG audio instructions execute; DSP DMOD interpolation and audio mix, effects routing, full-chip rounding and hardware audio equivalence remain outside this check'])
    (OUT/'parametric-eq-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,boundary_cases=len(cases),factory_effect_slots=len(factory),trim_cases=len(scalar),wet_cases=len(wet_cases),modulation_cases=len(modulation),host_impulses=len(impulses),max_coefficient_error=largest,max_pole_radius=max_pole),indent=2))
if __name__=='__main__':main()
