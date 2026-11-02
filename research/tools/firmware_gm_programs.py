#!/usr/bin/env python3
"""Recover offline GM records, native bank fallback and real voice selection."""
import argparse,collections,contextlib,csv,hashlib,io,json,struct
from pathlib import Path
from firmware_factory_voice_chain import Rig as MelodicRig,fold,selection_pitch,sb
from firmware_drum_voice_chain import Rig as DrumRig,KIT_OFFSET,KIT_STRIDE
from firmware_voice_lfo import sha,PRELOAD,OUT,h,sh,w
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

ACQ=ROOT/'research/derived/acquisitions/KROSS2_local_20261101-022845'
IMAGE=ROOT/'research/libraries/KROSS2_local_20261101-022845/internal-storage.img'
IMAGE_SHA='6cd9b98ca73626535106418bef26c12fa2ae361b92376ab73e958e23ae30c378'
FILES={'PROGGC.BIN':'1a59bd0643acb6135994d6516e1951e936d557b7e10996a831aceae6c802022c',
       'PROGGV.BIN':'397269b575c590533df19defe01f45d0a976c1a4f3a1098b4ad80b3f479658b2',
       'PROGGD.BIN':'5e9348967e7482a7258970647000903dabcbb01ac4089cb8e5e273f8f99a9e02',
       'DKITG.BIN':'0085bff91597f774909beec0fd94a6b6f3320992c2467ea3db98433c85b89d40'}

def sources():
    image=IMAGE.read_bytes();assert hashlib.sha256(image).hexdigest()==IMAGE_SHA
    audit=json.loads((ACQ/'image-audit.json').read_text());assert audit['source_sha256']==IMAGE_SHA
    fs=audit['filesystem'];output={}
    for filename,digest in FILES.items():
        data=(ACQ/'files'/filename).read_bytes();assert hashlib.sha256(data).hexdigest()==digest
        entry=next(e for e in audit['files'] if e['path']==filename)
        recovered=b''.join(image[fs['data_offset']+(c-2)*fs['cluster_bytes']:fs['data_offset']+(c-1)*fs['cluster_bytes']] for c in entry['clusters'])[:entry['bytes']]
        assert recovered==data and entry['sha256']==digest
        header=struct.unpack_from('>16I',data);assert data[:4]==b'KSB0' and header[1]==64 and header[7]==len(data)-64
        assert header[8] in [sum(data[64:])&65535,sum(data[64:])&0xFFFFFFFF]
        output[filename]=data[64:]
    return output

def bank_model(f,bank,program):
    if bank<=10:return bank,program,1
    if bank==20:
        index=(program>>3)+int(program>24)
        return 12,index if index<=8 else 0,1
    if bank>20:return bank,program,0
    variant=bank-11
    if variant<f.data[0x4513AC+program]:return 11,f.data[0x45142C+program]+variant,1
    return 10,program,0

class GMDrums(DrumRig):
    def __init__(self,f,preload,gm_kits):
        super().__init__(f,preload);self.gm_kits=gm_kits;self.special=False
        self.a.uc.mem_write(self.kitbase+58*KIT_STRIDE,gm_kits)
        self.a.write(self.kitarray+4,0x11005480);self.a.write(0x11005480,BASE+0x472080,self.kitbase+58*KIT_STRIDE,9)
        self.a.write(self.kitroot+4,2)
    def prepare(self,record,osc=0,special=True):
        a=self.a;self.record=bytes(record);self.oscillator=0;self.encoded_kit=h(record,0x566);self.kit=self.encoded_kit-96
        assert 58<=self.kit<=66;self.special=special;self.kitptr=self.kitbase+KIT_STRIDE*self.kit
        self.kitraw=self.gm_kits[(self.kit-58)*KIT_STRIDE:(self.kit-57)*KIT_STRIDE]
        a.uc.mem_write(self.patch,self.record)
        for ptr,n in [(self.osc,0x500),(self.context,0x200),(self.part,0x40),(self.channel,0x200),
                      (self.controls,128),(self.manager,0x100),(self.keycontrols,128*12)]:a.uc.mem_write(ptr,bytes(n))
        a.write(self.osc+8,self.patch+0x564);a.write(self.osc+0x48C,self.manager);a.write(self.osc+0x49C,self.context)
        a.write(self.osc+0x490,self.osc+0x490,self.osc+0x490,0)
        a.write(self.context+4,self.part,self.patch,self.patch+0x520,self.channel);a.write(self.context+0x8C,self.controls)
        a.write(self.channel+0x138,self.keycontrols)
        for off in [0x2E,0x4F,0x50]:self.put8(self.context+off,255)
        self.put8(self.part+5,127);self.put8(self.part+1,20);self.put8(0xC1B5719C,int(special))
        a.write(self.context+0x30,0xFFFFFFFF);a.write(self.clock,0,123);a.call(0x1F6654,self.osc)
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
        a.call(0x1FBF4C,self.manager+12);a.write(0xC1B5848C,0x12345678);self.clear()
    def expected_layers(self,note,velocity):
        if not self.special:return super().expected_layers(note,velocity)
        p=self.record;b=p[0x564:0x6E0];lo,hi=sorted(p[0x518:0x51A]);vl,vh=sorted(b[0x2D:0x2F])
        if not lo<=note<=hi or not vl<=velocity<=vh:return []
        transpose=sb(bytes([(12*sb(b,0x78)+b[0x79])&255]),0);folded=fold(note+transpose);distance=self.remap[folded]
        if distance<0:return []
        key=folded+distance
        if key<=34:
            key=sb(self.f.data,0x40595E+key)
            if key<0:return []
        k=self.kitraw[24+68*key:24+68*(key+1)]
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
            desc=k[12*row['slot']:12*(row['slot']+1)];number=h(desc,2);assert desc[1] in [0,1]
            for side,drum in enumerate(self.drum_pairs[number] if desc[1]&1 else [number]):
                expected.append(dict(layer=layer,side=side,key=key,drumsample=drum,sample=sh(self.f.data,0x408BFC+32*drum),pitch=pitch,valid=bool(desc[0]&1),**row))
        return expected

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');parser.add_argument('--smoke',action='store_true');args=parser.parse_args();f=Firmware();data=sources()
    for name,lo,hi in [('GM-bank-resolve',0x278720,0x2787B8),('GM-kit-number',0x285EFC,0x285F50),('GM-low-key-remap',0x1FD860,0x1FD918)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    records=[];variants=list(f.data[0x4513AC:0x45142C]);starts=list(f.data[0x45142C:0x4514AC]);assert sum(variants)==128
    var_ids={starts[n]+v:(11+v,n,f'g{v+1}-{n+1:03d}') for n in range(128) for v in range(variants[n])};assert set(var_ids)==set(range(128))
    drum_pc=[0,8,16,24,25,32,40,48,56]
    for filename,count in [('PROGGC.BIN',128),('PROGGV.BIN',128),('PROGGD.BIN',9)]:
        assert len(data[filename])==count*2140
        for i in range(count):
            raw=data[filename][2140*i:2140*(i+1)]
            bank,program,label=(10,i,f'G{i+1:03d}') if filename=='PROGGC.BIN' else var_ids[i] if filename=='PROGGV.BIN' else (20,drum_pc[i],f'gd-{drum_pc[i]+1:03d}')
            records.append(dict(id=label,logical_bank=bank,program_number=program,source=filename,index=i,name=raw[:24].decode('ascii').rstrip(' \0'),mode=raw[0x508]&7,
                source_sha256=hashlib.sha256(raw).hexdigest(),raw_hex=raw.hex()))
    official=list(csv.DictReader((ROOT/'research/derived/firmware/KROSS2_V124/sounds/factory/GM-programs.csv').open()));conflicts=[];mode_conflicts=[];name_conflicts=[]
    for row in records:
        matches=[x for x in official if ' '.join(x['name'].split())==' '.join(row['name'].split())]
        if not matches:
            matches=[x for x in official if x['bank_program']==row['id']]
            assert len(matches)==1,(row['id'],row['name'],matches)
            name_conflicts.append(dict(id=row['id'],record_name=row['name'],official_name=matches[0]['name']))
        assert len(matches)==1,(row['id'],row['name'],matches)
        row['official_id']=matches[0]['bank_program'];row['official_mode']=matches[0]['oscillator_mode']
        if row['mode']!={'S':0,'D':1,'d':2}[row['official_mode']]:mode_conflicts.append(dict(id=row['id'],name=row['name'],record_mode=row['mode'],official_mode=row['official_mode']))
        if row['id']!=row['official_id']:conflicts.append(dict(id=row['id'],official_id=row['official_id'],name=row['name']))
    assert any(x['id']=='G015' and x['official_id']=='G016' for x in conflicts)
    if not args.verify_arm:return
    getter=Arm(f);tmp=0x11030000;mapping=[]
    for bank,program in itertools_product(range(32),range(128)):
        getter.write(tmp,bank,program);ret=getter.call(0x278720,tmp,tmp+4);actual=struct.unpack('<II',getter.uc.mem_read(tmp,8));expected=bank_model(f,bank,program)
        assert (*actual,ret)==expected,(bank,program,actual,ret,expected)
        mapping.append(dict(bank=bank,program=program,physical_bank=actual[0],physical_program=actual[1],native_result=ret))
    print('GM bank mapping',len(mapping),'passed',flush=True)
    schema=[];reference=bytes.fromhex(records[0]['raw_hex'])
    for ns in range(0x27,0x60):schema.extend(f.group(ns,reference))
    cache={};positions=0
    for row in records[:2] if args.smoke else records:
        raw=bytes.fromhex(row['raw_hex']);values=[]
        for field in schema:
            off=field['program_offset'];desc=field['descriptor'];size=(1,2,4,1,2,4)[desc['type']];blob=raw[off:off+size]
            value=f.read_value(raw,off,desc);key=(blob,desc['raw_hex'])
            if key not in cache:cache[key]=getter.parameter(blob,desc)
            assert value==cache[key];values.append(value);positions+=1
        row['parameter_values']=values
    print('GM parameter fields',positions,'unique ARM inputs',len(cache),flush=True)
    melody=MelodicRig(f);drums=GMDrums(f,PRELOAD.read_bytes(),data['DKITG.BIN']);voices=[];drum_checks=[];selection=[];counts=collections.Counter()
    selected_records=records[:2]+records[-1:] if args.smoke else records
    for row in selected_records:
        raw=bytes.fromhex(row['raw_hex'])
        if row['mode']!=2:
            for osc in range(1+row['mode']):
                block=raw[0x564+380*osc:0x564+380*(osc+1)];lo,hi=sorted(raw[0x518+2*osc:0x51A+2*osc]);vl,vh=sorted(block[0x2D:0x2F]);velocities={max(1,vl),max(1,(vl+vh)//2),vh}
                for slot in range(3):
                    bottom,width=block[0x20+4*slot:0x22+4*slot];velocities.update([bottom-1,bottom,bottom+width//2,bottom+width])
                for note in sorted({lo,(lo+hi)//2,hi}):
                    for vel in sorted(v for v in velocities if max(1,vl)<=v<=vh):
                        melody.prepare(raw,osc);state=melody.note(note,vel);voices.append(dict(id=row['id'],oscillator=osc+1,**state));counts['melodic_startup_contexts']+=1
                counts['melodic_oscillators']+=1
            counts['melodic_programs']+=1
        else:
            for special in [False,True]:
                drums.prepare(raw,special=special);digest=hashlib.sha256();accepted=0
                for note in range(128):
                    for vel in ([1,64,127] if args.smoke else range(1,128)):
                        layers=drums.select(note,vel);digest.update(json.dumps([note,vel,layers],sort_keys=True).encode());accepted+=bool(layers);counts['drum_selection_cases']+=1
                selection.append(dict(id=row['id'],special=special,cases=384 if args.smoke else 16256,accepted=accepted,sha256=digest.hexdigest()))
                for note in range(3 if args.smoke else 128):
                    for vel in [1,64,127]:
                        drums.prepare(raw,special=special);state=drums.note(note,vel);drum_checks.append(dict(id=row['id'],special=special,**state));counts['drum_startup_contexts']+=1
            counts['drum_programs']+=1
        print('GM checked',row['id'],flush=True)
    for row in records:row.pop('raw_hex')
    inputs=[IMAGE,ACQ/'image-audit.json',PRELOAD,ROOT/'research/derived/firmware/KROSS2_V124/sounds/factory/GM-programs.csv']+[ACQ/'files'/name for name in FILES]
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_factory_voice_chain.py','firmware_drum_voice_chain.py','firmware_voice_lfo.py','voice_math.py']},
        inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in inputs],counts=dict(counts),parameter_fields=len(schema),parameter_positions=positions,unique_parameter_inputs=len(cache),schema=schema,
        variant_counts=variants,variant_starts=starts,mapping=mapping,records=records,official_conflicts=conflicts,official_mode_conflicts=mode_conflicts,official_name_conflicts=name_conflicts,melodic=voices,drums=drum_checks,drum_selection=selection,
        gm_low_key_table=list(struct.unpack_from('<35b',f.data,0x40595E)),boundaries=['Four KSB0 files rechecked against the frozen image cluster bytes and payload checksums; no acquisition or file-system execution',
            'Native logical-to-physical GM bank/program mapping compared for 32 banks and all128 programs; missing variations fall back without inventing records',
            'All GM Program indexed fields checked against original ARM getter, identical descriptor/raw inputs deduplicated and counted separately',
            'Melodic voices reuse original directory/bank/selection/region/parameter/init/TG chain; source key/velocity endpoints and stored layer boundaries tested',
            'GM kit encoded154..162 passes original lookup to aggregate kit58..66 in two real provider layouts; all128 keys/127 velocities in normal and GM low-key modes checked',
            'GM drum start checks all128 notes at velocities1/64/127 in both modes; original low-key table is applied after kit remap while retaining original pitch-distance and tracking note',
            'Private eight-voice pools and primitive bus/allocation/exception callbacks; no normal continuous GM refresh, full MIDI bank/program parser, DSP audio or hardware executes',
            'Official names cross-check resource records; mode differences are recorded, G015 Tubular Bells differs from the printed duplicate G016; old official catalog is preserved'])
    target=OUT/('gm-programs-smoke.json' if args.smoke else 'gm-programs-check.json');target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,counts=dict(counts),fields=len(schema),positions=positions,unique_parameter_inputs=len(cache)),indent=2))

def itertools_product(*args):
    import itertools
    return itertools.product(*args)
if __name__=='__main__':main()
