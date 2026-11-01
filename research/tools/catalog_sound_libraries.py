#!/usr/bin/env python3
"""Inventory real KROSS2 Program/PCM resources without changing the player.

Uses the existing firmware-derived KEP cipher and parameter descriptors. New
library sections allow drum-kit banks, unlike the Concert-specific extractor.
"""
from layout import PRODUCT_ROOT
import argparse
import csv
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

from program_firmware import Firmware, ROOT, FW_SHA, BASE
from extract_kep import prepare_context, word_sum, safe_name
from analyze_concert_program import GROUP_NAMES, LABELS

LIBRARIES={
    1:('OASYS Piano','EXPCM001/EXPCM001.KEP','output/kep-analysis/EXPCM001.dec.bin'),
    2:('E.P. Collection','research/libraries/EXPCM002_EP_Collection/EXPCM002/EXPCM002.KEP','research/derived/kep/EXPCM002/EXPCM002.dec.bin'),
    4:('Future Synth Collection','research/libraries/EXPCM004_Future_Synth_Collection/EXPCM004/EXPCM004.KEP','research/derived/kep/EXPCM004/EXPCM004.dec.bin'),
}
DEST=ROOT/'research/derived/firmware/KROSS2_V124/sounds'


def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def sections(data,salt):
    assert data[:4]==b'KORG' and data[64:68]==b'EXP1'
    assert struct.unpack_from('<I',data,4)[0]==(word_sum(data[8:64])+word_sum(salt))&0xffffffff
    result={};pos=192
    while pos<len(data):
        tag=data[pos:pos+4].decode('ascii')
        if tag in ('PRM1','PCM1'):
            header,size,checksum=struct.unpack_from('<3I',data,pos+4);assert header==16
            count=stride=None
        else:
            assert re.fullmatch('1K[A-Z0-9]{2}',tag),tag
            header=32;size,checksum,count,stride=struct.unpack_from('<4I',data,pos+4)
            assert size==count*stride
        payload=pos+header;end=payload+size
        assert end<=len(data) and checksum==word_sum(data[payload:end]),tag
        assert tag not in result
        result[tag]=dict(offset=pos,payload_offset=payload,bytes=size,count=count,stride=stride,checksum=f'{checksum:08x}')
        pos=end
    assert pos==len(data) and {'PRM1','PCM1','1KBP'}<=result.keys()
    return result


def parse_library(number,firmware,salt):
    name,source,decoded=LIBRARIES[number];original=(ROOT/source).read_bytes();path=ROOT/decoded
    # Recreate from the immutable KEP, rather than trusting a prior plaintext.
    path.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(ROOT/'build/kep_blowfish'),str(ROOT/'output/kep-analysis/sections/expanded_context.bin'),str(ROOT/source),str(path)],check=True,stdout=subprocess.DEVNULL)
    data=path.read_bytes();sec=sections(data,salt)
    ns,nr,nm=struct.unpack_from('<3I',data,0x9c)
    prm=data[sec['PRM1']['payload_offset']:sec['PRM1']['payload_offset']+sec['PRM1']['bytes']]
    known_bytes=ns*64+nr*20+nm*28
    assert known_bytes<=len(prm)
    auxiliary=prm[known_bytes:]
    if auxiliary:
        aux_path=ROOT/'research/derived/kep'/f'EXPCM{number:03d}'/'PRM1.aux.bin'
        aux_path.write_bytes(auxiliary)
    pcm=sec['PCM1'];samples=[]
    for index in range(ns):
        raw=prm[index*64:(index+1)*64];start,start2,loop,end=struct.unpack_from('<4I',raw,12)
        assert start<=start2<=end<pcm['bytes'] and start<=loop<=end
        native=data[pcm['payload_offset']+start:pcm['payload_offset']+end+1]
        samples.append(dict(id=index,descriptor_hex=raw.hex(),offset=pcm['payload_offset']+start,
                            frames=end-start+1,loop=loop-start,sha256=sha(native)))
    regions=[]
    for index in range(nr):
        o=ns*64+index*20;raw=prm[o:o+20];sample=struct.unpack_from('<H',raw)[0]
        assert sample<ns
        regions.append(dict(index=index,sample_id=sample,raw_hex=raw.hex(),top=raw[3],root=raw[4]))
    multisamples=[]
    for index in range(nm):
        o=ns*64+nr*20+index*28;first,count,flags=struct.unpack_from('<HBB',prm,o)
        assert first+count<=nr and count>0
        chosen=regions[first:first+count]
        assert all(a['top']<=b['top'] for a,b in zip(chosen,chosen[1:]))
        multisamples.append(dict(id=index,name=prm[o+4:o+28].decode('ascii').rstrip(' \0'),
                                 region_first=first,region_count=count,flags=flags,regions=chosen))
    programs=[];prg=sec['1KBP'];assert prg['stride']==2144
    for index in range(prg['count']):
        o=prg['payload_offset']+2144*index;raw=data[o:o+2144];program_name=raw[:24].decode('ascii').rstrip(' \0')
        target=ROOT/'research/derived/kep'/f'EXPCM{number:03d}'/'programs'/f'{index:03d}_{safe_name(program_name)}.bin'
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert target.read_bytes()==raw
        else:target.write_bytes(raw)
        programs.append(dict(index=index,name=program_name,path=str(target.relative_to(PRODUCT_ROOT)),sha256=sha(raw)))
    result=dict(id=number,name=name,source=source,source_sha256=sha(original),decoded=decoded,decoded_sha256=sha(data),
                header_and_section_checksums_pass=True,sections=sec,samples=samples,multisamples=multisamples,programs=programs,
                PRM1_auxiliary=dict(bytes=len(auxiliary),sha256=sha(auxiliary),scope='Uninterpreted trailing parameter data, retained separately; not needed for indexed multisample names'))
    save(ROOT/'research/derived/kep'/f'EXPCM{number:03d}'/'library.json',result)
    return result


def rom_catalog(firmware):
    # Confirmed by original pointer/count getters 0x20cf34 / 0x20cf40.
    start=0x48F5CC;count=497;records=[]
    for index in range(count):
        o=start+index*28;first,nregions,flags=struct.unpack_from('<HBB',firmware.data,o)
        name=firmware.data[o+4:o+28].decode('ascii').rstrip(' \0')
        assert name and all(32<=ord(c)<127 for c in name)
        records.append(dict(index=index,name=name,offset=o,first_region=first,region_count=nregions,flags=flags,
                            PCM_available=False,role='diagnostic tone' if name=='Sine 1kHz' else 'ROM multisample metadata'))
    return dict(offset=start,count=count,record_bytes=28,sha256=sha(firmware.data[start:start+count*28]),records=records,
                scope='Multisample metadata, not complete factory Programs and not ROM PCM')


def resolve(bank,number,libraries,rom):
    stereo=bool(bank&1)
    def pair_indices(records):
        pairs=[]
        for i in range(len(records)-1):
            left,right=records[i]['name'],records[i+1]['name']
            if left.endswith('-L') and right.endswith('-R') and left[:-2].rstrip()==right[:-2].rstrip():pairs.append([i,i+1])
        return pairs
    if bank in (0,1):
        pairs=pair_indices(rom['records'])
        indices=pairs[number] if stereo and number<len(pairs) else [] if stereo else [number]
        names=[rom['records'][i]['name'] for i in indices if i<len(rom['records'])]
        return dict(kind='ROM',available=False,multisample_indices=indices,names=names)
    libid=bank//2-1
    if libid not in libraries:return dict(kind='unknown_or_unavailable_bank',available=False,bank=bank)
    lib=libraries[libid];pairs=pair_indices(lib['multisamples'])
    indices=pairs[number] if stereo and number<len(pairs) else [] if stereo else [number]
    valid=bool(indices) and all(i<len(lib['multisamples']) for i in indices)
    return dict(kind='expansion',library_id=libid,available=valid,multisample_indices=indices,
                names=[lib['multisamples'][i]['name'] for i in indices if i<len(lib['multisamples'])],
                mapping_scope='even bank direct mono index; odd bank ordinal of matching consecutive -L/-R names; structural inference, full allocator not executed')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args()
    firmware=Firmware();_,context,salt=prepare_context(firmware.data)
    assert context==(ROOT/'output/kep-analysis/sections/expanded_context.bin').read_bytes()
    libraries={n:parse_library(n,firmware,salt) for n in LIBRARIES};rom=rom_catalog(firmware)
    # Reuse version-locked parameter descriptors for every actual Program.
    reference=(ROOT/'output/kep-analysis/Concert_SE_Grand/program.bin').read_bytes()
    descriptors=[]
    for namespace in range(0x27,0x60):descriptors.extend(firmware.group(namespace,reference))
    effects=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/catalog/effects.json').read_text())['effects']
    arm=None;checks=0
    if args.verify_arm:
        from program_firmware import Arm
        arm=Arm(firmware)
        assert (arm.call(0x20CF34)&0xffffffff)==BASE+rom['offset'] and arm.call(0x20CF40)==rom['count']
    candidates=[];values={}
    for libid,lib in libraries.items():
        for entry in lib['programs']:
            raw=(ROOT/entry['path']).read_bytes();key=f'EXPCM{libid:03d}:{entry["index"]:03d}'
            fields={}
            for field in descriptors:
                offset=field['program_offset'];desc=field['descriptor'];value=firmware.read_value(raw,offset,desc)
                if arm:assert arm.parameter(raw[offset:],desc)==value;checks+=1
                fields[f'{field["namespace"]:02x}:{field["index"]}']=value
            values[key]=fields
            mode=raw[0x508]&7;oscillators=[];active=[]
            for osc in range(2):
                groups={}
                for ns,name in GROUP_NAMES.items():
                    group=[f for f in descriptors if f['namespace']==ns+osc*16]
                    groups[name]={LABELS.get(ns,{}).get(f['index'],f'field_{f["index"]}'):fields[f'{ns+osc*16:02x}:{f["index"]}'] for f in group}
                base=0x564+380*osc;slots=[]
                for n in range(4):
                    off=base+8*n;enabled=bool(raw[off]&1)
                    if not enabled:continue
                    bank=raw[off+1];number=struct.unpack_from('<H',raw,off+2)[0]&4095
                    selection=dict(slot=n+1,bank=bank,number=number,level=raw[off+4],
                                   bottom_velocity=raw[base+32+n*4] if n<3 else 1,
                                   crossfade_width=raw[base+33+n*4] if n<3 else 0,
                                   source=resolve(bank,number,libraries,rom))
                    slots.append(selection)
                osc_active=(mode==1 or (mode==0 and osc==0))
                if osc_active:active.extend(slots)
                oscillators.append(dict(oscillator=osc+1,active=osc_active,slots=slots,groups=groups))
            fx=[]
            for i in range(7):
                payload=0x18+76*i if i<5 else (0x194,0x1d8)[i-5];head=payload+64;eid=raw[head]
                assert eid<len(effects)
                fx.append(dict(slot=f'IFX{i+1}' if i<5 else f'MFX{i-4}',id=eid,name=effects[eid]['name'],enabled=bool(raw[head+1]&64)))
            available=mode in (0,1) and bool(active) and all(s['source']['available'] for s in active)
            categories=(raw[0x512]&31,raw[0x512]>>5)
            candidate=dict(key=key,library_id=libid,library=lib['name'],**entry,oscillator_mode=mode,
                           category_raw=categories[0],subcategory_raw=categories[1],oscillators=oscillators,effects=fx,
                           sample_dependencies_complete=available,
                           missing_sources=[s['source'] for s in active if not s['source']['available']],
                           plugin_implemented=(key=='EXPCM001:002'),
                           audition_status='Original Program parameters extracted; full selected-Program audio not rendered',
                           engine_work='Requires per-Program controls/layers/effects; current engine remains Concert-specific')
            candidates.append(candidate)
        print('Catalogued',lib['name'],len(lib['programs']),'Programs',flush=True)
    DEST.mkdir(parents=True,exist_ok=True)
    save(DEST/'rom-multisamples.json',rom)
    save(DEST/'program-parameter-values.json',dict(firmware_sha256=FW_SHA,fields_per_program=len(descriptors),values=values))
    result=dict(firmware_sha256=FW_SHA,libraries=[{k:v for k,v in lib.items() if k not in ('samples','programs','multisamples')} for lib in libraries.values()],
                program_count=len(candidates),rom_multisample_records=rom['count'],parameter_getter_comparisons=checks,
                sample_complete_count=sum(p['sample_dependencies_complete'] for p in candidates),programs=candidates,
                firmware_factory_data=dict(referenced_but_not_in_update=['PPROGIA.BIN','PPROGIB.BIN','PPROGIC.BIN','PPROGID.BIN','PPROGIE.BIN','PPROGIF.BIN'],
                    scope='Update contains KROSSAPP.CMP and PPAT.BIN, not a complete factory Program/PCM dump; PPAT contains drum patterns'),
                scope=['Official expansion Program data decoded with firmware-derived cipher; header/section checksums verified',
                       '497 ROM multisample metadata records, including Sine 1kHz diagnostic, are not 497 playable Programs',
                       'Sample dependency mapping follows mono/even, stereo/odd banks; active Single/Double OSCs only; drum mode unresolved',
                       'Full original Program DSP/controls are not yet ported for these choices; only Concert is implemented',
                       'User accepts current Concert sound and explicitly waives physical-instrument A/B as an acceptance condition'])
    save(DEST/'programs.json',result)
    with (DEST/'programs.csv').open('w',newline='') as stream:
        w=csv.writer(stream);w.writerow(['key','name','library','sample_dependencies_complete','oscillator_mode','effects'])
        for p in candidates:w.writerow([p['key'],p['name'],p['library'],p['sample_dependencies_complete'],p['oscillator_mode'],'; '.join(e['name'] for e in p['effects'] if e['enabled'] and e['id'])])
    verification=dict(firmware_sha256=FW_SHA,program_count=len(candidates),parameter_getter_comparisons=checks,
                      raw_program_sha256={p['key']:p['sha256'] for p in candidates},
                      library_sha256={n:lib['source_sha256'] for n,lib in libraries.items()},
                      rom_pointer_and_count_original_ARM_verified=bool(arm),sample_complete_count=result['sample_complete_count'],
                      output_sha256={p.name:sha(p.read_bytes()) for p in (DEST/'programs.json',DEST/'program-parameter-values.json',DEST/'rom-multisamples.json')},
                      tool_sha256={name:sha((ROOT/'tools'/name).read_bytes()) for name in ('catalog_sound_libraries.py','program_firmware.py','analyze_concert_program.py','extract_kep.py')},
                      scope=result['scope'])
    save(ROOT/'research/derived/verification/sound-catalog-check.json',verification)
    print('PASS',len(candidates),'Programs;',checks,'ARM getter comparisons;',result['sample_complete_count'],'have available sample dependencies')


if __name__=='__main__':main()
