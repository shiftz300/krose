#!/usr/bin/env python3
"""Original recorded-parameter cache, replay flags and application queue intake."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import struct
from pathlib import Path
from program_firmware import Arm, Firmware, FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'


def region(group):
    if group==100:return 0x900,14
    if 108<=group<=123:return 0x938+240*(group-108),60
    if group==124:return 0x1838,47
    if 125<=group<=129:return 0x18F4+288*(group-125),72
    if group==130:return 0x1E94,9
    if group in [131,132]:return 0x1EB8+288*(group-131),72
    if group==175:return 0x20F8,3
    if group==176:return 0x2104,72
    return None


def child(group,index):
    if group==124 and 0<=index<=4:return 125+index
    if group==130 and 0<=index<=1:return 131+index
    if group==175 and index==0:return 176
    return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true')
    args=parser.parse_args();f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('parameter-cache-layout',0x23CCB8,0x23CF08),
                       ('parameter-cache-state',0x23D1D0,0x23D394),
                       ('parameter-cache-write-replay',0x23D508,0x23D83C),
                       ('parameter-queue-intake',0x38A64,0x38B64),
                       ('parameter-notification',0x3A1AC,0x3A218)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm:return
    a=Arm(f);obj,cache,output=0x11000000,0x11001000,0x11004000
    counts={g:f.u32(f.pointer(0x407BD0+g*4)) for g in range(100,179)}
    def call(p,*args,**kw):return a.call(p,*args,**kw)
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def get(data,p):return struct.unpack_from('<I',data,p)[0]
    def put(data,p,v):struct.pack_into('<I',data,p,v&0xFFFFFFFF)
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def pb(p,v):a.uc.mem_write(p,bytes([v&255]))
    a.write(obj,cache)
    mapping_cases=0
    for group,index in itertools.product(range(100,179),range(80)):
        r=region(group);expected=cache+r[0]+4*index if r and index<r[1] else 0
        assert call(0x23CCB8,cache,group,index)&0xFFFFFFFF==expected
        mapping_cases+=1
    slots=[]
    for group in range(100,179):
        if region(group):
            base,count=region(group);slots.extend(range(base,base+count*4,4))
    assert sorted(slots)==list(range(0x900,0x2224,4)) and len(slots)==1609
    a.uc.mem_write(cache,b'\xA5'*0x2300);call(0x23CDCC,cache)
    assert bytes(a.uc.mem_read(cache,0x2300))==bytes(0x900)+b'\xA5'*0x1A00
    pool_cases=[]
    for slot,alternate in itertools.product([0,1,7,15],range(2)):
        call(0x23D1D0,obj,slot,alternate)
        expected=0xC1712114 if alternate else 0xC169211C+0x2224*slot
        assert w(obj)==expected;pool_cases.append(dict(slot=slot,alternate=alternate,address=expected))
    a.write(obj,cache)

    write_cases=0;alias=[]
    baseline=b'\xA5'*0x2300
    for group in range(100,179):
        for index,value in itertools.product(sorted(set([0,1,31,32,59,60,71,72,max(0,counts[group]-1),counts[group],65535])),[0,0x12345678,0xFFFFFFFF]):
            a.uc.mem_write(cache,baseline);expected=bytearray(baseline)
            accepted=index<counts[group]
            r=region(group)
            if accepted:
                if r and index<r[1]:
                    bit_offset=32*(group-100)+4*(index//32);mask=1<<(index%32)
                    put(expected,bit_offset+0x480,get(expected,bit_offset+0x480)&~mask)
                    put(expected,bit_offset,get(expected,bit_offset)|mask)
                    put(expected,r[0]+4*index,value)
                derived=child(group,index)
                if derived is not None:
                    begin=32*(derived-100)
                    expected[begin:begin+32]=b'\xFF'*32
                    expected[begin+0x480:begin+0x480+32]=b'\xFF'*32
            call(0x23D61C,obj,group,index,value)
            assert bytes(a.uc.mem_read(cache,0x2300))==expected,(group,index,value)
            if group==175 and index in [0,1,2] and value==0x12345678:
                alias.append(dict(group=group,index=index,flag_offset=32*(group-100),second_flag_offset=32*(group-100)+0x480,
                                  value_offset=r[0]+4*index,child_group=child(group,index)))
            write_cases+=1
    clear_cases=0
    for group,index in itertools.product(range(100,136),[0,31,32,71,127,255]):
        a.uc.mem_write(cache,b'\xFF'*0x900)
        call(0x23CE38,cache,group,index)
        off=32*(group-100)+4*(index//32);expected=0xFFFFFFFF^(1<<(index%32))
        assert w(cache+off)==w(cache+off+0x480)==expected
        assert call(0x23CE7C,cache,group,index)==0
        clear_cases+=1

    replay=[]
    def capture(m):
        replay.append([m.get('R1'),m.get('R2'),m.get('R3'),w(m.get('SP')),w(m.get('SP')+4)])
        return 0
    a.stubs={0x241EBC:capture}
    replay_cases=0
    for group,index,present,blocked in itertools.product([100,108,123,124,130],[2,8],range(2),range(2)):
        a.uc.mem_write(cache,bytes(0x2300));replay.clear()
        base,count=region(group);value=0x87654321
        a.write(cache+base+4*index,value)
        off=32*(group-100)+4*(index//32);mask=1<<(index%32)
        a.write(cache+off,mask if present else 0);a.write(cache+off+0x480,mask if blocked else 0)
        call(0x23D6E8,obj,3,group,index,stack=(5,))
        expected=[[3,group-100,index,5,value]] if present and not blocked else []
        assert replay==expected
        replay_cases+=1
    transition_cases=0
    for parent,selection,derived in [(124,i,125+i) for i in range(5)]+[(130,i,131+i) for i in range(2)]:
        table=0xC0000000+f.pointer(0x407BD0+4*derived)
        original=w(table);a.write(table,72)
        for index in [0,31,32,71]:
            a.uc.mem_write(cache,bytes(0x2300));replay.clear()
            call(0x23D61C,obj,parent,selection,1)
            call(0x23D6E8,obj,3,derived,index,stack=(5,))
            assert replay==[] and call(0x23D23C,obj,derived,index)==1 and call(0x23D2F8,obj,derived,index)==1
            call(0x23D61C,obj,derived,index,0x12345678)
            call(0x23D6E8,obj,3,derived,index,stack=(5,))
            assert replay==[[3,derived-100,index,5,0x12345678]] and call(0x23D2F8,obj,derived,index)==0
            transition_cases+=1
        a.write(table,original)
    a.stubs={}
    serialization_cases=0
    for value in [0,1,127,128,0x7FFFFFFF,0x80000000,0xFFFFFFFF]:
        a.write(cache+0x900,value)
        call(0x23D300,obj,100,0,output,stack=(output+1,output+2,output+3,output+4))
        expected=[value>>28]+[(value>>s)&127 for s in [21,14,7,0]]
        assert list(a.uc.mem_read(output,5))==expected
        assert call(0x23D36C,obj,100,0)&0xFFFFFFFF==value
        serialization_cases+=1

    # Execute real SysEx parameter path, actual cache writer and notification
    # wrapper; retain application work-list allocation/map as boundaries.
    root,app,queue=0x11010000,0x11010100,0x11010200
    a.write(0xC0F55850,root);a.write(root+0x20,app)
    a.write(app+4,queue);a.write(app+0x20,1)
    a.write(queue+4,0x11010300);a.write(queue+8,0x11010400)
    a.write(0xC1690248,cache)
    allocated=[];appended=[];mapped={};next_alloc=0x11020000
    def allocate(m):
        nonlocal next_alloc
        assert m.get('R0')==16
        p=next_alloc;next_alloc+=16;allocated.append(p);return p
    def lookup(m):
        key=m.get('R1');p=mapped.get(key)
        if p:a.write(m.get('R2'),p)
        return int(p is not None)
    def insert(m):mapped[m.get('R1')]=m.get('R2');return 1
    def append(m):appended.append(m.get('R1'));return 1
    a.stubs={0x14E730:allocate,0x28E00:lookup,0x28CE4:insert,0x29084:append,0x2959C:lambda m:len(appended)}
    a.uc.mem_write(cache,bytes(0x2300));pb(0xC1DCD62A,1);pb(0xC1DCD628,3)
    pb(0xC17456AC+0x4FE,1<<5);ph(0xC171D4DC,0);ph(0xC171D4DA,0)
    from firmware_sequence_sysex import parameter
    integrated=[]
    for namespace,index in [(100,2),(108,1),(108,0),(124,0),(125,0),(175,0),(176,0)]:
        allocated.clear();appended.clear();mapped.clear()
        for value in [11,22,33]:
            raw,_=parameter(3,namespace-100,index,value)
            a.uc.mem_write(output,raw);call(0x2564E0,output,0)
        preserve=(child(namespace,index) is not None or 108<=namespace<=123 and index==0 or namespace in [125,126,127,128,129,131,132,176])
        assert len(allocated)==len(appended)==(3 if preserve else 1)
        values=[w(p+8) for p in appended]
        assert values==([11,22,33] if preserve else [33])
        for p in appended:
            assert list(struct.unpack('<HH',a.uc.mem_read(p+4,4)))==[namespace,index]
            assert list(a.uc.mem_read(p+12,2))==[12,1]
        integrated.append(dict(namespace=namespace,index=index,queued_values=values,records=len(appended),cache_supported=bool(region(namespace))))

    intake_cases=0
    for namespace,index in [(100,2),(108,0),(124,0),(125,0),(175,0),(176,0)]:
        preserve=(child(namespace,index) is not None or 108<=namespace<=123 and index==0 or namespace in [125,126,127,128,129,131,132,176])
        for kind,flag in itertools.product([12,14],range(2)):
            allocated.clear();appended.clear();mapped.clear()
            for value in [11,22,33]:call(0x38A64,queue,namespace,index,value,stack=(kind,flag))
            expected=[11,22,33] if kind==12 and flag and preserve else [33]
            assert [w(p+8) for p in appended]==expected
            assert all(list(a.uc.mem_read(p+12,2))==[kind,flag] for p in appended)
            intake_cases+=1
    threshold=[];flushed=[]
    a.stubs[0x3A0FC]=lambda m:flushed.append(m.get('R0')) or 1
    for active,flag,count in itertools.product(range(2),range(2),[499,500,501]):
        allocated.clear();appended.clear();mapped.clear();flushed.clear()
        a.write(app+0x20,active)
        a.stubs[0x2959C]=lambda m,n=count:n
        call(0x3A1AC,app,100,2,123,stack=(flag,))
        assert len(appended)==active
        assert bool(flushed)==bool(active and flag and count>500)
        threshold.append(dict(active=active,flag=flag,count=count,flush=bool(flushed)))

    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
        mapping_cases=mapping_cases,value_slots=len(slots),pool_cases=pool_cases,
        stock_parameter_counts=counts,write_cases=write_cases,clear_cases=clear_cases,
        replay_cases=replay_cases,transition_cases=transition_cases,serialization_cases=serialization_cases,late_namespace_flag_offsets=alias,
        integrated=integrated,intake_cases=intake_cases,notification_threshold=threshold,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        additional_helpers={'firmware_sequence_sysex.py':hashlib.sha256((ROOT/'research/tools/firmware_sequence_sysex.py').read_bytes()).hexdigest()},
        boundaries=['Original cache address map, flags, writer, getter, replay gate and application queue-intake logic execute',
                    'Replay destination 241EBC captured for flag matrix; integrated SysEx uses real 241EBC and 23D61C',
                    'Application allocation, linked-list insertion, map and size are modeled boundaries; dispatch callbacks not run',
                    'Parameter counts are initial firmware image values; dynamic effect namespaces may be activated later',
                    '28 selector/replay transitions use synthetic count=72 for seven effect namespaces, then restore the image counts',
                    'Namespace 175 writes flag locations beyond the initial 0x900 flag region in controlled RAM; full reachability pending',
                    'No devices, file loader, UI event loop or audio processing'])
    (OUT/'parameter-cache-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,mapping_cases=mapping_cases,value_slots=len(slots),write_cases=write_cases,
                         clear_cases=clear_cases,replay_cases=replay_cases,integrated=len(integrated)),indent=2))


if __name__=='__main__':main()
