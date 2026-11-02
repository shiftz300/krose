#!/usr/bin/env python3
"""Execute UI clipping, refresh state and tree-to-drawing dispatch."""
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
    for name,lo,hi in [('ui-refresh-visibility',0xDCE7C,0xDCFF4),('ui-refresh-draw',0xDCFF4,0xDD284),
                       ('ui-refresh-tree',0xDE2A8,0xDE460),('ui-refresh-top-level',0xDC6F4,0xDC780)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    a=Arm(f)
    def call(p,*args,**kw):return a.call(p,*args,**kw)&0xFFFFFFFF
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def rect(p,r):a.uc.mem_write(p,struct.pack('<4h',*r))
    widget,vt,outptr=0x11000000,0x11000100,0x11000200
    a.write(widget,vt);ph(widget+0xA,0)
    a.write(vt+0x10,0xC02FF000);a.write(vt+0x8C,0xC02FF004)
    a.stubs={0x2FF000:lambda m:1,0x2FF004:lambda m:0}
    rectangles=[(0,0,20,10),(5,2,10,8),(-5,2,10,8),(15,2,25,8),(2,-5,10,8),
                (2,5,10,15),(20,0,30,10),(21,0,30,10),(0,0,0,10),(0,0,20,0),
                (10,0,0,10),(0,10,20,0),(-32768,-32768,32767,32767)]
    clip=(0,0,20,10);rect(0xC10042C0,clip)
    visibility=[]
    for bounds,valid,flag6,flag8,clipping,special,kind,opaque in itertools.product(
            rectangles,[0,1],[0,0x10,0x40],[0,0x10],[0,1],[0,1],[0,1],[0,1]):
        ph(widget+0xA,0 if valid else 65535);ph(widget+6,flag6);ph(widget+8,flag8);rect(widget+0x14,bounds)
        a.write(0xC10042B8,clipping);a.write(0xC10042A0,special)
        a.stubs[0x2FF000]=lambda m:kind;a.stubs[0x2FF004]=lambda m:opaque
        a.write(outptr,0xDEADBEEF)
        area=bounds[2]>bounds[0] and bounds[3]>bounds[1]
        intersects=max(bounds[0],0)<min(bounds[2],20) and max(bounds[1],0)<min(bounds[3],10)
        visible=bool(valid and not(flag6&0x10 or flag8&0x10) and area and (not clipping or intersects))
        inside=bounds[0]>=0 and bounds[1]>=0 and bounds[2]<=20 and bounds[3]<=10
        partial=bool(visible and clipping and special and kind and flag6&0x40 and not opaque and not inside)
        got=call(0xDCE7C,widget,outptr)
        assert (got,w(outptr))==(int(visible),int(partial)),(bounds,valid,flag6,flag8,clipping,special,kind,opaque,got,w(outptr))
        visibility.append(dict(rect=bounds,valid=valid,flags=[flag6,flag8],clip=clipping,special=special,kind=kind,opaque=opaque,visible=visible,partial=partial))
    # The refresh marker preserves an existing pending state when drawing is hidden.
    draws=[];released=[]
    def draw(m):draws.append([m.get('R0'),m.get('R1'),m.get('R2')]);return 0
    a.stubs.update({0xDCFF4:draw,0xDBD74:lambda m:released.append(m.get('R0')) or 0})
    a.write(0xC10042B8,0);ph(widget+0xA,0);rect(widget+0x14,clip)
    states=[]
    for enabled,hidden,previous,mode,background in itertools.product([0,1],[0,1],[0,1,2,7],[0,1,2,3],[0,1]):
        ph(widget+6,0x10 if hidden else 0);ph(widget+8,0);a.write(0xC10042B0,enabled)
        a.write(widget+0x40,previous);a.write(widget+0x38,0xFFFFFFFF);draws.clear();released.clear()
        got=call(0xDD1DC,widget,mode,background)
        expected_state=1 if not enabled else (1 if hidden and previous==1 else 2)
        assert got==int(not hidden) and w(widget+0x40)==expected_state and w(widget+0x38)==0
        assert draws==([[widget,mode,background]] if enabled and not hidden else []) and released==[widget]
        states.append(dict(enabled=enabled,hidden=hidden,previous=previous,mode=mode,background=background,state=expected_state,drawn=bool(draws)))

    # Original drawing dispatcher. Renderers and context activation are recipients.
    events=[]
    def record(label,argc=2):
        def cb(m):events.append([label]+[m.get('R'+str(i)) for i in range(argc)]);return 0
        return cb
    for off,target in [(0x2C,0x2FF008),(0x30,0x2FF00C),(0x34,0x2FF010)]:a.write(vt+off,0xC0000000+target)
    def hook(m):
        op=m.get('R1');events.append(['hook',m.get('R0'),op,m.get('R2')]);return handled if op==2 else 0
    a.stubs={0xDBD20:record('context',1),0xE4F88:record('background',1),0xEFED4:record('element',2),
             0x2FF000:lambda m:kind,0x2FF008:record('body',2),0x2FF00C:record('flag80',1),
             0x2FF010:record('flag20',1),0x2FF014:hook}
    drawing=[]
    for mode,background,flags,flag8,has_hook,handled,kind in itertools.product(
            range(4),[0,1],[0,0x40,0x80,0x20,0xE0],[0,0x20],[0,1],[0,1],[0,1]):
        ph(widget+6,flags);ph(widget+8,flag8);a.write(widget+0x1C,0xC02FF014 if has_hook else 0)
        a.write(widget+0x38,123);ph(widget+0x24,9);ph(widget+0x26,9);events.clear()
        call(0xDCFF4,widget,mode,background)
        expected=[['context',widget]]
        if background and not flags&0x40:expected.append(['background',widget])
        if has_hook:expected.append(['hook',widget,1,0])
        if mode&1:
            if has_hook:expected.append(['hook',widget,2,0])
            if not(has_hook and handled):expected.append(['body',widget,0])
        if mode&2 and kind:expected.append(['element',widget,background])
        if flags&0x80:expected.append(['flag80',widget])
        if (flags|flag8)&0x20:expected.append(['flag20',widget])
        assert events==expected,(mode,background,flags,flag8,has_hook,handled,kind,events,expected)
        assert w(widget+0x38)==(0 if background else 123)
        assert list(struct.unpack('<HH',a.uc.mem_read(widget+0x24,4)))==([1,1] if mode&1 else [9,9])
        drawing.append(dict(mode=mode,background=background,flags=[flags,flag8],hook=has_hook,handled=handled,kind=kind,events=events.copy()))

    # Tree-to-refresh integration: original traversal, parent resolution,
    # clipping and marker; drawing bodies and context lifecycle are controlled.
    tree,array,nodes,widgets,contexts,owner=0x11001000,0x11001100,0x11001200,0x11002000,0x11003000,0x11004000
    objects=[widgets+0x100*i for i in range(7)]
    a.write(tree,0xC0468D20,array,0,0,nodes,0,7);a.write(array,0xC0468CC4,nodes,28,384)
    ring=[0,1,4,5,2,6,3];links=[(None,1,None),(0,4,2),(0,6,3),(0,None,None),(1,None,5),(1,None,None),(2,None,None)]
    for i,(parent,child,sibling) in enumerate(links):
        node=nodes+28*i;j=ring.index(i)
        a.write(node,0xC0468CF4,0 if parent is None else nodes+28*parent,0 if child is None else nodes+28*child,
                0 if sibling is None else nodes+28*sibling,nodes+28*ring[(j-1)%7],nodes+28*ring[(j+1)%7],objects[i])
        pointer=objects[i];a.write(pointer,vt);ph(pointer+0xA,i);rect(pointer+0x14,clip)
    a.write(0xC10042D0,tree);a.write(0xC10042CC,objects[0]);a.write(0xC1004298,owner)
    a.write(0xC10042B8,0)
    a.stubs={0x13F264:lambda m:objects[6],0xDCFF4:draw,0xDBD74:lambda m:released.append(m.get('R0')) or 0,0x2959C:lambda m:0}
    integrated=[]
    for root,enabled,old_ac,old_a8,hidden_parent in itertools.product([0,1],[0,1],[0,7],[0,7],[0,1]):
        draws.clear();released.clear()
        a.write(0xC10042B0,enabled);a.write(0xC10042AC,old_ac);a.write(0xC10042A8,old_a8);a.write(0xC1004294,0)
        for i,pointer in enumerate(objects):
            a.write(pointer+0x2C,contexts+0x20*i);a.write(pointer+0x40,0);a.write(pointer+0x38,99)
            ph(pointer+6,0x10 if i==1 and hidden_parent else 0);ph(pointer+8,0)
        call(0xDE344,objects[root])
        visits=ring if root==0 else ([1] if hidden_parent else [1,4,5])
        assert released==[objects[i] for i in visits]
        expected_draws=[]
        for i in visits:
            if enabled and not(i==1 and hidden_parent):
                bg=int((root!=0 and old_a8==0) or i==root)
                expected_draws.append([objects[i],3,bg])
            assert w(objects[i]+0x40)==(2 if enabled else 1)
            assert w(objects[i]+0x38)==0
            assert w(contexts+0x20*i+12)==(0 if i==0 else objects[1] if i in [1,4,5] else objects[2] if i in [2,6] else objects[3])
        assert draws==expected_draws,(root,enabled,old_ac,old_a8,hidden_parent,draws,expected_draws)
        assert w(0xC1004294)==0 and w(0xC10042AC)==(1 if old_ac else 0)
        assert w(0xC10042A8)==((1 if root==0 else old_a8) if old_a8 else 0)
        integrated.append(dict(root=root,enabled=enabled,old_ac=old_ac,old_a8=old_a8,hidden_parent=hidden_parent,visited=visits,draws=draws.copy()))

    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,visibility=visibility,states=states,drawing=drawing,integrated=integrated,
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                boundaries=['Original rectangle visibility, intersection, refresh marker and draw dispatcher execute',
                            'Widget layout, flag meanings and tree fixture are synthetic; conclusions describe tested fields and control flow',
                            'Integration executes DE344, tree traversal, top-level parent resolution, DE2A8 and DD1DC',
                            'Draw bodies, graphics-context lifecycle, focus getter and pending-list count are captured recipients',
                            'No physical display, full page constructor, font renderer or pixel writer runs in these checks'])
    (OUT/'ui-refresh-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,visibility_cases=len(visibility),state_cases=len(states),drawing_cases=len(drawing),integrated_cases=len(integrated)),indent=2))

if __name__=='__main__':main()
