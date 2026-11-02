#!/usr/bin/env python3
"""Original application queue drain and parameter record dispatch in private RAM."""
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

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('parameter-record-dispatch',0x39BD8,0x39D80),
                       ('parameter-batch-dispatch',0x39D80,0x3A1AC),
                       ('parameter-live-write',0x207DCC,0x2080CC),
                       ('parameter-common-callback',0x20A9B0,0x20ADA8)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm:return
    a=Arm(f)
    def call(p,*args,**kw):return a.call(p,*args,**kw)
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def h(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def b(p):return a.uc.mem_read(p,1)[0]
    def zero(m):return 0
    app,root,manager,context=0x11000000,0x11000100,0x11000200,0x11000300
    q1,q2,qbank,qpage=0x11001000,0x11001100,0x11001200,0x11001300
    record,changes=0x11002000,0x11003000
    a.write(app+0x18,root);a.write(root+0xC,manager);a.write(root+0x1C,0x11000400)
    a.write(manager+0x10,context);a.write(manager+0x14,0)
    a.write(0xC0F55850,root);a.write(0xC0F558C0,0)
    for q in [q1,q2,qbank,qpage]:a.write(q+4,q+0x40);a.write(q+8,q+0x60)
    flush_cases=[];order=[]
    for locked,which,mask in itertools.product(range(2),range(2),range(8)):
        active=[q1,q2][which]
        a.write(app+4,active,qbank,qpage,q1,q2);a.write(app+0x1C,locked)
        sizes={active+0x40:mask&1,qbank+0x40:(mask>>1)&1,qpage+0x40:(mask>>2)&1}
        order.clear()
        def dispatch(m,tag):
            assert m.get('R0')==app and m.get('R1')==active
            assert w(app+0x1C)==1 and w(app+4)==[q2,q1][which]
            order.append(tag);return 0
        a.stubs={0x2959C:lambda m:sizes[m.get('R0')],
                 0x395B0:lambda m:dispatch(m,'bank'),0x397C0:lambda m:dispatch(m,'context'),
                 0x39D80:lambda m:dispatch(m,'parameters')}
        result=call(0x3A0FC,app)
        expected=bool(mask and not locked)
        assert result==expected and order==(['bank','context','parameters'] if expected else [])
        assert w(app+0x1C)==locked
        assert w(app+4)==([q2,q1][which] if expected else active)
        flush_cases.append(dict(locked=locked,active=which,nonempty_mask=mask,processed=bool(result)))

    # Record dispatch: model getter and setter, execute original type decisions,
    # suppression flag and old/new notification record construction.
    arena=0x11010000;appended=[];events=[];current=17
    def allocate(m):
        nonlocal arena
        p=arena;arena+=0x40;a.uc.mem_write(p,bytes(0x40));return p
    def append(m):appended.append(m.get('R1'));return 0
    def getter(m):
        assert [m.get('R0'),m.get('R1'),m.get('R2'),m.get('R3')]==[100,2,0,1]
        events.append(['get',current]);return current
    def setter(m):
        nonlocal current
        events.append(['set',w(m.get('SP')),m.get('R3'),w(0xC171C4C4)])
        current=m.get('R3');return 0
    def post(m):events.append(['post',w(0xC171C4C4)]);return 0
    type_cases=[]
    for kind,flag,old,new in itertools.product([0,12,14,15,16,18,19,20,21],range(2),[0,17],[0,17,99]):
        arena=0x11010000;current=old;events.clear();appended.clear();a.write(0xC171C4C4,0)
        a.uc.mem_write(record,struct.pack('<IHHIBBxx',0,100,2,new,kind,flag))
        a.stubs={0xD5AC4:getter,0x207DCC:setter,0x208B68:post,0x14E730:allocate,0x29084:append}
        call(0x39BD8,app,changes,record)
        effective=14 if kind==15 and old!=new else kind
        skipped=kind==15 and old==new
        writes=kind in [12,14,16,18,19,20] or kind==15 and old!=new
        expected=[['get',old]]
        if kind==12:expected += [['set',12,new,flag],['post',0]]
        elif writes:expected += [['set',effective,new,0]]
        if not skipped:expected += [['get',new if writes else old]]
        assert events==expected,(kind,flag,old,new,events,expected)
        assert len(appended)==int(not skipped) and w(0xC171C4C4)==0
        if appended:
            data=list(struct.unpack('<IHHIIII',a.uc.mem_read(appended[0],24)))
            assert data==[0xC04714B4,100,2,effective,new if writes else old,old,flag],data
        type_cases.append(dict(kind=kind,flag=flag,old=old,requested=new,write=bool(writes),notice=not skipped))

    # Original descriptor getter + callback + scalar memory write. Retain the
    # recording hook, secondary notification and allocator as explicit boundaries.
    callbacks=[];notices=[]
    def recording(m):callbacks.append(m.get('R0'));return 0
    a.stubs={0x2DC184:zero,0x2DC1BC:zero,0x14E730:allocate,0x14E760:zero,0x2C4474:zero,
             0x2CD184:lambda m:w(0xC04AEDBC),0x262678:recording,
             0x324CC:zero,0x208B68:zero,0x29084:append}
    live_cases=[]
    for index,kind,flag,old,new in itertools.product(range(3),[12,14,15,16,18,19,20],range(2),[0,3],[0,3,7,255,256,0xFFFFFFFF]):
        arena=0x11010000;appended.clear();callbacks.clear()
        table=f.pointer(0x407BD0+100*4);entries=f.pointer(table+4);entry=f.pointer(entries+4*index)
        target=f.u32(entry);desc=f.pointer(entry+4);lo=f.u32(desc+8);hi=f.u32(desc+12)
        a.uc.mem_write(target,bytes([old]));a.write(0xC171C4C4,0)
        a.uc.mem_write(record,struct.pack('<IHHIBBxx',0,100,index,new,kind,flag))
        call(0x39BD8,app,changes,record)
        skipped=kind==15 and old==new
        expected=old if skipped else new&255
        assert b(target)==expected,(index,kind,flag,old,new,b(target),expected)
        assert len(appended)==int(not skipped)
        if appended:
            data=list(struct.unpack('<IHHIIII',a.uc.mem_read(appended[0],24)))
            assert data==[0xC04714B4,100,index,14 if kind==15 else kind,min(hi,max(lo,expected)),old,flag],data
        assert w(0xC171C4C4)==0
        live_cases.append(dict(index=index,kind=kind,flag=flag,old=old,requested=new,stored=expected,readback=min(hi,max(lo,expected)),notice=not skipped))

    # Batch iterator and effect parameter range handling. Execute original batch
    # logic, capturing the per-record dispatch to isolate its selection/range rules.
    batch_cases=[];lists={};iterators={};delivered=[];cleanup=[]
    def ctor(m):a.write(m.get('R0'),0x11005000);return 0
    a.write(0x11005004,0xC02FF000)
    def iterator(m):iterators[m.get('R0')]=iter(list(lists.get(m.get('R1'),[])));return 0
    def next_item(m):return next(iterators[m.get('R0')],0)
    def append_list(m):lists.setdefault(m.get('R0'),[]).append(m.get('R1'));return 0
    def record_boundary(m):delivered.append(m.get('R2'));return 0
    def clear_list(m):lists[m.get('R0')]=[];cleanup.append('list');return 0
    def clear_map(m):cleanup.append('map');return 0
    def effect_type(m):return 0
    table,entries,entry,desc=0x11006000,0x11006100,0x11006200,0x11006300
    for group in [125,126,127,128,129,131,132,176]:a.write(0xC0407BD0+group*4,table)
    a.write(table,1,entries);a.write(entries,entry);a.write(entry,0x11006400,desc)
    a.uc.mem_write(desc,struct.pack('<BBBBIiiI',0,0,0,0,0,-20,70,0))
    alg=0x11006500;a.write(0xC0336D6C,alg)
    base_stubs={0x2DC184:zero,0x2DC1BC:zero,0x14E730:allocate,0x29668:ctor,
                0x29F14:iterator,0x29FE0:next_item,0x29F94:zero,0x39BD8:record_boundary,
                0x345AC:zero,0x34B48:zero,0x207C00:zero,0x209904:zero,
                0x294F4:clear_list,0x28C2C:clear_map,0x2FF000:zero,0x23E038:effect_type}
    for group,address_valid,algorithm,value in itertools.product([100,125,126,127,128,129,131,132,176],range(2),[124,125],[-100,-20,0,70,100]):
        arena=0x11010000;delivered.clear();cleanup.clear();lists.clear();iterators.clear()
        a.write(entry,0x11006400 if address_valid else 0)
        a.uc.mem_write(alg+0x1E,struct.pack('<h',algorithm))
        a.uc.mem_write(record,struct.pack('<IHHIBBxx',0,group,0,value&0xFFFFFFFF,12,1))
        lists[q1+0x40]=[record];a.stubs=dict(base_stubs)
        call(0x39D80,app,q1)
        effect=group!=100
        skipped=effect and (not address_valid or group in [127,128,129] and algorithm>124)
        expected=min(70,max(-20,value)) if effect and not skipped else value
        assert delivered==([] if skipped else [record]),(group,address_valid,algorithm,delivered)
        assert w(record+8)==expected&0xFFFFFFFF,(group,value,w(record+8),expected)
        assert cleanup==['list','list','map']
        batch_cases.append(dict(group=group,address_valid=address_valid,algorithm=algorithm,requested=value,skipped=skipped,dispatched_value=expected if not skipped else None))

    # Continuous SysEx -> cache -> intake -> rotated batch -> original memory
    # callbacks. Three parameters, three drain cycles, two queue directions.
    from firmware_sequence_sysex import parameter
    cache,wire=0x11040000,0x11045000
    a.write(root+0x20,app);a.write(app+0x20,1);a.write(0xC1690248,cache)
    a.uc.mem_write(cache,bytes(0x2224))
    a.uc.mem_write(0xC1DCD62A,b'\x01');a.uc.mem_write(0xC1DCD628,b'\x03')
    a.uc.mem_write(0xC17456AC+0x4FE,b'\x20')
    a.uc.mem_write(0xC171D4DC,bytes(2));a.uc.mem_write(0xC171D4DA,bytes(2))
    song=0x11050000
    a.uc.mem_write(0xC1747538+0x208,b'\x07');a.write(0xC1747538+8+4*7,song)
    a.uc.mem_write(song+0x4F7,b'\xA5'*3)
    a.uc.mem_write(0xC171D516,bytes(2));a.write(0xC17146B4+0x14,0)
    mapped={};notice_batches=[]
    def lookup(m):
        value=mapped.get((m.get('R0'),m.get('R1')))
        if value:a.write(m.get('R2'),value)
        return int(value is not None)
    def insert(m):mapped[(m.get('R0'),m.get('R1'))]=m.get('R2');return 0
    def reset_map(m):
        for k in list(mapped):
            if k[0]==m.get('R0'):del mapped[k]
        return 0
    def notify_batch(m):
        notice_batches.append([list(struct.unpack('<IHHIIII',a.uc.mem_read(x,24))) for x in lists.get(m.get('R1'),[])])
        return 0
    integrated=[]
    for direction in range(2):
        arena=0x11010000;lists.clear();mapped.clear();notice_batches.clear()
        a.write(app+4,[q1,q2][direction],qbank,qpage,q1,q2);a.write(app+0x1C,0)
        for index in range(3):a.uc.mem_write(0xC1745BA3+index,b'\0')
        a.stubs=dict(base_stubs)
        del a.stubs[0x39BD8]
        del a.stubs[0x207C00]
        a.stubs.update({0x14E760:zero,0x2C4474:zero,0x2CD184:lambda m:w(0xC04AEDBC),
                       0x324CC:zero,0x208B68:zero,
                       0x28E00:lookup,0x28CE4:insert,0x28C2C:reset_map,
                       0x29084:append_list,0x2959C:lambda m:len(lists.get(m.get('R0'),[])),
                       0x2926C:zero,0x209904:notify_batch,0x2CD594:allocate,
                       0x205AC0:zero,0x2CD694:zero})
        for cycle,values in enumerate([[1,2,3],[17,255,256],[0,7,0xFFFFFFFF]]):
            active=w(app+4);before=list(a.uc.mem_read(0xC1745BA3,3))
            for value in values:
                for index in range(3):
                    raw,_=parameter(3,0,index,value)
                    a.uc.mem_write(wire,raw);call(0x2564E0,wire,0)
            assert len(lists[active+0x40])==3
            assert list(a.uc.mem_read(0xC1745BA3,3))==before
            assert [w(cache+0x900+4*i) for i in range(3)]==[values[-1]]*3
            assert call(0x3A0FC,app)==1
            stored=values[-1]&255
            assert list(a.uc.mem_read(0xC1745BA3,3))==[stored]*3
            assert bytes(a.uc.mem_read(song+0x4F7,3))==b'\xA5'*3
            assert w(app+4)!=active and lists[active+0x40]==[]
            records=notice_batches[-1]
            assert len(records)==3
            for index,row in enumerate(records):
                hi=[26,11,7][index]
                assert row==[0xC04714B4,100,index,12,min(hi,stored),min(hi,before[index]),1],row
            integrated.append(dict(direction=direction,cycle=cycle,inputs=values,stored=stored,notifications=records,song_mirror_unchanged=True))

    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
                flush_cases=flush_cases,type_cases=type_cases,live_cases=live_cases,batch_cases=batch_cases,integrated=integrated,
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                additional_helpers={'firmware_sequence_sysex.py':hashlib.sha256((ROOT/'research/tools/firmware_sequence_sysex.py').read_bytes()).hexdigest()},
                boundaries=['Original queue rotation, event-type branch and batch filter execute',
                            'Batch effect directories and algorithm entries are synthetic private-memory fixtures',
                            'Live cases execute original namespace 100 indices 0..2 descriptors, getter, callback and scalar writer',
                            'Six continuous cycles execute original SysEx, cache writer, intake, rotation, empty preparers, batch dispatch, namespace 100 callbacks, operation-8 notification and song-mirror gate',
                            'Allocation, exception registration and list/map containers are modeled; notification message handoff and type-14 follow-up are captured',
                            'Standalone live write matrix captures the song-mirror hook; continuous cycles execute it and confirm the saved song fields remain unchanged',
                            'Optional manager observer is null; no UI, sound engine, hardware or real song loader'])
    (OUT/'parameter-dispatch-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,flush_cases=len(flush_cases),type_cases=len(type_cases),live_cases=len(live_cases),batch_cases=len(batch_cases),integrated_cycles=len(integrated)),indent=2))

if __name__=='__main__':main()
