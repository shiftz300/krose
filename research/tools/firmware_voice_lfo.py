#!/usr/bin/env python3
"""Independent integer model of original voice LFO waveforms and timing."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
PRELOAD=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
NAMES=['Triangle','Saw','Square','Sine','Guitar','Exp.Triangle','Exp.Saw Down','Exp.Saw Up','Step Triangle 4','Step Triangle 6',
       'Step Saw 4','Step Saw 6','Random1(S/H)','Random2(S/H)','Random3(S/H)','Random4(cont)','Random5(cont)','Random6(cont)']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def s16(v):return (v+32768)%65536-32768
def s32(v):return (v+2**31)%2**32-2**31
def h(b,o):return struct.unpack_from('<H',b,o)[0]
def sh(b,o):return s16(h(b,o))
def w(b,o):return struct.unpack_from('<I',b,o)[0]
def ph(b,o,v):struct.pack_into('<H',b,o,v&65535)
def pw(b,o,v):struct.pack_into('<I',b,o,v&0xFFFFFFFF)
def clamp(v,lo,hi):return max(lo,min(hi,v))
def interpolate(a,b,f):return a+((b-a)*f>>8) if a<b else b+((a-b)*(255-f)>>8)
def ams_value(b):return (sh(b,0)*h(b,8)>>16)*16387>>16

class Model:
    def __init__(self,f):
        self.exp=list(struct.unpack_from('<128h',f.data,0x407178));self.guitar=list(struct.unpack_from('<256H',f.data,0x407390))
        self.sine=list(struct.unpack_from('<64H',f.data,0x407660));self.rate=list(struct.unpack_from('<100H',f.data,0x407590))
        self.fade=list(struct.unpack_from('<100H',f.data,0x4072C2));self.phase=list(struct.unpack_from('<37H',f.data,0x407278))
        self.jitter=list(struct.unpack_from('<65H',f.data,0x4078E4));self.periods=list(struct.unpack_from('<10H',f.data,0x457B9C))
        self.seed=1
    def draw(self):
        previous=self.seed;self.seed=previous*625&0xFFFFFFFF;return s32(previous*49920)>>16
    def exponential(self,phase):
        i,f=divmod(phase,512)
        return self.exp[i]+((self.exp[i+1]-self.exp[i])*f>>9) if i<127 else self.exp[i]
    def waveform(self,b,kind,shape=0,offset=0,amount=0,source=0):
        flags=b[0x12]&~4;phase=h(b,10);old=sh(b,2)
        if kind==0:
            v=s16(phase+16384);v=(~v)&65535 if v<0 else v;raw=s16(v-16384)*2
        elif kind==1:raw=32768-phase
        elif kind==2:raw=32767 if phase<32768 else -32767
        elif kind==3:
            def point(i):
                negative=i>=128;i=i%128;i=127-i if i>63 else i
                return self.sine[i]*(-1 if negative else 1)
            i,f=divmod(phase,256);raw=interpolate(point(i),point((i+1)&255),f)
        elif kind==4:
            i,f=divmod(phase,256);raw=interpolate(self.guitar[i],self.guitar[(i+1)&255],f)
        elif kind==5:
            def point(i):return self.exp[255-i if i>127 else i]
            i,f=divmod(phase,256);raw=interpolate(point(i),point((i+1)&255),f)
        elif kind in [6,7]:raw=self.exponential(65535-phase if kind==6 else phase)
        elif kind==8:raw=[-32767,0,32767,0][phase//16384]
        elif kind==9:
            raw=(-32767 if phase<=0x2AAA else -10923 if phase<=0x5554 else 10923 if phase<0x8000 else
                 32767 if phase<=0xAAAA else 10923 if phase<=0xD554 else -10923)
        elif kind==10:raw=[32767,10923,-10923,-32767][phase//16384]
        elif kind==11:
            raw=(32767 if phase<=0x2AAA else 19660 if phase<=0x5554 else 6553 if phase<0x8000 else
                 -6553 if phase<=0xAAAA else -19660 if phase<=0xD554 else -32767)
        elif kind in [12,13,14,16,17]:
            wrapped=bool(flags&2);previous=h(b,12)
            if wrapped:
                flags&=~2
                if kind==12:ph(b,12,self.draw())
                else:
                    speed=(self.draw()&65535)>>2;ph(b,16,max(1,speed));ph(b,12,self.draw())
            if kind in [12,13]:raw=sh(b,12)
            elif kind==14:raw=32767 if sh(b,12)>=0 else -32767
            else:
                if wrapped:
                    ph(b,14,previous)
                    ph(b,12,h(b,12)>>1 if kind==16 else 0 if previous else 32767)
                raw=(h(b,14)+((h(b,12)-h(b,14))*phase>>16))*2-32768
        elif kind==15:
            current=h(b,12);delta=sh(b,16);next_value=(current+2*delta)&65535
            if flags&2:
                flags&=~2;ph(b,12,next_value);ph(b,16,((self.draw()&65535)-next_value)>>1);sample=next_value
            else:sample=(current+(delta*phase>>15))&65535
            raw=sample-32768
        else:raise ValueError(kind)
        if kind in [1,6] and old<0 and raw>0:flags|=4
        if kind==7 and old>0 and raw<0:flags|=4
        if kind in [2,8,9,10,11,12,13,14] and old!=raw:flags|=4
        b[0x12]=flags;ph(b,2,raw)
        shaped=shape*331
        if amount:
            modulation=clamp(amount*source*331>>15,-32768,32767)
            shaped=clamp(shaped+8*modulation,-32768,32768)
        raw+=((32767-(raw*raw>>15))*shaped)>>16
        final=(661*offset>>2)+(raw>>1);ph(b,0,final);return final
    def set_phase(self,b,kind,start,clock):
        phase=0 if kind>11 else self.draw()&65535 if start==37 else self.phase[abs(start)]*(1 if start>=0 else -1)&65535
        ph(b,10,phase);ph(b,36,phase);pw(b,20,clock)
    def initialize(self,b,kind,start,delay,fade,clock,context,params,donor=None):
        pw(b,28,context);pw(b,32,0);pw(b,24,params)
        if donor is None:
            b[18]=2;self.set_phase(b,kind,start,clock);ph(b,4,delay<<9);ph(b,6,self.fade[fade]>>1)
            ph(b,8,65535 if w(b,4)==0x7FFF0000 else 0)
        else:
            for off,size in [(20,4),(4,2),(18,1),(8,2),(10,2)]:b[off:off+size]=donor[off:off+size]
        if kind in [15,16,17]:
            value=self.draw()&65535
            if kind==16:value>>=1
            if kind==17:value=32767 if value>32768 else 0
            ph(b,12,value)
        else:ph(b,12,0)
        ph(b,2,0);ph(b,16,0)
    def speed(self,b,freq,scale,sync,note,multiple,clock):
        if not sync:return clamp(self.rate[freq]*scale>>8,1,27525)
        period=self.periods[note]*multiple;elapsed=(clock-w(b,20))&0xFFFFFFFF
        if not period:return 1
        while elapsed>period:elapsed-=period
        pw(b,20,clock-elapsed);target=elapsed*65535//period+h(b,36);phase=h(b,10)
        return target-phase+(65536 if target<phase else 0)
    def advance(self,b,kind,scale,frozen,freq,sync,note,multiple,clock):
        delay=h(b,4)-max(scale,1);ph(b,4,delay)
        if delay<0:
            b[18]|=1;ph(b,4,0);ph(b,8,clamp(h(b,8)+(scale*sh(b,6)>>8),0,65535))
        if not b[18]&1 or frozen:return
        delta=self.speed(b,freq,scale,sync,note,multiple,clock)
        if kind in [13,14,16,17]:
            index,f=divmod(h(b,16),256);speed=self.jitter[index]+((self.jitter[index+1]-self.jitter[index])*f>>8)
            phase=h(b,10)+(speed*delta>>13)
            if phase>=65536:b[18]|=2;phase=0
        else:
            phase=h(b,10)+delta
            if phase>=65536:b[18]|=2
        ph(b,10,phase)

class Rig:
    def __init__(self,f):
        self.a=Arm(f);self.model=Model(f);self.state,self.params,self.ams,self.clock,self.context,self.donor=0x11008000,0x11009000,0x11009100,0x1100A000,0x1100B000,0x1100C000
        self.freq=0;self.signal=0
        self.voice=0x11010000;self.a.uc.mem_write(self.voice,bytes(0x84))
        self.a.write(0xC1B5720C,self.clock)
        self.a.stubs[0x27473C]=lambda a:a.get('R1') if a.get('LR')<0xC0200598 else self.freq
        self.a.stubs[0x274CC4]=lambda a:a.get('R1')
        self.a.stubs[0x273EE0]=lambda a:self.signal
    def seed(self,value):self.model.seed=value&0xFFFFFFFF;self.a.write(0xC1B5848C,value)
    def compare(self,b):
        actual=bytes(self.a.uc.mem_read(self.state,44));assert actual==bytes(b),[(i,x,y) for i,(x,y) in enumerate(zip(actual,b)) if x!=y]
        assert struct.unpack('<I',self.a.uc.mem_read(0xC1B5848C,4))[0]==self.model.seed
    def initialize(self,kind,start=0,delay=0,fade=0,clock=0,seed=1,donor=None):
        self.seed(seed);b=bytearray(44);self.a.uc.mem_write(self.state,bytes(b));self.a.write(self.clock+4,clock)
        if donor is not None:self.a.uc.mem_write(self.donor,bytes(donor))
        self.a.call(0x200208,self.state,0,self.context,kind,stack=(start,delay,fade,self.params,self.donor if donor is not None else 0))
        self.model.initialize(b,kind,start,delay,fade,clock,self.context,self.params,donor);self.compare(b);return b
    def wave(self,b,kind,shape=0,offset=0,amount=0,signal=0):
        self.signal=signal;self.a.uc.mem_write(self.ams,bytes([1,amount&255]));self.a.uc.mem_write(self.state,bytes(b))
        expected=self.model.waveform(b,kind,shape,offset,amount,signal)
        result=self.a.call(0x200A3C,self.state,kind,shape,self.ams,stack=(offset,));assert result==expected,(kind,h(b,10),shape,offset,amount,signal,result,expected)
        self.compare(b);return expected
    def advance(self,b,kind,scale=256,frozen=0,freq=0,sync=0,note=6,multiple=1,clock=0):
        self.freq=freq;self.a.write(self.clock+4,clock);self.a.uc.mem_write(self.params,bytes([sync*128+note,multiple]))
        self.a.uc.mem_write(self.state,bytes(b));self.a.call(0x200778,self.state,scale,frozen,kind,stack=(freq,))
        self.model.advance(b,kind,scale,frozen,freq,sync,note,multiple,clock);self.compare(b)
    def ams_output(self,b,slot):
        self.a.uc.mem_write(self.voice+0x2C+44*slot,bytes(b));before=bytes(self.a.uc.mem_read(self.voice,0x84))
        value=self.a.call(0x1F8608,self.voice,6+slot);assert value==ams_value(b),(slot,value,ams_value(b))
        assert bytes(self.a.uc.mem_read(self.voice,0x84))==before
        return value

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('voice-lfo-init',0x20014C,0x2003DC),('voice-lfo-waves',0x2003DC,0x200E20),('voice-lfo-random-and-scale',0x200E20,0x201120),('voice-lfo-wrapper',0x1FBD98,0x1FBF4C),('voice-lfo-ams-output',0x1F8608,0x1F8784)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    r=Rig(f);a=r.a;m=r.model;seeds=[0,1,65535,0x80000000,0xFFFFFFFF]+[i*2654435761&0xFFFFFFFF for i in range(512)]
    for seed in seeds:
        r.seed(seed);expect=m.draw();assert a.call(0x2C838C)==expect;r.compare(bytearray(a.uc.mem_read(r.state,44)))
    initializations=[]
    for kind,start in itertools.product(range(18),[-36,-1,0,1,36,37]):
        b=r.initialize(kind,start,0,0,clock=123,seed=0x9876543);initializations.append(dict(wave=kind,start=start,state=list(struct.unpack('<22H',b))))
    assert struct.unpack_from('<2I',f.data,0x1F8624+6*4)==(0xC01F86AC,0xC01F86B8)
    source_cases=[]
    for slot,value,level in itertools.product(range(2),[-32768,-32767,-16515,-16384,-1,0,1,8191,16383,16384,16515,32766,32767],[0,1,127,255,256,32767,32768,65534,65535]):
        b=bytearray(44);ph(b,0,value);ph(b,8,level)
        source_cases.append(dict(slot=slot+1,source_id=slot+6,wave_output=value,fade=level,ams=r.ams_output(b,slot)))
    control_trace=[];b=r.initialize(3,0,1,50,seed=1)
    for tick in range(160):
        value=r.wave(b,3);output=r.ams_output(b,0);assert r.ams_output(b,1)==output
        control_trace.append(dict(update=tick,phase=h(b,10),wave_output=value,fade=h(b,8),ams=output,delay=h(b,4)))
        r.advance(b,3,freq=80,clock=tick)
    phases=sorted({i*256+j for i in range(256) for j in [0,1,127,254,255]}|{0x2AAA,0x2AAB,0x5554,0x5555,0xAAAA,0xAAAB,0xD554,0xD555})
    waves=[];wave_cases=0
    for kind in range(12):
        points=[]
        for phase in phases:
            b=bytearray(44);ph(b,10,phase);value=r.wave(b,kind);wave_cases+=1
            if phase%256==0:points.append([phase,value])
        waves.append(dict(wave=kind,name=NAMES[kind],points=points))
    shape_cases=0
    for kind,phase,shape,offset,amount,signal in itertools.product([0,1,3,4,5,6,7,11],[0,8192,16384,32768,49152,65535],[-99,0,99],[-99,0,99],[-99,0,99],[-16384,0,16384]):
        b=bytearray(44);ph(b,10,phase);r.wave(b,kind,shape,offset,amount,signal);shape_cases+=1
    traces=[]
    for kind,seed in itertools.product(range(12,18),[1,0x12345678,0xFFFFFFFF]):
        b=r.initialize(kind,0,0,0,seed=seed);steps=[]
        for tick in range(256):
            value=r.wave(b,kind);r.advance(b,kind,freq=80,clock=tick)
            steps.append(dict(tick=tick,value=value,phase=h(b,10),random=h(b,12),previous=h(b,14),speed_or_delta=sh(b,16),flags=b[18],seed=m.seed))
        traces.append(dict(wave=kind,name=NAMES[kind],seed=seed,steps=steps))
    timing=[]
    for kind,delay,fade,frozen in itertools.product([0,3,12,13,15,17],[0,1,99],[0,50,99],range(2)):
        b=r.initialize(kind,0,delay,fade,seed=0x12345678);wraps=0
        for tick in range(240):
            r.wave(b,kind);r.advance(b,kind,frozen=frozen,freq=99,clock=tick);wraps+=bool(b[18]&2)
        timing.append(dict(wave=kind,delay=delay,fade=fade,frozen=frozen,final_state=list(struct.unpack('<22H',b)),wrap_visits=wraps))
    synchronized=[]
    for kind,note,multiple,phase_start in itertools.product([0,3,12,13],range(10),[1,2,32],[0,36]):
        b=r.initialize(kind,phase_start,0,0,clock=100,seed=1);period=m.periods[note]*multiple;steps=[]
        for tick in [100,101,100+period-1,100+period,101+period,100+period*3]:
            r.wave(b,kind);r.advance(b,kind,sync=1,note=note,multiple=multiple,clock=tick)
            steps.append(dict(clock=tick,phase=h(b,10),origin=w(b,20),flags=b[18]))
        synchronized.append(dict(wave=kind,note=note,multiple=multiple,start=phase_start,period=period,steps=steps))
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b';factory=[]
    for program in range(768):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140]
        for osc,lfo in itertools.product(range(2),range(2)):
            payload=0x564+380*osc+0x30+28*lfo;params=record[payload:payload+28];kind=params[0]&63
            assert kind<18 and params[1]<=99 and params[6]<=99 and params[7]<=99
            start=struct.unpack_from('<b',params,3)[0];shape,shift=struct.unpack_from('<bb',params,4)
            assert -36<=start<=37 and -99<=shape<=99 and -99<=shift<=99
            b=r.initialize(kind,start,params[6],params[7],seed=0x12345678);steps=[]
            for tick in [0,1,15,60,240,480,960,1920]:
                value=r.wave(b,kind,shape,shift)
                r.advance(b,kind,freq=params[1],frozen=(params[0]>>6)&1,sync=params[12]>>7,note=params[12]&15,multiple=params[13],clock=tick)
                steps.append([value,h(b,10),h(b,8),b[18]])
            factory.append(dict(program=chr(65+program//128)+str(program%128).zfill(3),oscillator=osc+1,lfo=lfo+1,source_offset=offset,
                                source_sha256=hashlib.sha256(record).hexdigest(),payload_offset=payload,wave=kind,parameters=list(params),steps=steps))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],waveform_names=NAMES,prng_seed_cases=len(seeds),initializations=initializations,
        waveform_cases=wave_cases,waveforms=waves,shape_cases=shape_cases,random_traces=traces,timing=timing,synchronized=synchronized,factory=factory,
        ams_source_cases=source_cases,ams_source_trace=control_trace,
        lookup_tables=dict(exponential=m.exp,guitar=m.guitar,sine_quarter=m.sine,rate=m.rate,fade=m.fade,phase=m.phase,jitter=m.jitter,sync_periods=m.periods),
        boundaries=['Original LFO initializer, all 18 waveform branches, phase advance, delay/fade and original 32-bit PRNG execute in private memory',
                    'Independent Python integer model compares all 44 state bytes, return values and PRNG state',
                    'Tone Adjust parameter helpers 0x27473C/0x274CC4 supply validated raw values; common AMS source getter 0x273EE0 supplies the test signal',
                    'Factory scan includes 3072 stored oscillator LFO blocks in 768 Programs, under zero external AMS, fixed seed and explicit musical-clock visits; audibility is not asserted',
                    'Original voice AMS getter 0x1F8608 executes source IDs 6/7 against synthetic voice LFO state, including delay/fade output; all voice bytes remain unchanged',
                    'Sync clocks are explicit counter values, not measured wall time; full voice-owned parameter/AMS input routing, stereo donor rules and final audio modulation remain separate work',
                    'No OS, MMIO, physical device, TG audio processing or product code executes'])
    (OUT/'voice-lfo-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,waveform_cases=wave_cases,shape_cases=shape_cases,initializations=len(initializations),random_traces=len(traces),
                         timing_traces=len(timing),synchronized_traces=len(synchronized),factory_blocks=len(factory),ams_source_cases=len(source_cases),ams_trace_updates=len(control_trace)),indent=2))
if __name__=='__main__':main()
