#!/usr/bin/env python3
"""Original synchronous message reply table, event pump and parameter handoff."""
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
    for name,lo,hi in [('reply-table',0x2B9D90,0x2BA094),('reply-wait-pump',0x312EC,0x31454),
                       ('reply-normal-pump',0x31250,0x312EC),('parameter-message-handoff',0x205AC0,0x205B6C),
                       ('parameter-mmi-copy-reply',0x14658C,0x146708)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f)
    def call(p,*args,**kw):return a.call(p,*args,**kw)
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def h(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def zero(m):return 0
    table,msg,other,context,vtable=0x11000000,0x11001000,0x11001100,0x11002000,0x11002100
    def message(p,kind,subtype,command,token):
        a.uc.mem_write(p,struct.pack('<IBBHHHI',0,kind&255,subtype&255,token&65535,command&65535,0,0))
    def row(i):return list(struct.unpack('<HHHHI',a.uc.mem_read(table+8+12*i,12)))
    def reset():a.uc.mem_write(table,b'\xA5'*0x190);call(0x2B9DE0,table)
    reset();assert all(row(i)==[65535,65535,0,0xA5A5,0] for i in range(32))
    register_cases=[]
    for i in range(34):
        ret=call(0x2B9ECC,table,i%8,100+i,i)
        assert ret==i+1
        register_cases.append(dict(request=i,stored=i<32,counter=ret))
    assert [row(i)[:3] for i in range(32)]==[[i%8,100+i,i] for i in range(32)]
    call(0x2B9F40,table,3,103,3);assert row(3)[:3]==[65535,65535,0] and w(table+4)==34
    assert call(0x2B9ECC,table,7,999,65535)==35 and row(3)[:3]==[7,999,65535]
    a.write(table+4,0xFFFFFFFF);assert call(0x2B9ECC,table,1,123,99)==0

    match_cases=0
    for subtype,command,token,delta in itertools.product([0,1,7,127],[0,5,13,32767,65535],[0,1,65535],range(4)):
        reset();call(0x2B9ECC,table,subtype,command,token)
        sub2,cmd2,tok2=subtype,command,token
        if delta==1:sub2=(sub2+1)%128
        if delta==2:cmd2=(cmd2+1)&65535
        if delta==3:tok2=(tok2+1)&65535
        message(msg,8,sub2,cmd2,tok2)
        found=call(0x2B9FC0,table,msg)
        assert found==int(delta==0)
        if found:
            message(other,8,sub2,cmd2,tok2)
            assert call(0x2B9FC0,table,other)==1 and row(0)[4]==msg
        assert call(0x2BA000,table,subtype,command,token)&0xFFFFFFFF==(msg if found else 0)
        assert call(0x2BA000,table,subtype,command,token)==0
        assert w(table+4)==1
        match_cases+=1

    a.write(context,vtable);a.write(context+0x28,table)
    a.write(vtable+0xC,0xC02FF000,0xC02FF004)
    received=[];dispatched=[];feed=[]
    def receive(m):
        assert feed,'wait loop consumed more input than expected'
        flags,pointer=feed.pop(0);a.write(m.get('R1'),pointer)
        received.append([flags,pointer]);return flags
    def dispatch(m):dispatched.append([m.get('R1'),m.get('R2')]);return 0
    a.stubs={0x2FF000:receive,0x2FF004:dispatch}
    wait_cases=[]
    cases=[('plain-event',0x40000000,0,0,0,0,False),
           ('no-event',0,0,0,0,0,False),
           ('ordinary-message',0x80000000,9,0,13,42,False),
           ('unknown-reply',0x80000000,8,0,13,41,False),
           ('reserved-command',0x80000000,8,0,5,42,False),
           ('negative-subtype',0x80000000,8,255,13,42,False),
           ('large-subtype',0x80000000,8,8,13,42,False),
           ('other-request',0x80000000,8,1,20,71,True),
           ('other-request-and-event',0xC0000000,8,1,20,71,True)]
    for name,flags,kind,subtype,command,token,cache_other in cases:
        for matching_flags in [0x80000000,0xC0000000,0xFFFFFFFF]:
            reset();received.clear();dispatched.clear()
            if cache_other:call(0x2B9ECC,table,1,20,71)
            message(msg,kind,subtype,command,token);message(other,8,0,13,42)
            ptr=msg if flags&0x80000000 else 0
            feed[:]=[(flags,ptr),(matching_flags,other)]
            assert call(0x312EC,context,0,13,42)&0xFFFFFFFF==other
            expected=[]
            first=flags&0x7FFFFFFF if cache_other else flags
            if first:expected.append([first,msg if first&0x80000000 else 0])
            remaining=matching_flags&0x7FFFFFFF
            if remaining:expected.append([remaining,0])
            assert dispatched==expected,(name,matching_flags,dispatched,expected)
            assert len(received)==2 and not feed
            if cache_other:assert call(0x2BA000,table,1,20,71)&0xFFFFFFFF==msg
            wait_cases.append(dict(name=name,matching_flags=matching_flags,dispatched=dispatched.copy(),other_reply_saved=cache_other))

    # Cached current reply becomes available while an unrelated event handler
    # runs. The callback is a controlled representation of nested processing.
    reset();received.clear();dispatched.clear();message(other,8,0,13,42)
    def nested_dispatch(m):
        dispatched.append([m.get('R1'),m.get('R2')]);a.write(table+8+8,other);return 0
    a.stubs[0x2FF004]=nested_dispatch;feed[:]=[(0x40000000,0)]
    assert call(0x312EC,context,0,13,42)&0xFFFFFFFF==other
    assert len(received)==1 and row(0)[:3]==[65535,65535,0]

    # Ordinary pump: a cached matching reply loses the message-ready flag while
    # other event flags remain dispatchable. No synchronous wait is active here.
    normal_cases=[];a.stubs[0x2FF004]=dispatch;a.stubs[0x2926C]=zero
    for kind,subtype,flags,registered in itertools.product([8,9],[0,7,8,255],[0x80000000,0xC0000000],range(2)):
        reset();dispatched.clear();received.clear();message(msg,kind,subtype,5,88)
        if registered:call(0x2B9ECC,table,subtype,5,88)
        feed[:]=[(flags,msg)];call(0x31250,context)
        cached=kind==8 and subtype<=7 and registered
        remaining=flags&0x7FFFFFFF if cached else flags
        assert dispatched==([[remaining,msg if remaining&0x80000000 else 0]] if remaining else [])
        assert (row(0)[4]==msg)==bool(cached)
        normal_cases.append(dict(kind=kind,subtype=subtype,flags=flags,registered=registered,cached=bool(cached)))

    # Real parameter sender and RDAPI queue append. Receiver execution is a
    # virtual-call boundary returning a synthetic reply after checking the queue.
    heap=0x11080000;allocations=[]
    def allocate(m):
        nonlocal heap
        n=m.get('R0');p=heap;heap+=(n+15)&~15;a.uc.mem_write(p,bytes((n+15)&~15));allocations.append(n);return p
    osobj=0xC1B5AE44;manager=0x11003000;ref=0x11003100;reply=0x11003200;signals=[]
    a.write(manager+0x10,context)
    a.stubs={0x2DC184:zero,0x2DC1BC:zero,0x2E2F9C:allocate,0x14E730:allocate}
    call(0x2CCEB4,osobj,500,12)
    queues=w(osobj+4);destination=f.u32(0x4AEDB8);assert destination==3
    def wake(m):signals.append([m.get('R0'),m.get('R1')]);return 0
    source=0;request=0
    def reply_receive(m):
        head=w(queues+12*destination);tail=w(queues+12*destination+4)
        assert w(head)==request and w(request)==tail
        assert h(request+6)==source
        # Consume at the receiver boundary; queue link insertion itself ran.
        a.write(head,tail);a.write(tail,head)
        message(reply,8,0,13,source);a.write(m.get('R1'),reply);return 0x80000000
    a.stubs={0x132660:lambda m:0x55,0x132670:zero,0x2FC618:wake,
             0x2FF000:reply_receive,0x2FF004:dispatch}
    integrated=[]
    for source in [0,1,65534,65535]:
        reset();signals.clear();dispatched.clear();ph(0xC0F55856,source)
        request=call(0x2CD594,osobj,0)&0xFFFFFFFF
        message(request,9,0,12,0);a.write(ref,request)
        call(0x205AC0,manager,ref,13)
        assert w(ref)==reply and h(0xC0F55856)==(source+1)&65535
        assert signals==[[3,0x80000000]] and dispatched==[]
        a.write(ref,request);call(0x2CD694,osobj,ref)
        integrated.append(dict(token=source,next_token=(source+1)&65535,destination_task=destination,returned_reply=True))

    # Split the two task bodies at the synchronous wait boundary. Original
    # sender/queues, MMI type/subtype/command dispatch, clone loop and reply run;
    # resume the saved wait arguments after the real MMI reply is available.
    mmi,parameter_manager,destination_list=0x11006000,0x11006100,0x11006200
    payload,source_list,records=0x11004000,0x11004100,0x11005000
    a.write(mmi+4,parameter_manager);a.write(parameter_manager+4,destination_list)
    source_records=[];clones=[];iterators={};wait_args=[];freed=[]
    def begin(m):
        assert m.get('R1')==source_list
        iterators[m.get('R0')]=iter(source_records);return 0
    def next_item(m):return next(iterators[m.get('R0')],0)
    def append(m):
        assert m.get('R0')==destination_list
        clones.append(m.get('R1'));return 0
    def defer_wait(m):
        wait_args[:]=[m.get('R0'),m.get('R1'),m.get('R2'),m.get('R3')]
        return request
    def free_payload(m):freed.append(m.get('R0'));return 0
    handoffs=[]
    for length,source in itertools.product([0,1,3,32],[0,65535]):
        reset();signals.clear();clones.clear();wait_args.clear();freed.clear();dispatched.clear()
        source_records[:]=[records+24*i for i in range(length)]
        expected=[]
        for i,pointer in enumerate(source_records):
            raw=struct.pack('<IHHIIII',0xC04714B4,100+i%36,i%60,[12,14,16][i%3],0x12340000+i,0x87650000+i,i%2)
            expected.append(raw);a.uc.mem_write(pointer,raw)
        a.write(payload,source_list);ph(0xC0F55856,source)
        a.stubs={0x132660:lambda m:0x55,0x132670:zero,0x2FC618:wake,
                 0x312EC:defer_wait,0x2DC184:zero,0x2DC1BC:zero,
                 0x29F14:begin,0x29FE0:next_item,0x29F94:zero,
                 0x14E730:allocate,0x29084:append,0x14E760:free_payload}
        request=call(0x2CD594,osobj,0)&0xFFFFFFFF
        message(request,9,0,12,0);a.write(request+12,payload);a.write(ref,request)
        call(0x205AC0,manager,ref,13)
        assert wait_args==[context,0,13,source]
        assert call(0x2CD7F4,queues+3*12)&0xFFFFFFFF==request
        call(0x143994,mmi,request)
        assert len(clones)==length and all(p not in source_records for p in clones)
        assert [bytes(a.uc.mem_read(p,24)) for p in clones]==expected
        for p in source_records:a.uc.mem_write(p,bytes(24))
        assert [bytes(a.uc.mem_read(p,24)) for p in clones]==expected
        reply_pointer=call(0x2CD7F4,queues+2*12)&0xFFFFFFFF
        assert reply_pointer==request
        assert list(a.uc.mem_read(reply_pointer+4,2))==[8,0] and h(reply_pointer+8)==13
        assert h(reply_pointer+6)==source and w(reply_pointer+12)==payload
        assert signals==[[3,0x80000000],[2,0x80000000]]
        del a.stubs[0x312EC]
        a.stubs.update({0x2FF000:receive,0x2FF004:dispatch})
        feed[:]=[(0x80000000,reply_pointer)]
        assert call(0x312EC,*wait_args)&0xFFFFFFFF==reply_pointer and not feed
        call(0x205B38,manager,reply_pointer,payload)
        assert freed==[payload] and w(w(osobj))==reply_pointer
        handoffs.append(dict(records=length,token=source,copies_independent=True,reply_reuses_request=True,payload_freed=True,message_recycled=True))

    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
                register_cases=register_cases,matching_cases=match_cases,wait_cases=wait_cases,
                cached_current_reply=True,normal_cases=normal_cases,integrated=integrated,handoffs=handoffs,
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                boundaries=['Original 32-slot table, reply cache, synchronous wait, ordinary pump and parameter sender execute',
                            'Integrated sender uses original RDAPI pool and queue insertion; kernel wake and receiver virtual call are boundaries',
                            'Eight split-task handoffs execute original sender, MMI copy/reply dispatch, resumed wait and recycle; task scheduling and list/allocator services are modeled',
                            'Cached-current test injects a reply pointer during an unrelated callback to model nested processing',
                            'A full table retains 32 entries while registration counter advances; actual 33-deep nesting reachability not established',
                            'No OS scheduling, full receiver task loop, page rendering, devices or audio execution'])
    (OUT/'message-replies-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,matching_cases=match_cases,wait_cases=len(wait_cases),normal_cases=len(normal_cases),integrated=len(integrated),handoffs=len(handoffs)),indent=2))

if __name__=='__main__':main()
