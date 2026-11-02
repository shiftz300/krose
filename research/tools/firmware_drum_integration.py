#!/usr/bin/env python3
"""Keyboard -> original drum manager -> PPAT -> local MIDI, offline."""
import argparse,hashlib,json,struct
from collections import Counter
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
SOURCE=ROOT/'research/firmware/KROSS2_V124/KROSS2SY/PPAT.BIN'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();a=Arm(f);ctx=0x11000000;routes=0x11010000;stream=0x11020000
    assert sha(SOURCE)=='1f734fb8ffd41efa030079f9436753dae7e10e5cf7ac05a42921c28cc6592135'
    raw=SOURCE.read_bytes()[64:];base=struct.unpack_from('<I',raw)[0];a.uc.mem_write(base,raw)
    notes=[(36,90,60,0),(38,100,120,120),(42,110,180,300)]
    packed=struct.pack('<BBBBHH',1,0,0,19,4,0)+b''.join(struct.pack('<BBBBHH',9,0,*x) for x in notes)+bytes([3])+bytes(7)
    a.uc.mem_write(stream,packed);record=base+4+32*799;a.write(record+28,stream);a.uc.mem_write(record+24,bytes([1]))
    now=0;events=[];ui=[]
    def call(p,*args):return a.call(p,*args)
    def b(p,v):a.uc.mem_write(p,bytes([v&255]))
    def h(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def word(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def emit(m):events.append([now,m.get('R1')&255,m.get('R2')&255,m.get('R3')&255]);return 1
    a.stubs={0x2BD7B4:emit,0x132660:lambda m:0,0x132670:lambda m:0,
             0x12AF28:lambda m:ui.append(['on',m.get('R0')]) or 0,
             0x12AEE4:lambda m:ui.append(['off',m.get('R0')]) or 0,
             0x12B05C:lambda m:ui.append(['blink',m.get('R0')]) or 0,
             0x2D9E0:lambda m:0}
    def setup(wait,latch,sync=False,phase=0):
        a.uc.mem_write(ctx,bytes(0x650));a.uc.mem_write(routes,bytes(1024));a.write(ctx,routes)
        a.write(0xC1716398,1);b(0xC1DCD62A,0);h(0xC171D526,0);h(0xC0F55A74,0);h(0xC0F55A72,0)
        call(0x246BCC,ctx);a.write(ctx,routes)
        b(ctx+8,799&255);b(ctx+12,0x83);b(ctx+10,0x31);b(ctx+9,0x30 if sync else 0)
        # Original sync query reads an active peer's current phase. Its clock
        # remains fixed in this fixture so the sampled input phase is explicit.
        master,owner,peer,vel,keys,params=0x11030000,0x11030100,0x11030200,0x11030300,0x11030400,0x11030500
        a.uc.mem_write(master,bytes(0x600));a.write(0xC0F55850,master);a.write(master+0x2C,owner);a.write(owner+8,0)
        a.write(0xC0A00000,peer);a.write(peer,phase);a.write(peer+0x28,480)
        a.write(peer+0x60,vel);a.write(vel+128,1 if sync else 0)
        a.write(peer+0x68,keys);a.write(keys+4,1 if sync else 0);a.write(peer+0x74,params)
        b(ctx+0x18,9);b(ctx+0x19,0);b(0xC1DCD628,0)
        b(ctx+0x10,wait);b(ctx+0x11,latch);b(ctx+0x12,48);b(ctx+0x13,72);b(ctx+0x14,1);b(ctx+0x15,127)
        call(0x248324,ctx,128,wait)
        assert h_read(0xC1714D24)==1
        events.clear();ui.clear()
    def h_read(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    traces=[]
    for wait,latch in [(0,0),(1,0),(1,1)]:
        setup(wait,latch)
        for now in range(720):
            if wait and now==37:call(0x2488F8,ctx,0,60,90)
            if wait and now==187:call(0x2488F8,ctx,0,60,0)
            call(0x24725C);call(0x248440,ctx)
        call(0x247480,ctx);call(0x248440,ctx)
        ons=[e for e in events if e[1]&240==144]
        assert ons,(wait,latch,events)
        start=37 if wait else 0;expected=[]
        for note,velocity,duration,tick in notes:
            on=start+max(0,tick-1);off=start+tick+duration-1
            if wait and not latch and on>=187:continue
            if wait and not latch:off=min(off,187)
            expected.extend([[on,144,note,velocity],[off,128,note,64]])
        expected.sort(key=lambda x:x[0]);assert events==expected,(wait,latch,events,expected)
        if wait:
            assert not any(e[0]<37 for e in ons)
            assert bool(any(e[0]>187 for e in ons))==bool(latch),(wait,latch,ons)
        balance=Counter()
        for t,s,n,v in events:
            balance[n]+=1 if s&240==144 else -1;assert balance[n]>=0
        assert not any(balance.values())
        assert not a.uc.mem_read(0xC1714D48+0x32,1)[0]
        assert word(ctx+0x628)==0
        traces.append(dict(wait=wait,latch=latch,events=events.copy(),ui=ui.copy(),active_tracks=h_read(0xC1714D24)))
    synchronized=[]
    for phase in [0,1,59,60,120,479]:
        setup(0,0,True,phase)
        offset=0 if phase==0 else -phase if phase<60 else 480-phase
        for now in range(960):call(0x24725C);call(0x248440,ctx)
        call(0x247480,ctx);call(0x248440,ctx)
        ons=[e for e in events if e[1]&240==144]
        assert ons and ons[0][0]==max(0,offset-1),(phase,offset,ons)
        balance=Counter()
        for t,s,n,v in events:balance[n]+=1 if s&240==144 else -1;assert balance[n]>=0
        assert not any(balance.values()) and not word(ctx+0x628)
        synchronized.append(dict(peer_phase=phase,offset=offset,events=events.copy()))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        inputs=[dict(path=str(SOURCE.relative_to(ROOT)),sha256=sha(SOURCE))],traces=traces,synchronized=synchronized,
        boundaries=['Original manager initialization, route selection, track allocation/binding, key trigger, request queue consumer, tick counter, note decoder and stop execute',
                    'Three synthetic notes replace one PPAT entry in emulator memory only; immediate, keyboard/Latch off and keyboard/Latch on traces execute',
                    'Only critical sections, LED/cache notifications and final local MIDI ingress are intercepted',
                    'Six Sync cases use original phase query against an active peer fixture held at the declared phase',
                    'Active recording, live peer clock progression, OS interrupt ordering, wire MIDI and audio remain unverified'])
    (OUT/'drum-integration-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,traces=len(traces),events=sum(len(x['events']) for x in traces)),indent=2))
if __name__=='__main__':main()
