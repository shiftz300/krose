#!/usr/bin/env python3
"""Recover real 128-key factory kits from official editor PRELOAD.

0x61 parameter descriptors establish the 68-byte key schema. Optional original
ARM getter checks run in mocked memory only; no MIDI or hardware access.
"""
from layout import PRODUCT_ROOT
import argparse
import contextlib
import hashlib
import io
import json
import struct

from decode_factory_rom import DERIVED, ROOT, load, save
from program_firmware import Firmware, Arm, PARAMETER_GROUPS, BASE
from firmware_inspect import inspect

PRELOAD=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
OFFSET=0x48be20
STRIDE=24+128*68


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args()
    fw=Firmware();data=PRELOAD.read_bytes();assert hashlib.sha256(data).hexdigest()=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    assert OFFSET==0x1ef220+1280*2140 and STRIDE==8728
    group=fw.pointer(PARAMETER_GROUPS+0x61*4);table=fw.pointer(group+4);assert fw.u32(group)==70
    schema=[]
    for i in range(3,70):
        cell=fw.pointer(table+i*4);address=fw.u32(cell);offset=address-0xc1439738
        assert 0<=offset<68
        schema.append(dict(index=i,offset=offset,descriptor=fw.descriptor(fw.pointer(cell+4))))
    drum=load('drumsamples');pairs=[]
    for a,b in zip(drum,drum[1:]):
        if a['name'].endswith('-L') and b['name']==a['name'][:-2]+'-R':pairs.append([a,b])
    assert len(pairs)==49
    arm=Arm(fw) if args.verify_arm else None;checks=0;all_fields=0;kits=[];range_checks=0
    for kit in range(58):
        record=data[OFFSET+kit*STRIDE:OFFSET+(kit+1)*STRIDE];name=record[:24].decode('ascii').rstrip(' \0')
        assert name=='InitDrumkit' if kit>=42 else name!='InitDrumkit'
        keys={}
        for note in range(128):
            raw=record[24+note*68:24+(note+1)*68]
            values={}
            for field in schema:
                desc=field['descriptor'];value=fw.read_value(raw,field['offset'],desc)
                assert desc['minimum']<=value<=desc['maximum'],(kit,note,field['index'],value)
                values[field['index']]=value;range_checks+=1
                if arm and kit<42 and note in (0,24,36,38,48,50,54,56,58,60,72,96,127):
                    assert arm.parameter(raw[field['offset']:],desc)==value
                    checks+=1
            if kit>=42 or not raw[65]&1:continue
            layers=[]
            for slot in range(4):
                o=slot*12
                if not raw[o]&1:continue
                bank=raw[o+1];number=struct.unpack_from('<H',raw,o+2)[0]
                assert bank in (0,1)
                selected=pairs[number] if bank==1 else [drum[number]]
                layers.append(dict(slot=slot+1,bank=bank,number=number,
                                   samples=[d['sample_index'] for d in selected],name=selected[0]['name'].removesuffix('-L') if bank else selected[0]['name'],
                                   bottom=raw[48+slot*4] if slot<3 else 1,
                                   crossfade=raw[49+slot*4] if slot<3 else 0,
                                   level=struct.unpack_from('<b',raw,o+4)[0],start_offset=raw[o+5]&15,reverse=bool(raw[o+5]&128),
                                   coarse=struct.unpack_from('<b',raw,o+6)[0],fine=struct.unpack_from('<b',raw,o+7)[0]))
            assert layers
            keys[str(note)]=dict(layers=layers,pan=raw[60],exclusive=raw[64],flags=raw[65],raw_hex=raw.hex())
            all_fields+=len(layers)
        if kit<42:kits.append(dict(id=f'DK{kit:03d}',index=kit,name=name,category='DRUM/SFX',keys=keys,source_sha256=hashlib.sha256(record).hexdigest()))
    programs=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/sounds/factory/programs.json').read_text())['programs']
    refs={p['bank_program']:f'DK{p["oscillators"][0]["slots"][0]["number"]:03d}' for p in programs if p['kind']=='factory_A_F' and p['oscillator_mode']=='d'}
    assert len(kits)==len(refs)==42 and set(refs.values())=={k['id'] for k in kits}
    # Cross-check named key assignments published on the official Voice Name
    # List p21: C3 kick, D3 snare, F#3 closed hat, A#3 open hat.
    expected={48:1,50:174,54:467,58:470}
    for note,index in expected.items():assert kits[0]['keys'][str(note)]['layers'][0]['number']==index
    report=dict(source=str(PRELOAD.relative_to(PRODUCT_ROOT)),source_sha256=hashlib.sha256(data).hexdigest(),record_offset=OFFSET,record_bytes=STRIDE,
                records=58,factory_kits=42,initialized_records=16,key_stride=68,keys_per_kit=128,
                parameter_namespace='0x61',schema=schema,range_checks=range_checks,ARM_parameter_checks=checks,
                published_Basic_Kit_1_key_checks=expected,kits=kits,program_to_kit=refs,
                scope='Original sample assignment, velocity thresholds, tuning, pan and exclusive groups recovered. Web amp/EG/filter/FX remain approximations; raw fields retained.')
    save(DERIVED/'factory-drumkits.json',report)
    with contextlib.redirect_stdout(io.StringIO()) as capture:inspect(fw.data,0x1f5c88,0x1f5ce0)
    (DERIVED/'drum-exclusive-group.arm.txt').write_text(capture.getvalue())
    print(f'42 factory kits, {sum(len(k["keys"]) for k in kits)} assigned keys, {all_fields} sample slots; {range_checks} field bounds and {checks} original ARM getter checks',flush=True)


if __name__=='__main__':main()
