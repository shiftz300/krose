#!/usr/bin/env python3
"""Original clipped rectangle writers, framebuffer bytes and refresh-to-clear path."""
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
    for name,lo,hi in [('ui-bitmap-pattern',0xE2EC4,0xE3440),('ui-bitmap-clear',0xE4C70,0xE4FF8),
                       ('ui-bitmap-position',0xDC42C,0xDC4DC)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    assert [f.pointer(0xE3150+i*4) for i in range(5)]==[0xE3164,0xE327C,0xE31F0,0xE31F0,0xE3308]
    if not args.verify_arm:return
    a=Arm(f)
    def call(p,*args,**kw):return a.call(p,*args,**kw)&0xFFFFFFFF
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def rect(p,r):a.uc.mem_write(p,struct.pack('<4h',*r))
    widget,context,queue,params,clips,frame=0x11000000,0x11000100,0x11000200,0x11000300,0x11000400,0x11001020
    a.write(widget,0xC0469BEC);ph(widget+0xA,0);a.write(widget+0x2C,context)
    a.write(context,0,0,queue,0,1);a.write(0xC104751C,frame);a.write(0xC10042B0,1)
    regions=[];iterators={};guard=bytes([0xA7]*32)
    def begin(m):assert m.get('R1')==queue;iterators[m.get('R0')]=iter(range(len(regions)));return 0
    def nxt(m):
        i=next(iterators[m.get('R0')],None);return 0 if i is None else clips+8*i
    base={0x2DC184:lambda m:0,0x2DC1BC:lambda m:0,0x2959C:lambda m:len(regions),
          0x29F14:begin,0x29FE0:nxt,0x29F94:lambda m:0}
    a.stubs=dict(base)
    raw=bytes(((i*73+19)^(i//30*11))&255 for i in range(1920))
    pattern=[0x18,0x24,0x42,0x81,0xA5,0x5A,0xC3,0x3C]
    def setup(origin,cliplist,source=raw):
        nonlocal regions
        ph(widget+6,0);ph(widget+8,0);ph(widget+0x28,origin[0]);ph(widget+0x2A,origin[1])
        rect(widget+0xC,(0,0,240,64));regions=cliplist
        for i,r in enumerate(regions):rect(clips+8*i,r)
        a.uc.mem_write(frame-32,guard+source+guard)
    def model(source,bounds,cliplist,op,override):
        output=bytearray(source)
        for region in cliplist:
            left=max(bounds[0],region[0]);top=max(bounds[1],region[1])
            right=min(bounds[2],region[2]);bottom=min(bounds[3],region[3])
            for y in range(top,bottom):
                for x in range(left,right):
                    assert 0<=x<240 and 0<=y<64
                    bit=128>>(x&7);offset=y*30+(x>>3)
                    old=int(bool(output[offset]&bit));pat=int(bool(pattern[y&7]&bit))
                    if override==2:new=1-old
                    elif op==0:new=pat
                    elif op==1:new=old&(1-pat)
                    elif op in [2,3]:new=old|pat
                    elif op==4:new=old^pat
                    elif op=='clear':new=0
                    else:new=old
                    if new:output[offset]|=bit
                    else:output[offset]&=255^bit
        return bytes(output)
    def verify(expected):
        actual=bytes(a.uc.mem_read(frame,1920))
        assert actual==expected,next((i for i,(x,y) in enumerate(zip(actual,expected)) if x!=y),None)
        assert bytes(a.uc.mem_read(frame-32,32))==guard and bytes(a.uc.mem_read(frame+1920,32))==guard
        return hashlib.sha256(actual).hexdigest()
    region_sets=[[(0,0,240,64)],[(12,9,38,23)],[(0,0,20,64),(20,0,240,64)],[(4,4,35,28),(16,8,48,32)]]
    pattern_cases=[]
    for phase,width,op,override,ci in itertools.product(range(8),[1,7,8,9,17],[0,1,2,3,4,5],[0,2],range(4)):
        origin=(3,2);bounds=(phase+2,3,phase+2+width,23);absolute=(bounds[0]+3,bounds[1]+2,bounds[2]+3,bounds[3]+2)
        setup(origin,region_sets[ci]);a.write(params,op,override);rect(params+8,bounds)
        a.uc.mem_write(params+16,struct.pack('<8H',*[0xA500|v for v in pattern]))
        call(0xE2EFC,widget,params)
        assert tuple(struct.unpack('<4h',a.uc.mem_read(params+8,8)))==absolute
        digest=verify(model(raw,absolute,regions,op,override))
        pattern_cases.append(dict(phase=phase,width=width,op=op,override=override,clips=ci,sha256=digest))
    clear_cases=[]
    for phase,width,origin,ci in itertools.product(range(8),[1,7,8,9,17,200],[(0,0),(3,2),(-4,-3)],range(4)):
        bounds=(phase,1,phase+width,19);absolute=(bounds[0]+origin[0],bounds[1]+origin[1],bounds[2]+origin[0],bounds[3]+origin[1])
        setup(origin,region_sets[ci]);rect(params,bounds)
        call(0xE4C70,widget,params)
        digest=verify(model(raw,absolute,regions,'clear',0))
        assert tuple(struct.unpack('<4h',a.uc.mem_read(params,8)))==bounds
        assert tuple(struct.unpack('<4h',a.uc.mem_read(0xC1004824,8)))==absolute
        clear_cases.append(dict(phase=phase,width=width,origin=origin,clips=ci,sha256=digest))
    # Full framebuffer and boundary pixels, including exact byte boundaries.
    edges=[]
    for bounds in [(0,0,240,64),(0,0,1,1),(239,63,240,64),(7,0,8,64),(8,0,9,64),(0,63,240,64),(0,0,0,64),(240,0,250,64)]:
        setup((0,0),region_sets[0]);rect(params,bounds);call(0xE4C70,widget,params)
        edges.append(dict(rect=bounds,sha256=verify(model(raw,bounds,regions,'clear',0))))
    gating=[]
    for enabled,flag6,flag8 in itertools.product([0,1],[0,0x10],[0,0x10]):
        setup((0,0),region_sets[0]);a.write(0xC10042B0,enabled);ph(widget+6,flag6);ph(widget+8,flag8)
        rect(params,(0,0,240,64));call(0xE4C70,widget,params)
        allowed=enabled and not(flag6 or flag8)
        gating.append(dict(enabled=enabled,flag6=flag6,flag8=flag8,sha256=verify(bytes(1920) if allowed else raw)))
    a.write(0xC10042B0,1)
    # Original DD1DC -> DCFF4 -> E4F88 -> E4C70, ending in framebuffer stores.
    # Mode 0 selects background only; context activation/release stay controlled.
    context_events=[]
    def activate(m):context_events.append('activate');return queue
    def release(m):context_events.append('release');return 0
    a.stubs.update({0xDBD20:activate,0xDBD74:release})
    integrated=[]
    for origin,width,height,flag in itertools.product([(0,0),(7,9)],[(1),(33)],[1,17],[0,0x40]):
        setup(origin,region_sets[0]);rect(widget+0xC,(2,3,2+width,3+height))
        bounds=(origin[0],origin[1],origin[0]+width,origin[1]+height)
        rect(widget+0x14,bounds);ph(widget+6,flag);a.write(widget+0x1C,0)
        a.write(0xC10042B8,0);context_events.clear()
        call(0xDD1DC,widget,0,1)
        digest=verify(raw if flag else model(raw,bounds,regions,'clear',0))
        assert context_events==['activate','release'] and w(widget+0x40)==2
        integrated.append(dict(origin=origin,width=width,height=height,flag=flag,sha256=digest))
    # A synthetic 240x64 raster produced by original pattern writer, saved for figure reproduction.
    setup((0,0),region_sets[0],bytes(1920))
    panels=[]
    for op in range(5):
        bounds=(8+46*op,8,44+46*op,56)
        # Seed each panel with a contrasting low-frequency pattern using original replace.
        for pass_op,pat in [(0,[0xF0,0xF0,0xF0,0xF0,0x0F,0x0F,0x0F,0x0F]),(op,pattern)]:
            a.write(params,pass_op,0);rect(params+8,bounds)
            a.uc.mem_write(params+16,struct.pack('<8H',*pat));call(0xE2EFC,widget,params)
        panels.append(dict(op=op,rect=bounds))
    raster=bytes(a.uc.mem_read(frame,1920));(OUT/'ui-bitmap-pattern-sample.bin').write_bytes(raster)
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,pattern_cases=pattern_cases,clear_cases=clear_cases,
                edge_cases=edges,gating=gating,integrated=integrated,sample=dict(panels=panels,sha256=hashlib.sha256(raster).hexdigest()),
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                boundaries=['Original clipped pattern and clear writers modify every compared framebuffer byte; guard bytes remain unchanged',
                            'Pattern source uses low byte of eight 16-bit rows, selected by absolute y modulo eight',
                            'Region list and iterator services are modeled; coordinates, intersection, masks and stores execute unchanged',
                            'Continuous refresh checks execute DD1DC to framebuffer with mode zero/background only; context services captured',
                            'Saved raster is a synthetic primitive demonstration, not a recovered factory page or physical LCD capture'])
    (OUT/'ui-bitmap-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pattern_cases=len(pattern_cases),clear_cases=len(clear_cases),edges=len(edges),integrated=len(integrated)),indent=2))

if __name__=='__main__':main()
