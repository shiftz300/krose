#!/usr/bin/env python3
"""Execute bounded original ARM kernel helpers in private synthetic memory.

Never calls reset, kernel_start, dispatch, IRQ entry, task bodies, drivers,
flash paths or a device API. Callback bodies are intercepted. Requires JIT.
"""
import hashlib
import json
import random
import struct
from pathlib import Path

from program_firmware import Arm, Firmware, FW_SHA, BASE
from layout import PRODUCT_ROOT as ROOT
from firmware_architecture_index import OUT


def main():
    import unicorn
    f = Firmware()
    startup = json.loads((OUT/'startup.json').read_text())
    a = Arm(f)
    def u32(p):
        return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def byte(p):
        return bytes(a.uc.mem_read(p,1))[0]
    results = {}
    # cpu_initialize decodes existing low-vector LDR literals; no exception runs.
    a.uc.mem_map(0,0x1000)
    a.uc.mem_write(0,f.data[:0x3C])
    a.call(0x2FBB0C)
    for i,v in enumerate(startup['vectors']):
        p = v['literal_offset']
        assert u32(0xC1B7A2E0+i*4) == p
        assert u32(0xC1B7A2BC+i*4) == BASE+v['initial_target_offset']
    a.call(0x2FBA88)
    assert u32(0x34) == BASE+0x2FCB30
    assert all(u32(0xC1B7A128+i*4)==0 for i in range(101))
    results['vector_decode_and_irq_install'] = dict(vectors=8, irq_literal_address=0x34,
                                                   irq_handler=BASE+0x2FCB30, cleared_handlers=101)
    # Actual initialization, make_active and ready insertion; task PC not entered.
    a.call(0x2FBB98)
    groups = {}
    for task in startup['tasks']:
        t = task['tcb_address']
        sp = task['stack_end_exclusive']-8
        assert u32(t+8)==BASE+task['config_offset']
        assert byte(t+12)==1 and byte(t+13)==task['internal_priority']
        assert u32(t+24)==sp and u32(t+28)==BASE+0x2FCDF8
        assert u32(sp)==task['exinf'] and u32(sp+4)==task['virtual_entry']
        groups.setdefault(task['internal_priority'],[]).append(t)
    for pri,expected in groups.items():
        head=0xC1B7A31C+pri*8
        p=u32(head); seen=[]
        while p!=head:
            assert len(seen)<11
            seen.append(p); p=u32(p)
        assert seen==expected
        assert u32(head+4)==expected[-1]
    assert u32(0xC1B7A3A0)==0 and u32(0xC1B7A3A8)==startup['tasks'][0]['tcb_address']
    assert u32(0xC1B7A39C)==15
    results['static_task_initialize'] = dict(tasks=11, tcb_bytes=32, stack_bytes=119808,
        initial_ready_primap=15, initial_schedtsk_id=1, fifo_groups={str(k):len(v) for k,v in groups.items()},
        executed_task_bodies=0)
    # Every nonempty 16-bit ready bitmap; expected priority from Python bit ops.
    for pri in range(16):
        a.write(0xC1B7A31C+pri*8,0x11050000+pri*32)
    for mask in range(1,65536):
        a.write(0xC1B7A39C,mask)
        actual=a.call(0x2FD724,count=100)
        expected=(mask & -mask).bit_length()-1
        assert actual==0x11050000+expected*32,(mask,actual,expected)
    results['ready_bitmap_search'] = dict(cases=65535, priorities=16, rule='lowest set bit wins; smaller internal number is higher priority')
    # Synchronization tables are initialized without waiting or dispatching.
    a.call(0x2FC3CC)
    for i in range(startup['semaphore_count']):
        p=0xC1B79E7C+i*16
        assert u32(p)==p and u32(p+4)==p
        assert u32(p+8)==BASE+0x459328+i*12
        assert u32(p+12)==f.u32(0x459328+i*12+4)
    a.call(0x2FC5C8)
    for i in range(startup['eventflag_count']):
        p=0xC1B7A054+i*16
        assert u32(p)==p and u32(p+4)==p
        assert u32(p+8)==BASE+0x4592BC+i*8
        assert u32(p+12)==0
    results['IPC_table_initialize'] = dict(semaphores=startup['semaphore_count'],eventflags=startup['eventflag_count'])
    # Heap insertion/deletion and tick callback dispatch with 32-bit wraparound.
    heap_cases=[]
    for anchor in [0,0xFFFFFFF0]:
        a.call(0x2FBD20)
        a.write(0xC1B7A3AC,anchor)
        a.write(0xC1B7A3B0,(anchor+1)&0xFFFFFFFF)
        a.write(0xC1B7A2DC,1)
        relative=[7,1,7,31,2,16,0,5,31]
        live={}
        def check_heap():
            n=u32(0xC1B7A3B8)
            assert n==len(live)
            nodes=[]
            for j in range(1,n+1):
                p=0xC1B79E9C+(j-1)*8
                time,event=u32(p),u32(p+4)
                assert event in live and time==live[event]
                assert u32(event)==j
                nodes.append((time-anchor)&0xFFFFFFFF)
            assert all(nodes[(j-1)//2]<=nodes[j] for j in range(1,n))
        for i,delta in enumerate(relative):
            event=0x11070000+i*16
            a.write(event,0,BASE+0x2C8808,i)
            deadline=(anchor+delta)&0xFFFFFFFF
            a.call(0x2FD58C,event,deadline)
            live[event]=deadline;check_heap()
        deleted=[2,5,7]
        for i in deleted:
            event=0x11070000+i*16
            a.call(0x2FD5D8,event)
            del live[event];check_heap()
        seen=[]
        a.stubs={0x2C8808:lambda m: seen.append((m.get('R0'),u32(0xC1B7A3B0))) or 0}
        for _ in range(32):
            a.set('CPSR',0x13)
            a.call(0x2FBD5C,count=2000)
        assert u32(0xC1B7A3AC)==(anchor+32)&0xFFFFFFFF
        assert u32(0xC1B7A3B8)==0
        assert sorted(i for i,tick in seen)==[i for i in range(9) if i not in deleted]
        for i,tick in seen:
            expected=(anchor+max(1,relative[i]))&0xFFFFFFFF
            assert tick==expected,(i,tick,expected)
        assert [relative[i] for i,t in seen]==sorted(relative[i] for i,t in seen)
        heap_cases.append(dict(anchor=anchor,insertions=9,deletions=3,ticks=32,captured_callbacks=seen))
        a.stubs={}
    results['time_event_heap'] = dict(cases=heap_cases,callback_bodies_executed=False)
    # RDAPI's intrusive singly-linked message queue; no scheduler dependency.
    queue,head,tail=0x11080000,0x11080020,0x11080040
    a.write(queue,head,tail)
    a.write(head,tail);a.write(tail,head)
    nodes=[0x11080100+i*16 for i in range(7)]
    for p in nodes:
        a.write(p,0)
        a.call(0x2CD7AC,queue,p)
    popped=[a.call(0x2CD7F4,queue) for _ in range(8)]
    assert popped==nodes+[0],popped
    results['RDAPI_message_queue'] = dict(enqueued=7,popped_fifo=7,empty_returns=0)
    # Derived constructors execute their original vptr stores; complex base
    # constructors are deliberately stubbed. This is not full object startup.
    object_cases=[]
    for obj,base_ctor in zip(startup['resolved_object_dispatch'],
                             [0x2B55A8,0x2B55A8,0x13F72C,0x13F72C,0x2C4A0C,0x2C4A0C]):
        target=0x11090000
        a.uc.mem_write(target,bytes(0x200))
        bases=[]
        a.stubs={base_ctor:lambda m:bases.append(m.get('R0')) or 0}
        # USB driver constructor has additional base initialization helpers;
        # test only through its vptr store, excluding hardware-dependent tail.
        if obj['class_name']=='CUsbDrv':
            a.set('R0',target);a.set('SP',a.stack);a.set('LR',0x10000000)
            a.uc.emu_start(BASE+obj['constructor_offset'],BASE+0x2CA924,count=1000)
            assert a.get('PC')==BASE+0x2CA924
        else:
            a.call(obj['constructor_offset'],target)
        assert bases==[target]
        vt=u32(target)
        assert vt==BASE+obj['vtable_address_point_offset']
        assert u32(vt+8)==BASE+obj['run_entry_offset']
        object_cases.append(dict(class_name=obj['class_name'],vptr=vt,run_entry=u32(vt+8)))
    a.stubs={}
    results['object_run_slot_resolution']=dict(cases=object_cases,base_constructor_bodies_executed=False)
    # Exhaust every interior LCD pixel with a deterministic packed framebuffer.
    framebuffer=0x110A0000
    raw=bytes((i*73+19)&255 for i in range(240*64//8))
    a.uc.mem_write(framebuffer,raw);a.write(0xC104751C,framebuffer)
    for y in range(64):
        for x in range(240):
            bit=x+y*240
            expected=0 if raw[bit//8] & (0x80>>(bit%8)) else 1
            assert a.call(0x2C6CD4,0,x,y,count=100)==expected
    results['lcd_packed_bitmap']=dict(pixels=15360,width=240,height=64,row_bytes=30,
                                     bit_order='MSB first',getter_inverts_bit=True)
    result=dict(firmware_sha256=FW_SHA,tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        startup_input_sha256=hashlib.sha256((OUT/'startup.json').read_bytes()).hexdigest(),
        unicorn_version=unicorn.__version__,passed=True,results=results,
        limits=['Synthetic RAM only; low vectors are private emulator pages',
               'No reset/kernel_start/context-dispatch/IRQ/task/driver body executed',
               'No actual MCU timing, interrupt nesting, device events or audio measured',
               'Exhaustive ready bitmap test does not prove all scheduler interleavings'])
    (OUT/'arm-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,checks=list(results),bitmap_cases=65535,device_access=False),indent=2))


if __name__=='__main__':
    main()
