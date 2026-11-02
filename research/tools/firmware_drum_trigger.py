#!/usr/bin/env python3
"""Original drum keyboard trigger, held keys and deferred command queue."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from collections import deque
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('drum-key-trigger',0x2488F8,0x248AFC),('drum-request-queue',0x246704,0x24696C),('drum-key-bits',0x246A48,0x246AF8)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    a=Arm(f);ctx=0x11000000;desc=0x11001000;output=0x11002000;q=ctx+0x20
    a.stubs={0x132660:lambda m:0,0x132670:lambda m:0,0x246FA0:lambda m:desc,0x248440:lambda m:0}
    def call(p,*args):return a.call(p,*args)
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def b(p,v):a.uc.mem_write(p,bytes([v&255]))
    def reset(wait=1,latch=0,mode=0):
        a.uc.mem_write(ctx,bytes(0x650));a.uc.mem_write(desc,bytes(8));b(desc+2,mode<<4)
        b(ctx+0x10,wait);b(ctx+0x11,latch);b(ctx+0x12,48);b(ctx+0x13,72);b(ctx+0x14,64);b(ctx+0x15,96)
        a.write(0xC1716398,1);b(0xC1DCD628,0)
        call(0x246704,q)
    def commands():
        n=w(q+0x608);i=w(q+0x604)
        return [[a.uc.mem_read(q+12*((i+j)&127),12)[k] for k in [0,1,4]] for j in range(n)]
    def keys(offset):
        raw=bytes(a.uc.mem_read(ctx+offset,16));return [n for n in range(128) if raw[n//8]&(1<<(n%8))]
    gates=0
    for wait,latch,mode,channel,note,velocity in itertools.product([0,1],[0,1],[0,3],[0,1],[47,48,60,72,73],[0,1,63,64,96,97,127]):
        reset(wait,latch,mode);assert call(0x2488F8,ctx,channel,note,velocity)==1
        allowed=wait==1 and mode!=3 and channel==0 and 48<=note<=72
        accepted=allowed and 64<=velocity<=96
        expected=[[3,0,0]] if accepted else [[3,0,1]] if allowed and velocity==0 and latch==0 else []
        assert commands()==expected,(wait,latch,mode,channel,note,velocity,commands(),expected)
        assert keys(0x62C)==([note] if accepted else [])
        assert keys(0x63C)==([note] if velocity else [])
        gates+=1
    traces=[]
    sequence=[(60,80),(64,90),(60,100),(60,0),(64,0),(67,96),(67,0),(67,0)]
    for latch in [0,1]:
        reset(latch=latch);held=set();expected=[];trace=[]
        for note,velocity in sequence:
            if velocity and 64<=velocity<=96:
                if not held:expected.append([3,0,0])
                held.add(note)
            elif not velocity:
                held.discard(note)
                if not held and not latch:expected.append([3,0,1])
            call(0x2488F8,ctx,0,note,velocity)
            assert commands()==expected and keys(0x62C)==sorted(held)
            trace.append(dict(note=note,velocity=velocity,held=sorted(held),commands=commands()))
        traces.append(dict(latch=latch,trace=trace))
    # Ring capacity is 127, with 128 backing slots. Verify wrap and FIFO data.
    reset();model=deque();operations=0
    for batch in [130,-100,90,-130,5,-5]:
        for j in range(abs(batch)):
            if batch>0:
                values=(operations,operations^0x12345678,operations^0xAABBCCDD)
                call(0x246718,q,*values)
                if len(model)<127:model.append(struct.pack('<III',*values))
            else:
                call(0x246908,output,q)
                if model:assert bytes(a.uc.mem_read(output,12))==model.popleft()
                else:assert a.uc.mem_read(output,1)==b'\0'
            assert w(q+0x608)==len(model);operations+=1
    # Execute the real consumer up to its track resume/suspend boundaries.
    del a.stubs[0x248440]
    dispatch=[];actions=[]
    for address,label in [(0x24814C,'resume'),(0x247334,'suspend'),(0x247390,'finish')]:
        a.stubs[address]=lambda m,label=label:actions.append(label) or 0
    a.stubs[0x415E0]=lambda m:0;a.stubs[0x41600]=lambda m:0
    a.uc.mem_write(0xC1714D24,bytes(20))
    for latch in [0,1]:
        reset(latch=latch);held=set();expected=[];actions.clear()
        for note,velocity in sequence:
            if velocity and 64<=velocity<=96:
                if not held:expected.append('resume')
                held.add(note)
            elif not velocity:
                held.discard(note)
                if not held and not latch:expected.append('suspend')
            call(0x2488F8,ctx,0,note,velocity)
            assert not commands() and actions==expected,(latch,note,velocity,actions,expected)
        dispatch.append(dict(latch=latch,actions=actions.copy()))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),gate_cases=gates,traces=traces,queue_operations=operations,dispatch=dispatch,
        boundaries=['Original trigger, channel getter, held-key bitsets, queue append/pop and capacity/wrap execute',
                    'Route descriptor lookup 0x246FA0 returns a synthetic descriptor; critical sections are intercepted',
                    'Gate checks intercept consumer 0x248440; dispatch traces execute it and capture track resume/suspend boundaries with zero clock reads and no active tracks',
                    'Only defined command bytes 0,1,4 are compared for wrapper requests; unused stack padding is not assigned semantics'])
    (OUT/'drum-trigger-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,gate_cases=gates,sequence_operations=16,queue_operations=operations),indent=2))
if __name__=='__main__':main()
