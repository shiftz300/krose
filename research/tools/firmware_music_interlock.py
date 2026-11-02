#!/usr/bin/env python3
"""Original central musical tick driving simultaneous arp and drum engines."""
import argparse,hashlib,json,struct
from collections import Counter
from pathlib import Path
from program_firmware import Firmware,FW_SHA
from firmware_arpeggio_sync import Rig
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
SOURCE=ROOT/'research/firmware/KROSS2_V124/KROSS2SY/PPAT.BIN'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();r=Rig(f);a=r.a;ctx=0x11040000;routes=0x11041000;stream=0x11042000;app=0x11045000;shared=0x11046000
    assert sha(SOURCE)=='1f734fb8ffd41efa030079f9436753dae7e10e5cf7ac05a42921c28cc6592135'
    raw=SOURCE.read_bytes()[64:];base=struct.unpack_from('<I',raw)[0];a.uc.mem_write(base,raw)
    a.uc.mem_write(stream,struct.pack('<BBBBHH',1,0,0,19,4,0)+b''.join(struct.pack('<BBBBHH',9,0,*v) for v in [(36,90,60,0),(38,100,120,120),(42,110,180,300)])+bytes([3])+bytes(7))
    a.write(base+32+32*799,stream);r.b(base+4+32*799+24,1)
    now=0;drums=[]
    def emit(m):drums.append([now,m.get('R1')&255,m.get('R2')&255,m.get('R3')&255]);return 1
    a.stubs.update({0x2BD7B4:emit,0x132660:lambda m:0,0x132670:lambda m:0,
                    0x12AF28:lambda m:0,0x12AEE4:lambda m:0,0x12B05C:lambda m:0,0x2D9E0:lambda m:0,
                    0x1396CC:lambda m:0})
    def balance(events,arp=False):
        counts=Counter()
        for v in events:
            n,on=(v['note'],v['on']) if arp else (v[2],v[1]&240==144)
            counts[n]+=1 if on else -1;assert counts[n]>=0
        assert not any(counts.values()),counts
    traces=[]
    for first in ['arp','drum']:
        for key_sync in [0,1]:
            for trigger in [37,61,121,479]:
                r.reset();r.bind(0,0,1,flags=1|key_sync*4)
                a.uc.mem_write(ctx,bytes(0x650));a.uc.mem_write(routes,bytes(1024));a.write(ctx,routes)
                a.write(0xC0F55850,app);a.write(app+0x2C,r.owner);a.write(0xC1B5720C,shared);a.write(shared,0,0)
                r.h(0xC171D526,0);r.h(0xC0F55A74,0);r.h(0xC0F55A72,0);r.b(0xC1714371,0)
                r.call(0x246BCC,ctx);a.write(ctx,routes)
                r.b(ctx+8,799&255);r.b(ctx+12,0x83);r.b(ctx+10,0x31);r.b(ctx+9,0x30)
                r.b(ctx+0x18,9);r.b(ctx+0x19,0);r.b(0xC1DCD628,0)
                wait=int(first=='arp');r.b(ctx+0x10,wait);r.b(ctx+0x11,1)
                r.b(ctx+0x12,48);r.b(ctx+0x13,72);r.b(ctx+0x14,1);r.b(ctx+0x15,127)
                if first=='arp':
                    for n in [60,64,67]:r.note(0,n,90)
                r.call(0x248324,ctx,128,wait);r.events.clear();drums.clear();snapshots=[]
                stop_arp=first=='arp' and key_sync==1 and trigger==121
                for now in range(1440):
                    r.now=now
                    if now==trigger:
                        if first=='arp':r.call(0x2488F8,ctx,0,60,90)
                        else:
                            for n in [60,64,67]:r.note(0,n,90)
                        snapshots.append(dict(tick=now,arp_counter=r.si(r.engines[0]),arp_wait=r.si(r.engines[0]+8),
                            drum_position=struct.unpack('<h',r.read(0xC1714D48+0x14,2))[0]))
                    if stop_arp and now==610:r.call(0x3C38,r.owner,0,0)
                    r.call(0x2C82C0);r.call(0x2A64,r.owner);r.call(0x248440,ctx)
                    assert r.w(shared+4)==now+1
                r.call(0x247480,ctx);r.call(0x248440,ctx);r.stop();balance(r.events,True);balance(drums)
                arp_on=[e for e in r.events if e['on']];drum_on=[e for e in drums if e[1]&240==144]
                assert arp_on and drum_on,(first,key_sync,trigger)
                second=drum_on if first=='arp' else arp_on
                times=[e[0] if isinstance(e,list) else e['tick'] for e in second]
                assert min(times)>=trigger,(first,trigger,times)
                arp_times=[e['tick'] for e in arp_on];drum_times=[e[0] for e in drum_on]
                if first=='arp':
                    assert arp_times==list(range(0,610 if stop_arp else 1440,120))
                    phase=trigger-1;offset=-phase if phase<60 else 480-phase
                    expected_drums=[trigger,120,300] if offset<=0 else [trigger+offset-1+t for t in [0,120,300]]
                    assert drum_times==expected_drums,(trigger,drum_times,expected_drums)
                    if stop_arp:assert any(t>610 for t in drum_times)
                else:
                    assert drum_times==[0,119,299]
                    if key_sync:expected_arp=[trigger+1]+list(range(trigger+120,1440,120))
                    else:
                        phase=trigger;offset=-phase if phase<60 else 480-phase
                        onset=trigger if offset<=0 else trigger+offset-1
                        second=trigger+120-phase-2 if offset<0 else onset+119
                        expected_arp=[onset]+list(range(second,1440,120))
                        assert snapshots[0]['arp_wait']==offset
                    assert arp_times==expected_arp,(trigger,key_sync,arp_times,expected_arp)
                assert [e['note'] for e in arp_on]==([60,64,67]*(len(arp_on)//3)+[60,64,67][:len(arp_on)%3])
                assert not r.w(ctx+0x628) and not r.read(0xC1714D48+0x32,1)[0]
                traces.append(dict(first=first,key_sync=key_sync,trigger=trigger,stop_arp_at=610 if stop_arp else None,snapshots=snapshots,arp=r.events.copy(),drums=drums.copy()))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={'firmware_arpeggio_sync.py':sha(ROOT/'research/tools/firmware_arpeggio_sync.py')},
        inputs=[dict(path=str(SOURCE.relative_to(ROOT)),sha256=sha(SOURCE))],traces=traces,
        boundaries=['Original central tick 0x2C82C0 increments shared clock and both consumers; original arp and drum managers execute every tick',
                    'Sixteen scenarios cover both start orders, Key Sync states and four live input positions; output order and final balance checked',
                    'Display callback 0x1396CC, LED/cache, critical sections, heap and final output endpoints intercepted',
                    'Synthetic PPAT entry and preset UP drive live peer queries; timer interrupt and OS ordering, active song/recording and audio remain outside this check'])
    (OUT/'music-interlock-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,traces=len(traces),central_ticks=1440*len(traces)),indent=2))
if __name__=='__main__':main()
