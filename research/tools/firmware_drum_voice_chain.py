#!/usr/bin/env python3
"""Factory drum kits: native directory, remapping, voice start and exclusivity."""
import argparse,collections,contextlib,hashlib,io,json,struct
from pathlib import Path
from firmware_factory_voice_chain import Rig as FactoryRig,fold,selection_pitch,sb
from firmware_voice_lfo import sha,PRELOAD,OUT,h,sh,w,s32
from program_firmware import Firmware,FW_SHA,BASE
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

KIT_OFFSET=0x48BE20
KIT_STRIDE=8728

class Rig(FactoryRig):
    def __init__(self,f,raw):
        super().__init__(f)
        self.raw=raw;self.drumdir=0x11005200;self.drumpairsdir=0x11005300
        self.kitroot=0x11005400;self.kitarray=0x11005420;self.kitprovider=0x11005440
        self.kitbase=0x110E0000;self.keycontrols=0x11020000;self.selection=0x11021000
        a=self.a;a.write(self.banks+0x20,1014);a.write(self.banks+0x30,BASE+0x408BFC)
        a.write(self.drumdir,0x11008000,1014);a.write(self.drumpairsdir,0x11009000,507)
        a.write(self.registry+0x400,self.drumdir,self.drumpairsdir)
        a.call(0x283AF8,self.drumdir,0,1);a.call(0x283E04,self.drumpairsdir,1,self.drumdir,1,count=4000000)
        self.drum_pairs=[]
        for i in range(self.word(self.drumpairsdir+4)):
            ptr=self.word(0x11009000+4*i);self.drum_pairs.append([self.half(ptr+4)&32767,self.half(ptr+6)&32767])
        names=[f.data[0x408BFC+32*i+4:0x408BFC+32*i+28].decode('ascii').rstrip(' \0') for i in range(1014)]
        expected=[[i,i+1] for i in range(1013) if names[i].endswith('-L') and names[i+1]==names[i][:-1]+'R']
        assert self.drum_pairs==expected
        self.drum_caps=[]
        for i in range(1014):
            sample=sh(f.data,0x408BFC+32*i)
            allowed=sample>=0 and not f.data[0x410ABC+64*sample+7]&1
            actual=a.call(0x2857B8,self.registry,0,i);assert actual==int(allowed),(i,sample,allowed,actual)
            self.drum_caps.append(allowed)
        a.uc.mem_write(self.kitbase,raw[KIT_OFFSET:KIT_OFFSET+58*KIT_STRIDE])
        a.write(self.kitroot,self.kitarray,1);a.write(self.kitarray,self.kitprovider)
        a.write(self.kitprovider,BASE+0x472080,self.kitbase,58);a.write(0xC199BD90,self.kitroot)
        self.hardstops=[];self.releases=[]

    def observe(self,uc,address,size,user):
        a=self.a;off=address-BASE
        if off==0x1F6958:
            sp=a.get('SP');selection=self.word(sp+8);layer=self.word(sp+12);side=self.word(sp+16)
            row=selection+4+20*layer;keyptr=self.word(row+4);desc=self.word(row+8)
            self.prepared.append(dict(layer=layer,side=side,slot=(desc-keyptr)//12,weight=self.half(row),
                key=(keyptr-self.kitptr-24)//68,selection_note=self.half(selection),selection_pitch=self.half(selection+2)))
        elif off==0x1F7278:
            v=a.get('R0');self.started.append(dict(address=v,sample_ptr=self.word(v+0x20),key_ptr=self.word(v+0x28),desc_ptr=self.word(v+0x24),
                layer_level=bytes(a.uc.mem_read(0xC165D9A4,1))[0],level_correction=sb(bytes(a.uc.mem_read(0xC165D9A5,1)),0),
                max_level=bytes(a.uc.mem_read(0xC165D9B8,1))[0],root=s32(self.word(0xC165D9B0)),
                tune=s32(self.word(0xC165D9AC)),pitch=s32(self.word(0xC165D9A8))))
        elif off==0x1F9028:self.sample_starts.append(a.get('R0'))
        elif off==0x2857B8:self.reverse_requests.append([a.get('R1'),a.get('R2')])
        elif off==0x1FD53C:self.hardstops.append((a.get('R1')-self.voices)//588)
        elif off==0x1F7CC8:self.releases.append((a.get('R0')-self.voices)//588)

    def prepare(self,record,osc=0):
        a=self.a;self.record=bytes(record);self.oscillator=0;self.kit=h(record,0x566)
        self.kitptr=self.kitbase+KIT_STRIDE*self.kit;self.kitraw=self.raw[KIT_OFFSET+KIT_STRIDE*self.kit:KIT_OFFSET+KIT_STRIDE*(self.kit+1)]
        a.uc.mem_write(self.patch,self.record)
        for ptr,n in [(self.osc,0x500),(self.context,0x200),(self.part,0x40),(self.channel,0x200),
                      (self.controls,128),(self.manager,0x100),(self.keycontrols,128*12)]:a.uc.mem_write(ptr,bytes(n))
        a.write(self.osc+8,self.patch+0x564);a.write(self.osc+0x48C,self.manager);a.write(self.osc+0x49C,self.context)
        a.write(self.osc+0x490,self.osc+0x490,self.osc+0x490,0)
        a.write(self.context+4,self.part,self.patch,self.patch+0x520,self.channel);a.write(self.context+0x8C,self.controls)
        a.write(self.channel+0x138,self.keycontrols)
        for off in [0x2E,0x4F,0x50]:self.put8(self.context+off,255)
        self.put8(self.part+5,127);a.write(self.context+0x30,0xFFFFFFFF);a.write(self.clock,0,123)
        a.call(0x1F6654,self.osc)
        assert self.word(self.osc+0x10)==self.kitptr
        self.remap=[]
        for note in range(128):
            target=next((k for k in range(note,128) if self.kitraw[24+68*k+65]&1),None)
            self.remap.append(-1 if target is None else target-note)
        assert list(struct.unpack('<128b',a.uc.mem_read(self.osc+24,128)))==self.remap
        assert bytes(a.uc.mem_read(self.keycontrols,128*12))==bytes([64]*7+[127,255,255,255,0])*128
        a.write(self.manager+4,self.voices);a.write(self.manager+0x3C,self.nodes,self.members,8,0)
        a.write(self.manager+0xCC,self.manager+0xCC,self.manager+0xCC,0,self.waitnodes,8)
        a.uc.mem_write(self.voices,bytes(8*588));a.uc.mem_write(0xC165DA38,bytes(24));a.call(0x1FEDE4)
        for i in range(8):
            v=self.voices+588*i;a.call(0x1F68D4,v);self.put8(v+0x16,i);self.put8(v+0x1A,i);a.write(v+0x1C,self.tg);a.write(v+0x240,0xFFFFFFFF)
            for nodes in [self.nodes,self.members,self.waitnodes]:a.write(nodes+12*i,0,0,v)
        a.call(0x1FBF4C,self.manager+12);a.write(0xC1B5848C,0x12345678)
        self.clear()

    def clear(self):
        for attr in ['writes','reads','prepared','started','sample_starts','reverse_requests','hardstops','releases']:getattr(self,attr).clear()

    def expected_layers(self,note,velocity):
        p=self.record;b=p[0x564:0x6E0];lo,hi=sorted(p[0x518:0x51A]);vl,vh=sorted(b[0x2D:0x2F])
        if not lo<=note<=hi or not vl<=velocity<=vh:return []
        transpose=sb(bytes([(12*sb(b,0x78)+b[0x79])&255]),0);key=fold(note+transpose);distance=self.remap[key]
        if distance<0:return []
        key+=distance;k=self.kitraw[24+68*key:24+68*(key+1)]
        if not k[65]&4:return []
        pitch=selection_pitch((60-distance)&255,0,sb(b,0x7C));slot=next((i for i in range(3) if velocity>=k[48+4*i]),3)
        rows=[dict(slot=slot,weight=32768)];width=k[49+4*slot] if slot<3 else 0
        if width and velocity<k[48+4*slot]+width:
            first=(velocity-k[48+4*slot])*32768//width;second=32768-first;curve=k[50+4*slot]&3
            if curve==2:first=second=32768
            elif curve==1:
                def shape(x):
                    if x>=32768:return x
                    index,fraction=divmod(x,256);low=h(self.f.data,0x40585C+2*index);high=h(self.f.data,0x40585C+2*(index+1))
                    return low+((high-low)*fraction>>8)
                first,second=shape(first),shape(second)
            rows[0]['weight']=first;rows.append(dict(slot=slot+1,weight=second))
        expected=[]
        for layer,row in enumerate(rows):
            desc=k[12*row['slot']:12*(row['slot']+1)];bank=desc[1];number=h(desc,2);assert bank in [0,1]
            indices=[number] if bank==0 else self.drum_pairs[number]
            for side,drum in enumerate(indices):
                sample=sh(self.f.data,0x408BFC+32*drum)
                expected.append(dict(layer=layer,side=side,key=key,drumsample=drum,sample=sample,pitch=pitch,valid=bool(desc[0]&1),**row))
        return expected

    def select(self,note,velocity):
        expected=self.expected_layers(note,velocity);n=self.a.call(0x1FD718,self.manager,self.osc,note,velocity,stack=(self.selection,))
        layers=[x for x in expected if x['side']==0];assert n==len(layers),(self.kit,note,velocity,n,layers)
        if layers:
            assert self.half(self.selection)==note and self.half(self.selection+2)==layers[0]['pitch']
        for i,row in enumerate(layers):
            ptr=self.selection+4+20*i;keyptr=self.kitptr+24+68*row['key']
            assert (self.half(ptr),self.word(ptr+4),self.word(ptr+8),self.word(ptr+12),bytes(self.a.uc.mem_read(ptr+16,1))[0])==(
                row['weight'],keyptr,keyptr+12*row['slot'],self.keycontrols+12*row['key'],int(sum(x['layer']==i for x in expected)==2))
        return layers

    def active(self):
        result=[];head=self.osc+0x490;node=self.word(head)
        while node!=head:
            assert len(result)<8
            v=self.word(node+8);assert v;result.append((v-self.voices)//588);node=self.word(node)
        return result

    def note(self,note,velocity):
        self.clear();self.put8(self.context+0x44,note);self.put8(self.context+0x45,velocity)
        expected=self.expected_layers(note,velocity);self.a.uc.mem_write(0x111E0000,bytes(0x10000))
        self.a.call(0x1F62F0,self.osc,0x90+(note<<8)+(velocity<<16));self.a.call(0x1FEDB8,0xC165DA38)
        attempted=[];failed_layer=None
        for row in expected:
            if row['layer']==failed_layer:continue
            attempted.append(row)
            if not row['valid']:failed_layer=row['layer']
        assert len(self.prepared)==len(attempted),(self.kit,note,velocity,self.prepared,expected)
        for actual,wanted in zip(self.prepared,attempted):
            assert all(actual[k]==wanted[k] for k in ['layer','side','slot','weight','key']),(actual,wanted)
            assert (actual['selection_note'],actual['selection_pitch'])==(note,wanted['pitch'])
        valid=[x for x in attempted if x['valid']];assert len(self.started)==len(valid),(self.started,valid)
        rows=[]
        for start,row in zip(self.started,valid):
            v=start['address'];key=row['key'];k=self.kitraw[24+68*key:24+68*(key+1)];desc=k[12*row['slot']:12*(row['slot']+1)]
            drum=self.f.data[0x408BFC+32*row['drumsample']:0x408BFC+32*(row['drumsample']+1)]
            level=127*row['weight']>>15;tune=2*(100*sb(desc,6)+sb(desc,7));correction=sb(desc,4)
            assert (start['sample_ptr'],start['key_ptr'],start['desc_ptr'])==(BASE+0x410ABC+64*row['sample'],self.kitptr+24+68*key,self.kitptr+24+68*key+12*row['slot'])
            assert (start['root'],start['tune'],start['pitch'],start['layer_level'],start['level_correction'],start['max_level'])==(
                60*256,tune,row['pitch'],level,correction,drum[28]),(start,row,desc.hex())
            pair_type=self.word(v+0x218);gain=self.math.multisample_gain(level,correction,sb(drum,28))
            assert self.half(v+0x200)==(0 if pair_type==2 else gain),(row,pair_type,self.half(v+0x200),gain)
            reverse=desc[5]>>7
            if reverse:reverse=int(all(self.drum_caps[j] for j in ([h(desc,2)] if not desc[1]&1 else self.drum_pairs[h(desc,2)])))
            release=int(not (self.record[0x508]&64 and self.record[0x50D]<=note<=self.record[0x50E] and not k[65]&8))
            assert bytes(self.a.uc.mem_read(v+0x20C,2))==bytes([reverse,release])
            assert self.word(v+0x228)==self.keycontrols+12*key and self.word(v+0x238)==row['sample']
            tracking=[self.math.keyboard_tracking(self.record[0x660:0x667],note),self.math.keyboard_tracking(self.record[0x6A0:0x6A7],note,True),
                      self.math.keyboard_tracking(self.record[0x554:0x55B],note),self.math.keyboard_tracking(self.record[0x55C:0x563],note)]
            assert [sh(bytes(self.a.uc.mem_read(v+off,2)),0) for off in [0x204,0x206,0x212,0x214]]==tracking
            sample=self.f.data[0x410ABC+64*row['sample']:0x410ABC+64*(row['sample']+1)]
            start_offset=bytes(self.a.uc.mem_read(v+0x20A,1))[0];boundary=drum[3]
            assert bytes(self.a.uc.mem_read(v+0x20B,1))[0]==boundary
            regs={}
            if v in self.sample_starts:
                field=12 if not start_offset else 56 if start_offset-boundary+8==7 else 60 if start_offset-boundary+8==8 else 16 if start_offset==1 else 32+4*(start_offset-1)
                flags=sample[7];startaddr=w(sample,20);loop=w(sample,field)
                if flags&8:
                    loop=w(sample,24)
                    if flags&32:startaddr=w(sample,12)
                    elif reverse:flags|=32
                elif reverse:startaddr=w(sample,28);loop=w(sample,32);flags|=40
                regs={0x200:((flags>>2)&14)|(flags&1),0x208:startaddr,0x20C:(w(sample,24)-1)&0xFFFFFFFF,0x210:loop}
                actual={off:value for slot,off,value in self.writes if slot==bytes(self.a.uc.mem_read(v+0x1A,1))[0] and off in regs}
                assert actual==regs,(row,actual,regs)
            rows.append(dict(**row,voice_slot=(v-self.voices)//588,pair_type=pair_type,layer_level=level,level_correction=correction,
                gain=self.half(v+0x200),tune=tune,reverse=reverse,release=release,exclusive=k[64],key_flags=k[65],start_offset=start_offset,
                max_level=sb(drum,28),amp_target=self.half(v+0x150),pitch_increment=self.word(v+0x9C),
                filter_route=bytes(self.a.uc.mem_read(v+0x116,1))[0],pan_target=self.half(v+0x1C0),
                sample_registers={hex(k):v for k,v in regs.items()}))
        return dict(note=note,velocity=velocity,voices=rows,active=self.active(),hardstops=list(self.hardstops),tg_start_calls=len(self.sample_starts))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');parser.add_argument('--smoke',action='store_true');args=parser.parse_args()
    f=Firmware();raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    for name,lo,hi in [('drum-kit-remap',0x1F5A80,0x1F5B24),('drum-exclusive',0x1F5C30,0x1F5CF4),
                       ('drum-note-on',0x1F62F0,0x1F6580),('drum-key-controls',0x26E094,0x26E0EC),('drum-provider',0x285B28,0x285B40)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f,raw);factory=[];kits=[];counts=collections.Counter();programs=[]
    for i in range(768):
        record=raw[0x1EF220+2140*i:0x1EF220+2140*(i+1)]
        if record[0x508]&7==2:programs.append((chr(65+i//128)+str(i%128).zfill(3),record))
    for name,record in programs[:1] if args.smoke else programs:
        r.prepare(record);kit=r.kit;remap=list(r.remap);assigned=[k for k in range(128) if r.kitraw[24+68*k+65]&1]
        digest=hashlib.sha256()
        for note in range(128):
            for velocity in ([1,64,127] if args.smoke else range(1,128)):
                layers=r.select(note,velocity);counts['selection_cases']+=1
                digest.update(json.dumps([note,velocity,layers],sort_keys=True,separators=(',',':')).encode())
        kits.append(dict(program=name,kit=kit,name=r.kitraw[:24].decode('ascii').rstrip(' \0'),remap=remap,assigned_keys=assigned,selection_sha256=digest.hexdigest()))
        for note in assigned[:3] if args.smoke else assigned:
            k=r.kitraw[24+68*note:24+68*(note+1)];velocities={100}
            for slot in range(3):
                bottom,width=k[48+4*slot:50+4*slot];velocities.update([bottom-1,bottom,bottom+width//2,bottom+width-1,bottom+width])
            for velocity in sorted(v for v in velocities if 1<=v<=127):
                r.prepare(record);state=r.note(note,velocity);factory.append(dict(program=name,kit=kit,**state))
                counts['startup_cases']+=1;counts['voices']+=len(state['voices']);counts['starts']+=state['tg_start_calls']
        counts['kits']+=1;counts['assigned_keys']+=len(assigned);print(name,dict(counts),flush=True)
    choke=[];release=[]
    for name,record in programs[:1] if args.smoke else programs:
        r.prepare(record);groups=collections.defaultdict(list);release_keys={}
        for key in range(128):
            k=r.kitraw[24+68*key:24+68*(key+1)]
            layers=r.expected_layers(key,100)
            if not k[65]&1 or not any(x['valid'] for x in layers):continue
            groups[k[64]].append(key);release_keys.setdefault(bool(k[65]&8),key)
        for group,keys in sorted(groups.items()):
            if len(keys)<2:continue
            r.prepare(record);first=r.note(keys[0],100);old=set(first['active'])
            second=r.note(keys[-1],100);new={v['voice_slot'] for v in second['voices']}
            expected_stops=old if group else set()
            assert set(second['hardstops'])==expected_stops,(name,group,first,second)
            assert set(second['active'])==(old-expected_stops)|new,(name,group,first,second)
            assert r.word(r.manager+0x48)==8-len(second['active'])
            choke.append(dict(program=name,kit=r.kit,group=group,first=first,second=second))
        for obey_note_off,key in sorted(release_keys.items()):
            r.prepare(record);state=r.note(key,100);before={v['voice_slot']:bytes(r.a.uc.mem_read(r.voices+588*v['voice_slot']+0x15C,100)) for v in state['voices']}
            r.clear();r.a.call(0x1F60A4,r.osc,0x80+(key<<8)+(64<<16));voices=[]
            for v in state['voices']:
                ptr=r.voices+588*v['voice_slot'];flags=r.half(ptr+0x10)
                assert not flags&128 and flags&1 and bool(flags&4)==bool(v['release']),(name,key,v,flags)
                unchanged=before[v['voice_slot']]==bytes(r.a.uc.mem_read(ptr+0x15C,100))
                if not v['release']:assert unchanged
                voices.append(dict(voice_slot=v['voice_slot'],release=v['release'],flags=flags,amp_unchanged=unchanged))
            assert set(r.releases)==set(v['voice_slot'] for v in state['voices'])
            release.append(dict(program=name,kit=r.kit,note=key,key_obeys_note_off=obey_note_off,voices=voices,writes=list(r.writes)))
    counts['choke_sequences']=len(choke);counts['release_cases']=len(release)
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_factory_voice_chain.py','firmware_voice_lfo.py','voice_math.py']},
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],counts=dict(counts),stereo_pairs=r.drum_pairs,reverse_capabilities=r.drum_caps,
        kits=kits,factory=factory,choke_sequences=choke,release_cases=release,boundaries=['Original directory/capability construction and kit provider lookup execute on private factory resource copies',
            'Original OSC refresh creates the remap and neutral per-key controls; no kit getter or sound computation is intercepted',
            'All 128 notes and 127 nonzero velocities are checked per kit; startup cases use assigned keys at threshold/crossfade boundaries and velocity 100',
            'Original OSC note-on, layer selection, allocation, real drumsample/sample builder, full control initialization, choke dispatch, list attach and TG start execute together',
            'Independent checks cover remap, selected layers, weights, drumsample/sample addresses, level/tuning, reverse/release permission, tracking and sample TG words',
            'Fresh eight-voice pool per startup case; TG reads return zero, primitive bus writes/reads are intercepted; no hardware or rendered audio',
            'Two distinct-key note-ons per populated exclusive group (including group zero) check native hard-stop and surviving active voices; original note-off checks representative key flags per kit',
            'GM special-remap mode, expansion banks, arbitrary per-key edits and normal continuous refresh remain separate coverage'])
    destination=OUT/('drum-voice-chain-smoke.json' if args.smoke else 'drum-voice-chain-check.json');destination.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,counts=dict(counts),pairs=len(r.drum_pairs),reverse_allowed=sum(r.drum_caps))))
if __name__=='__main__':main()
