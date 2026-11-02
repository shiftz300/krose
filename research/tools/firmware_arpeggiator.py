#!/usr/bin/env python3
"""Offline original ARM checks: arpeggio storage, key logic, timing and playback."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import struct
from collections import Counter
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
SOURCE=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
SOURCE_SHA='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
START=0x507790;SIZE=552;COUNT=1280
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def signed(x):return x-256 if x>=128 else x
def trunc(n,d):return (abs(n)//abs(d))*(-1 if (n<0)!=(d<0) else 1)
def swing_value(base,mod):
    return base-((-mod*(base+100))>>6) if mod<0 else base+(((mod+1)*(100-base))>>6) if mod>0 else base
def time_at(step,resolution,swing,mode,length,custom=True):
    selected=(step%2==1,step%4==2,step%8==4)[mode]
    return step*resolution+(trunc(swing*(resolution//2),50) if custom and selected and step<length else 0)
def tone_selection(mask,nkeys,kind,fixed,all_tones,notes):
    result=[]
    for tone in range(12):
        if not mask&(1<<tone):continue
        if fixed and all_tones:index=tone
        elif tone<nkeys:index=tone
        elif kind==0:index=tone
        elif kind==1:index=nkeys-1 if nkeys else 0
        elif kind==2:index=tone%nkeys if nkeys else 0
        else:
            period=2*nkeys-2
            k=tone%period if period>0 else 0
            index=k if k<nkeys else period-k
        if not(fixed and all_tones) and tone>=nkeys and any(x[0]==index for x in result):continue
        result.append((index,notes[tone]&127 if fixed else -1))
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();assert sha(SOURCE)==SOURCE_SHA
    data=SOURCE.read_bytes();patterns=[data[START+i*SIZE:START+(i+1)*SIZE] for i in range(COUNT)]
    assert all(len(x)==SIZE and all(32<=c<127 for c in x[:24]) for x in patterns)
    OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('arp-storage',0x27575C,0x275B68),('arp-key-input',0x6458,0x67FC),
                       ('arp-key-release',0x52B0,0x5738),('arp-tone-mapping',0x5960,0x5E3C),
                       ('arp-timing',0x6878,0x6BB0),('arp-user-step',0x75C4,0x7BA0),
                       ('arp-dispatch',0x83C0,0x85B4),('arp-clock-consumer',0x2A64,0x2B74)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    catalog=[]
    for i,raw in enumerate(patterns):
        steps=[]
        for j in range(64):
            s=raw[40+8*j:48+8*j]
            steps.append(dict(index=j,pitch=signed(s[0]),gate=s[1],velocity=s[2],flam=signed(s[3]),
                              tones=struct.unpack_from('<H',s,4)[0],extra=s[6:8].hex()))
        catalog.append(dict(index=i,name=raw[:24].decode().rstrip(),source_offset=START+SIZE*i,
                            sha256=hashlib.sha256(raw).hexdigest(),length=raw[25],flags=raw[24],
                            octave_motion=raw[24]&3,arpeggio_type=(raw[24]>>2)&3,
                            fixed=bool(raw[24]&16),all_tones=bool(raw[24]&32),swing_grid=raw[26],
                            fixed_notes=list(raw[28:40]),steps=steps))
    (OUT/'arpeggio-patterns.json').write_text(json.dumps(dict(source=str(SOURCE.relative_to(ROOT)),
        source_sha256=SOURCE_SHA,offset=START,stride=SIZE,patterns=catalog),indent=2)+'\n')
    if not args.verify_arm:return
    a=Arm(f)
    def call(p,*args,**kw):return a.call(p,*args,**kw)
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def si(p):return struct.unpack('<i',a.uc.mem_read(p,4))[0]
    def b(p,v):a.uc.mem_write(p,bytes([v&255]))
    def h(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def read(p,n):return bytes(a.uc.mem_read(p,n))
    engine,params,owner,context,mode,holder,slots,array=0x11000000,0x11001000,0x11002000,0x11002100,0x11002200,0x11003000,0x11003100,0x11003200
    scratch,mod,master,dummy=0x11004020,0x11005000,0x11005100,0x11006000
    factory=0x11040000
    a.uc.mem_write(factory,b''.join(patterns))
    a.write(holder,slots,1);a.write(slots,array);a.write(array,0xC0471B94,factory,COUNT)
    a.write(0xC1743318,holder);a.write(0xC199BD3C,mode);a.write(mode,0xFFFFFFFF)
    a.write(0xC0A00000,engine,dummy,dummy+0x100);a.write(0xC0F5386C,master);a.write(master+8,1)
    a.write(0xC0F55730,0);b(0xC1DCC2DC,0);b(0xC0A0000D,255)
    b(0xC1DCD62A,0);b(0xC0A0000C,0)
    a.write(owner,context);a.write(context+0x2C,0x11005200)
    arena=0x11010000;allocations=[];events=[];now=0;free_calls=[]
    def allocate(m):
        nonlocal arena
        size=m.get('R0');pointer=arena;arena+=(size+15)&~15
        assert arena<0x11040000,(size,hex(arena));a.uc.mem_write(pointer,bytes(size));allocations.append(size);return pointer
    def emit(m):
        events.append(dict(tick=now,engine=m.get('R1'),note=m.get('R2'),velocity=m.get('R3'),
                           stamp=w(m.get('SP')),on=bool(w(m.get('SP')+4))))
        return 0
    a.stubs={0x14E730:allocate,0x2E2F9C:allocate,0x14E760:lambda m:free_calls.append(m.get('R0')) or 0,
             0x2DC184:lambda m:0,0x2DC1BC:lambda m:0,0x271C:lambda m:0,0x275C:lambda m:0,
             0x3644:emit}
    call(0x47C4,engine,context,owner,480,stack=(0,))
    assert allocations==[132,128,16,128,12,320,16,104],allocations
    assert w(engine+0x78)==factory
    resolutions=list(struct.unpack('<8h',read(0xC0A0007E,16)));assert resolutions==[40,60,80,120,160,240,320,480]
    vel,through,keylist,active,tones=[w(engine+x) for x in [0x60,0x64,0x68,0x6C,0x70]]
    assert w(keylist+8)==128 and w(active+4)==20 and w(tones+4)==13
    keybuf=w(keylist);tonebuf=w(tones+12)
    engine_initial=read(engine,0x88)
    # The real bank selector and initializer validate the complete source block.
    for i in range(COUNT):assert call(0x275D0C,holder,i)==factory+SIZE*i
    call(0x275770,scratch);initial=read(scratch,SIZE)
    assert all(raw==initial for raw in patterns[1024:])
    assert sum(raw==initial for raw in patterns)==256
    # All editing checks compare full records and unchanged guard bytes.
    seed=bytes(range(40))+b''.join(bytes([j,(3*j+1)&255,2,3,4,5,6,255-j]) for j in range(64))
    guard=bytes([0xA7]*32);default=bytes([0,50,64,0,0,0,0,0]);edits=Counter()
    def put(raw):a.uc.mem_write(scratch-32,guard+raw+guard)
    def check(raw):
        assert read(scratch,SIZE)==raw
        assert read(scratch-32,32)==guard and read(scratch+SIZE,32)==guard
    for flag in [0,1]:
        put(seed);call(0x275934,scratch,flag)
        expect=seed[:40]+b''.join(default[:4]+struct.pack('<H',0 if flag else 4095)+bytes([0,255-j]) for j in range(64))
        check(expect);edits['initialize_steps']+=1
    for start in range(64):
        for end in range(start,64):
            for dest in sorted({0,63,start,max(0,start-1),min(63,start+1)}):
                put(seed);call(0x275980,scratch,start,end,dest);expect=bytearray(seed)
                length=min(end-start+1,64-dest)
                expect[40+8*dest:40+8*(dest+length)]=seed[40+8*start:40+8*(start+length)]
                check(expect);edits['copy_steps']+=1
    for pos in range(64):
        parts=[seed[40+8*j:48+8*j] for j in range(64)]
        put(seed);call(0x275A1C,scratch,pos);check(seed[:40]+b''.join(parts[:pos]+parts[pos+1:]+[default]));edits['delete_step']+=1
        put(seed);call(0x275A7C,scratch,pos);check(seed[:40]+b''.join(parts[:pos]+[default]+parts[pos:63]));edits['insert_step']+=1
    for length,direction in itertools.product(range(1,65),[0,1]):
        parts=[seed[40+8*j:48+8*j] for j in range(64)];s=parts[:length]
        s=s[-1:]+s[:-1] if direction else s[1:]+s[:1]
        put(seed);call(0x275AE0,scratch,direction,length);check(seed[:40]+b''.join(s+parts[length:]));edits['rotate_steps']+=1
    # Original binding and key input, with other engines inactive and transport stopped.
    def setup(raw=None,index=0,flags=1,resolution=3):
        nonlocal arena
        arena=0x11011000
        a.uc.mem_write(engine,engine_initial)
        a.uc.mem_write(params,bytes(16));h(params,index+5);b(params+2,resolution<<2);b(params+3,flags)
        b(params+4,101);b(params+5,129);b(params+7,127);b(params+8,0);b(params+9,127);b(params+10,1)
        a.uc.mem_write(mod,bytes(4))
        if raw is not None:a.uc.mem_write(scratch,raw)
        call(0x5F0C,engine,params,mod,1,stack=(scratch if raw is not None else 0,))
        call(0x5EB4,engine,1)
        call(0x5174,engine)
        assert read(vel,132)==bytes([255]*128)+bytes(4)
        a.uc.mem_write(through,bytes(128));events.clear()
    key_checks=0;key_examples=[]
    for sort,latch,keyboard,sync in itertools.product([0,1],repeat=4):
        flags=sort|latch*2|sync*4|keyboard*8;setup(flags=flags)
        sequence=[(67,80),(60,96),(64,110),(67,90),(64,0),(60,0),(67,0),(72,100),(72,0)]
        expected_keys=[];held={};expected_vel={}
        for note,velocity in sequence:
            if velocity:
                if note not in held:
                    expected_keys=[n for n in expected_keys if n in held]
                    expected_keys.append(note)
                    if sort:expected_keys.sort()
                held[note]=velocity;expected_vel[note]=velocity
            elif note in held:
                expected_vel[note]=held.pop(note)|128
                if not latch:expected_keys.remove(note)
            returned=call(0x6458,engine,note,velocity)
            assert list(read(keybuf,w(keylist+4)))==expected_keys,(flags,note,velocity,list(read(keybuf,w(keylist+4))),expected_keys)
            assert w(vel+128)==len(held),(flags,note,velocity,w(vel+128),len(held))
            for n,v in expected_vel.items():assert read(vel+n,1)[0]==v
            # Zero-velocity Note On invokes release with release velocity zero,
            # outside the configured velocity zone; explicit release uses its own velocity.
            assert returned==(1 if velocity==0 else keyboard),(flags,note,velocity,returned)
            key_examples.append(dict(flags=flags,note=note,velocity=velocity,keys=expected_keys.copy(),held=len(held),pass_through=returned))
            key_checks+=1
    # All 128 MIDI notes fill the allocated list without crossing its capacity.
    setup(flags=1);before=read(keybuf+128,16)
    for note in reversed(range(128)):call(0x6458,engine,note,64)
    assert read(keybuf,128)==bytes(range(128)) and w(keylist+4)==128 and w(vel+128)==128
    assert read(keybuf+128,16)==before
    for note in range(128):call(0x53E4,engine,note,64)
    assert w(keylist+4)==w(vel+128)==0
    zone_checks=0
    for enabled,keyboard,note,velocity in itertools.product([0,1],[0,1],[47,48,60,72,73],[0,1,63,64,96,97,127]):
        setup(flags=1+8*keyboard);a.write(engine+0x24,enabled)
        b(params+7,72);b(params+8,48);b(params+9,96);b(params+10,64)
        in_zone=48<=note<=72 and 64<=velocity<=96
        expected=int(not(enabled and in_zone and not keyboard))
        assert call(0x6458,engine,note,velocity)==expected
        assert w(vel+128)==int(enabled and in_zone)
        if velocity:
            assert call(0x53E4,engine,note,64)==expected
            assert w(vel+128)==0 and w(keylist+4)==0
        zone_checks+=1
    # Tone mapping uses real step masks, including deduplication after fill/roundtrip.
    mapping_cases=0;mapping_examples=[]
    setup()
    for nkeys,kind,fixed,all_tones,mask in itertools.product([1,2,3,7,12],[0,1,2,3],[0,1],[0,1],[0,1,7,0x249,0xFFF]):
        raw=bytearray(initial);raw[24]=kind*4+fixed*16+all_tones*32;raw[28:40]=bytes(range(36,48));struct.pack_into('<H',raw,44,mask)
        a.uc.mem_write(scratch,bytes(raw));a.write(engine+0x78,scratch);a.write(keylist+4,nkeys);a.write(vel+128,nkeys)
        call(0x46EC,tones);count=call(0x5A14,engine,0,scratch)
        got=[(struct.unpack('<h',read(tonebuf+8*j,2))[0],signed(read(tonebuf+8*j+2,1)[0])) for j in range(count)]
        expected=tone_selection(mask,nkeys,kind,fixed,all_tones,raw[28:40]);assert got==expected,(nkeys,kind,fixed,all_tones,mask,got,expected)
        assert w(tones+8)==count and read(tonebuf+8*count,2)==b'\xff\xff'
        mapping_cases+=1
        if nkeys==3 and mask==0xFFF and not fixed and not all_tones:mapping_examples.append(dict(kind=kind,tones=got))
    factory_steps=0
    for i,raw in enumerate(patterns):
        a.write(engine+0x78,factory+SIZE*i);a.write(keylist+4,3);a.write(vel+128,3)
        for step in range(raw[25]):
            call(0x46EC,tones);count=call(0x5A14,engine,step,factory+SIZE*i)
            mask=struct.unpack_from('<H',raw,44+8*step)[0]
            expected=tone_selection(mask,3,(raw[24]>>2)&3,bool(raw[24]&16),bool(raw[24]&32),raw[28:40])
            got=[(struct.unpack('<h',read(tonebuf+8*j,2))[0],signed(read(tonebuf+8*j+2,1)[0])) for j in range(count)]
            assert got==expected,(i,step,got,expected);factory_steps+=1
    # Real swing helper + runtime length + timing, signed rounding independently modeled.
    timing_cases=0;timing_examples=[];length_checks=0
    setup(raw=initial)
    for length in [0,1,8,48,64,65,255]:
        b(scratch+25,length);assert call(0x691C,engine)==max(1,min(64,length));length_checks+=1
    b(scratch+25,8)
    for res,grid,base,m in itertools.product(resolutions,[0,1,2],[-100,-25,0,25,100],[-64,-1,0,1,63]):
        a.write(engine+0x4C,res);b(scratch+26,grid);b(params+6,base);b(mod+3,m)
        swing=swing_value(base,m);assert call(0x68B0,engine)==swing
        for step in range(9):
            got=call(0x6994,engine,step);expected=time_at(step,res,swing,grid,8)
            assert got==expected,(res,grid,base,m,step,got,expected);timing_cases+=1
        if res==120 and m==0 and base==25:
            timing_examples.append(dict(grid=grid,times=[call(0x6994,engine,j) for j in range(9)]))
    # Continuous user-pattern playback: actual input, dispatch, step decoding,
    # note table and output adapter. Capture only the final assignment boundary.
    def run(raw=None,index=0,notes=(60,64,67),cycles=2,flags=1):
        nonlocal now
        setup(raw=raw,index=index,flags=flags);now=0
        for n in notes:call(0x6458,engine,n,90)
        length=call(0x691C,engine);limit=cycles*length*120
        states=[]
        for now in range(limit+1):
            call(0x2B00);assert si(engine)==now
            call(0x2A64,owner)
            if now%120==0:states.append(dict(tick=now,step=w(engine+0x44),active=w(active)))
        call(0x52B0,engine,-1)
        balance=Counter()
        for event in events:
            assert 0<=event['note']<=127 and 1<=event['velocity']<=127
            balance[event['note']]+=1 if event['on'] else -1
            assert balance[event['note']]>=0,(index,event)
        assert not any(balance.values()),(index,balance)
        assert w(active)==0
        return dict(index=index,name=patterns[index][:24].decode().rstrip() if raw is None else 'synthetic',
                    length=length,ticks=limit,events=events.copy(),states=states)
    raw=bytearray(initial);raw[25]=4
    for j in range(4):struct.pack_into('<H',raw,44+8*j,1<<j)
    playback=[]
    for kind in range(4):
        raw[24]=kind<<2;trace=run(bytes(raw),cycles=1)
        on=[e['note'] for e in trace['events'] if e['on'] and e['tick']<480]
        expected=[[60,64,67],[60,64,67,67],[60,64,67,60],[60,64,67,64]][kind]
        assert on==expected,(kind,on,expected)
        assert all(e['tick']%120==0 for e in trace['events'] if e['on']),trace
        trace['kind']=kind;playback.append(trace)
    # Representative factory patterns include strums, fixed-note drums and a rest slot.
    for index in [0,16,100,914,915,916,1023,1024]:playback.append(run(index=index,cycles=1))
    # Independent chord-strum expectations exercise the original timed substeps.
    strums=[]
    for flam,pitch,velocity,fixed in itertools.product([-50,0,50],[-48,0,48],[80,128],[0,1]):
        raw=bytearray(initial);raw[24]=0x30 if fixed else 0;raw[25]=2;raw[28:40]=bytes(range(36,48))
        for step in range(2):
            raw[40+8*step:48+8*step]=struct.pack('<bBBbHBB',pitch,50,velocity,flam,7,0,0)
        trace=run(bytes(raw),cycles=1,notes=(60,64,67));ons=[e for e in trace['events'] if e['on'] and e['tick']<240]
        base=[36,37,38] if fixed else [60,64,67]
        pitches=[]
        for n in base:
            n+=pitch
            while n<0:n+=12
            while n>127:n-=12
            pitches.append(n)
        if flam<0:pitches.reverse()
        expected=[(step*120+j*(20 if flam else 0),note,90 if velocity==128 else velocity) for step in range(2) for j,note in enumerate(pitches)]
        got=[(e['tick'],e['note'],e['velocity']) for e in ons];assert got==expected,(flam,pitch,velocity,fixed,got,expected)
        offs=[e for e in trace['events'] if not e['on'] and e['tick']<240]
        expected_off=[(step*120+60+j*(10 if flam else 0),note) for step in range(2) for j,note in enumerate(pitches)]
        assert [(e['tick'],e['note']) for e in offs]==expected_off,(flam,pitch,fixed,offs,expected_off)
        strums.append(dict(flam=flam,pitch=pitch,velocity=velocity,fixed=fixed,events=trace['events']))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
        inputs=[dict(path=str(SOURCE.relative_to(ROOT)),sha256=SOURCE_SHA)],
        catalog=dict(offset=START,stride=SIZE,count=COUNT,initialized=256,named=1024,
                     length_histogram=dict(Counter(x[25] for x in patterns)),
                     sha256=sha(OUT/'arpeggio-patterns.json')),
        constructor=dict(allocations=allocations[:8],resolutions=resolutions,key_capacity=128,active_capacity=20,tone_capacity=13),
        editing=dict(edits),key_input=dict(cases=key_checks,zone_cases=zone_checks,full_keyboard_operations=256,traces=key_examples),
        tone_mapping=dict(synthetic_cases=mapping_cases,factory_steps=factory_steps,examples=mapping_examples),
        timing=dict(cases=timing_cases,length_cases=length_checks,examples=timing_examples),playback=playback,strums=strums,
        tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        boundaries=['Original constructor, bank lookup, storage edits, note input/release, tone mapping, timing, user step decoder, output note table, three-engine clock consumer and pending dispatcher execute',
                    'Heap allocation/free, exception registration and critical sections are intercepted; internal clock mode is read by original getter, other engines and transport are inactive',
                    'Final assignment output at 0x3644 is captured; MIDI routing, voice synthesis and TG audio do not execute',
                    'Factory mapping covers every declared step of 1280 patterns; continuous playback covers eight factory examples and four independently checked synthetic types',
                    'Dual arpeggiator synchronization, fixed-note latch edge cases, complete preset generators and sequencer recording remain for further checks'])
    (OUT/'arpeggiator-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,editing=dict(edits),key_input=key_checks,tone_mapping=mapping_cases,
                         factory_steps=factory_steps,timing=timing_cases,playback_patterns=len(playback),
                         strum_cases=len(strums),output_events=sum(len(x['events']) for x in playback+strums)),indent=2))
if __name__=='__main__':main()
