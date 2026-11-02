#!/usr/bin/env python3
"""Run original factory stereo-directory and key-map builders; audit both sides."""
import argparse
import contextlib
import hashlib
import io
import json
import struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('factory-stereo-directory',0x283E04,0x2841EC),('factory-key-map',0x1F5904,0x1F5A80),
        ('OSC-material-refresh',0x1F6654,0x1F67C4)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f)
    def word(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def half(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def call(entry,*argv,**kw):return a.call(entry,*argv,**kw)&0xFFFFFFFF
    def put8(p,x):a.uc.mem_write(p,bytes([x&255]))
    system,banks,source,target,registry=0x11000000,0x11001000,0x11004000,0x11005000,0x11006000
    source_array,target_array,records,heap,maps=0x11008000,0x11009000,0x11010000,0x11018000,0x11020000
    a.write(0xC1743270,system);a.write(system+0x28,banks)
    a.write(banks+0x14,4070,5570,497);a.write(banks+0x24,BASE+0x410ABC,BASE+0x492C28,BASE+0x48F5CC)
    a.write(source,source_array,497);a.write(target,target_array,248);a.write(registry+4,target)
    for i in range(497):a.write(source_array+4*i,records+32*i)
    allocated=[]
    def allocate(m):
        assert m.get('R0')==32
        address=heap+32*len(allocated);allocated.append(address);return address
    a.stubs={0x1E2974:lambda m:0,0x2DC184:lambda m:0,0x2DC1BC:lambda m:0,0x14E730:allocate}
    call(0x283E04,target,1,source,0)
    pairs=[]
    for i in range(word(target+4)):
        record=word(target_array+4*i);left,right=half(record+4)&32767,half(record+6)&32767
        assert call(0x28543C,registry,1,i,0,stack=(0,))==left
        assert call(0x28543C,registry,1,i,1,stack=(0,))==right
        pairs.append(dict(index=i,left=left,right=right,name=bytes(a.uc.mem_read(record+8,24)).decode('ascii').rstrip()))
    expected=[]
    names=[f.data[0x48F5CC+28*i+4:0x48F5CC+28*i+28].decode('ascii').rstrip(' \0') for i in range(497)]
    for i,name in enumerate(names):
        if name.endswith('-L') and i+1<len(names) and names[i+1]==name[:-1]+'R':expected.append((i,i+1))
    assert [(x['left'],x['right']) for x in pairs]==expected
    # Actual key-map builder and region getter, all 496 ordinary multisamples.
    mapped=[];lookup_cases=0;unwritten=[];absent=0
    for i in range(496):
        address=maps+144*i
        a.uc.mem_write(address,bytes(144));call(0x1F5928,address,0,i)
        first,count=struct.unpack_from('<HB',f.data,0x48F5CC+28*i)
        expected_map=[0]*128;written=set();previous=-1
        for j in range(count):
            top=f.data[0x492C28+20*(first+j)+3]
            if top>0:
                for note in range(previous+1,top+1):expected_map[note]=j;written.add(note)
            previous=top
        for note in range(previous+1,128):expected_map[note]=255;written.add(note)
        actual=list(a.uc.mem_read(address+12,128));assert actual==expected_map
        if len(written)<128:
            unwritten.append(dict(multisample=i,name=names[i],notes=sorted(set(range(128))-written)))
            probe=0x11040000;a.uc.mem_write(probe,bytes([165])*144);call(0x1F5928,probe,0,i)
            assert all(a.uc.mem_read(probe+12+n,1)[0]==165 for n in set(range(128))-written)
        regions=[]
        for note,index in enumerate(actual):
            wanted=0 if index==255 else BASE+0x492C28+20*(first+index)
            actual_ptr=call(0x1F5B24,address,note);assert actual_ptr==wanted
            if not wanted:regions.append(None);absent+=1
            else:
                sample=half(wanted);assert sample<4068
                regions.append(dict(region=first+index,sample=sample))
            lookup_cases+=1
        mapped.append(dict(index=i,name=names[i],first_region=first,region_count=count,key_map=actual,regions=regions))
    for pair in pairs:
        left,right=mapped[pair['left']]['regions'],mapped[pair['right']]['regions']
        pair['asymmetric_missing_notes']=[n for n in range(128) if (left[n] is None)!=(right[n] is None)]
        pair['both_missing_notes']=[n for n in range(128) if left[n] is None and right[n] is None]
        pair['valid_note_count']=sum(x is not None and y is not None for x,y in zip(left,right))
        assert not pair['asymmetric_missing_notes']
    # Execute the actual OSC refresh against every active melodic OSC in PRELOAD.
    # Its original stereo lookup consumes the directory just constructed above.
    preload_path=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all';preload=preload_path.read_bytes()
    assert hashlib.sha256(preload).hexdigest()=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    osc,params,timbre,patch=0x11050000,0x11051000,0x11052000,0x11053000
    a.write(osc+8,params);a.write(osc+0x49C,timbre);a.write(timbre+8,patch);a.write(0xC199BD88,registry)
    references=[];oscillators=0;programs=0;slot_checks=0
    for pindex in range(768):
        data=preload[0x1EF220+2140*pindex:0x1EF220+2140*(pindex+1)];mode=data[0x508]&7
        if mode==2:continue
        assert mode in [0,1];programs+=1;a.uc.mem_write(patch,data)
        for oscillator in range(1+mode):
            block=data[0x564+380*oscillator:0x564+380*(oscillator+1)];a.uc.mem_write(params,block)
            # Clear only the maps before a refresh, preserving object pointers.
            a.uc.mem_write(osc+12,bytes(4*288));call(0x1F6654,osc);oscillators+=1
            for slot in range(4):
                if not block[8*slot]&3:continue
                bank=block[8*slot+1];number=struct.unpack_from('<H',block,8*slot+2)[0]
                assert bank in [0,1]
                indices=[number] if bank==0 else [pairs[number]['left'],pairs[number]['right']]
                for side,index in enumerate(indices):
                    address=osc+12+288*slot+144*side
                    assert word(address)==BASE+0x48F5CC+28*index
                    assert bytes(a.uc.mem_read(address+12,128))==bytes(mapped[index]['key_map'])
                    slot_checks+=1
                references.append(dict(program=f'{chr(65+pindex//128)}{pindex%128:03d}',oscillator=oscillator+1,
                    slot=slot+1,bank=bank,number=number,multisamples=indices))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
        stereo_pairs=pairs,multisamples=496,region_lookup_cases=lookup_cases,missing_map_entries=absent,
        preserved_map_entries=unwritten,programs=programs,active_oscillators=oscillators,material_side_checks=slot_checks,
        references=references,mappings=mapped,
        conclusion='No asymmetric missing key region or invalid sample index in the seven built-in melodic stereo pairs',
        boundaries=['bank-id mapping fixed to built-in bank0; memory allocation and exception-frame helpers supplied',
            'maps start with zeroed bytes; six organ maps preserve note0 instead of writing it',
            'expansion banks, dynamic bank unload and damaged storage are not covered',
            'Program slots are checked for mapping integrity; per-note pitch, layer admission and audio are separate'],
        inputs=[dict(path=str(preload_path.relative_to(ROOT)),sha256=hashlib.sha256(preload).hexdigest())],
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest())
    (OUT/'factory-regions-check.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({k:result[k] for k in ['passed','stereo_pairs','region_lookup_cases','missing_map_entries','preserved_map_entries','programs','active_oscillators','material_side_checks']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
