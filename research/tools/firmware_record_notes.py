#!/usr/bin/env python3
"""Original recording consumer, quantization and eight-byte note creation."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();a=Arm(f);queue=0xC1714708;buffer=0x11010000;channel=9;track=2
    for name,lo,hi in [('record-consumer',0x25E944,0x25EFAC),('record-note-pair',0x25C428,0x25C894),('record-event-append',0x25B650,0x25B8B0)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    ctrl=0xC1716970+32*track;active=0xC1716B90+0x300*track
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def h(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def pb(p,v):a.uc.mem_write(p,bytes([v]))
    a.stubs={0x132660:lambda m:0,0x132670:lambda m:0}
    active_template=struct.pack('<IHHBBH',0,0x7FFD,0,0,0,0)*(16*64)
    def reset(grid=1):
        a.uc.mem_write(queue,bytes(0x606));pb(0xC1714D11,1);pb(0xC1714D10,0);pb(0xC1714D20,0)
        a.write(0xC17146B4+0x14,0,0);ph(0xC17146B4+4,grid)
        pb(0xC171C42E+channel,track);ph(0xC04ADF72,0);ph(0xC171C3BE,0);ph(0xC171C3CC,0)
        ph(0xC171D4EE,1920);ph(0xC171D4F4,0);ph(0xC171BCD4,grid)
        ph(0xC171D516,1<<track)
        ph(0xC171BCE8,0);ph(0xC171BCEA,0);a.write(0xC1714700,0,0)
        a.uc.mem_write(0xC1716970,bytes(16*32));a.uc.mem_write(0xC171BCEC,bytes(16))
        a.uc.mem_write(0xC1716B90,active_template)
        a.uc.mem_write(buffer,b'\xA5'*4096);a.uc.mem_write(buffer,struct.pack('<BBBBHH',1,0,0,0,1,0))
        a.write(ctrl,buffer,buffer+8,511,buffer);ph(ctrl+0x10,1)
        a.uc.mem_write(0xC171BCD8,bytes(8))
    def event(t,status,note=60,velocity=100):
        assert a.call(0x243ED4,0xC17146B4,status|channel,note,velocity,stack=(channel,0,t))==1
        assert a.call(0x25E944,1)==1
        assert h(queue+0x604)==0
    cases=[]
    for grid,start,duration,velocity in itertools.product([1,30,40,60,80,120,160,240,320,480],
            [0,1,14,15,19,20,29,30,31,59,60,61,119,120,121,479,480,481,1400,1410,1411,1439],
            [0,1,59,60,121,480,509],[1,64,127]):
        if start+duration>=1920:continue
        reset(grid);event(start,0x90,velocity=velocity)
        quantized=((start+grid//2)//grid)*grid
        expected=struct.pack('<BBBBHH',9,0,60,velocity,0x7FFF,quantized)
        assert bytes(a.uc.mem_read(buffer+8,8))==expected,(grid,start,duration,velocity)
        assert a.uc.mem_read(0xC171BCEC+track,1)[0]==1 and h(active+4)==start
        assert w(active)==buffer+8
        # Alternate real Note Off and zero-velocity Note On consumers.
        off_status=0x80 if velocity!=64 else 0x90
        event(start+duration,off_status,velocity=0)
        stored=min(duration,1920-quantized)
        expected=struct.pack('<BBBBHH',9,0,60,velocity,stored,quantized)
        expected_buffer=struct.pack('<BBBBHH',1,0,0,0,1,0)+expected+b'\xA5'*4080
        assert bytes(a.uc.mem_read(buffer,4096))==expected_buffer,(grid,start,duration,velocity,bytes(a.uc.mem_read(buffer+8,8)).hex(),expected.hex())
        assert w(ctrl+4)==buffer+16 and h(ctrl+0x10)==2 and w(ctrl+8)==510
        assert a.uc.mem_read(0xC171BCEC+track,1)[0]==0 and h(active+4)==0x7FFD
        cases.append(dict(grid=grid,start=start,quantized=quantized,duration=duration,stored_duration=stored,velocity=velocity,off_status=off_status))

    # Duplicate-pitch matching is FIFO in the active table.
    reset(30);event(3,0x90,velocity=100);event(31,0x90,velocity=90)
    event(63,0x80,velocity=0)
    assert bytes(a.uc.mem_read(buffer+8,16))==struct.pack('<BBBBHH',9,0,60,100,60,0)+struct.pack('<BBBBHH',9,0,60,90,0x7FFF,30)
    event(90,0x80,velocity=0)
    assert bytes(a.uc.mem_read(buffer+16,8))==struct.pack('<BBBBHH',9,0,60,90,59,30)
    duplicate=bytes(a.uc.mem_read(buffer+8,16)).hex()
    # A mismatched release leaves the active note untouched.
    reset();event(3,0x90);event(31,0x80,note=61,velocity=0)
    assert h(buffer+8+4)==0x7FFF and a.uc.mem_read(0xC171BCEC+track,1)[0]==1

    # Capacity 64: a 65th onset does not append a note or evict an older one.
    reset()
    for i in range(65):event(i,0x90)
    assert w(ctrl+4)==buffer+8+64*8 and a.uc.mem_read(0xC171BCEC+track,1)[0]==64
    for i in range(64):event(100+i,0x80,velocity=0)
    expected=b''.join(struct.pack('<BBBBHH',9,0,60,100,100,i) for i in range(64))
    assert bytes(a.uc.mem_read(buffer+8,512))==expected
    assert a.uc.mem_read(0xC171BCEC+track,1)[0]==0
    assert bytes(a.uc.mem_read(buffer+520,3576))==b'\xA5'*3576
    # Original bar append closes the previous header's event count.
    marker=0x11003000;a.uc.mem_write(marker,struct.pack('<BBBBHH',1,0,0,0,1,1))
    assert a.call(0x25B6CC,ctrl,marker)==1
    assert h(buffer+4)==65 and w(ctrl+4)==buffer+528 and h(ctrl+0x10)==1
    assert bytes(a.uc.mem_read(buffer+520,8))==struct.pack('<BBBBHH',1,0,0,0,1,1)

    # Finishing a take uses the stored, quantized onset for remaining durations.
    finish=[]
    for boundary in [0,60,120,121,300,1920]:
        reset(30);event(123,0x90)
        a.call(0x25BD58,boundary)
        duration=max(0,min(boundary,1920)-120)
        assert h(buffer+12)==duration and a.uc.mem_read(0xC171BCEC+track,1)[0]==0
        assert h(active+4)==0x7FFD
        finish.append(dict(start=123,quantized=120,boundary=boundary,stored_duration=duration))

    # Join the drum source to the real FIFO and the real song consumer in one
    # execution, retaining only the separate playback handoff as a boundary.
    reset();descriptor=0x11004000;pending=[]
    a.stubs[0x25F1B8]=lambda m:pending.append(list(a.uc.mem_read(m.get('R1')+1,3))) or 1
    a.write(0xC1716398,3);pb(0xC1714371,1);pb(0xC1DCD62A,0)
    a.uc.mem_write(descriptor,bytes([0,3,0x30,0]))
    drum_trace=[(0,0x99,36,100),(59,0x89,36,0),(119,0x99,38,90),(239,0x89,38,0)]
    for tick,status,note,velocity in drum_trace:
        ph(0xC17163A8,0);ph(0xC17163AA,tick)
        a.call(0x244A60,descriptor,status,note,velocity)
    assert h(queue+0x604)==4 and w(ctrl+4)==buffer+8
    assert a.call(0x25E944,1)==1
    drum_notes=struct.pack('<BBBBHH',9,0,36,100,59,0)+struct.pack('<BBBBHH',9,0,38,90,120,119)
    assert bytes(a.uc.mem_read(buffer,4096))==struct.pack('<BBBBHH',1,0,0,0,1,0)+drum_notes+b'\xA5'*4072
    assert pending==[[s,n,v] for t,s,n,v in drum_trace]
    assert h(queue+0x604)==0 and a.uc.mem_read(0xC171BCEC+track,1)[0]==0
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        cases=cases,duplicate_notes_hex=duplicate,capacity=dict(accepted=64,ignored=1,release_events=64,bar_header_count=65),finish=finish,mismatched_release_checked=True,drum_song_notes_hex=drum_notes.hex(),drum_source_events=drum_trace,
        boundaries=['Original intake 0x243ED4, FIFO, consumer 0x25E944, quantization, note constructors/pairing, event append and duration writes execute',
                    'Full private 4096-byte track buffer compared outside all expected note records; no allocator or note writer is intercepted',
                    'Critical section enter/leave are intercepted; integrated drum source additionally intercepts playback handoff 0x25F1B8; valid preallocated one-bar track and state are controlled fixtures',
                    'Explicit bar append and take-finish helpers are checked separately from consumer dispatch',
                    'Cross-bar held notes, growing/replacing event pools, recording mode transitions, files and audio remain outside this check'])
    (OUT/'record-notes-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,note_cases=len(cases),capacity=result['capacity'],finish_cases=len(finish)),indent=2))
if __name__=='__main__':main()
