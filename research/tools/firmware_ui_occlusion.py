#!/usr/bin/env python3
"""Original graphics context, fixed region pool, occlusion splitting and pixels."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('ui-context-pool',0xD8744,0xD8A08),('ui-context-subtract',0xD8E84,0xD927C),
                       ('ui-context-activate',0xD927C,0xD963C),('ui-context-borrow',0xDBC5C,0xDBDD0)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    a=Arm(f)
    def call(p,*args,**kw):return a.call(p,*args,**kw)&0xFFFFFFFF
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def putrect(p,r):a.uc.mem_write(p,struct.pack('<4h',*r))
    def getrect(p):return tuple(struct.unpack('<4h',a.uc.mem_read(p,8)))
    ctx,pair,cutter,tree,array,nodes,widgets,borrowed,frame=0x11000000,0x11000100,0x11000200,0x11000300,0x11000400,0x11000500,0x11001000,0x11002000,0x11004020
    arena=0x11010000;allocations=[];frees=[]
    def allocate(m):
        nonlocal arena
        size=m.get('R0');pointer=arena;arena+=(size+15)&~15
        assert arena<0x11100000;a.uc.mem_write(pointer,bytes(size));allocations.append(dict(size=size,pointer=pointer));return pointer
    a.stubs={0x14E730:allocate,0x2E2F9C:allocate,0x14E760:lambda m:frees.append(m.get('R0')) or 0,
             0x2DC184:lambda m:0,0x2DC1BC:lambda m:0}
    call(0xD88DC,ctx)
    pool=w(ctx+4);queue=w(ctx+8);freequeue=w(pool)
    assert w(queue+0x18)==w(freequeue+0x18)==8 and w(queue+8)==0 and w(freequeue+8)==8
    assert [x['size'] for x in allocations]==[4,28,96]+[8]*8+[28,96]
    snapshot=bytes(a.uc.mem_read(0x11010000,arena-0x11010000));ctx_initial=bytes(a.uc.mem_read(ctx,20))
    def reset():a.uc.mem_write(0x11010000,snapshot);a.uc.mem_write(ctx,ctx_initial)
    def list_values(pointer):
        count=w(pointer+8);node=w(pointer+4);result=[]
        for _ in range(count):
            assert node;result.append(w(node+8));nxt=w(node+4);assert w(nxt)==node;node=nxt
        assert not count or node==w(pointer+4)
        return result
    original_slots=set(list_values(freequeue))
    def pixels(r):return {(x,y) for y in range(r[1],r[3]) for x in range(r[0],r[2])}
    def check_regions(expected):
        rects=[getrect(pointer) for pointer in list_values(queue)];seen=set()
        for r in rects:
            assert r[0]<r[2] and r[1]<r[3],r
            part=pixels(r);assert not part&seen,rects;seen|=part
        assert seen==expected,(rects,len(seen),len(expected))
        assert w(queue+8)+w(freequeue+8)==8
        assert set(list_values(queue))|set(list_values(freequeue))==original_slots
        return rects
    def release_context():
        call(0xD9594,ctx)
        assert not list_values(queue) and set(list_values(freequeue))==original_slots
        assert w(ctx+12)==w(ctx+16)==0
    # Independent area-set oracle checks all positional arrangements.
    intervals=list(itertools.combinations([-12,-4,0,3,7,10,16],2))
    splits=[]
    for source,xr,yr in itertools.product([(0,0,10,10),(-8,-4,12,9),(2,3,7,8)],intervals,intervals):
        reset();occluder=(xr[0],yr[0],xr[1],yr[1]);pointer=call(0xD88A8,pool)
        putrect(pointer,source);putrect(cutter,occluder);call(0x29084,queue,pointer);a.write(pair,pointer,cutter)
        retained=call(0xD8E84,ctx,pair)
        expected=pixels(source)-pixels(occluder)
        assert retained==int(bool(expected))
        if not retained:assert call(0x29228,queue,pointer)==pointer;call(0xD88D4,pool,pointer)
        rects=check_regions(expected);release_context()
        splits.append(dict(source=source,occluder=occluder,rectangles=rects))
    # Pool exhaustion returns zero; returning entries restores all eight slots.
    reset();taken=[call(0xD88A8,pool) for _ in range(9)]
    assert set(taken[:8])==original_slots and taken[8]==0
    for pointer in taken[:8]:call(0xD88D4,pool,pointer)
    assert set(list_values(freequeue))==original_slots

    # Root R with same-level A,B,C and a child under B. Activation of A subtracts
    # later siblings B,C; the descendant has no effect on this sibling loop.
    obj=[widgets+0x100*i for i in range(5)]
    links=[(None,1,None),(0,None,2),(0,4,3),(0,None,None),(2,None,None)]
    a.write(tree,0xC0468D20,array,0,0,nodes,0,5);a.write(array,0xC0468CC4,nodes,28,384)
    for i,(parent,child,sibling) in enumerate(links):
        a.write(nodes+28*i,0xC0468CF4,0 if parent is None else nodes+28*parent,
                0 if child is None else nodes+28*child,0 if sibling is None else nodes+28*sibling,0,0,obj[i])
        a.write(obj[i],0xC0469BEC);ph(obj[i]+0xA,i)
    a.write(0xC10042D0,tree);a.write(0xC10042CC,obj[0]);a.write(0xC10042B0,1)
    boxA=(0,0,64,24);boxB=(16,4,30,20);boxC=(25,12,50,22)
    for pointer,box in zip(obj,[(0,0,64,24),boxA,boxB,boxC,(0,0,64,24)]):
        putrect(pointer+0xC,(0,0,box[2]-box[0],box[3]-box[1]));putrect(pointer+0x14,box)
        ph(pointer+0x28,box[0]);ph(pointer+0x2A,box[1])
    clip=(8,3,56,21);putrect(0xC10042C0,clip)
    # Borrow list executes real generic list services too.
    call(0x29668,borrowed);call(0x29084,borrowed,ctx);a.write(0xC100429C,borrowed)
    raw=bytes([255]*1920);guard=bytes([0xA7]*32);a.write(0xC104751C,frame)
    activation=[]
    for skip_occlusion,clipping,flagB,flagC,field8,branch in itertools.product([0,1],[0,1],[0,0x10,0x40],[0,0x10,0x40],[0,0x10],[0,1,2]):
        reset();a.write(obj[1]+0x2C,0);a.write(0xC10042A8,skip_occlusion);a.write(0xC10042B8,clipping)
        ph(obj[2]+6,flagB);ph(obj[3]+6,flagC);ph(obj[2]+8,field8)
        # 0 resolves top level from tree; 1 uses A; 2 explicitly starts at B.
        a.write(ctx+12,0 if branch==0 else obj[branch])
        expected=pixels(boxA)&(pixels(clip) if clipping else pixels(boxA))
        if not skip_occlusion:
            if branch!=2 and not flagB&0x50:expected-=pixels(boxB)
            if not flagC&0x50:expected-=pixels(boxC)
        assert call(0xDBD20,obj[1])==queue
        assert w(obj[1]+0x2C)==ctx and w(ctx+16)==1 and w(borrowed+8)==0
        rects=check_regions(expected)
        # Use the generated region list in original clear and return the context.
        a.uc.mem_write(frame-32,guard+raw+guard);putrect(pair,boxA)
        call(0xE4C70,obj[1],pair)
        expected_frame=bytearray(raw)
        for x,y in expected:expected_frame[y*30+x//8]&=255^(128>>(x%8))
        actual=bytes(a.uc.mem_read(frame,1920));assert actual==bytes(expected_frame)
        assert bytes(a.uc.mem_read(frame-32,32))==guard and bytes(a.uc.mem_read(frame+1920,32))==guard
        call(0xDBD74,obj[1])
        assert w(obj[1]+0x2C)==0 and list_values(borrowed)==[ctx]
        assert not list_values(queue) and set(list_values(freequeue))==original_slots
        activation.append(dict(skip_occlusion=skip_occlusion,clipping=clipping,flags=[flagB,flagC],field8=field8,branch=branch,
                               rectangles=rects,visible_pixels=len(expected),frame_sha256=hashlib.sha256(actual).hexdigest()))
    # Root context bypasses subtraction; empty clipping yields an active empty list.
    extra=[]
    for root,clipbox in itertools.product([0,1],[(0,0,64,24),(100,30,120,40)]):
        reset();pointer=obj[0] if root else obj[1];a.write(pointer+0x2C,0)
        a.write(0xC10042A8,0);a.write(0xC10042B8,1);putrect(0xC10042C0,clipbox)
        ph(obj[2]+6,0);ph(obj[3]+6,0)
        call(0xDBD20,pointer)
        expected=pixels(boxA)&pixels(clipbox)
        if not root:expected-=pixels(boxB)|pixels(boxC)
        check_regions(expected);assert w(ctx+16)==1
        call(0xDBD74,pointer);extra.append(dict(root=root,clip=clipbox,visible_pixels=len(expected)))

    # Deliberately fragmented synthetic layout reaches the eight-slot boundary.
    # Capture the emulator's actual null write; no null page or device is mapped.
    reset();pointer=call(0xD88A8,pool);putrect(pointer,(0,0,64,24));call(0x29084,queue,pointer)
    holes=[(4,4,10,10),(20,4,26,10),(36,4,42,10),(4,15,10,21),(20,15,26,21),(36,15,42,21)]
    fragmentation=[];fault=None;expected=pixels((0,0,64,24))
    for hole in holes:
        putrect(cutter,hole)
        try:
            # Original activate loop calls subtraction repeatedly on the retained
            # fragment until it no longer intersects, then advances its iterator.
            for pointer in list_values(queue).copy():
                a.write(pair,pointer,cutter)
                while True:
                    before=getrect(pointer);retained=call(0xD8E84,ctx,pair)
                    if not retained:call(0x29228,queue,pointer);call(0xD88D4,pool,pointer);break
                    if not(pixels(getrect(pointer))&pixels(hole)):break
                    assert getrect(pointer)!=before
            expected-=pixels(hole);rects=check_regions(expected)
            fragmentation.append(dict(hole=hole,regions=rects,free_slots=w(freequeue+8)))
        except RuntimeError:
            if not a.memory_fault:raise
            fault=dict(a.memory_fault);fault['hole']=hole;fault['free_slots']=w(freequeue+8);fault['active_regions']=w(queue+8)
            assert int(fault['address'],16)<8 and fault['free_slots']==0,fault
            break
    assert fault is not None
    # Reproduce the same boundary through the original sibling loop, without a
    # Python subtraction loop or modeled container operations.
    reset();a.write(0xC10042A8,0);a.write(0xC10042B8,0)
    for i in range(6):
        pointer=widgets+0x100*i;node=nodes+28*i
        a.write(pointer,0xC0469BEC);ph(pointer+0xA,i);ph(pointer+6,0);ph(pointer+8,0)
        a.write(node,0xC0468CF4,0 if i==0 else nodes,nodes+28 if i==0 else 0,
                nodes+28*(i+1) if 1<=i<5 else 0,0,0,pointer)
        box=(0,0,64,24) if i<2 else holes[i-2]
        putrect(pointer+0xC,(0,0,box[2]-box[0],box[3]-box[1]));putrect(pointer+0x14,box)
        ph(pointer+0x28,box[0]);ph(pointer+0x2A,box[1])
    activation_fault=None
    try:call(0xD927C,ctx,obj[1])
    except RuntimeError:
        if not a.memory_fault:raise
        activation_fault=dict(a.memory_fault)
    assert activation_fault is not None and activation_fault['address']=='0x6' and activation_fault['pc']=='0xc00d91d0'
    assert w(freequeue+8)==0 and w(queue+8)==8
    assert len(frees)==len(activation)+len(extra)
    assert len(allocations)==14+len(frees) and all(row['size']==12 for row in allocations[13:])
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,allocations=allocations,heap_frees=frees,
                subtraction=splits,pool_taken=taken,activation=activation,extra=extra,fragmentation=fragmentation,capacity_fault=fault,
                capacity_activation_fault=activation_fault,
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                boundaries=['Original context and eight-region pool constructors, fixed list allocation, iterators, split, borrow and recycle execute',
                            'Only heap allocation/free and exception registration are modeled in successful checks; no graphics list service is stubbed',
                            'Synthetic tree and widget geometry drive original sibling occlusion and clipped framebuffer stores',
                            'Capacity fault reproduces through original activation and sibling traversal for four synthetic interior occluders; factory-page reachability is unproven',
                            'No hardware, real page construction, font rendering or physical LCD transfer executes'])
    (OUT/'ui-occlusion-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,subtraction_cases=len(splits),activation_to_pixels=len(activation),extra=len(extra),capacity_fault=fault),indent=2))

if __name__=='__main__':main()
