#!/usr/bin/env python3
"""Original MMI deferred parameter list and operation-9/24 callbacks."""
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
    for name,lo,hi in [('mmi-parameter-batch',0x146F54,0x14731C),
                       ('mmi-parameter-callback',0x146C98,0x146E94),
                       ('mmi-parameter-ready',0x145F84,0x145FF0)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f)
    def call(p,*args,**kw):return a.call(p,*args,**kw)
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def zero(m):return 0
    manager,owner,queue,auxqueue,widget,vtable,records=0x11000000,0x11000100,0x11000200,0x11000300,0x11000400,0x11000500,0x11001000
    a.write(manager,owner,queue,auxqueue,0x11000600,0)
    a.write(widget,vtable);a.write(vtable+0x88,0xC02FF000)
    a.write(vtable+0xB4,0xC02FF004)
    temp_vtable=0x11000700;a.write(temp_vtable+4,0xC02FF008)
    lists={};maps={};arena=0x11010000;deleted=[];dispatches=[]
    def allocate(m):
        nonlocal arena
        p=arena;arena+=0x40;a.uc.mem_write(p,bytes(0x40));return p
    def list_ctor(m):a.write(m.get('R0'),temp_vtable);lists[m.get('R0')]=[];return 0
    def map_ctor(m):maps[m.get('R0')]={};return 0
    def pop(m):
        values=lists.setdefault(m.get('R0'),[]);return values.pop(0) if values else 0
    def append(m):lists.setdefault(m.get('R0'),[]).append(m.get('R1'));return 0
    def lookup(m):
        value=maps[m.get('R0')].get(m.get('R1'))
        if value:a.write(m.get('R2'),value)
        return int(value is not None)
    def insert(m):maps[m.get('R0')][m.get('R1')]=m.get('R2');return 0
    def delete(m):deleted.append(m.get('R0'));return 0
    def dispatch(m):
        dispatches.append([m.get('R1'),m.get('R2'),m.get('R3')]+[w(m.get('SP')+4*i) for i in range(6)])
        return 0
    base={0x2DC184:zero,0x2DC1BC:zero,0x14E730:allocate,0x14E760:zero,
          0x29668:list_ctor,0x28BE0:map_ctor,0x2926C:pop,0x29084:append,
          0x28E00:lookup,0x28CE4:insert,0x28CB4:zero,0x2FF008:zero,
          0x205274:delete,0x146D30:dispatch,0x2959C:lambda m:len(lists.get(m.get('R0'),[]))}
    batch_cases=[]
    for busy,present,active,disabled,ready,kind,source_flag in itertools.product(range(2),range(2),range(2),range(2),range(2),[12,14],[0,1,0xFFFFFFFF]):
        arena=0x11010000;lists.clear();maps.clear();deleted.clear();dispatches.clear()
        ph(owner+0x7C,busy);a.write(widget+0x68,disabled)
        ps=[records+24*i for i in range(4)]
        for i,pointer in enumerate(ps):
            a.uc.mem_write(pointer,struct.pack('<IHHIIII',0xC04714B4,100,2 if i<3 else 1,kind,10*(i+1),i,source_flag))
        lists[queue]=ps.copy();lists[auxqueue]=[]
        a.stubs=dict(base);a.stubs.update({0xDE090:lambda m:widget if present else 0,0x2FF000:lambda m:active,0x145F84:lambda m:ready})
        call(0x1472D0,manager)
        deferred=bool(busy or present and active and not disabled and not ready)
        process=not busy and not (present and active and (disabled or not ready)) and (kind!=12 or present)
        retained=[ps[0],ps[3]] if deferred else []
        assert lists[queue]==retained,(busy,present,active,disabled,ready,kind,lists[queue])
        assert deleted==([ps[1],ps[2]] if deferred else ps)
        expected=[]
        if process:
            for i in range(4):expected.append([100,2 if i<3 else 1,widget if present else 0,kind,0,0,7 if i<3 else 11,10*(i+1),i])
        assert dispatches==expected,(busy,present,active,disabled,ready,kind,dispatches,expected)
        assert w(manager+0x10)==0
        batch_cases.append(dict(busy=busy,present=present,active=active,disabled=disabled,ready=ready,kind=kind,source_flag=source_flag,deferred=deferred,callback_count=len(dispatches),retained_new_values=[w(p+12) for p in retained]))

    # Multiple blocked passes preserve the earliest record for each key.
    lists.clear();maps.clear();deleted.clear();dispatches.clear();arena=0x11010000
    ph(owner+0x7C,1);a.write(widget+0x68,0)
    a.stubs=dict(base);a.stubs.update({0xDE090:lambda m:widget,0x2FF000:lambda m:1,0x145F84:lambda m:1})
    lists[queue]=[];lists[auxqueue]=[];deferred_trace=[]
    for i,value in enumerate([11,22,33,44]):
        pointer=records+24*i
        a.uc.mem_write(pointer,struct.pack('<IHHIIII',0xC04714B4,100,2,14,value,value-1,1))
        lists[queue].append(pointer);call(0x1472D0,manager)
        assert lists[queue]==[records] and dispatches==[]
        deferred_trace.append(dict(input=value,retained=w(records+12)))
    ph(owner+0x7C,0);call(0x1472D0,manager)
    assert lists[queue]==[] and dispatches==[[100,2,widget,14,0,0,7,11,10]]

    # Reentrance guard skips all batch work and retains its original state.
    a.write(manager+0x10,1);before=len(dispatches)
    call(0x1472D0,manager)
    assert w(manager+0x10)==1 and len(dispatches)==before
    a.write(manager+0x10,0)

    # Original readiness helper: active owner state refuses; otherwise invokes
    # associated object's virtual +A0 under global C10042B0 and restores it only
    # when its original value was zero.
    associated,assoc_vtable=0x11000800,0x11000900
    a.write(associated,assoc_vtable);a.write(assoc_vtable+0xA0,0xC02FF00C)
    calls=[];ready_cases=[]
    def aux(m):calls.append([m.get('R0'),w(0xC10042B0)]);return 0
    for owner_state,disabled,has_associated,old_global in itertools.product(range(2),range(2),range(2),[0,1,7]):
        calls.clear();a.write(widget+0x68,disabled,associated if has_associated else 0);a.write(0xC10042B0,old_global)
        a.stubs={0x141014:lambda m:owner_state,0x2FF00C:aux}
        assert call(0x145F84,manager,widget)==int(not owner_state)
        assert calls==([[associated,1]] if not owner_state and not disabled and has_associated else [])
        assert w(0xC10042B0)==(old_global if owner_state or old_global==0 else 1)
        ready_cases.append(dict(owner_state=owner_state,disabled=disabled,associated=has_associated,old_global=old_global,result=int(not owner_state),new_global=w(0xC10042B0)))

    # Original operation-9 context construction and operation-24 follow-up.
    notices=[];widget_calls=[];secondary=[]
    def parameter_callback(m):
        op=m.get('R0');p=m.get('R1')
        if op==9:notices.append(list(struct.unpack('<HHIIIIIIII',a.uc.mem_read(p,36))))
        else:assert op==24
        return followup if op==24 else 0
    def widget_changed(m):
        widget_calls.append([m.get('R0'),m.get('R1'),m.get('R2'),m.get('R3')]+[w(m.get('SP')+i*4) for i in range(3)])
        return 0
    def secondary_notice(m):
        secondary.append([m.get('R0'),m.get('R1'),m.get('R2'),m.get('R3'),w(m.get('SP')),w(m.get('SP')+4)]);return 0
    callback_cases=[]
    a.stubs={0x1DEA58:parameter_callback,0x2FF004:widget_changed,0x13A194:secondary_notice}
    for present,valid,changed,followup,kind in itertools.product(range(2),range(2),range(2),[0,1,32767,32768,65535],[12,14]):
        notices.clear();widget_calls.clear();secondary.clear();ph(widget+0xA,0 if valid else 65535)
        new=7;old=3 if changed else 7;pwidget=widget if present else 0
        call(0x146D30,manager,100,2,pwidget,stack=(kind,0,0,7,new,old))
        assert notices==[[100,2,owner,pwidget,kind,0,0,7,new,old]],notices
        assert widget_calls==([[widget,new,old,0,7,kind,0]] if present and valid and changed else [])
        assert secondary==([[0x11000600,followup,100,2,kind,0]] if 0<followup<32768 else [])
        callback_cases.append(dict(present=present,valid=valid,changed=changed,followup=followup,kind=kind,widget_called=bool(widget_calls),secondary_called=bool(secondary)))

    # Original MMI receive routing and record copy followed by original batch
    # drain and callback context. Container services and final recipients remain
    # controlled; no page object constructor is substituted into this fixture.
    source_list,packet,payload=0x11000A00,0x11000B00,0x11000C00
    iterators={};replies=[];integrated=[]
    def begin(m):iterators[m.get('R0')]=iter(list(lists[m.get('R1')]));return 0
    def next_item(m):return next(iterators[m.get('R0')],0)
    def reply(m):replies.append([m.get('R1'),w(m.get('R2'))]);return 0
    a.write(owner+4,manager);a.write(payload,source_list);ph(owner+0x7C,0)
    a.write(widget+0x68,0);ph(widget+0xA,0);followup=1
    a.stubs=dict(base);del a.stubs[0x146D30]
    a.stubs.update({0xDE090:lambda m:widget,0x2FF000:lambda m:1,0x145F84:lambda m:1,
                   0x29F14:begin,0x29FE0:next_item,0x29F94:zero,0x2CD684:reply,
                   0x1DEA58:parameter_callback,0x2FF004:widget_changed,0x13A194:secondary_notice})
    for length in [0,3,6]:
        lists.clear();maps.clear();notices.clear();widget_calls.clear();secondary.clear();replies.clear();deleted.clear()
        arena=0x11010000;lists[queue]=[];lists[auxqueue]=[]
        source_records=[records+24*i for i in range(length)];lists[source_list]=source_records
        raw=[]
        for i,pointer in enumerate(source_records):
            data=struct.pack('<IHHIIII',0xC04714B4,100,i%3,[12,14,16][i%3],i+1,0,1)
            a.uc.mem_write(pointer,data);raw.append(data)
        a.uc.mem_write(packet,struct.pack('<IBBHHHI',0,9,0,65535,12,0,payload))
        call(0x143994,owner,packet)
        copies=lists[queue].copy()
        assert [bytes(a.uc.mem_read(p,24)) for p in copies]==raw
        assert replies==[[2,packet]] and list(a.uc.mem_read(packet+4,2))==[8,0]
        assert struct.unpack('<HH',a.uc.mem_read(packet+6,4))==(65535,13)
        call(0x1472D0,manager)
        expected=[[100,i%3,owner,widget,[12,14,16][i%3],0,0,[26,11,7][i%3],i+1,0] for i in range(length)]
        assert notices==expected and len(widget_calls)==len(secondary)==length
        assert lists[queue]==[] and deleted==copies
        integrated.append(dict(records=length,operation9=notices.copy(),widget_calls=len(widget_calls),secondary_calls=len(secondary),clones_destroyed=len(deleted)))

    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
                batch_cases=batch_cases,deferred_trace=deferred_trace,reentrance_guard=True,ready_cases=ready_cases,callback_cases=callback_cases,integrated=integrated,
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                boundaries=['Original MMI batch selection, duplicate retention, reentrance guard, readiness helper and callback context execute',
                            'List/map/allocator services are modeled; parameter-object lookup and virtual readiness are controlled',
                            'Batch matrix captures 146D30; separate callback matrix executes it and captures widget, descriptor and secondary recipients',
                            'Three receive-to-drain cases execute original MMI dispatch, copying, batch selection and operation-9/24 context; final callbacks captured',
                            'Raw state fields are not assigned full panel-mode meanings; no actual page tree, rendering, devices or audio'])
    (OUT/'mmi-parameters-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,batch_cases=len(batch_cases),ready_cases=len(ready_cases),callback_cases=len(callback_cases),deferred_passes=len(deferred_trace),integrated=len(integrated)),indent=2))

if __name__=='__main__':main()
