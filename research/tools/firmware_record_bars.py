#!/usr/bin/env python3
"""Original cross-bar recording, meter changes and tied-note storage."""
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
    for name,lo,hi in [('record-next-bar',0x25DDC0,0x25DFB8),('record-held-continuation',0x25B914,0x25BC60),('record-take-end',0x25C08C,0x25C108)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f);buf,meta=0x11010000,0x11020000;channel,track=9,2
    ctrl=0xC1716970+32*track;global_ctrl=0xC1716B70;queue=0xC1714708
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def h(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def pb(p,v):a.uc.mem_write(p,bytes([v]))
    a.stubs={0x132660:lambda m:0,0x132670:lambda m:0}
    def reset(codes,grid=1):
        a.uc.mem_write(queue,bytes(0x606));pb(0xC1714D11,1);pb(0xC1714D10,0);pb(0xC1714D20,0)
        a.uc.mem_write(0xC17146B4,bytes(0x3C));ph(0xC17146B4+4,grid)
        pb(0xC171C42E+channel,track);ph(0xC04ADF72,0);ph(0xC171C3BE,0);ph(0xC171C3CC,0)
        ph(0xC171D4EE,1920);ph(0xC171D4F4,0);ph(0xC171BCD4,grid);pb(0xC171BD00,19)
        ph(0xC171D516,1<<track);ph(0xC171BCE8,0);ph(0xC171BCEA,0);a.write(0xC1714700,0,0)
        a.uc.mem_write(0xC1716970,bytes(17*32));a.call(0x25BC60)
        a.uc.mem_write(0xC1719D94,bytes(0x1294));a.uc.mem_write(0xC171BCD8,bytes(8))
        a.uc.mem_write(0xC171BFA0,bytes(2)+bytes(codes)+bytes([19])*(1000-len(codes)))
        a.uc.mem_write(buf,b'\xA5'*4096);a.uc.mem_write(meta,b'\x5A'*4096)
        a.call(0x25B650,ctrl,buf,0,512);a.call(0x25B650,global_ctrl,meta,0,512)
        assert a.call(0x25DDC0,0)==1
    def event(bar,t,status,note=60,velocity=100):
        assert a.call(0x243ED4,0xC17146B4,status|channel,note,velocity,stack=(channel,bar,t))==1
        assert a.call(0x25E944,1)==1
        assert h(queue+0x604)==0
    def length(code):return ((code&15)+1)*[0,480,240,120][code>>4]
    cases=[];replays=[];messages=[];now=(0,0)
    def ingress(m):messages.append([*now,m.get('R1')&255,m.get('R2')&255,m.get('R3')&255]);return 1
    a.stubs[0x2BD7B4]=ingress
    def replay(codes,start,endbar,endtick,velocity,onbar=0):
        nonlocal now
        messages.clear();playq=0xC171BD04;cur=0xC1714408+40*track
        a.uc.mem_write(0xC171C4C8,struct.pack('<HBB',0x7FFD,0,0)*1024)
        a.uc.mem_write(0xC171D4C8,bytes(16))
        for p in [0xC171D4D8,0xC171D4DC,0xC171D514]:ph(p,0)
        ph(0xC171D4DA,65535);ph(0xC171D518,1<<track);ph(0xC171D502,0)
        pb(0xC1716968,0);pb(0xC1DCD62A,1);a.write(0xC17231F4,0)
        pb(0xC17456AC+0x4FE+44*track,channel)
        a.uc.mem_write(playq,bytes(0x298));a.write(playq+0x20C,128)
        a.call(0x241364,cur);a.call(0x241608,cur,buf)
        for bar in range(endbar+1):
            ticks={0,length(codes[bar])-1}
            if bar==onbar:ticks.update([start,max(0,start-1)])
            if bar==endbar:ticks.update([endtick,max(0,endtick-1)])
            for tick in sorted(ticks):
                ph(0xC171D500,length(codes[bar]));now=(bar,tick)
                a.call(0x257850,bar,tick);a.call(0x25F184,playq)
        expected=[[onbar,start,0x90|channel,60,velocity],[endbar,endtick,0x80|channel,60,64]]
        assert messages==expected,(codes,start,endbar,endtick,messages,expected)
        assert a.uc.mem_read(0xC171D4C8+track,1)==b'\0' and w(playq+0x200)==0
        return list(messages)
    for code in range(16,64):
        codes=[code]+[16+(code-16+shift)%48 for shift in [7,19,31]]+[code]
        starts=[1,max(1,length(code)-121)]
        for grid,start,endbar,endtick in itertools.product([1,30,120],sorted(set(starts)),[1,3],[0,1,119]):
            velocity=64 if (code+grid+start)&1 else 127
            reset(codes,grid);event(0,start,0x90,velocity=velocity)
            quantized=(start+grid//2)//grid*grid
            event(endbar,endtick,0x80,velocity=0)
            assert a.uc.mem_read(0xC171BCEC+track,1)==b'\0'
            # The original take-end helper appends type 3 and closes both headers.
            a.call(0x25C08C)
            for bar in range(endbar+1):
                header=buf+16*bar;note=header+8
                assert (a.uc.mem_read(header,1)[0],a.uc.mem_read(header+3,1)[0],h(header+4),h(header+6))==(1,codes[bar],2,bar)
                assert (a.uc.mem_read(note,1)[0],a.uc.mem_read(note+2,1)[0],a.uc.mem_read(note+3,1)[0],h(note+4),h(note+6))==(9,60,velocity,0x7FFF if bar<endbar else endtick,quantized if bar==0 else 0x7FFF)
                mh=meta+8*bar
                assert (a.uc.mem_read(mh,1)[0],a.uc.mem_read(mh+3,1)[0],h(mh+4),h(mh+6))==(1,codes[bar],1,bar)
            used=16*(endbar+1)+8;meta_used=8*(endbar+2)
            assert w(ctrl+4)==buf+used and w(global_ctrl+4)==meta+meta_used
            assert a.uc.mem_read(buf+used-8,1)==b'\x03' and h(buf+used-2)==endbar
            assert a.uc.mem_read(meta+meta_used-8,1)==b'\x03' and h(meta+meta_used-2)==endbar
            assert bytes(a.uc.mem_read(buf+used,4096-used))==b'\xA5'*(4096-used)
            assert bytes(a.uc.mem_read(meta+meta_used,4096-meta_used))==b'\x5A'*(4096-meta_used)
            raw=bytes(a.uc.mem_read(buf,used))
            row=dict(meters=codes,grid=grid,start=start,quantized=quantized,endbar=endbar,endtick=endtick,velocity=velocity,track_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest())
            cases.append(row)
            if start==starts[0] and endbar==3 and endtick==119:
                trace=replay(codes,quantized,endbar,endtick,velocity)
                replays.append(dict(meters=codes,grid=grid,events=trace))
    deferred=[]
    for start,release_same_bar,end in [(s,False,t) for s in [1860,1861,1890,1919] for t in [1,120]]+[(s,True,s+d) for s in [1860,1861,1890] for d in [1,10]]:
        codes=[19]*5;reset(codes,120);event(0,start,0x90)
        active=0xC1716B90+0x300*track
        assert w(ctrl+4)==buf+8 and a.uc.mem_read(active+8,1)[0]==60|0x80
        if release_same_bar:
            event(0,end,0x80,velocity=0)
            assert h(active+8)&0x8000 and h(active+4)==end-start
            ph(0xC171D4F4,1);assert a.call(0x25DDC0,1)==1
            duration=end-start
        else:
            event(1,end,0x80,velocity=0);duration=1920-start+end
        assert a.uc.mem_read(0xC171BCEC+track,1)==b'\0'
        a.call(0x25C08C)
        assert h(buf+4)==1 and h(buf+8+4)==2
        note=buf+16
        assert (a.uc.mem_read(note,1)[0],a.uc.mem_read(note+2,1)[0],a.uc.mem_read(note+3,1)[0],h(note+4),h(note+6))==(9,60,100,duration,0)
        trace=replay(codes,0,1,duration,100,onbar=1)
        deferred.append(dict(start=start,release_same_bar=release_same_bar,release_tick=end,stored_bar=1,stored_tick=0,stored_duration=duration,playback=trace))
    full_queue=[]
    for state_flag,suppress,matched,status in itertools.product(range(2),range(2),range(2),[0x80,0x90]):
        reset([19]*5);event(0,100,0x90)
        ph(0xC171C3BE,state_flag);pb(0xC1714D10,suppress);ph(queue+0x604,120)
        before=bytes(a.uc.mem_read(queue,0x606));note=60 if matched else 61
        assert a.call(0x243ED4,0xC17146B4,status|channel,note,0,stack=(channel,0,200))==1
        cleaned=not suppress and bool(matched) and status==0x80
        assert a.uc.mem_read(0xC171BCEC+track,1)[0]==int(not cleaned)
        assert h(buf+12)==(0 if cleaned and not state_flag else 0x7FFF)
        assert bytes(a.uc.mem_read(queue,0x606))==before
        full_queue.append(dict(state_flag=state_flag,suppress=suppress,matched=matched,status=status,active_removed=cleaned,stored_duration=h(buf+12)))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        cases=cases,replays=replays,deferred=deferred,full_queue=full_queue,
        boundaries=['Original record initialization, intake, queue, consumer, next-bar dispatcher, continuation writers and final note-off execute',
                    'All 48 meter codes appear as initial meter; mixed-meter one- and three-bar held notes use controlled preallocated track and global buffers',
                    'Recorded event type, meter, count, bar index, pitch, velocity, duration and position compare independently; unwritten tail bytes remain intact',
                    'Producer leaves some reserved bytes undefined; raw records are retained and only assigned fields are interpreted',
                    'Recorded tracks replay through original cursor, active-track dispatcher, ties, note-end queue and local MIDI formatter; only local MIDI ingress and critical sections are intercepted',
                    'Original take-end helper 0x25C08C closes last headers and appends type-3 end markers; deferred boundary onsets execute original pending and closed-pending branches',
                    'Full-queue cases execute cleanup 0x25BCB0 against an actually recorded held note, including unmatched releases and zero-velocity Note On',
                    'Take-end helper and a bar advance for already released deferred notes are invoked explicitly; event-pool growth, recording mode transitions, final file save and audio remain outside this check'])
    (OUT/'record-bars-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cross_bar_cases=len(cases),record_playback_traces=len(replays),deferred_cases=len(deferred),full_queue_cases=len(full_queue)),indent=2))
if __name__=='__main__':main()
