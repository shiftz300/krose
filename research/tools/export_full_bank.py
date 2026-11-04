#!/usr/bin/env python3
"""Freeze every locally recovered Program and its PCM into the native bundle.

No device access; immutable, hash-checked inputs. Program order preserves the
six starter IDs. Future Synth kits retain their stored user-slot references.
"""
import collections
import csv
import hashlib
import json
import struct
import wave
from pathlib import Path
from layout import ROOT, PRODUCT_ROOT
from program_firmware import Firmware

DEST = PRODUCT_ROOT / 'assets/factory-starter'
CAT = ROOT / 'derived/firmware/KROSS2_V124'
CATEGORIES = ['PIANO','E.PIANO','ORGAN','BELL','STRINGS','BRASS','SYNTH LEAD','SYNTH PAD','GUITAR','BASS','DRUM/SFX']
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return json.loads(path.read_text())
def sb(data, offset): return struct.unpack_from('<b', data, offset)[0]
def h(data, offset): return struct.unpack_from('<H', data, offset)[0]
def fold(note):
    while note < 0: note += 12
    while note > 127: note -= 12
    return note

def selection_pitch(note, transpose, slope):
    if slope == 0: value = 60*256
    elif slope == 10: value = note*256
    elif slope == -10: value = (120-note)*256
    elif slope == 20: value = max(0,min(32767,512*note-60*256))
    else: value = max(0,min(32767,60*256+((820*note-49200)*slope >> 5)))
    return (fold(transpose+(value>>8))<<8)|(value&255)

def pairs(items):
    return [[i,i+1] for i in range(len(items)-1) if items[i]['name'].endswith('-L') and items[i+1]['name']==items[i]['name'][:-1]+'R']

def main():
    fw = Firmware()
    samples, multis, drums, stereo, drumstereo = {}, {}, {}, {}, {}
    manifest = read(ROOT/'output/Factory_ROM_WAV/manifest.json')
    for s in manifest['samples']:
        if s['sample_id'] < 4068:
            samples[s['sample_id']] = dict(s,path=ROOT/'output/Factory_ROM_WAV'/s['file'])
    ms = read(CAT/'rom/catalog/multisamples.json')
    regions = read(CAT/'rom/catalog/key-regions.json')
    multis[0] = [[bytes.fromhex(r['raw_hex']) for r in regions[m['first_region']:m['first_region']+m['region_count']]] for m in ms]
    stereo[0] = pairs(ms)
    ds = read(CAT/'rom/catalog/drumsamples.json')
    drums[0] = [bytes.fromhex(d['raw_hex']) for d in ds]
    drumstereo[0] = pairs(ds)
    expansions = read(CAT/'architecture/stage04/expansion-pcm-check.json')
    source_inputs = {}
    libraries = {}
    for lid in [1,2,4]:
        lib = read(ROOT/f'derived/kep/EXPCM{lid:03d}/library.json')
        path=ROOT/lib['decoded']; assert sha(path)==lib['decoded_sha256']
        raw=path.read_bytes(); source_inputs[str(path.relative_to(PRODUCT_ROOT))]=lib['decoded_sha256']
        bank=lid+1; libraries[lid]=(lib,raw)
        multis[bank]=[[bytes.fromhex(r['raw_hex']) for r in m['regions']] for m in lib['multisamples']]
        stereo[bank]=pairs(lib['multisamples'])
        native=next(b for b in expansions['resources']['banks'] if b['library']==lid)
        drums[bank]=[bytes.fromhex(d['raw_hex']) for d in native['drumsamples']]
        drumstereo[bank]=pairs(native['drumsamples'])
        if lid==1:
            for s in read(ROOT/'output/OASYS_Piano_WAV/manifest.json')['samples']:
                samples[s['sample_id']]=dict(s,path=ROOT/'output/OASYS_Piano_WAV'/s['file'])
        else:
            for s in next(e for e in expansions['exports'] if e['library']==lid)['samples']:
                sid=lid*10000+s['id']
                samples[sid]=dict(sample_id=sid,path=ROOT/s['file'],frames=s['frames'],loop_start_relative=s['loop'],flags=s['flags'],pitch_field=s['pitch'],wav_sha256=s['sha256'])
    def sample_id(bank,index): return index if bank==0 else (bank-1)*10000+index
    preload=ROOT/'libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
    assert sha(preload)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    kitbytes=preload.read_bytes()[0x48be20:0x48be20+58*8728]
    kits=[kitbytes[i*8728:(i+1)*8728] for i in range(58)]
    gmkit=ROOT/'derived/acquisitions/KROSS2_local_20261101-022845/files/DKITG.BIN'
    assert sha(gmkit)=='0085bff91597f774909beec0fd94a6b6f3320992c2467ea3db98433c85b89d40'
    gmraw=gmkit.read_bytes()[64:];kits.extend(gmraw[i*8728:(i+1)*8728] for i in range(9))
    lib,decoded=libraries[4];section=lib['sections']['1KBD'];ext=decoded[section['payload_offset']:section['payload_offset']+section['bytes']]
    extension_kits={42+i:ext[i*8728:(i+1)*8728] for i in range(4)}
    records=[]
    factory_catalog=read(CAT/'sounds/factory/programs.json')
    categories=list(dict.fromkeys(p['category'] for p in factory_catalog['programs']))
    assert categories==CATEGORIES
    for p in factory_catalog['programs']:
        if p['kind']!='factory_A_F':continue
        path=ROOT/p['program_file'];assert sha(path)==p['program_sha256']
        records.append(dict(id=p['bank_program'],name=p['name'],category=p['category'],index=p['category_index'],group='Factory',raw=path.read_bytes(),source=str(path.relative_to(PRODUCT_ROOT)),sha256=p['program_sha256']))
    starter=read(ROOT/'config/native-starter.json')['programs']
    records.sort(key=lambda p:(starter.index(p['id']) if p['id'] in starter else len(starter),p['id']))
    gm=read(CAT/'architecture/stage04/gm-programs-check.json')
    official=list(csv.DictReader((CAT/'sounds/factory/GM-programs.csv').open()))
    for p in gm['records']:
        path=ROOT/'derived/acquisitions/KROSS2_local_20261101-022845/files'/p['source']
        blob=path.read_bytes()[64+2140*p['index']:64+2140*(p['index']+1)]
        assert hashlib.sha256(blob).hexdigest()==p['source_sha256']
        matches=[row for row in official if ' '.join(row['name'].split())==' '.join(p['name'].split())]
        if not matches:matches=[row for row in official if row['bank_program']==p['official_id']]
        assert len(matches)==1,(p['id'],matches)
        category_row=matches[0]
        records.append(dict(id=p['id'],name=p['name'],category=category_row['category'],index=int(category_row['category_index']),group='GM',raw=blob,source=str(path.relative_to(PRODUCT_ROOT)),sha256=p['source_sha256']))
    for p in read(CAT/'sounds/programs.json')['programs']:
        path=ROOT/p['path'];assert sha(path)==p['sha256']
        records.append(dict(id=p['key'],name=p['name'],category=CATEGORIES[min(p['category_raw'],10)],index=p['index'],group=p['library'],raw=path.read_bytes()[:2140],source=str(path.relative_to(PRODUCT_ROOT)),sha256=p['sha256']))
    assert len(records)==1161 and len({p['id'] for p in records})==1161
    zones=[];used=set();missing=[];kitlinks=[]
    # Each slot has its original threshold and fade, plus the previous slot's
    # fade-out. Selection is indexed by OSC/key/slot, never by searching PCM.
    def fades(raw,base,slot):
        bottom=raw[base+4*slot] if slot<3 else 1
        upper=min([raw[base+4*i]-1 for i in range(slot)]+[127])
        iw=raw[base+4*slot+1] if slot<3 else 0
        ic=raw[base+4*slot+2]&3 if slot<3 else 0
        ob=raw[base+4*(slot-1)] if slot else 0
        ow=raw[base+4*(slot-1)+1] if slot else 0
        oc=raw[base+4*(slot-1)+2]&3 if slot else 0
        ranges=[(bottom,upper)] if bottom<=upper else []
        end=min(127,ob+ow-1,min([raw[base+4*i]-1 for i in range(slot-1)]+[127]))
        if ow and ob<=end:ranges.append((ob,end))
        if not ranges:return 128,127,[slot,iw,ic,ob,ow,oc]
        return max(1,min(a for a,b in ranges)),max(b for a,b in ranges),[slot,iw,ic,ob,ow,oc]
    def add(sids,note,vlo,vhi,roots,fines,osc,level,pan,exclusive,flags,gain,coarse,fine,fade):
        if vlo>vhi:return
        assert all(s in samples for s in sids),sids
        used.update(sids)
        z=[sids[0],sids[1] if len(sids)>1 else 0xffffffff,note,note,vlo,vhi,roots[0],fines[0],roots[-1],fines[-1],osc,level,pan,exclusive,flags,gain,coarse,fine]+fade
        # Coalesce neighboring keys with identical region data.
        if zones and zones[-1][3]==note-1 and zones[-1][:2]==z[:2] and zones[-1][4:]==z[4:]:zones[-1][3]=note
        else:zones.append(z)
    for p in records:
        raw=p['raw'];assert len(raw)==2140
        first=len(zones);mode=raw[0x508]&7;p['drum']=mode==2
        for osc in range(2 if mode==1 else 1):
            b=raw[0x564+380*osc:0x564+380*(osc+1)]
            nlo,nhi=sorted(raw[0x518+2*osc:0x51a+2*osc]);vl,vh=sorted(b[0x2d:0x2f]);vl=max(1,vl)
            transpose=sb(bytes([(12*sb(b,0x78)+b[0x79])&255]),0)
            if mode==2:
                kit=h(b,2);kit=kit-96 if p['group']=='GM' else kit
                kraw=extension_kits[kit] if p['id'].startswith('EXPCM') else kits[kit]
                kitlinks.append(dict(program=p['id'],stored_kit=h(b,2),kit_name=kraw[:24].decode('ascii').rstrip(' \0')))
                for note in range(nlo,nhi+1):
                    folded=fold(note+transpose)
                    key=next((k for k in range(folded,128) if kraw[24+68*k+65]&1),None)
                    if key is None:continue
                    distance=key-folded
                    if p['group']=='GM' and key<=34:key=sb(fw.data,0x40595e+key)
                    if key<0:continue
                    k=kraw[24+68*key:24+68*(key+1)]
                    if not k[65]&4:continue
                    for slot in range(4):
                        d=k[12*slot:12*(slot+1)]
                        if not d[0]&1:continue
                        low,high,fade=fades(k,48,slot);low=max(low,1)
                        if low>high or low>vh or high<vl:continue
                        bank=d[1]//2;number=h(d,2)
                        if bank not in drums:
                            missing.append(dict(program=p['id'],note=note,key=key,slot=slot,bank=bank,number=number,velocity=[low,high]));continue
                        indices=drumstereo[bank][number] if d[1]&1 else [number]
                        desc=[drums[bank][i] for i in indices];sids=[sample_id(bank,h(x,0)) for x in desc]
                        reverse=bool(d[5]&128) and all(not samples[s]['flags']&1 for s in sids)
                        tune=sb(d,6)+(selection_pitch((60-distance)&255,0,sb(b,0x7c))-60*256)/256
                        # Retain sub-semitone remap pitch in the fine field.
                        coarse=int(tune);fine=sb(d,7)+round((tune-coarse)*100)
                        add(sids,note,low,high,[60]*2,[0]*2,0,127,k[60],k[64],8|int(reverse),2**((sb(d,4)-99)/50),coarse,fine,fade)
            else:
                for slot in range(4):
                    d=b[8*slot:8*(slot+1)]
                    if not d[0]&3:continue
                    low,high,fade=fades(b,0x20,slot);low=max(low,1)
                    if low>high or low>vh or high<vl:continue
                    bank=d[1]//2;number=h(d,2);assert bank in multis,(p['id'],bank)
                    indices=stereo[bank][number] if d[1]&1 else [number]
                    for note in range(nlo,nhi+1):
                        query=selection_pitch(note,transpose,sb(b,0x7c))>>8
                        matches=[next((r for r in multis[bank][i] if r[3]>=query),None) for i in indices]
                        if any(r is None for r in matches):continue
                        flags=sum(2<<i for i,r in enumerate(matches) if r[5]&1)
                        sids=[sample_id(bank,h(r,0)) for r in matches]
                        if d[5]&128 and all(not samples[s]['flags']&1 for s in sids):flags|=1
                        add(sids,note,low,high,[r[4] for r in matches],[struct.unpack_from('<h',r,6)[0] for r in matches],osc,d[4],b[0x149]&127,0,flags,1.,0,0,fade)
        p.update(first=first,zones=len(zones)-first)
        assert p['zones']>0,p['id']
    ids=sorted(used);mapping={sid:i for i,sid in enumerate(ids)}
    for z in zones:
        z[0]=mapping[z[0]]
        if z[1]!=0xffffffff:z[1]=mapping[z[1]]
    DEST.mkdir(parents=True,exist_ok=True);target=DEST/'Factory.samples'
    offset=24+224*4+256*2+129*2+len(ids)*32+len(zones)*96+len(records)*2232
    with target.open('wb') as out:
        out.write(b'KRPRG002');out.write(struct.pack('<4I',2,len(ids),len(zones),len(records)))
        out.write(fw.data[0x405b88:0x405b88+224*4]);out.write(fw.data[0x405984:0x405984+256*2]);out.write(fw.data[0x40585c:0x40585c+129*2])
        for sid in ids:
            s=samples[sid];assert sha(s['path'])==s['wav_sha256']
            out.write(struct.pack('<5IiQ',sid,s['frames'],s['loop_start_relative'],s['frames']-1,s['flags'],s['pitch_field'],offset));offset+=s['frames']*3
        for z in zones:out.write(struct.pack('<7IiIi5If8i',*z))
        for p in records:
            out.write(p['id'].encode().ljust(16,b'\0')+p['name'].encode().ljust(64,b'\0')+struct.pack('<3I',p['drum'],p['first'],p['zones'])+p['raw'])
        for sid in ids:
            s=samples[sid]
            with wave.open(str(s['path']),'rb') as w:
                assert w.getsampwidth()==3 and w.getnchannels()==1 and w.getnframes()==s['frames']
                out.write(w.readframes(w.getnframes()))
    assert target.stat().st_size==offset
    names=['Concert SE Grand']+[p['name'] for p in records]
    header=DEST/'FactoryPrograms.h'
    header.write_text('#pragma once\nnamespace segrand {\ninline constexpr int kInstrumentProgramCount='+str(len(names))+';\ninline constexpr const char* kInstrumentProgramNames[]={'+','.join(json.dumps(n) for n in names)+'};\n}\n')
    # One source of truth for browser order, labels, icons and host indices.
    browser=DEST/'FactoryPrograms.json'
    warnings={}
    for p in records:
        absent=sorted({row['note'] for row in missing if row['program']==p['id']})
        if absent:warnings[p['id']]='缺少部分采样：MIDI '+', '.join(map(str,absent))
    warnings['EXPCM004:041']='原始引用指向 Nu DISCO Kit，导入器重映射待核对'
    entries=[['EX','Concert SE Grand','PIANO',0,'Concert']]+[[p['id'],p['name'],p['category'],p['index'],p['group'],warnings.get(p['id'],'')] for p in records]
    browser.write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n')
    groups=list(dict.fromkeys(p['group'] for p in records))+['Concert']
    def display_key(i):
        p=entries[i];rank=categories.index(p[2])
        # Factory and GM category numbers share the original Voice Name List.
        # Expansion records follow those entries in each category, in file order.
        return (rank,0,p[3],i) if p[4] in ['Factory','GM'] else (rank,1,groups.index(p[4]),p[3],i)
    order=sorted(range(len(entries)),key=display_key)
    presentation=DEST/'FactoryBrowser.json'
    presentation.write_text(json.dumps(dict(categories=categories,groups=groups,order=order,source=factory_catalog['source_pdf'],source_sha256=factory_catalog['source_pdf_sha256']),indent=2)+'\n')
    report=dict(format_version=2,kind='Complete locally recovered Factory, GM and expansion Programs',files=[dict(file=f.name,bytes=f.stat().st_size,sha256=sha(f)) for f in [target,header,browser,presentation]],programs=[{k:v for k,v in p.items() if k!='raw'} for p in records],sample_count=len(ids),region_count=len(zones),missing_layers=missing,expansion_kit_links=[x for x in kitlinks if x['program'].startswith('EXPCM')],source_inputs=source_inputs,source_WAV_sha256={str(s):samples[s]['wav_sha256'] for s in ids},exporter_sha256=sha(Path(__file__)),scope='Original Program controls, key/velocity selection, stereo regions, transpose/slope and layer crossfades. Host filter/FX and drum gain remain approximations; drum start-offset, expansion importer kit relocation and missing logical bank 6 remain unresolved.')
    (DEST/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(programs=len(records),samples=len(ids),regions=len(zones),bytes=offset,missing_layers=len(missing),groups=dict(collections.Counter(p['group'] for p in records))),indent=2))
if __name__=='__main__':main()
