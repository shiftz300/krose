#!/usr/bin/env python3
"""Original sequencer recording intake, timestamp clamp and bounded FIFO."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware()
    for name,lo,hi in [('record-fifo',0x242B78,0x242CD0),('record-enqueue',0x2434C8,0x2436C8),('record-midi-intake',0x243ED4,0x243F94)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f);queue=0xC1714708;source,dest,descriptor=0x11001000,0x11002000,0x11003000
    def h(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def pb(p,v):a.uc.mem_write(p,bytes([v]))
    def zero(m):return 0
    a.stubs={0x132660:zero,0x132670:zero}
    def reset(count=0,override=0,punch=0,first=0):
        a.uc.mem_write(queue,b'\xA5'*0x600+struct.pack('<HHH',0,0,count))
        a.write(0xC17146B4+0x14,override);ph(0xC171C3BE,punch<<8)
        ph(0xC1714700,3);ph(0xC1714702,240);a.write(0xC1714704,first)
    matrix=[]
    for count,override,punch,status,time,first in itertools.product([0,119,120,127,128],range(2),range(2),[1,0x90],[(-1,0),(3,239),(3,240),(3,241),(4,0)],range(2)):
        reset(count,override,punch,first)
        raw=struct.pack('<BBHHhhH',status,60,100,0x5AA5,*time,0x1234)
        a.uc.mem_write(source,raw);before=bytes(a.uc.mem_read(queue,0x606))
        ret=a.call(0x2435B4,queue,source)
        accepted=count<120 and (not override or punch or status==1)
        expect=bytearray(before)
        if accepted:
            stored=bytearray(raw);stamp=(3,240) if first or time<(3,240) else time
            stored[6:10]=struct.pack('<hh',*stamp)
            expect[:12]=stored;expect[0x600:0x602]=struct.pack('<H',1);expect[0x604:0x606]=struct.pack('<H',count+1)
        assert bytes(a.uc.mem_read(queue,0x606))==bytes(expect)
        assert ret==int(count<120)
        expected_time=(3,240) if not accepted or first or time<(3,240) else time
        assert (h(0xC1714700),h(0xC1714702))==expected_time
        matrix.append(dict(count=count,override=override,punch=punch,status=status,time=time,first=first,accepted=bool(accepted),returned=ret))

    # Exact FIFO contents after full, drain, refill and index wrap; urgent events
    # use all 128 slots while ordinary MIDI intake stops at 120.
    reset();model=[];ops=[];sequence=0
    def enqueue(urgent=False):
        nonlocal sequence
        raw=struct.pack('<BBHHhhH',0x90,sequence%128,sequence&65535,0x4321,4,sequence,0xABCD);sequence+=1
        a.uc.mem_write(source,raw);limit=128 if urgent else 120
        ok=len(model)<limit;ret=a.call(0x2434C8 if urgent else 0x2435B4,queue,source)
        assert ret==int(ok)
        if ok:model.append(raw)
        assert h(queue+0x604)==len(model)
        ops.append(dict(op='urgent' if urgent else 'enqueue',accepted=ok,count=len(model)))
    def dequeue():
        ok=bool(model);ret=a.call(0x242BE0,queue,dest);assert ret==int(ok)
        if ok:assert bytes(a.uc.mem_read(dest,12))==model.pop(0)
        assert h(queue+0x604)==len(model)
        ops.append(dict(op='dequeue',accepted=ok,count=len(model)))
    for _ in range(121):enqueue()
    for _ in range(9):enqueue(True)
    for _ in range(64):dequeue()
    for _ in range(56):enqueue()
    for _ in range(8):enqueue(True)
    for _ in range(129):dequeue()
    assert not model and h(queue+0x600)==h(queue+0x602)==64

    # Original peek copies one record and returns the same cached record until
    # the original cache-clear function acknowledges it.
    reset();raw=struct.pack('<BBHHhhH',0x90,60,100,0,4,10,0);a.uc.mem_write(source,raw)
    assert a.call(0x2435B4,queue,source)==1
    a.call(0x242C60)
    assert a.call(0x243410)==1 and h(queue+0x604)==0
    assert bytes(a.uc.mem_read(0xC1714D14,12))==raw
    assert bytes(a.uc.mem_read(0xC17146F4,12))==raw
    assert a.call(0x243410)==1 and h(queue+0x604)==0
    a.call(0x242C60);assert a.call(0x243410)==0

    fallbacks=[]
    a.stubs[0x25BCB0]=lambda m:fallbacks.append([m.get('R0'),m.get('R1')]) or 0
    intake=[]
    for active,mapped,override,punch,full,status,channel,value,cleanup_suppress in itertools.product(range(2),[0,15,16],range(2),range(2),range(2),[0x80,0x90,0xB0],[0,9,15],[0,127,8192],range(2)):
        reset(120 if full else 0,override,punch);fallbacks.clear()
        pb(0xC1714D11,active);pb(0xC171C42E+channel,mapped);pb(0xC1714D10,cleanup_suppress)
        before=bytes(a.uc.mem_read(queue,0x606))
        ret=a.call(0x243ED4,0xC17146B4,status|5,60,value,stack=(channel,3,240))
        queued=active and mapped!=16 and not full and (not override or punch)
        assert ret==active and h(queue+0x604)==(120 if full else int(queued))
        if queued:
            r=bytes(a.uc.mem_read(queue,12))
            assert (r[0],r[1],struct.unpack_from('<H',r,2)[0],struct.unpack_from('<HH',r,6))==(status|channel,60,value,(3,240))
        else:assert bytes(a.uc.mem_read(queue,0x606))==before
        fallback=active and mapped!=16 and full and not cleanup_suppress and status==0x80
        assert fallbacks==([[mapped,60]] if fallback else []),(active,mapped,override,punch,full,status,channel,value,fallbacks)
        intake.append(dict(active=active,mapped=mapped,override=override,punch=punch,full=full,status=status,channel=channel,value=value,cleanup_suppress=cleanup_suppress,queued=bool(queued),fallback=bool(fallback)))

    # Drum output -> ordinary MIDI pending queue boundary AND real record intake.
    pending=[];local=[]
    a.stubs[0x25F1B8]=lambda m:pending.append(list(a.uc.mem_read(m.get('R1')+1,3))) or 1
    a.stubs[0x2BD7B4]=lambda m:local.append([m.get('R1'),m.get('R2'),m.get('R3')]) or 0
    reset();pb(0xC1714D11,1);pb(0xC171C42E+9,2);pb(0xC1714D10,0)
    a.write(0xC1716398,3);pb(0xC1714371,1);pb(0xC1DCD62A,0);ph(0xC171D4DC,0)
    a.uc.mem_write(descriptor,bytes([0,3,0x30,0]));ph(0xC1714700,0);ph(0xC1714702,0)
    trace=[(0,0x99,36,100),(59,0x89,36,0),(119,0x99,38,90),(239,0x89,38,0)]
    for tick,status,note,value in trace:
        ph(0xC17163A8,0);ph(0xC17163AA,tick)
        a.call(0x244A60,descriptor,status,note,value)
    assert not local and pending==[[s,n,v] for t,s,n,v in trace]
    assert h(queue+0x604)==4
    drum=[]
    for tick,status,note,value in trace:
        assert a.call(0x242BE0,queue,dest)==1;r=bytes(a.uc.mem_read(dest,12))
        assert (r[0],r[1],h(dest+2),h(dest+6),h(dest+8))==(status,note,value,0,tick)
        drum.append(dict(tick=tick,status=status,note=note,value=value,record_hex=r.hex()))
    assert a.call(0x242BE0,queue,dest)==0
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        enqueue_cases=matrix,fifo_operations=ops,intake_cases=intake,drum_trace=drum,peek_cache_checked=True,
        boundaries=['Original MIDI recording gate/channel mapping, 12-byte record construction, time clamp, 120/128 thresholds, enqueue/dequeue and peek cache execute',
                    'Drum mode-3 output 0x244A60 calls original 0x243ED4 and writes records into the real global ring queue',
                    'Critical sections, playback pending-queue handoff, local MIDI sink and full-queue note-off cleanup 0x25BCB0 intercepted',
                    'Timestamp globals and record state are controlled; undefined record padding is preserved only in explicitly supplied raw FIFO records',
                    'Conversion into eight-byte song events, quantization, event-pool growth, save/load and OS scheduling remain outside this check'])
    (OUT/'record-intake-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,enqueue_cases=len(matrix),fifo_operations=len(ops),intake_cases=len(intake),drum_events=len(drum)),indent=2))
if __name__=='__main__':main()
