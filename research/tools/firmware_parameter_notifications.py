#!/usr/bin/env python3
"""Original parameter notification context, song mirror and effect block copies."""
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
    for name,lo,hi in [('parameter-notify-context',0x205B6C,0x205C24),
                       ('parameter-notify-list',0x207C00,0x207DCC),
                       ('parameter-song-mirror',0x2625F8,0x262794),
                       ('parameter-effect-copy',0x23D394,0x23D508)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    a=Arm(f)
    def call(p,*args,**kw):return a.call(p,*args,**kw)
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def pb(p,v):a.uc.mem_write(p,bytes([v]))
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v))
    def zero(m):return 0
    ctx,access,cache,song=0x11000000,0x11000100,0x11010000,0x11020000
    a.write(0xC1690248,cache)
    def state(group,index,present,playing,override,suppress):
        a.uc.mem_write(cache,bytes(0x2224))
        if 100<=group<=135 and present:
            a.write(cache+32*(group-100)+4*(index//32),1<<(index%32))
        ph(0xC171D516,playing);a.write(0xC17146B4+0x14,override);a.write(0xC171C4C4,suppress)
    gate_cases=0
    for group,index in [(99,0),(100,2),(108,1),(123,59),(124,0),(130,1),(135,1),(136,0),(175,0)]:
        for present,playing,override,suppress in itertools.product(range(2),[0,1,0x8000],range(2),[0,1,2]):
            state(group,index,present,playing,override,suppress)
            expected=100<=group<=135 and not present and (not playing or override) and suppress==0
            assert call(0x2625F8,group,index)==expected
            gate_cases+=1

    # Direct callback operation 2/3 writes to current song's relocated field,
    # restoring the access object's original address on return.
    header=f.pointer(0x407BD0+100*4);table=f.pointer(header+4);entry=f.pointer(table+2*4)
    target=f.u32(entry);desc=f.u32(entry+4);relative=target-0xC17456AC
    mirror_cases=0;examples=[]
    for slot,op,kind,present,playing,override,suppress,value in itertools.product([0,7,127],[1,2,3],[12,14,18,20],range(2),range(2),range(2),range(2),[3,255,256]):
        state(100,2,present,playing,override,suppress)
        pb(0xC1747538+0x208,slot);a.write(0xC1747538+8+4*slot,song)
        a.write(access,0,target,desc,0,0,1)
        a.uc.mem_write(ctx,bytes(0x40));ph(ctx,100);ph(ctx+2,2)
        a.write(ctx+8,3);a.write(ctx+0x10,kind);a.write(ctx+0x18,access);a.write(ctx+0x24,value)
        pb(target,0x55);pb(song+relative,0xA5)
        call(0x262678,op,ctx,0)
        eligible=not present and (not playing or override) and not suppress
        changed=eligible and op in [2,3] and kind not in [18,20]
        assert a.uc.mem_read(song+relative,1)[0]==(value&255 if changed else 0xA5)
        assert a.uc.mem_read(target,1)[0]==0x55 and w(access+4)==target
        mirror_cases+=1
        if slot==0 and op==2 and not present and not playing and not override and not suppress:
            examples.append(dict(kind=kind,input=value,mirrored=changed,stored=value&255 if changed else None))

    # Changed effect selectors first snapshot 64 live bytes regardless of the
    # later eligibility gate, then optionally copy those bytes to the song.
    selectors=[(124,i,0x18+76*i) for i in range(5)]+[(130,i,0x194+68*i) for i in range(2)]+[(175,0,0x220)]
    effect_cases=[]
    for group,index,offset in selectors:
        for equal,present,suppress,kind in itertools.product(range(2),range(2),range(2),[12,13,14]):
            state(group,index,present,0,0,suppress)
            pb(0xC1747538+0x208,7);a.write(0xC1747538+8+4*7,song)
            source=bytes((index*17+i*3+group)&255 for i in range(64))
            a.uc.mem_write(0xC17456AC+offset,source)
            a.uc.mem_write(0xC1690290+offset,b'\xA5'*64)
            a.uc.mem_write(song+offset,b'\x5A'*64)
            a.uc.mem_write(ctx,bytes(0x40));ph(ctx,group);ph(ctx+2,index)
            a.write(ctx+0xC,kind);a.write(ctx+0x1C,1,1 if equal else 2)
            call(0x262678,8,ctx,0)
            snapshot=bytes(a.uc.mem_read(0xC1690290+offset,64))
            saved=bytes(a.uc.mem_read(song+offset,64))
            eligible=100<=group<=135 and not present and not suppress
            mirrored=not equal and eligible and kind!=13
            assert snapshot==(b'\xA5'*64 if equal else source)
            assert saved==(source if mirrored else b'\x5A'*64)
            effect_cases.append(dict(group=group,index=index,equal=equal,present=present,suppress=suppress,kind=kind,snapshot=not equal,song_copy=mirrored))

    # Execute original list traversal and operation-8 context construction.
    # Capture descriptor callback, transport and final type-14 follow-up.
    manager,context,items,rec,packet=0x11040000,0x11040100,0x11040200,0x11040300,0x11040400
    a.write(manager+0x10,context)
    iterators={};sequence=[];callbacks=[];followups=[];sent=[];released=[]
    def begin(m):iterators[m.get('R0')]=iter(sequence);return 0
    def next_item(m):return next(iterators[m.get('R0')],0)
    def callback(m):
        assert m.get('R0')==8
        p=m.get('R1')
        callbacks.append(dict(group=struct.unpack('<H',a.uc.mem_read(p,2))[0],index=struct.unpack('<H',a.uc.mem_read(p+2,2))[0],
                              context=w(p+4),type=w(p+8),kind=w(p+12),new=w(p+28),old=w(p+32),suppress=w(0xC171C4C4)))
        return 0
    def followup(m):followups.append([m.get('R1'),m.get('R2'),m.get('R3')]);return 0
    def alloc(m):return 0x11040500
    def send(m):
        p=w(m.get('R1'));sent.append(dict(command=m.get('R2'),bytes=list(a.uc.mem_read(p,12)),list_pointer=w(w(p+12))))
        return 0
    def release(m):released.append(w(m.get('R1')));return 0
    a.stubs={0x2DC184:zero,0x2DC1BC:zero,0x29F14:begin,0x29FE0:next_item,0x29F94:zero,
             0x1DEA58:callback,0x2CD594:lambda m:packet,0x14E730:alloc,0x205AC0:send,
             0x14E760:zero,0x2CD694:release,0x2096FC:followup}
    notify_cases=[]
    for kind,flag,old,new in itertools.product([12,13,14,15,16,18,20],range(2),[0,3],[0,3,7]):
        a.uc.mem_write(rec,struct.pack('<IHHIIII',0xC04714B4,100,2,kind,new,old,flag))
        sequence[:]=[rec];callbacks.clear();followups.clear();sent.clear();released.clear()
        a.uc.mem_write(packet,bytes(16));a.write(0xC171C4C4,0)
        call(0x207C00,manager,items)
        assert callbacks==[dict(group=100,index=2,context=context,type=3,kind=kind,new=new,old=old,suppress=flag)],callbacks
        assert w(0xC171C4C4)==0
        assert sent==[dict(command=13,bytes=[0,0,0,0,9,0,0,0,12,0,0,0],list_pointer=items)],sent
        assert released==[packet]
        call(0x209904,manager,items)
        assert followups==([[100,2,new]] if kind==14 else [])
        notify_cases.append(dict(kind=kind,flag=flag,old=old,new=new,type14_followup=kind==14))

    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
                gate_cases=gate_cases,mirror_cases=mirror_cases,mirror_examples=examples,effect_cases=effect_cases,notify_cases=notify_cases,
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                boundaries=['Original eligibility gate, scalar mirror, effect 64-byte copies, list traversal and operation-8 context execute',
                            'Private song buffers and globals are controlled fixtures; no actual song file is loaded',
                            'Notification descriptor callback, message handoff and type-14 receiver are captured',
                            'Allocation, list iterator and exception registration are modeled; OS queues and audio/UI are not run'])
    (OUT/'parameter-notifications-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,gate_cases=gate_cases,mirror_cases=mirror_cases,effect_cases=len(effect_cases),notify_cases=len(notify_cases)),indent=2))

if __name__=='__main__':main()
