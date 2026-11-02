#!/usr/bin/env python3
"""Native MIDI Program Change through timbre loading and PCM OSC binding."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Firmware,BASE,FW_SHA
from firmware_gm_programs import GMDrums,sources,bank_model,IMAGE,IMAGE_SHA
from firmware_factory_voice_chain import Rig as MelodicRig
from firmware_midi_banks import model as bank_input_model
from firmware_voice_lfo import PRELOAD
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

class Rig(GMDrums):
    def __init__(self,f,raw,gm):
        super().__init__(f,raw,gm['DKITG.BIN'])
        a=self.a;a.uc.mem_map(0x12000000,0x400000)
        self.container=0x11040000;self.providers=0x11040100;self.provider_base=0x11040200;self.provider_vtable=0x11040400;self.program_manager=0x11041000
        self.channels=0x11050000;self.event=0x11052000;self.channel_nodes=0x11053000
        self.ts=[0x11054000+152*i for i in range(3)];self.ps=[0x11055000+64*i for i in range(3)];self.cs=[0x11056000+128*i for i in range(3)]
        self.pools=[0x11057000+64*i for i in range(3)];self.node_roots=[0x11058000+16*i for i in range(3)];self.osc_nodes=[0x11059000+32*i for i in range(3)]
        self.oscs=[[0x11068000+0x500*(2*i+j) for j in range(2)] for i in range(3)];self.osc_array=0x11074000
        self.fetches=[];self.notices=[];self.bindings=[];self.loaded=[];self.catalog={};cursor=0x12000000
        for bank in range(6):
            for program in range(128):
                record=raw[0x1EF220+2140*(bank*128+program):0x1EF220+2140*(bank*128+program+1)]
                self.catalog[bank,program]=(cursor,record);a.uc.mem_write(cursor,record);cursor+=2144
        for bank,name,count in [(10,'PROGGC.BIN',128),(11,'PROGGV.BIN',128),(12,'PROGGD.BIN',9)]:
            for program in range(count):
                record=gm[name][2140*program:2140*(program+1)];assert len(record)==2140
                self.catalog[bank,program]=(cursor,record);a.uc.mem_write(cursor,record);cursor+=2144
        a.write(self.container,self.providers);a.write(self.provider_vtable+0x14,BASE+0x5FF000)
        for bank in range(21):
            ptr=self.provider_base+32*bank
            # Keep the virtual table outside the provider array.
            if bank>=16:ptr=0x11040500+32*(bank-16)
            a.write(self.providers+4*bank,ptr);a.write(ptr,self.provider_vtable,bank,0,int(bank not in [0,1,2,3,4,5,10,11,12]))
        a.write(self.program_manager+0x85C,self.container,self.mode);a.uc.mem_write(self.program_manager+0x864,struct.pack('<hh',-1,-1))
        a.write(0xC1745678,self.container);a.write(0xC174567C,self.program_manager);a.write(0xC1666410+0x10,0)
        a.write(self.system+0x10,3,2,self.channels,self.ts[0]);a.write(self.system+0x34,self.osc_array)
        a.stubs.update({0x5FF000:self.fetch,0x27DFDC:lambda m:self.notices.append(['program',m.get('R1')]) or 0,
                        0x591EC:lambda m:self.notices.append(['drum-mode']) or 0,0x58E74:lambda m:0})
        from unicorn import UC_HOOK_CODE
        a.uc.hook_add(UC_HOOK_CODE,self.observe_load)
        self.reset()
    def fetch(self,a):
        bank=self.word(a.get('R0')+4);program=a.get('R1');self.fetches.append([bank,program])
        assert (bank,program) in self.catalog,(bank,program,hex(a.get('LR')))
        return self.catalog[bank,program][0]
    def observe_load(self,uc,address,size,user):
        off=address-BASE;a=self.a
        if off==0x1F6884:
            self.bindings.append([a.get('R0'),a.get('R1'),a.get('R2')])
            self.before_bind[a.get('R0')]=bytes(a.uc.mem_read(a.get('R0'),0x500))
        elif off==0x27263C:self.loaded.append([a.get('R0'),a.get('R1'),a.get('R2')])
    def reset(self,mode=3,config=3,alternate=0,part_gates=(1,1,1),part_types=(1,1,1),bank_lock=(0,0,0)):
        self.before_bind={};self.mode_value=mode;self.config=config;self.alternate=alternate
        a=self.a;a.write(self.mode,mode);a.write(self.system+0x2C,0);self.put8(0xC199BD38,0)
        self.put8(0xC1DCC2D8+0x1350,0);self.put8(0xC1DCC2D8+0x1352,16 if alternate else 0);self.put8(0xC1DCC2D8+0x1353,config)
        for n in range(16):
            channel=self.channels+436*n;a.uc.mem_write(channel,bytes(436));a.call(0x26E08C,channel,n)
        self.channel=self.channels+7*436;a.call(0x26E094,self.channel,0)
        for i,t in enumerate(self.ts):
            for p,size in [(t,152),(self.ps[i],64),(self.cs[i],128),(self.pools[i],32),(self.osc_nodes[i],24)]:a.uc.mem_write(p,bytes(size))
            a.write(t+4,self.ps[i]);a.write(t+0x10,self.channel);a.write(t+0x20,self.node_roots[i],self.pools[i]);a.write(t+0x8C,self.cs[i])
            self.put8(t+0x28,i);self.put8(t+0x2E,255);self.put8(t+0x4F,255);self.put8(t+0x50,255);a.write(t+0x30,0xFFFFFFFF)
            self.put8(self.ps[i]+2,32);self.put8(self.ps[i]+5,127);self.put8(self.ps[i]+0x19,1)
            a.write(self.node_roots[i],self.osc_nodes[i]);a.write(self.pools[i]+0x18,0x1105A000+128*i);self.put8(self.pools[i]+0x1C,10)
            a.write(self.channel+0x138,0x11060000)
            for j,o in enumerate(self.oscs[i]):
                a.uc.mem_write(o,bytes(0x500));a.write(o,BASE+0x470DE0);self.put8(o+4,j);a.write(o+0x48C,self.manager)
                a.write(o+0x490,o+0x490,o+0x490,0);a.write(self.osc_array+4*(2*i+j),o)
            a.call(0x27263C,t,self.ps[i],1)
            self.put8(self.ps[i]+2,part_types[i]<<5);self.put8(self.ps[i]+0x19,part_gates[i]);self.put8(t+0x29,2 if bank_lock[i] else 0)
        for n,t in enumerate(self.ts[:2]):a.write(self.channel_nodes+12*n,self.channel_nodes+12*(n+1),0,t)
        a.write(self.channel_nodes+24,self.channel_nodes+24,0,0);a.write(self.channel+0xFC,self.channel_nodes)
        a.write(self.channel_nodes+48,self.channel_nodes+60,0,self.ts[2]);a.write(self.channel_nodes+60,self.channel_nodes+60,0,0);a.write(self.channel+0x108,self.channel_nodes+48)
        self.fetches.clear();self.notices.clear();self.bindings.clear();self.loaded.clear()
    def send(self,status,first,second=0,source=0):
        self.a.write(self.event,0,status+(first<<8)+(second<<16)+(source<<24),0);self.a.call(0x271500,self.system,self.event)
    def cc(self,k,v,source=0):self.send(0xB7,k,v,source)
    def change(self,program):
        for x in [self.fetches,self.notices,self.bindings,self.loaded]:x.clear()
        self.send(0xC7,program)
    def state(self):
        return dict(parts=[bytes(self.a.uc.mem_read(p,64)).hex() for p in self.ps],
                    program_pointers=[self.word(t+8) for t in self.ts],bend=[struct.unpack('<h',self.a.uc.mem_read(t+0x94,2))[0] for t in self.ts],
                    controls=[bytes(self.a.uc.mem_read(p,128)).hex() for p in self.cs],channel=bytes(self.a.uc.mem_read(self.channel,436)).hex(),
                    fetches=list(self.fetches),bindings=list(self.bindings),notifications=list(self.notices))
    def observe(self,uc,address,size,user):
        if getattr(self,'record',b'\0'*0x509)[0x508]&7==2:super().observe(uc,address,size,user)
        else:MelodicRig.observe(self,uc,address,size,user)
    def check_binding(self,index,bank,program):
        physical,number,_=bank_model(self.f,bank,program);ptr,record=self.catalog[physical,number];a=self.a;t=self.ts[index]
        assert (self.word(t+8),self.word(t+12))==(ptr,ptr+0x520)
        count=2 if record[0x508]&7==1 else 1;node=self.word(t+0x14);objects=[]
        while node!=t+0x14:
            assert len(objects)<2;objects.append(self.word(node+8));node=self.word(node)
        assert objects==self.oscs[index][:count],(objects,self.oscs[index][:count])
        for j,osc in enumerate(objects):
            params=ptr+0x564+380*j;assert (self.word(osc+8),self.word(osc+0x49C))==(params,t)
            if record[0x508]&7==2:
                encoded=int.from_bytes(record[0x566:0x568],'little');kit=encoded if encoded<58 else encoded-96
                kitptr=self.kitbase+8728*kit;kitraw=bytes(a.uc.mem_read(kitptr,8728));assert self.word(osc+0x10)==kitptr
                wanted=[next((k-n for k in range(n,128) if kitraw[24+68*k+65]&1),-1) for n in range(128)]
                assert list(struct.unpack('<128b',a.uc.mem_read(osc+24,128)))==wanted
                assert bytes(a.uc.mem_read(0x11060000,1536))==bytes([64]*7+[127,255,255,255,0])*128
            else:
                before=self.before_bind[osc]
                for layer in range(4):
                    desc=record[0x564+380*j+8*layer:0x56C+380*j+8*layer];encoded=desc[1];ms=int.from_bytes(desc[2:4],'little')
                    assert encoded in [0,1]
                    numbers=self.pairs[ms] if encoded&1 else [ms]
                    for side,num in enumerate(numbers):
                        dst=osc+12+288*layer+144*side
                        assert self.word(dst)==BASE+0x48F5CC+28*num
                        assert (a.uc.mem_read(dst+0x8C,1)[0],self.half(dst+0x8E))==(0,num)
                        expected=bytearray(before[dst-osc+12:dst-osc+140]);first,n=struct.unpack_from('<HB',self.f.data,0x48F5CC+28*num);previous=-1
                        for region in range(n):
                            top=struct.unpack_from('<b',self.f.data,0x492C28+20*(first+region)+3)[0]
                            if top>0 and top>previous:expected[previous+1:top+1]=bytes([region])*(top-previous)
                            previous=top
                        if previous<127:expected[previous+1:128]=bytes([255])*(127-previous)
                        assert bytes(a.uc.mem_read(dst+12,128))==bytes(expected),(bank,program,j,layer,side)
        return dict(bank=bank,program=program,physical_bank=physical,physical_program=number,record_sha256=hashlib.sha256(record).hexdigest(),oscillators=count,drum=record[0x508]&7==2)
    def check_change(self,program):
        a=self.a;before=self.state();parts=[bytearray.fromhex(p) for p in before['parts']];channel=bytearray.fromhex(before['channel']);ctrl=[bytes.fromhex(x) for x in before['controls']]
        encoded=(channel[0x82]<<8)|channel[0xA2];bank,newprog,accepted,special=bank_input_model(self.f,encoded,program,self.alternate,special=a.uc.mem_read(0xC1B5719C,1)[0])
        assert accepted and bank>=0,(encoded,program,self.alternate)
        # All controlled storage providers6..9 are empty. They occur only on queried paths here.
        if bank in [6,7,8,9]:bank=0
        updated=[];expected_notices=[];expected_binds=[];expected_fetches=[];expected_loaded=[]
        self.change(program)
        if self.config&1:
            channel[0]=channel[0]&127
            if encoded==0x3F7F or encoded&0x7F00==0x7E00:channel[0]|=128
            if self.mode_value in [0,3]:
                for i in range(2):
                    if not parts[i][0x19]&1:continue
                    oldbank,oldprog=parts[i][1],parts[i][0];ob,op,_=bank_model(self.f,oldbank,oldprog);expected_fetches.append([ob,op])
                    if parts[i][2]>>5 in [1,2]:
                        if not a.uc.mem_read(self.ts[i]+0x29,1)[0]&2:parts[i][1]=bank
                        parts[i][0]=newprog;nb,np,_=bank_model(self.f,parts[i][1],newprog)
                        expected_fetches.append([nb,np]);expected_loaded.append([self.ts[i],self.ps[i],1])
                        row=self.check_binding(i,parts[i][1],newprog);updated.append(dict(timbre=i,**row))
                        expected_binds.extend([[self.oscs[i][j],self.catalog[nb,np][0]+0x564+380*j,self.ts[i]] for j in range(row['oscillators'])])
                    else:nb,np=ob,op
                    expected_fetches.append([nb,np]);old_dr=(self.catalog[ob,op][1][0x508]&7)==2;new_dr=(self.catalog[nb,np][1][0x508]&7)==2
                    if old_dr!=new_dr:expected_notices.append(['drum-mode'])
                    expected_notices.append(['program',i]);ctrl[i]=bytes(channel[0x82:0xFA])+ctrl[i][120:];before['bend'][i]=0
        assert a.uc.mem_read(0xC1B5719C,1)[0]==special if self.config&1 else True
        assert bytes(a.uc.mem_read(self.channel,436))==bytes(channel)
        for i in range(3):
            actual=bytes(a.uc.mem_read(self.ps[i],64))
            assert actual==bytes(parts[i]),(self.mode_value,self.config,i,[(hex(n),v,parts[i][n]) for n,v in enumerate(actual) if v!=parts[i][n]])
            assert bytes(a.uc.mem_read(self.cs[i],128))==ctrl[i]
            assert struct.unpack('<h',a.uc.mem_read(self.ts[i]+0x94,2))[0]==before['bend'][i]
            if not any(r['timbre']==i for r in updated):assert self.word(self.ts[i]+8)==before['program_pointers'][i]
        assert self.fetches==expected_fetches,(self.fetches,expected_fetches)
        assert self.bindings==expected_binds and self.loaded==expected_loaded
        assert self.notices==expected_notices,(self.notices,expected_notices)
        return dict(input_bank=encoded,input_program=program,mode=self.mode_value,alternate=self.alternate,loaded=updated,notifications=list(self.notices),bend=before['bend'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');p.add_argument('--contexts-only',action='store_true');args=p.parse_args();f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('MIDI-timbre-change',0x26EAE4,0x26EC34),('MIDI-Program-loader',0x1DBB80,0x1DBC54),('MIDI-timbre-binding',0x27263C,0x272824),('MIDI-timbre-switch',0x272DA0,0x272EF0)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm:return
    assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    raw=PRELOAD.read_bytes();gm=sources();r=Rig(f,raw,gm)
    r.cc(0,0);r.cc(32,1);r.cc(7,99);r.send(0xE7,127,127)
    example=r.check_change(17)
    if args.smoke:print(json.dumps(example,indent=2));return
    counts={};factory=[];gm_rows=[];contexts=[];alternate_rows=[];empty_rows=[]
    for bank,program in ([] if args.contexts_only else itertools.product(range(6),range(128))):
        r.cc(0,0);r.cc(32,bank);row=r.check_change(program);factory.append(row)
    counts['factory_programs']=len(factory)
    for bank,program in ([] if args.contexts_only else itertools.product(range(10,21),range(128))):
        r.cc(0,121 if bank<20 else 120);r.cc(32,bank-10 if bank<20 else 0);row=r.check_change(program);gm_rows.append(row)
    counts['gm_logical_selections']=len(gm_rows)
    if not args.contexts_only:
        r.reset(alternate=1)
        for encoded,program in itertools.product([0,1,9,0x3F00,0x3F05,0x4000,0x7E00,0x7F00],range(128)):
            r.cc(0,encoded>>8);r.cc(32,encoded&255);alternate_rows.append(r.check_change(program))
        r.reset()
        for bank,program in itertools.product(range(6,10),[0,64,127]):
            r.cc(0,0);r.cc(32,bank);empty_rows.append(r.check_change(program))
    counts['alternate_selections']=len(alternate_rows);counts['empty_bank_selections']=len(empty_rows)
    for mode,config,gates,types,locks,source in itertools.product([0,1,2,3],[2,3],[(0,0,0),(1,0,1),(0,1,0),(1,1,1)],[(1,1,1),(0,3,1),(2,1,1)],[(0,0,0),(1,0,0)], [0,5]):
        r.reset(mode,config,part_gates=gates,part_types=types,bank_lock=locks)
        r.cc(0,0,source);r.cc(32,1,source);r.cc(7,99,source);r.send(0xE7,127,127)
        contexts.append(r.check_change(17))
    counts['loading_contexts']=len(contexts)
    if args.contexts_only:print(json.dumps(dict(contexts_passed=True,counts=counts),indent=2));return
    result=dict(passed=True,smoke_only=False,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py']},
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA)],counts=counts,factory=factory,gm=gm_rows,contexts=contexts,alternate=alternate_rows,empty=empty_rows,example=example,
        boundaries=['Native271500/26EC34/26EAE4/1DBB80/272E00/27263C/1F6884/1F6654/2742A0 execute; no Program arithmetic or OSC binding replaced',
            'Three controlled timbres share channel7; two primary timbres receive Program Change, secondary receives controllers and bend only',
            'Only storage provider virtual getter returns immutable real source records; availability and logical-to-physical GM conversion execute natively',
            'Existing private PCM/DrumKit directories use original constructors; exception bookkeeping, allocation and TG I/O remain inherited fixture boundaries',
            'Program UI and drum-mode notifications27DFDC/591EC and modulation notification58E74 are intercepted',
            'Independent model compares all channel436 bytes, all Part64/controller128 bytes, bend, fetch/bind/notification order, actual source pointers and all active PCM region maps or drum remaps',
            'Mode1/2 global-channel queued application change, mode0 global-channel Combi option, bank sentinel-1 storage layout, timbre15/song special route, actual NoteOn after change and audio remain outside this result'])
    (OUT/'midi-program-load-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=counts),indent=2))
if __name__=='__main__':main()
