#!/usr/bin/env python3
"""Native channel RPN/NRPN, pressure and pitch with independent state model."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
FIELDS={20:0,21:1,22:2,23:3,24:4,25:5,26:7,28:8,29:10,30:9}
NRPN_CC={8:76,9:77,10:78,32:74,33:71,99:73,100:75,102:72}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clamp(v,lo,hi):return max(lo,min(hi,v))
def s8(v):return v-256 if v&128 else v
def sh(raw,at):return struct.unpack_from('<h',raw,at)[0]
def put16(raw,at,v):struct.pack_into('<H',raw,at,v&65535)
def div100(v):return v//100 if v>=0 else -((-v)//100)
def rem100(v):return v-100*div100(v)
def cc_map(controller,value):
    if controller==77 and value>64:return 64+((value-64)*3>>2)
    if controller==78:return 64+((value-64)*10>>4)
    if controller==71:return (value>>1)+32
    return value
def bend_value(low,high):return ((low<<2)|(high<<9)|(high&3))-32768

class Rig:
    def __init__(self,f):
        self.f=f;self.a=a=Arm(f);self.system=0x11000000;self.channels=0x11001000;self.channel=self.channels+7*436;self.event=0x11004000
        self.nodes=0x11005000;self.timbres=[0x11006000+256*i for i in range(3)];self.parts=[0x11007000+64*i for i in range(3)]
        self.programs=[0x11008000+0x1000*i for i in range(3)];self.controls=[0x1100B000+128*i for i in range(3)];self.keys=0x1100C000;self.mode=0x1100D000;self.notifications=[]
        a.stubs={0x27E0EC:lambda m:self.notifications.append(['range',m.get('R1')]) or 0,
            0x27E084:lambda m:self.notifications.append(['tune',m.get('R1')]) or 0,
            0x27E074:lambda m:self.notifications.append(['transpose',m.get('R1')]) or 0,
            0x58E74:lambda m:0}
        a.write(0xC1743270,self.system);a.write(self.system+0x18,self.channels);a.write(0xC199BD3C,self.mode)
        a.write(0xC0FE9DC0,0x1100D100)
        self.reset()
    def reset(self,mode=0,gates=(1,1,1),ranges=(2,2,2),tunes=(305,-305,100),transposes=(0,0,0)):
        a=self.a;a.write(self.system+0x2C,0);a.write(self.mode,mode)
        for n in range(16):
            chan=self.channels+436*n;a.uc.mem_write(chan,bytes(436));a.call(0x26E08C,chan,n)
        a.uc.mem_write(self.keys,bytes(1536));a.write(self.channel+0x138,self.keys);a.call(0x26E094,self.channel,1)
        for i,t in enumerate(self.timbres):
            a.uc.mem_write(t,bytes(256));a.uc.mem_write(self.parts[i],bytes(64));a.uc.mem_write(self.programs[i],bytes(2144));a.uc.mem_write(self.controls[i],bytes(128))
            a.write(t+4,self.parts[i],self.programs[i]);a.write(t+0x8C,self.controls[i]);self.byte(t+0x28,i)
            self.byte(self.programs[i]+0x508,2 if i==1 else 0);self.byte(self.parts[i]+0x1B,16 if gates[i] else 0)
            self.byte(self.parts[i]+6,ranges[i]);self.byte(self.parts[i]+7,transposes[i]);a.uc.mem_write(self.parts[i]+8,struct.pack('<h',tunes[i]))
        for i,t in enumerate(self.timbres[:2]):a.write(self.nodes+12*i,self.nodes+12*(i+1),0,t)
        a.write(self.nodes+24,self.nodes+24,0,0);a.write(self.channel+0xFC,self.nodes)
        a.write(self.nodes+48,self.nodes+60,0,self.timbres[2]);a.write(self.nodes+60,self.nodes+60,0,0);a.write(self.channel+0x108,self.nodes+48)
        self.c=bytearray(a.uc.mem_read(self.channel,436));self.p=[bytearray(a.uc.mem_read(p,64)) for p in self.parts]
        self.q=bytearray(a.uc.mem_read(self.keys,1536));self.ctrl=[bytearray(128) for _ in range(3)];self.bends=[0,0,0];self.mode_value=mode;self.notifications.clear();self.expected_notifications=[]
    def byte(self,p,v):self.a.uc.mem_write(p,bytes([v&255]))
    def controller(self,k,v,shadow=True):
        self.c[0x82+k]=v&255
        if shadow:self.c[0x13C+k]=v&255
        for c in self.ctrl:c[k]=v&255
    def rpn(self,kind,absolute,delta=0):
        for i in range(2):
            part=self.p[i];gate=bool(part[0x1B]&16)
            if kind==0:
                if self.mode_value not in [1,2] and (not gate or s8(part[6])==-25):continue
                part[6]=clamp(s8(part[6])+delta if delta else absolute,0,24);self.expected_notifications.append(['range',i])
            elif not gate:continue
            elif kind==1:
                old=sh(part,8)
                value=(100*div100(old)+(rem100(old)+delta if delta else absolute)) if i==1 else (old+delta if delta else absolute)
                put16(part,8,clamp(value,-1200,1200));self.expected_notifications.append(['tune',i])
            elif kind==2:
                value=clamp((div100(sh(part,8))+delta if delta else clamp(absolute,-24,24))*100+rem100(sh(part,8)),-1200,1200) if i==1 else clamp(s8(part[7])+delta if delta else absolute,-24,24)
                if i==1:put16(part,8,value);self.expected_notifications.append(['tune',i])
                else:part[7]=value&255;self.expected_notifications.append(['transpose',i])
    def nrpn(self,value,delta=0):
        high,low=self.c[0xE5],self.c[0xE4]
        if high==1:
            k=NRPN_CC.get(low)
            if k is None:return
            v=clamp(self.c[0x82+k]+delta,0,127) if delta else cc_map(k,value)
            self.controller(k,v,True)
        elif high in FIELDS:
            at=12*low+FIELDS[high];self.q[at]=clamp(s8(self.q[at])+delta,0,127) if delta else value
    def model(self,status,first,second,source):
        self.expected_notifications=[];kind=status&240
        if kind==176:
            self.controller(first,second,source!=5);flags=self.c[0x114]
            if first in [98,99]:
                flags=(flags&~64)|(0x88 if first==98 else 0x84)
                if flags&(4 if first==98 else 8):flags&=~48
            elif first in [100,101]:
                flags=(flags&127)|(0x42 if first==100 else 0x41)
                if flags&(1 if first==100 else 2):flags&=~48
            elif first in [6,38]:
                if flags&0x43==0x43:
                    flags|=16 if first==6 else 32
                    if not self.c[0xE7]:
                        selection=self.c[0xE6]
                        if first==6 and selection==0:self.rpn(0,second)
                        elif selection==1:
                            fine=(((self.c[0x88]<<8)|(self.c[0xA8]<<1))-16384)*400>>16;self.rpn(1,fine)
                        elif first==6 and selection==2:self.rpn(2,second-64)
                elif first==6 and flags&0x8C==0x8C:self.nrpn(second)
            elif first in [96,97]:
                delta=1 if first==96 else -1
                if flags&0x43==0x43:
                    if not self.c[0xE7] and self.c[0xE6]<=2:self.rpn(self.c[0xE6],0,delta)
                elif flags&0x8C==0x8C:self.nrpn(0,delta)
            self.c[0x114]=flags
        elif kind==224:
            v=bend_value(first,second);put16(self.c,0xFA,v);self.bends=[v]*3
        elif kind==208:self.c[1]=first
        elif kind==160:self.c[2+first]=second
    def send(self,status,first,second=0,source=0):
        self.model(status,first,second,source);self.notifications.clear();self.a.write(self.event,0,status+(first<<8)+(second<<16)+(source<<24),0)
        self.a.call(0x271500,self.system,self.event)
        assert bytes(self.a.uc.mem_read(self.channel,436))==bytes(self.c),(status,first,second,[(hex(i),x,y) for i,(x,y) in enumerate(zip(self.a.uc.mem_read(self.channel,436),self.c)) if x!=y][:12])
        for i in range(3):
            assert bytes(self.a.uc.mem_read(self.parts[i],64))==bytes(self.p[i]),(status,first,second,i,self.p[i].hex(),bytes(self.a.uc.mem_read(self.parts[i],64)).hex())
            assert bytes(self.a.uc.mem_read(self.controls[i],128))==bytes(self.ctrl[i])
            assert sh(bytes(self.a.uc.mem_read(self.timbres[i]+0x94,2)),0)==self.bends[i]
        assert bytes(self.a.uc.mem_read(self.keys,1536))==bytes(self.q)
        assert self.notifications==self.expected_notifications,(self.notifications,self.expected_notifications)
    def cc(self,k,v,source=0):self.send(0xB7,k,v,source)
    def select(self,kind,high,low):self.cc(101 if kind=='rpn' else 99,high);self.cc(100 if kind=='rpn' else 98,low)
    def state(self):return dict(flags=self.c[0x114],range=[s8(p[6]) for p in self.p],transpose=[s8(p[7]) for p in self.p],tune=[sh(p,8) for p in self.p],bend=sh(self.c,0xFA))

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('MIDI-channel-parameters',0x26F864,0x26FAD8),('MIDI-RPN-tuning',0x26E264,0x26E5BC),('MIDI-pressure-bend',0x26FF84,0x270078)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm:return
    r=Rig(f);counts={};examples=[]
    # Full selector-flag domain, including stale values and incomplete pairs.
    cases=0
    for initial,controller,value in itertools.product(range(256),[98,99,100,101],[0,1,127]):
        r.reset();r.byte(r.channel+0x114,initial);r.c[0x114]=initial;r.cc(controller,value);cases+=1
    counts['selector_flags']=cases
    # Original fine tuning keeps the coarse hundred-cent component for drum mode.
    r.reset();r.select('rpn',0,1);fine=[]
    for value in range(16384):
        msb,lsb=divmod(value,128);r.cc(6,msb);r.cc(38,lsb)
        if value in [0,1,4096,8191,8192,8193,12288,16383]:fine.append(dict(value=value,**r.state()))
    counts['fine_values']=16384
    cases=0
    for mode,gates,kind,value in itertools.product(range(5),[(0,0,0),(1,0,1),(0,1,0),(1,1,1)],[0,1,2,3,127],range(128)):
        r.reset(mode,gates,ranges=(-25,24,2));r.select('rpn',0,kind);r.cc(6,value);r.cc(38,127);r.cc(96,127);r.cc(97,0);cases+=1
    counts['rpn_contexts']=cases
    cases=0
    for high,low,value in itertools.product([0,1,2,127],range(128),[0,64,127]):
        r.reset();r.select('rpn',high,low);r.cc(6,value);r.cc(38,value);cases+=1
    counts['rpn_selection_gates']=cases
    cases=0
    for high,low,value in itertools.product([1]+list(range(20,31)),range(128),[0,64,127]):
        r.reset();r.select('nrpn',high,low);r.cc(6,value);r.cc(96,0);r.cc(97,127);r.cc(38,64);cases+=1
    counts['nrpn_contexts']=cases
    r.reset();bend=[]
    for value in range(16384):
        r.send(0xE7,value&127,value>>7)
        if value in [0,1,127,128,8191,8192,8193,16383]:bend.append(dict(value=value,output=r.bends[0]))
    counts['bend_values']=16384
    cases=0
    for key,value in itertools.product(range(128),[0,1,64,127]):r.send(0xA7,key,value);cases+=1
    for value in range(128):r.send(0xD7,value)
    counts['poly_pressure']=cases;counts['channel_pressure']=128
    # Source5 updates live controllers but does not overwrite the shadow copy.
    for source in [0,1,5,8]:
        r.reset();r.select('rpn',0,2);r.cc(6,76,source);r.select('nrpn',20,48);r.cc(6,99,source);r.select('rpn',127,127);r.cc(6,127,source)
        examples.append(dict(source=source,state=r.state(),live_data=r.c[0x88],shadow_data=r.c[0x142],drum_cutoff=r.q[48*12]))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),counts=counts,fine_examples=fine,bend_examples=bend,source_examples=examples,
        nrpn_cc=NRPN_CC,drum_fields=FIELDS,boundaries=['Original event-kind/channel routing271500, channel dispatcher26EC34, CC copying27422C, bend copying274258 and RPN/NRPN setters execute',
            'One controlled channel7 has two primary timbres (melodic/drum) and one secondary timbre; actual per-timbre controller buffers are compared',
            'Only application refresh notifications27E0EC/27E084/27E074 and modulation notification58E74 are intercepted; no tuning, selector or controller arithmetic is replaced',
            'Independent model compares all436 channel bytes, all three64-byte Part records, all three128-byte controller buffers, bend fields,1536 key-control bytes and notification order after every message',
            'Program Change/bank conversion, Reset All Controllers, complete front-end filtering, actual voice refresh and audio are outside this result'])
    (OUT/'midi-parameters-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=counts),indent=2))
if __name__=='__main__':main()
