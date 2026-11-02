#!/usr/bin/env python3
"""Original PPAT binding, track advance, loop and note release."""
import argparse,contextlib,hashlib,io,json,struct
from collections import Counter
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
SOURCE=ROOT/'research/firmware/KROSS2_V124/KROSS2SY/PPAT.BIN'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('drum-track-bind',0x2456C4,0x245A04),('drum-track-decode',0x245ECC,0x246358),('drum-note-slots',0x244CE4,0x24502C)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    catalog_path=OUT/'drum-patterns.json';catalog=json.loads(catalog_path.read_text());assert sha(SOURCE)==catalog['source_sha256']
    a=Arm(f);track=0x11000000;desc=0x11001000;now=0;events=[]
    payload=SOURCE.read_bytes()[64:];base=struct.unpack_from('<I',payload)[0];a.uc.mem_write(base,payload)
    def call(p,*args):return a.call(p,*args)
    def b(p,v):a.uc.mem_write(p,bytes([v&255]))
    def h(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def emit(m):events.append([now,m.get('R1')&255,m.get('R2')&255,m.get('R3')&255]);return 1
    a.stubs={0x2BD7B4:emit}
    a.write(0xC1716398,1);b(0xC1DCD62A,0)
    def setup(index,shift=0,channel=9,loop=1):
        nonlocal now
        now=0;events.clear();a.uc.mem_write(track,bytes(0x164));a.uc.mem_write(desc,bytes(8))
        call(0x2456C4,track,0)
        b(desc,index&255);b(desc+4,0x80+(index>>8));b(desc+1,0);b(desc+2,0x30|loop);b(desc+3,shift)
        assert call(0x245760,track,desc,0,channel)==1,index
        call(0x2458C0,track,0)
        return h(track+0x1C)
    def stop():
        call(0x245A44,track)
        assert a.uc.mem_read(track+0x32,1)==b'\0'
        balance=Counter()
        for t,s,n,v in events:
            if s&0xF0==0x90:balance[n]+=1
            elif s&0xF0==0x80:balance[n]-=1;assert balance[n]>=0
        assert not any(balance.values()),balance
    # Synthetic one-bar Pattern: validate exact note/expiry, transpose clipping and loop.
    synth=0x11002000;record=base+4+32*799
    original_record=bytes(a.uc.mem_read(record,32))
    def note(n,v,d,t):return struct.pack('<BBBBHH',9,0,n,v,d,t)
    stream=struct.pack('<BBBBHH',1,0,0,19,4,0)+note(36,90,60,0)+note(38,100,120,120)+note(42,110,3000,1800)+bytes([3])+bytes(7)
    a.uc.mem_write(synth,stream);a.write(record+28,synth);b(record+24,1)
    synthetic=[]
    for shift in [-48,-38,0,24,86,100]:
        size=setup(799,shift);assert size==1920,size
        for now in range(3840):call(0x2462B8,track,int(now!=0))
        stop();ons=[x for x in events if x[1]&0xF0==0x90]
        expected=[(cycle*1920+t+int(cycle>0 and t==0),n+shift,v) for cycle in range(2) for n,v,t in [(36,90,0),(38,100,120),(42,110,1800)] if 0<=n+shift<=127]
        assert [(t,n,v) for t,s,n,v in ons]==expected,(shift,ons[:8],expected)
        offs=[(t,n) for t,s,n,v in events if s&0xF0==0x80]
        expected_off=[(t,n+shift) for t,n in [(60,36),(240,38),(1920,42),(1980,36),(2160,38),(3839,42)] if 0<=n+shift<=127]
        assert offs==expected_off,(shift,offs,expected_off)
        synthetic.append(dict(shift=shift,events=events.copy()))
    a.uc.mem_write(record,original_record)
    factory=[];notes=0
    for row in catalog['patterns'][:800]:
        size=setup(row['index']);length=len(row['bars'])*size
        expected=[];times={0}
        for bar in row['bars']:
            for raw in bar['events']:
                r=bytes.fromhex(raw);duration,t=struct.unpack_from('<HH',r,4)
                if t>=size:continue
                expected.append((bar['number']*size+t,r[2],r[3]))
                times.add(bar['number']*size+t);times.add(bar['number']*size+min(t+duration,size))
            times.add(bar['number']*size)
        previous=0
        for now in sorted(t for t in times if t<length):
            call(0x2462B8,track,now-previous);previous=now
        stop();ons=[x for x in events if x[1]&0xF0==0x90]
        assert [(t,n,v) for t,s,n,v in ons]==expected,(row['index'],ons[:5],expected[:5],len(ons),len(expected))
        notes+=len(ons)
        factory.append(dict(index=row['index'],name=row['name'],bar_ticks=size,notes=len(ons),
            events_sha256=hashlib.sha256(json.dumps(events).encode()).hexdigest(),first_events=events[:6]))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        inputs=[dict(path=str(SOURCE.relative_to(ROOT)),sha256=sha(SOURCE)),dict(path=str(catalog_path.relative_to(ROOT)),sha256=sha(catalog_path))],
        synthetic=synthetic,factory=factory,factory_notes=notes,
        boundaries=['Original PPAT selector, track bind, position setup, event decoder, 64-slot note table, loop and stop execute',
                    'Only local MIDI ingress 0x2BD7B4 is captured; wire output disabled by original global gate',
                    'Synthetic loops run per tick; factory checks advance at independent event/expiry boundaries',
                    'Keyboard trigger consumer integration, synchronization waiting, recording and voice audio remain outside this check'])
    (OUT/'drum-playback-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,synthetic_loops=len(synthetic),factory_patterns=len(factory),factory_notes=notes),indent=2))
if __name__=='__main__':main()
