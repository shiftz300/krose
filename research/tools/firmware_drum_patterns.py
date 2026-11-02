#!/usr/bin/env python3
"""Original PPAT pointer relocation, event blocks and packed replacement."""
import argparse,contextlib,hashlib,io,json,struct
from pathlib import Path
from collections import Counter
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
SOURCE=ROOT/'research/firmware/KROSS2_V124/KROSS2SY/PPAT.BIN'
SHA='1f734fb8ffd41efa030079f9436753dae7e10e5cf7ac05a42921c28cc6592135'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def decode(data,start):
    cursor=start;bars=[];types=Counter()
    while data[cursor]!=3:
        assert data[cursor]==1,(hex(cursor),data[cursor:cursor+8].hex())
        count,bar=struct.unpack_from('<HH',data,cursor+4);assert count>0
        events=[data[cursor+8*j:cursor+8*(j+1)] for j in range(1,count)]
        for e in events:types[e[0]]+=1
        bars.append(dict(number=bar,offset=cursor,records=count,events=[e.hex() for e in events]))
        cursor+=count*8
    return data[start:cursor+8],bars,types
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();assert sha(SOURCE)==SHA;source=SOURCE.read_bytes();data=source[64:]
    assert source[:4]==b'KSB0' and struct.unpack_from('>I',source,4)[0]==64
    assert struct.unpack_from('>I',source,28)[0]==len(data)==0x1404E4
    old=struct.unpack_from('<I',data)[0];rows=[];streams=[];metadata=[];all_types=Counter();tail=0x7CE4
    for i in range(999):
        r=data[4+32*i:36+32*i];ptr=struct.unpack_from('<I',r,28)[0];metadata.append(r)
        stream,bars,types=decode(data,ptr-old) if ptr else (b'',[],Counter())
        if ptr:assert ptr-old==tail;tail+=len(stream)
        streams.append(stream);all_types.update(types)
        rows.append(dict(index=i,name=r[:24].decode().rstrip(),attributes=r[24:28].hex(),
                         original_pointer=ptr,offset=ptr-old if ptr else None,bytes=len(stream),bars=bars,types=dict(types)))
    assert not any(data[tail:])
    OUT.mkdir(parents=True,exist_ok=True)
    catalog=dict(source=str(SOURCE.relative_to(ROOT)),source_sha256=SHA,original_base=old,directory_count=999,
                 used_bytes=tail,types=dict(all_types),patterns=rows)
    (OUT/'drum-patterns.json').write_text(json.dumps(catalog,indent=2)+'\n')
    for name,lo,hi in [('drum-pattern-directory',0x286E5C,0x28718C),('drum-pattern-replace',0x28718C,0x287318),('drum-pattern-bar',0x2880EC,0x2881EC)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    a=Arm(f);base=0x11000020;meta=0x11160000;events=0x11170000
    def read(p,n):return bytes(a.uc.mem_read(p,n))
    def call(p,*args,**kw):return a.call(p,*args,**kw)&0xFFFFFFFF
    def expected(metas,ss):
        out=bytearray(len(data));struct.pack_into('<I',out,0,base);cursor=0x7CE4
        for i,(m,s) in enumerate(zip(metas,ss)):
            out[4+32*i:36+32*i]=m;struct.pack_into('<I',out,32+32*i,base+cursor if s else 0)
            out[cursor:cursor+len(s)]=s;cursor+=len(s)
        return bytes(out)
    a.uc.mem_write(base,data);call(0x2870C0,base,count=15000000)
    pristine=expected(metadata,streams);assert read(base,len(data))==pristine
    assert call(0x287030,base)==sum(len(x)//8 for x in streams)
    assert call(0x287038,base)==base+tail
    bar_checks=0
    for row in rows:
        i=row['index'];assert call(0x286E5C,base,i)==base+4+32*i
        ptr=call(0x286E78,base,i);assert ptr==(base+row['offset'] if row['offset'] is not None else 0)
        assert call(0x286FBC,base,i)==len(streams[i])//8
        for b in row['bars']:
            assert call(0x286EA4,base,i,b['number'])==base+b['offset'];bar_checks+=1
    assert call(0x286E5C,base,999)==0
    # Replace first/middle/last occupied and empty slots; compare the entire pool.
    filled=[i for i,s in enumerate(streams) if s];empty=[i for i,s in enumerate(streams) if not s]
    edits=[];targets=sorted(set([0,1,filled[len(filled)//2],filled[-1],empty[0],998]))
    for index in targets:
        for n in [0,1,7,32]:
            a.uc.mem_write(base,pristine)
            if n:
                blocks=[]
                for bar in range(2):
                    blocks.append(struct.pack('<BBBBHH',1,0,0,0,n+1,bar))
                    blocks.extend(struct.pack('<BBBBHH',9,0,36+j%12,80+j%48,60,j*30) for j in range(n))
                new=b''.join(blocks)+bytes([3,0,0,0,0,0,0,0])
            else:new=b''
            m=b'Replacement'.ljust(24,b' ')+bytes([2,19,0,0])+bytes(4)
            a.uc.mem_write(meta,m);a.uc.mem_write(events,new or bytes(8))
            assert call(0x28718C,base,index,meta,events if new else 0,count=15000000)==1
            ss=streams.copy();mm=metadata.copy();ss[index]=new;mm[index]=m
            assert read(base,len(data))==expected(mm,ss),(index,n)
            edits.append(dict(index=index,notes_per_bar=n,records=len(new)//8))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),inputs=[dict(path=str(SOURCE.relative_to(ROOT)),sha256=SHA)],
        catalog_sha256=sha(OUT/'drum-patterns.json'),directory_count=999,occupied=len(filled),empty=len(empty),
        event_records=sum(len(x)//8 for x in streams),bar_checks=bar_checks,types=dict(all_types),edits=edits,
        boundaries=['Original relocation, directory selection, event count, bar lookup, memmove, replacement and tail clear execute without stubs',
                    'All source patterns are checked; replacement uses synthetic two-bar note blocks and compares the complete packed pool',
                    'Playback triggers, synchronization, note synthesis and physical file I/O do not execute'])
    (OUT/'drum-patterns-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['passed','occupied','empty','event_records','bar_checks','types']},indent=2))
if __name__=='__main__':main()
