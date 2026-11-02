#!/usr/bin/env python3
"""Factory PCM selection, allocation, real region assembly and TG start chain."""
import argparse,collections,contextlib,hashlib,io,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from voice_math import VoiceMath
from firmware_voice_lfo import sha,PRELOAD,OUT,h,sh,w,s32
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

def sb(b,o):return struct.unpack_from('<b',b,o)[0]
def fold(note):
    while note<0:note+=12
    while note>127:note-=12
    return note
def selection_pitch(note,transpose,slope):
    if slope==0:value=60*256
    elif slope==10:value=note*256
    elif slope==-10:value=(120-note)*256
    elif slope==20:value=max(0,min(32767,512*note-60*256))
    else:value=max(0,min(32767,60*256+(s32((820*note-49200)*slope)>>5)))
    return (fold(transpose+(value>>8))<<8)|(value&255)

class Rig:
    def __init__(self,f):
        self.f=f;self.math=VoiceMath(f);self.a=Arm(f);self.writes=[];self.reads=[];self.allocations=[]
        self.system=0x11000000;self.banks=0x11001000;self.registry=0x11004000
        self.primarydir=0x11005000;self.stereodir=0x11005100;self.primaryarray=0x11006000;self.stereoarray=0x11007000
        self.osc=0x11010000;self.context=0x11012000;self.part=0x11014000;self.patch=0x11016000
        self.channel=0x11018000;self.controls=0x1101A000;self.clock=0x1101C000;self.mode=0x1101E000
        self.manager=0x11080000;self.voices=0x11090000;self.nodes=0x110A0000;self.members=0x110A1000;self.waitnodes=0x110A2000
        self.heap=0x110D0000;self.tg=0x60000000;self.heap_size=0;self.current_slot=0
        self.prepared=[];self.started=[];self.sample_starts=[];self.reverse_requests=[]
        def fail(a):raise AssertionError('Native assertion at '+hex(a.get('LR')))
        self.a.stubs={0x2C5220:fail,0x2DC184:lambda a:0,0x2DC1BC:lambda a:0,
                      0x14E730:self.allocate,0x132690:self.bus_write,0x1326B4:self.bus_read}
        from unicorn import UC_HOOK_CODE
        self.hook=self.a.uc.hook_add(UC_HOOK_CODE,self.observe)
        a=self.a;a.write(0xC1743270,self.system);a.write(self.system+0x28,self.banks)
        a.write(self.banks+0x14,4070,5570,497);a.write(self.banks+0x24,BASE+0x410ABC,BASE+0x492C28,BASE+0x48F5CC)
        a.write(self.banks+0x1A34,0,0)
        a.write(self.primarydir,self.primaryarray,497);a.write(self.stereodir,self.stereoarray,248)
        a.write(self.registry,self.primarydir,self.stereodir);a.write(self.registry+0x404,self.stereodir)
        a.write(0xC199BD88,self.registry)
        a.call(0x283AF8,self.primarydir,0,0);a.call(0x283E04,self.stereodir,1,self.primarydir,0)
        self.pairs=[]
        for i in range(self.word(self.stereodir+4)):
            p=self.word(self.stereoarray+4*i);self.pairs.append([self.half(p+4)&32767,self.half(p+6)&32767])
        expected=[]
        names=[f.data[0x48F5CC+28*i+4:0x48F5CC+28*i+28].decode('ascii').rstrip(' \0') for i in range(497)]
        for i,name in enumerate(names[:-1]):
            if name.endswith('-L') and names[i+1]==name[:-1]+'R':expected.append([i,i+1])
        assert self.pairs==expected
        self.reverse_caps=[]
        for i in range(497):
            first,count=struct.unpack_from('<HB',f.data,0x48F5CC+28*i)
            allowed=all(not f.data[0x410ABC+64*h(f.data,0x492C28+20*j)+7]&1 for j in range(first,first+count))
            actual=self.a.call(0x285758,self.registry,0,i);assert actual==int(allowed)
            self.reverse_caps.append(allowed)
        a.write(0xC199BD3C,self.mode);a.write(self.mode,4);a.write(0xC0F5389C,self.system)
        a.write(self.system+0x54,0x1101F000);a.uc.mem_write(0x1101F000,bytes(32))
        a.write(0xC1B5720C,self.clock);a.write(self.clock,0,123)
        a.uc.mem_write(0xC1439F10,bytes(48));a.uc.mem_write(0xC1439F10+31,b'\xff');a.uc.mem_write(0xC1439F10+35,b'\xff')
        a.uc.mem_write(0xC1439F10+1,b'\xff')  # selector50: retain the stored reverse choice before capability check
        a.uc.mem_write(0xC1743294,bytes(128));a.uc.mem_write(0xC165DA38,bytes(24));self.put8(0xC104728C,1)
    def word(self,p):return w(bytes(self.a.uc.mem_read(p,4)),0)
    def half(self,p):return h(bytes(self.a.uc.mem_read(p,2)),0)
    def put8(self,p,v):self.a.uc.mem_write(p,bytes([v&255]))
    def allocate(self,a):
        size=a.get('R0');assert size in [8,32]
        address=self.heap+self.heap_size;self.heap_size+=(size+15)&~15
        assert self.heap_size<0x8000;self.allocations.append([address,size]);return address
    def bus_write(self,a):
        offset=a.get('R0')-self.tg;value=a.get('R1');assert 0<=offset<0x4000,(hex(offset),hex(a.get('LR')))
        self.writes.append([self.current_slot,offset,value])
        if offset==0x400:self.current_slot=value
        return 0
    def bus_read(self,a):
        offset=a.get('R0')-self.tg;assert 0<=offset<0x4000
        self.reads.append(offset);return 0
    def observe(self,uc,address,size,user):
        a=self.a;off=address-BASE
        if off==0x1F6958:
            sp=a.get('SP');selection=self.word(sp+8);layer=self.word(sp+12);side=self.word(sp+16)
            row=selection+4+20*layer;descriptor=self.word(row+4);slot=(descriptor-(self.patch+0x564+380*self.oscillator))//8
            self.prepared.append(dict(layer=layer,side=side,slot=slot,weight=self.half(row),selection_note=self.half(selection),selection_pitch=self.half(selection+2)))
        elif off==0x1F7278:
            voice=a.get('R0');self.started.append(dict(address=voice,sample_ptr=self.word(voice+0x20),region_ptr=self.word(voice+0x22C),
                layer_level=bytes(a.uc.mem_read(0xC165D9A4,1))[0],root=s32(self.word(0xC165D9B0)),tune=s32(self.word(0xC165D9AC)),
                pitch=s32(self.word(0xC165D9A8))))
        elif off==0x1F9028:self.sample_starts.append(a.get('R0'))
        elif off==0x285758:self.reverse_requests.append([a.get('R1'),a.get('R2')])
    def prepare(self,record,osc):
        a=self.a;self.record=bytes(record);self.oscillator=osc;a.uc.mem_write(self.patch,self.record)
        a.uc.mem_write(self.osc,bytes(0x500));a.uc.mem_write(self.context,bytes(0x200));a.uc.mem_write(self.part,bytes(0x40))
        a.uc.mem_write(self.channel,bytes(0x200));a.uc.mem_write(self.controls,bytes(128));a.uc.mem_write(self.manager,bytes(0x100))
        a.write(self.osc+8,self.patch+0x564+380*osc);a.write(self.osc+0x48C,self.manager);a.write(self.osc+0x49C,self.context);self.put8(self.osc+4,osc)
        a.write(self.context+4,self.part,self.patch,self.patch+0x520,self.channel);a.write(self.context+0x8C,self.controls)
        self.put8(self.context+0x2E,255);self.put8(self.context+0x4F,255);self.put8(self.context+0x50,255)
        self.put8(self.part+5,127);a.write(self.context+0x30,0xFFFFFFFF)
        a.call(0x1F6654,self.osc)
        a.write(self.manager+4,self.voices);a.write(self.manager+0x0C+0x30,self.nodes,self.members,8,0)
        a.write(self.manager+0xCC,self.manager+0xCC,self.manager+0xCC,0,self.waitnodes,8)
        a.uc.mem_write(self.voices,bytes(8*588));a.uc.mem_write(0xC165DA38,bytes(24))
        for i in range(8):
            v=self.voices+588*i;a.call(0x1F68D4,v);self.put8(v+0x16,i);self.put8(v+0x1A,i);a.write(v+0x1C,self.tg);a.write(v+0x240,0xFFFFFFFF)
            for nodes in [self.nodes,self.members,self.waitnodes]:a.write(nodes+12*i,0,0,v)
        a.call(0x1FBF4C,self.manager+12);a.write(0xC1B5848C,0x12345678)
        self.writes.clear();self.reads.clear();self.prepared.clear();self.started.clear();self.sample_starts.clear();self.reverse_requests.clear()
    def expected_layers(self,note,velocity):
        p=self.record;b=p[0x564+380*self.oscillator:0x564+380*(self.oscillator+1)]
        lo,hi=sorted(p[0x518+2*self.oscillator:0x51A+2*self.oscillator]);vlow,vhigh=sorted(b[0x2D:0x2F])
        if not lo<=note<=hi or not vlow<=velocity<=vhigh:return []
        transpose=sb(bytes([(12*sb(b,0x78)+b[0x79])&255]),0)
        pitch=selection_pitch(note,transpose,sb(b,0x7C));slot=next((i for i in range(3) if velocity>=b[0x20+4*i]),3)
        rows=[dict(slot=slot,weight=32768,pitch=pitch)];width=b[0x21+4*slot] if slot<3 else 0
        if width and velocity<b[0x20+4*slot]+width:
            first=(velocity-b[0x20+4*slot])*32768//width;second=32768-first;curve=b[0x22+4*slot]&3
            if curve==2:first=second=32768
            elif curve==1:
                def shape(x):
                    if x>=32768:return x
                    index,fraction=divmod(x,256);lo=h(self.f.data,0x40585C+2*index);hi=h(self.f.data,0x40585C+2*(index+1))
                    return lo+((hi-lo)*fraction>>8)
                first,second=shape(first),shape(second)
            rows[0]['weight']=first;rows.append(dict(slot=slot+1,weight=second,pitch=pitch))
        expected=[]
        for layer,row in enumerate(rows):
            slot=row['slot'];desc=b[8*slot:8*(slot+1)];bank=desc[1];number=h(desc,2)
            assert bank in [0,1]
            indices=[number] if bank==0 else self.pairs[number]
            for side,multisample in enumerate(indices):
                valid=bool(desc[0]&3);region=None;query=pitch>>8
                if valid:
                    first,count=struct.unpack_from('<HB',self.f.data,0x48F5CC+28*multisample);previous=-1
                    for index in range(count):
                        top=sb(self.f.data,0x492C28+20*(first+index)+3)
                        if previous<query<=top and top>0:region=first+index;break
                        if query==0 and top==0:region=first+index;break
                        previous=top
                expected.append(dict(layer=layer,side=side,multisample=multisample,region=region,valid=valid,**row))
        return expected
    def note(self,note,velocity):
        self.note_number=note;self.velocity=velocity;self.put8(self.context+0x44,note);self.put8(self.context+0x45,velocity)
        expected=self.expected_layers(note,velocity);self.writes.clear();self.reads.clear();self.prepared.clear();self.started.clear();self.sample_starts.clear();self.reverse_requests.clear()
        returned=self.a.call(0x1FDC8C,self.manager,0x90+(note<<8)+(velocity<<16),self.osc,0,stack=(0xFFFFFFFF,))&0xFFFFFFFF
        attempted=[];failed_layer=None
        for row in expected:
            row['attempted']=row['layer']!=failed_layer
            if row['attempted']:
                attempted.append(row)
                if not row['valid'] or row['region'] is None:failed_layer=row['layer']
        assert len(self.prepared)==len(attempted),(self.oscillator,note,velocity,self.prepared,expected)
        for actual,wanted in zip(self.prepared,attempted):
            assert all(actual[k]==wanted[k] for k in ['layer','side','slot','weight']), (actual,wanted)
            assert actual['selection_note']==note and actual['selection_pitch']==wanted['pitch'],(actual,wanted)
        valid=[x for x in attempted if x['valid'] and x['region'] is not None]
        assert len(self.started)==len(valid),(self.prepared,self.started,expected)
        rows=[];block=self.record[0x564+380*self.oscillator:0x564+380*(self.oscillator+1)]
        for start,selected in zip(self.started,valid):
            v=start['address'];region=selected['region'];r=self.f.data[0x492C28+20*region:0x492C28+20*(region+1)]
            sample=h(r,0);desc=block[8*selected['slot']:8*(selected['slot']+1)];level=desc[4]*selected['weight']>>15
            assert start['region_ptr']==BASE+0x492C28+20*region and start['sample_ptr']==BASE+0x410ABC+64*sample
            assert (start['layer_level'],start['root'],start['tune'],start['pitch'])==(level,sb(r,4)<<8,sh(r,6),selected['pitch'])
            assert self.word(v+0x4C)==v and self.word(v+0x78)==v
            tracking=[self.math.keyboard_tracking(block[0xFC:0x103],note),self.math.keyboard_tracking(block[0x13C:0x143],note,True),
                      self.math.keyboard_tracking(self.record[0x554:0x55B],note),self.math.keyboard_tracking(self.record[0x55C:0x563],note)]
            assert [sh(bytes(self.a.uc.mem_read(v+off,2)),0) for off in [0x204,0x206,0x212,0x214]]==tracking
            gain=self.math.multisample_gain(level,sb(r,8),0)
            pair_type=self.word(v+0x218)
            assert self.half(v+0x200)==(0 if pair_type==2 else gain),(selected,level,sb(r,8),pair_type,self.half(v+0x200),gain)
            assert self.half(v+0x10)==0xC0
            assert self.word(v+0x224)==self.patch+0x564+380*self.oscillator
            assert self.word(v+0x220)==self.patch+0x520
            reverse=desc[5]>>7
            if reverse:reverse=int(all(self.reverse_caps[i] for i in ([h(desc,2)] if not desc[1]&1 else self.pairs[h(desc,2)])))
            assert bytes(self.a.uc.mem_read(v+0x20C,1))[0]==reverse
            rows.append(dict(**selected,voice_slot=(v-self.voices)//588,tg_slot=bytes(self.a.uc.mem_read(v+0x1A,1))[0],sample=sample,
                layer_level=level,region_level_correction=sb(r,8),multisample_gain=self.half(v+0x200),region_gain_formula=gain,reverse=reverse,pair_type=pair_type,
                partner_slot=((self.word(v+0x230)-self.voices)//588 if self.word(v+0x230) else None),
                delay=sh(bytes(self.a.uc.mem_read(v+0x208,2)),0),amp_target=self.half(v+0x150),
                pitch_word=self.half(v+0x94),pitch_increment=self.word(v+0x9C),filter_route=bytes(self.a.uc.mem_read(v+0x116,1))[0],
                eg_stages=[bytes(self.a.uc.mem_read(v+off+6,1))[0] for off in [0xBC,0x120,0x15C]]))
        assert self.word(self.manager+12+0x3C)==8-len(rows)
        chain=[];node=returned
        while node:
            assert len(chain)<8;chain.append((self.word(node+8)-self.voices)//588);node=self.word(node)
        assert set(chain)=={r['voice_slot'] for r in rows}
        byslot={r['voice_slot']:r for r in rows}
        for row in rows:
            v=self.voices+588*row['voice_slot']
            if v in self.sample_starts:
                raw=self.f.data[0x410ABC+64*row['sample']:0x410ABC+64*(row['sample']+1)]
                offset=bytes(self.a.uc.mem_read(v+0x20A,1))[0];boundary=bytes(self.a.uc.mem_read(v+0x20B,1))[0]
                field=12 if not offset else 56 if offset-boundary+8==7 else 60 if offset-boundary+8==8 else 16 if offset==1 else 32+4*(offset-1)
                flags=raw[7];start=w(raw,20);loop=w(raw,field)
                if flags&8:
                    loop=w(raw,24)
                    if flags&32:start=w(raw,12)
                    elif row['reverse']:flags|=32
                elif row['reverse']:start=w(raw,28);loop=w(raw,32);flags|=40
                want={0x200:((flags>>2)&14)|(flags&1),0x208:start,0x20C:(w(raw,24)-1)&0xFFFFFFFF,0x210:loop}
                actual={off:value for slot,off,value in self.writes if slot==row['tg_slot'] and off in want}
                assert actual==want,(row,actual,want)
                row['sample_registers']={hex(k):v for k,v in want.items()}
            if row['pair_type']==1:
                partner=byslot[row['partner_slot']];assert partner['pair_type']==2 and partner['partner_slot']==row['voice_slot']
                assert row['tg_slot']<partner['tg_slot']
                for off,size in [(0xBC,48),(0x120,48),(0x15C,100),(0xEC,51),(0x1F0,16),(0x150,10)]:
                    assert bytes(self.a.uc.mem_read(self.voices+588*row['voice_slot']+off,size))==bytes(self.a.uc.mem_read(self.voices+588*partner['voice_slot']+off,size))
        return dict(note=note,velocity=velocity,selection=expected,voices=rows,returned_chain=chain,reverse_queries=list(self.reverse_requests),
                    tg_start_calls=len(self.sample_starts),writes=len(self.writes),startup_registers=[x for x in self.writes if x[1] in [0x200,0x208,0x20C,0x210,0x418]])

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('factory-reverse-capability',0x283AF8,0x283E04),('factory-native-bank-lookup',0x1E2974,0x1E29AC),
                       ('factory-note-pitch',0x1FF8D4,0x1FF9A0)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory=[];extra=[];counts=collections.Counter();overlap_representatives={}
    for index in range(768):
        record=raw[0x1EF220+2140*index:0x1EF220+2140*(index+1)];mode=record[0x508]&7
        if mode==2:continue
        for osc in range(1+mode):
            b=record[0x564+380*osc:0x564+380*(osc+1)]
            for slot in range(3):
                bottom,width,kind=b[0x20+4*slot:0x23+4*slot]
                if width and bottom>0 and bottom+width<=128 and b[8*slot]&3 and b[8*(slot+1)]&3:
                    overlap_representatives.setdefault(kind&3,dict(program_index=index,osc=osc,slot=slot,bottom=bottom,width=width))
    overlap_pairs={(row['program_index'],row['osc']) for row in overlap_representatives.values()}
    for index in range(1 if args.smoke else 768):
        off=0x1EF220+2140*index;record=raw[off:off+2140];mode=record[0x508]&7
        if mode==2:continue
        assert mode in [0,1];counts['programs']+=1
        for osc in range(1+mode):
            block=record[0x564+380*osc:0x564+380*(osc+1)];lo,hi=sorted(record[0x518+2*osc:0x51A+2*osc]);vl,vh=sorted(block[0x2D:0x2F])
            note=(lo+hi)//2;vel=max(1,(vl+vh)//2);r.prepare(record,osc);state=r.note(note,vel)
            factory.append(dict(program=chr(65+index//128)+str(index%128).zfill(3),oscillator=osc+1,source_offset=off,
                                source_sha256=hashlib.sha256(record).hexdigest(),**state))
            counts['oscillators']+=1;counts['voices']+=len(state['voices']);counts['starts']+=state['tg_start_calls']
            if index%128==0:print('Factory',index,'OSC',osc+1,dict(counts),flush=True)
    if not args.smoke:
        # Piano layer endpoints, real overlap representatives, all pitch-slope variants and reversed descriptor.
        for index in range(768):
            off=0x1EF220+2140*index;record=raw[off:off+2140];mode=record[0x508]&7
            if mode==2:continue
            for osc in range(1+mode):
                block=record[0x564+380*osc:0x564+380*(osc+1)]
                if index!=0 and (index,osc) not in overlap_pairs and block[0x7C]==10 and not any(block[8*s]&3 and block[8*s+5]&128 for s in range(4)):continue
                lo,hi=sorted(record[0x518+2*osc:0x51A+2*osc]);vl,vh=sorted(block[0x2D:0x2F])
                notes=sorted({lo,(lo+hi)//2,hi});velocities={max(1,vl),max(1,(vl+vh)//2),vh}
                if index==0 or (index,osc) in overlap_pairs:
                    for slot in range(3):
                        bottom,width=block[0x20+4*slot:0x22+4*slot];velocities.update([bottom-1,bottom,bottom+width//2,bottom+width-1,bottom+width])
                for note in notes:
                    for velocity in sorted(v for v in velocities if max(1,vl)<=v<=vh):
                        r.prepare(record,osc);state=r.note(note,velocity)
                        extra.append(dict(program=chr(65+index//128)+str(index%128).zfill(3),oscillator=osc+1,**state))
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),
                helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['voice_math.py','firmware_voice_lfo.py']},
                inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],counts=dict(counts),stereo_pairs=r.pairs,reverse_capabilities=r.reverse_caps,
                factory=factory,extra=extra,overlap_representatives=overlap_representatives,boundaries=['Original directory capability scan, stereo directory construction, bank lookup and OSC material refresh execute in private memory',
                    'Original note-layer selection, allocator, real region/sample builder, parameter copy, stereo state sharing and complete TG startup execute in one call chain',
                    'Only allocation, exception-frame bookkeeping and primitive TG bus reads/writes are supplied, plus an assertion trap; no synthesis computation is replaced',
                    'Full factory scan is one configured-range midpoint note/velocity per active melodic OSC; extra cases cover A000 layer thresholds, original linear/table/layer overlaps, all stored nonstandard pitch slopes and reversed descriptor',
                    'Independent checks cover selected layers/weights/pitch, real region/sample addresses, root/tune/level, gain/tracking, reverse capability, owner/pair/list invariants',
                    'Fresh eight-voice pool per case; TG ready/status/readback values are zero; no full MIDI parser, continuous stealing, drum kit, expansion bank or audio executes',
                    'Neutral part transpose, disabled external controllers, zero Tone Adjust offsets with reverse/pause overrides unset, no previous voice/legato history and fixed clock are controlled inputs'])
    destination=OUT/('factory-voice-chain-smoke.json' if args.smoke else 'factory-voice-chain-check.json')
    destination.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,**counts,extra_cases=len(extra)),indent=2))
if __name__=='__main__':main()
