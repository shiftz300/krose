#!/usr/bin/env python3
"""Expansion Programs through native material refresh, allocation and TG start."""
import argparse,collections,contextlib,hashlib,io,json,struct
from pathlib import Path
from firmware_factory_voice_chain import Rig as FactoryRig,selection_pitch,sb
from firmware_expansion_pcm import read_library
from firmware_voice_lfo import sha,PRELOAD,OUT,h,sh,w
from program_firmware import Firmware,BASE,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

class Rig(FactoryRig):
    def __init__(self,f,libraries):
        super().__init__(f);a=self.a;a.uc.mem_map(0x12000000,0x400000)
        self.sources={0:dict(samples=f.data[0x410ABC:0x410ABC+4070*64],regions=f.data[0x492C28:0x492C28+5570*20],
            multisamples=f.data[0x48F5CC:0x48F5CC+497*28],drums=f.data[0x408BFC:0x408BFC+1014*32],
            sample_ptr=BASE+0x410ABC,region_ptr=BASE+0x492C28,ms_ptr=BASE+0x48F5CC,drum_ptr=BASE+0x408BFC,
            pairs=list(self.pairs),caps=list(self.reverse_caps),library=0)}
        a.write(self.banks+0x20,1014);a.write(self.banks+0x30,BASE+0x408BFC)
        for slot,lib in enumerate(libraries,1):
            logical=lib['id']+1;base=0x12000000+(slot-1)*0x100000;ns=len(lib['samples']);nr=lib['region_count'];nm=len(lib['multisamples']);nd=lib['declared_drumsamples']
            raw=lib['raw_prm'];rp=64*ns;mp=rp+20*nr;dp=mp+28*nm;a.uc.mem_write(base,raw)
            header=self.banks+52*slot;a.write(header+0x14,ns,nr,nm,nd);a.write(header+0x24,base,base+rp,base+mp,base+dp if nd else 0)
            a.write(self.banks+0x1A34+8*slot,logical,slot)
            mono=base+0x80000;stereo=base+0x80020;ma=base+0x81000;sa=base+0x82000;encoded=2*logical
            a.write(mono,ma,nm);a.write(stereo,sa,nm//2);a.write(self.registry+4*encoded,mono,stereo)
            a.call(0x283AF8,mono,encoded,0);a.call(0x283E04,stereo,encoded+1,mono,0)
            pairs=[[self.half(self.word(sa+4*i)+4)&32767,self.half(self.word(sa+4*i)+6)&32767] for i in range(self.word(stereo+4))]
            self.sources[logical]=dict(samples=raw[:rp],regions=raw[rp:mp],multisamples=raw[mp:dp],drums=raw[dp:],
                sample_ptr=base,region_ptr=base+rp,ms_ptr=base+mp,drum_ptr=base+dp,pairs=pairs,
                caps=[bool(a.call(0x285758,self.registry,encoded,i)) for i in range(nm)],library=lib['id'])
        for logical,source in self.sources.items():
            base=0x12300000+logical*0x10000;count=len(source['drums'])//32
            if not count:source.update(drum_pairs=[],drum_caps=[]);continue
            mono=base;stereo=base+32;ma=base+0x100;sa=base+0x2000;encoded=2*logical
            a.write(mono,ma,count);a.write(stereo,sa,count//2);a.write(self.registry+0x400+4*encoded,mono,stereo)
            a.call(0x283AF8,mono,encoded,1);a.call(0x283E04,stereo,encoded+1,mono,1,count=4000000)
            source['drum_pairs']=[[self.half(self.word(sa+4*i)+4)&32767,self.half(self.word(sa+4*i)+6)&32767] for i in range(self.word(stereo+4))]
            source['drum_caps']=[bool(a.call(0x2857B8,self.registry,encoded,i)) for i in range(count)]
        self.kitroot=0x11005400;self.kitarray=0x11005420;self.kitprovider=0x11005440;self.kitbase=0x11100000;self.keycontrols=0x11020000;self.selection=0x11021000
        raw=bytearray(PRELOAD.read_bytes()[0x48BE20:0x48BE20+58*8728]);future=libraries[-1];section=future['sections']['1KBD']
        kits=future['decoded_bytes'][section['payload_offset']:section['payload_offset']+section['bytes']];raw[42*8728:46*8728]=kits
        self.kit_bytes=bytes(raw);a.uc.mem_write(self.kitbase,self.kit_bytes)
        a.write(self.kitroot,self.kitarray,1);a.write(self.kitarray,self.kitprovider);a.write(self.kitprovider,BASE+0x472080,self.kitbase,58);a.write(0xC199BD90,self.kitroot)
    def prepare(self,record,osc=0):
        a=self.a;self.record=bytes(record);self.oscillator=osc;self.drum=(record[0x508]&7)==2
        a.uc.mem_write(self.patch,self.record)
        for p,n in [(self.osc,0x500),(self.context,0x200),(self.part,64),(self.channel,0x200),(self.controls,128),(self.manager,0x100)]:a.uc.mem_write(p,bytes(n))
        a.write(self.osc+8,self.patch+0x564+380*osc);a.write(self.osc+0x48C,self.manager);a.write(self.osc+0x49C,self.context);self.put8(self.osc+4,osc)
        a.write(self.context+4,self.part,self.patch,self.patch+0x520,self.channel);a.write(self.context+0x8C,self.controls)
        for at in [0x2E,0x4F,0x50]:self.put8(self.context+at,255)
        self.put8(self.part+5,127);a.write(self.context+0x30,0xFFFFFFFF);a.write(self.clock,0,123)
        if self.drum:
            self.kit=h(record,0x566);assert 42<=self.kit<=45;self.kitptr=self.kitbase+8728*self.kit;self.kitraw=self.kit_bytes[8728*self.kit:8728*(self.kit+1)]
            a.uc.mem_write(self.keycontrols,bytes(128*12));a.write(self.channel+0x138,self.keycontrols)
        a.call(0x1F6654,self.osc)
        if self.drum:
            assert self.word(self.osc+16)==self.kitptr
            self.remap=[]
            for note in range(128):
                target=next((i for i in range(note,128) if self.kitraw[24+68*i+65]&1),None);self.remap.append(-1 if target is None else target-note)
            assert list(struct.unpack('<128b',a.uc.mem_read(self.osc+24,128)))==self.remap
        a.write(self.manager+4,self.voices);a.write(self.manager+0x3C,self.nodes,self.members,8,0)
        a.write(self.manager+0xCC,self.manager+0xCC,self.manager+0xCC,0,self.waitnodes,8);a.uc.mem_write(self.voices,bytes(8*588));a.uc.mem_write(0xC165DA38,bytes(24))
        for i in range(8):
            v=self.voices+588*i;a.call(0x1F68D4,v);self.put8(v+0x16,i);self.put8(v+0x1A,i);a.write(v+0x1C,self.tg);a.write(v+0x240,0xFFFFFFFF)
            for nodes in [self.nodes,self.members,self.waitnodes]:a.write(nodes+12*i,0,0,v)
        a.call(0x1FBF4C,self.manager+12);a.write(0xC1B5848C,0x12345678);self.clear()
    def clear(self):
        for name in ['writes','reads','prepared','started','sample_starts','reverse_requests']:getattr(self,name).clear()
    def observe(self,uc,address,size,user):
        if address-BASE!=0x1F6958:return super().observe(uc,address,size,user)
        a=self.a;sp=a.get('SP');sel=self.word(sp+8);layer=self.word(sp+12);side=self.word(sp+16);row=sel+4+20*layer
        if not self.drum:descriptor=self.word(row+4);slot=(descriptor-(self.patch+0x564+380*self.oscillator))//8
        else:descriptor=self.word(row+8);slot=(descriptor-self.word(row+4))//12
        self.prepared.append(dict(layer=layer,side=side,slot=slot,weight=self.half(row),selection_note=self.half(sel),selection_pitch=self.half(sel+2)))
    def expected_layers(self,note,velocity):
        p=self.record;b=p[0x564+380*self.oscillator:0x564+380*(self.oscillator+1)];lo,hi=sorted(p[0x518+2*self.oscillator:0x51A+2*self.oscillator]);vl,vh=sorted(b[0x2D:0x2F])
        if not lo<=note<=hi or not vl<=velocity<=vh:return []
        transpose=sb(bytes([(12*sb(b,0x78)+b[0x79])&255]),0);key=None
        if self.drum:
            from firmware_factory_voice_chain import fold
            folded=fold(note+transpose);distance=self.remap[folded]
            if distance<0:return []
            key=folded+distance;params=self.kitraw[24+68*key:24+68*(key+1)]
            if not params[65]&4:return []
            pitch=selection_pitch((60-distance)&255,0,sb(b,0x7C));threshold=48;stride=12
        else:params=b;pitch=selection_pitch(note,transpose,sb(b,0x7C));threshold=32;stride=8
        slot=next((i for i in range(3) if velocity>=params[threshold+4*i]),3);rows=[dict(slot=slot,weight=32768)];width=params[threshold+4*slot+1] if slot<3 else 0
        if width and velocity<params[threshold+4*slot]+width:
            first=(velocity-params[threshold+4*slot])*32768//width;second=32768-first;curve=params[threshold+4*slot+2]&3
            if curve==2:first=second=32768
            elif curve==1:
                def shape(x):
                    if x>=32768:return x
                    i,frac=divmod(x,256);low=h(self.f.data,0x40585C+2*i);high=h(self.f.data,0x40585C+2*i+2);return low+((high-low)*frac>>8)
                first,second=shape(first),shape(second)
            rows[0]['weight']=first;rows.append(dict(slot=slot+1,weight=second))
        result=[]
        for layer,row in enumerate(rows):
            desc=params[stride*row['slot']:stride*(row['slot']+1)];encoded=desc[1];logical=encoded>>1;number=h(desc,2);valid=bool(desc[0]&(1 if self.drum else 3));source=self.sources.get(logical)
            if source is None:
                result.append(dict(layer=layer,side=0,slot=row['slot'],weight=row['weight'],pitch=pitch,key=key,bank=logical,valid=valid,missing_bank=True));continue
            indices=[number] if not encoded&1 else source['drum_pairs' if self.drum else 'pairs'][number]
            for side,index in enumerate(indices):
                region=None;sample_bank=logical;sample=None
                if self.drum:
                    sample=h(source['drums'],32*index) if valid else None
                elif valid:
                    first,count=struct.unpack_from('<HB',source['multisamples'],28*index);previous=-1
                    for i in range(count):
                        top=sb(source['regions'],20*(first+i)+3)
                        if previous<(pitch>>8)<=top and top>0 or pitch>>8==0 and top==0:region=first+i;break
                        previous=top
                    if region is not None:sample=h(source['regions'],20*region);sample_bank=source['regions'][20*region+2]
                result.append(dict(layer=layer,side=side,index=index,bank=logical,sample_bank=sample_bank,sample=sample,region=region,key=key,pitch=pitch,valid=valid,missing_bank=False,**row))
        return result
    def select(self,note,velocity):
        expected=self.expected_layers(note,velocity);rows=[x for x in expected if x['side']==0]
        count=self.a.call(0x1FD718,self.manager,self.osc,note,velocity,stack=(self.selection,));assert count==len(rows)
        for i,row in enumerate(rows):
            at=self.selection+4+20*i;descriptor=self.word(at+8 if self.drum else at+4)
            expected_ptr=self.kitptr+24+68*row['key']+12*row['slot'] if self.drum else self.patch+0x564+380*self.oscillator+8*row['slot']
            assert descriptor==expected_ptr and self.half(at)==row['weight'] and self.half(self.selection+2)==row['pitch']
        return expected
    def note(self,note,velocity):
        self.clear();self.put8(self.context+0x44,note);self.put8(self.context+0x45,velocity);expected=self.expected_layers(note,velocity)
        if any(x['valid'] and x['missing_bank'] for x in expected):return dict(note=note,velocity=velocity,deferred_missing_bank=True,selection=expected,voices=[],tg_start_calls=0)
        returned=self.a.call(0x1FDC8C,self.manager,0x90+(note<<8)+(velocity<<16),self.osc,0,stack=(0xFFFFFFFF,))&0xFFFFFFFF
        attempted=[];failed=None
        for row in expected:
            if row['layer']==failed:continue
            attempted.append(row)
            if not row['valid'] or row['sample'] is None:failed=row['layer']
        assert len(self.prepared)==len(attempted),(note,velocity,self.prepared,expected)
        for actual,row in zip(self.prepared,attempted):
            assert all(actual[k]==row[k] for k in ['layer','side','slot','weight']) and (actual['selection_note'],actual['selection_pitch'])==(note,row['pitch'])
        valid=[x for x in attempted if x['valid'] and x['sample'] is not None];assert len(self.started)==len(valid),(self.started,valid);rows=[]
        block=self.record[0x564+380*self.oscillator:0x564+380*(self.oscillator+1)]
        for start,row in zip(self.started,valid):
            v=start['address'];source=self.sources[row['bank']];sample_source=self.sources[row['sample_bank']];sample=row['sample'];sample_raw=sample_source['samples'][64*sample:64*(sample+1)]
            if self.drum:
                key=self.kitraw[24+68*row['key']:24+68*(row['key']+1)];desc=key[12*row['slot']:12*(row['slot']+1)];drum=source['drums'][32*row['index']:32*(row['index']+1)]
                level=127*row['weight']>>15;root=15360;tune=2*(100*sb(desc,6)+sb(desc,7));correction=sb(desc,4);extra=sb(drum,28);boundary=drum[3]
                assert self.word(v+0x28)==self.kitptr+24+68*row['key'] and self.word(v+0x24)==self.kitptr+24+68*row['key']+12*row['slot']
                release=int(not (self.record[0x508]&64 and self.record[0x50D]<=note<=self.record[0x50E] and not key[65]&8))
                assert bytes(self.a.uc.mem_read(v+0x20D,1))[0]==release
            else:
                reg=source['regions'][20*row['region']:20*(row['region']+1)];desc=block[8*row['slot']:8*(row['slot']+1)]
                level=desc[4]*row['weight']>>15;root=sb(reg,4)<<8;tune=sh(reg,6);correction=sb(reg,8);extra=0;boundary=source['multisamples'][28*row['index']+3]
                assert start['region_ptr']==source['region_ptr']+20*row['region']
            assert start['sample_ptr']==sample_source['sample_ptr']+64*sample
            assert (start['layer_level'],start['root'],start['tune'],start['pitch'])==(level,root,tune,row['pitch'])
            pair=self.word(v+0x218);gain=self.math.multisample_gain(level,correction,extra);assert self.half(v+0x200)==(0 if pair==2 else gain)
            reverse=desc[5]>>7
            if reverse:
                caps=source['drum_caps' if self.drum else 'caps'];indices=source['drum_pairs' if self.drum else 'pairs'][h(desc,2)] if desc[1]&1 else [h(desc,2)];reverse=int(all(caps[i] for i in indices))
            assert bytes(self.a.uc.mem_read(v+0x20C,1))[0]==reverse
            tracking=[self.math.keyboard_tracking(block[0xFC:0x103],note),self.math.keyboard_tracking(block[0x13C:0x143],note,True),self.math.keyboard_tracking(self.record[0x554:0x55B],note),self.math.keyboard_tracking(self.record[0x55C:0x563],note)]
            assert [sh(bytes(self.a.uc.mem_read(v+at,2)),0) for at in [0x204,0x206,0x212,0x214]]==tracking
            registers={};start_offset=bytes(self.a.uc.mem_read(v+0x20A,1))[0]
            assert bytes(self.a.uc.mem_read(v+0x20B,1))[0]==boundary
            if v in self.sample_starts:
                field=12 if not start_offset else 56 if start_offset-boundary+8==7 else 60 if start_offset-boundary+8==8 else 16 if start_offset==1 else 32+4*(start_offset-1)
                flags=sample_raw[7];start_address=w(sample_raw,20);loop=w(sample_raw,field)
                if flags&8:
                    loop=w(sample_raw,24)
                    if flags&32:start_address=w(sample_raw,12)
                    elif reverse:flags|=32
                elif reverse:start_address=w(sample_raw,28);loop=w(sample_raw,32);flags|=40
                registers={0x200:((flags>>2)&14)|(flags&1),0x208:start_address,0x20C:(w(sample_raw,24)-1)&0xFFFFFFFF,0x210:loop}
                slot=bytes(self.a.uc.mem_read(v+0x1A,1))[0];actual={off:value for s,off,value in self.writes if s==slot and off in registers};assert actual==registers,(row,actual,registers)
            library=sample_source['library'];file=(f'research/output/Factory_ROM_WAV/samples/{sample:04d}.wav' if library==0 else f'research/output/OASYS_Piano_WAV/{10000+sample}.wav' if library==1 else f'research/output/Expansion_PCM_WAV/EXPCM{library:03d}/{sample:04d}.wav')
            assert (ROOT/file).is_file(),file
            rows.append(dict(**row,voice_slot=(v-self.voices)//588,pair_type=pair,partner_slot=(self.word(v+0x230)-self.voices)//588 if self.word(v+0x230) else None,
                level=level,region_correction=correction,extra_correction=extra,gain=self.half(v+0x200),root=root,tune=tune,reverse=reverse,
                start_offset=start_offset,delay=sh(bytes(self.a.uc.mem_read(v+0x208,2)),0),amp_target=self.half(v+0x150),pitch_increment=self.word(v+0x9C),
                sample_registers={hex(k):v for k,v in registers.items()},source_wav=file))
        assert self.word(self.manager+0x48)==8-len(rows);chain=[];node=returned
        while node:
            assert len(chain)<8;chain.append((self.word(node+8)-self.voices)//588);node=self.word(node)
        assert set(chain)=={x['voice_slot'] for x in rows}
        byslot={row['voice_slot']:row for row in rows}
        for row in rows:
            if row['pair_type']==1:
                partner=byslot[row['partner_slot']];assert partner['pair_type']==2 and partner['partner_slot']==row['voice_slot']
                for at,n in [(0xBC,48),(0x120,48),(0x15C,100),(0xEC,51),(0x1F0,16),(0x150,10)]:assert bytes(self.a.uc.mem_read(self.voices+588*row['voice_slot']+at,n))==bytes(self.a.uc.mem_read(self.voices+588*partner['voice_slot']+at,n))
        return dict(note=note,velocity=velocity,deferred_missing_bank=False,selection=expected,voices=rows,tg_start_calls=len(self.sample_starts))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');parser.add_argument('--smoke',action='store_true');args=parser.parse_args();f=Firmware();libs=[read_library(n) for n in [1,2,4]]
    for name,lo,hi in [('expansion-voice-material',0x1F6654,0x1F67C4),('expansion-voice-region',0x1F6DA0,0x1F6FAC)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f,libs);melodic=[];drums=[];selection=[];kit_links=[];counts=collections.Counter();inputs=[PRELOAD,OUT/'expansion-pcm-check.json']
    for lib in libs:
        inputs.extend(lib['inputs']);bank=lib['sections']['1KBP'];chosen=lib['programs'][:1] if args.smoke else lib['programs']
        if args.smoke and lib['id']==4:chosen=chosen+lib['programs'][41:45]
        for program in chosen:
            path=ROOT/program['path'];raw=path.read_bytes();assert sha(path)==program['sha256'];assert raw==lib['decoded_bytes'][bank['payload_offset']+2144*program['index']:bank['payload_offset']+2144*(program['index']+1)]
            inputs.append(path);mode=raw[0x508]&7;identity=f"EXPCM{lib['id']:03d}:{program['index']:03d}"
            if mode!=2:
                counts['melodic_programs']+=1
                for osc in range(1+mode):
                    counts['melodic_oscillators']+=1;b=raw[0x564+380*osc:0x564+380*(osc+1)];lo,hi=sorted(raw[0x518+2*osc:0x51A+2*osc]);vl,vh=sorted(b[0x2D:0x2F]);velocities={max(1,vl),max(1,(vl+vh)//2),vh}
                    for slot in range(3):
                        bottom,width=b[32+4*slot:34+4*slot];velocities.update([bottom-1,bottom,bottom+width//2,bottom+width])
                    for note in ([max(lo,min(60,hi))] if args.smoke else sorted({lo,(lo+hi)//2,hi})):
                        for velocity in sorted(v for v in velocities if max(1,vl)<=v<=vh):
                            r.prepare(raw,osc);state=r.note(note,velocity);melodic.append(dict(program=identity,name=program['name'],oscillator=osc+1,**state))
            else:
                counts['drum_programs']+=1;r.prepare(raw);kit_links.append(dict(program=identity,name=program['name'],stored_kit=r.kit,fixture_kit_index=r.kit-42,fixture_kit_name=r.kitraw[:24].decode('ascii').rstrip(' \0')))
                digest=hashlib.sha256()
                for note in range(128):
                    for velocity in ([1,64,127] if args.smoke else range(1,128)):
                        expected=r.select(note,velocity);counts['drum_selection_cases']+=1;digest.update(json.dumps([note,velocity,expected],sort_keys=True).encode())
                selection.append(dict(program=identity,sha256=digest.hexdigest()))
                for note in range(128):
                    velocities={1,64,127};base=r.expected_layers(note,64)
                    if base:
                        key=r.kitraw[24+68*base[0]['key']:24+68*(base[0]['key']+1)]
                        for slot in range(3):
                            bottom,width=key[48+4*slot:50+4*slot];velocities.update([bottom-1,bottom,bottom+width//2,bottom+width])
                    for velocity in sorted(v for v in velocities if 1<=v<=127):
                        r.prepare(raw);state=r.note(note,velocity);drums.append(dict(program=identity,name=program['name'],**state))
            print('Expansion voice checked',identity,flush=True)
    for label,rows in [('melodic',melodic),('drum',drums)]:
        counts[label+'_contexts']=len(rows);counts[label+'_voices']=sum(len(x['voices']) for x in rows);counts[label+'_starts']=sum(x['tg_start_calls'] for x in rows);counts[label+'_deferred']=sum(x['deferred_missing_bank'] for x in rows)
    waveforms=sorted({v['source_wav'] for x in melodic+drums for v in x['voices']})
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_factory_voice_chain.py','firmware_expansion_pcm.py','firmware_voice_lfo.py','voice_math.py']},
        inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in dict.fromkeys(inputs)],source_waveforms=[dict(path=p,sha256=sha(ROOT/p)) for p in waveforms],counts=dict(counts),melodic=melodic,drums=drums,drum_selection=selection,kit_links=kit_links,
        boundaries=['Original expanded bank/capability/stereo directories and OSC material refresh execute on private PRM copies, then original manager selection/allocation/parameter/copy/full control init/TG start',
            'Independent checks cover layer weights/pitch, source bank/region/Sample pointers, gain/root/tune/tracking, stereo control copy, release/reverse flags and sample TG words',
            'Source WAV fingerprints connect initialized Samples to existing exports; this is source provenance, not a complete rendered Program',
            'Expansion sample addresses remain relative to their original PCM payloads; upload relocation and TG physical-memory placement are outside this fixture',
            'Four packaged drum kits occupy controlled user slots42..45 in file order; raw Program kit numbers are followed without name-based reassignment, actual importer remapping remains unresolved',
            'Missing-bank selected layers defer the entire startup context and are counted separately; native selection still runs, no substitute material or missing-bank voice builder is executed',
            'Fresh eight-slot pools, neutral Part/controllers and supplied idle TG readbacks; allocation, exception bookkeeping and primitive bus interfaces only are intercepted',
            'No full loader/import, normal refresh, cross-OSC live interaction, effects, interpolation, hardware or complete Program audio executes'])
    target=OUT/('expansion-voices-smoke.json' if args.smoke else 'expansion-voices-check.json');target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=dict(counts),source_wavs=len(waveforms)),indent=2))
if __name__=='__main__':main()
