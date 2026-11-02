#!/usr/bin/env python3
"""Original preset generators and shared arpeggiator synchronization, offline."""
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
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lfsr(s):return ((s<<1)|((s^(s>>2)^(s>>11)^(s>>15))&1))&65535
def fold_note(n):
    while n>127:n-=12
    return n
def expected_notes(kind,keys,octaves,steps,seed=1):
    positions=[fold_note(n+12*o) for o in range(octaves) for n in keys]
    if kind==0:cycle=positions
    elif kind==1:cycle=positions[::-1]
    elif kind==2:cycle=positions+positions[-2:0:-1]
    elif kind==3:cycle=positions+positions[::-1]
    else:
        result=[]
        for _ in range(steps):seed=lfsr(seed);result.append(positions[seed%len(positions)])
        return result
    return [cycle[i%len(cycle)] for i in range(steps)]

class Rig:
    def __init__(self,f):
        self.a=Arm(f);self.engines=[0x11000000+0x100*i for i in range(3)]
        self.params=[0x11001000+0x100*i for i in range(3)];self.mods=[0x11002000+0x100*i for i in range(3)]
        self.owner=0x11003000;self.context=0x11003100;self.mode=0x11003200;self.master=0x11003300
        self.pattern=0x11004000;self.holder=0x11005000;self.slots=0x11005100;self.array=0x11005200
        self.arena=0x11010000;self.temporary=0x11018000;self.constructing=True;self.busy=False
        self.events=[];self.now=0;self.allocations=[]
        a=self.a;a.write(0xC0A00000,*self.engines);a.write(0xC1743318,self.holder)
        a.write(self.holder,self.slots,1);a.write(self.slots,self.array);a.write(self.array,0xC0471B94,self.pattern,1)
        a.write(0xC199BD3C,self.mode);a.write(self.mode,1)
        a.write(0xC0F5386C,self.master);a.write(self.master+8,1);a.write(0xC0F55730,0)
        a.write(self.owner,self.context);a.write(self.context+0x14,0x11003400);a.write(self.context+0x2C,0x11003500)
        self.b(0xC0A0000C,0);self.b(0xC0A0000D,255);self.b(0xC1DCD62A,0);self.b(0xC1DCC2DC,0);self.h(0xC1714D24,0)
        def allocate(m):
            size=m.get('R0');self.allocations.append(size)
            if self.constructing:
                p=self.arena;self.arena+=(size+15)&~15
            else:
                assert size==20 and not self.busy;self.busy=True;p=self.temporary
            a.uc.mem_write(p,bytes(size));return p
        def release(m):assert m.get('R0')==self.temporary and self.busy;self.busy=False;return 0
        def emit(m):
            self.events.append(dict(tick=self.now,engine=m.get('R1'),note=m.get('R2'),velocity=m.get('R3'),
                                    stamp=self.w(m.get('SP')),on=bool(self.w(m.get('SP')+4))))
            return 0
        a.stubs={0x14E730:allocate,0x2E2F9C:allocate,0x14E760:release,0x2DC184:lambda m:0,
                 0x2DC1BC:lambda m:0,0x271C:lambda m:0,0x275C:lambda m:0,0x3644:emit}
        self.call(0x275770,self.pattern)
        for i,e in enumerate(self.engines):self.call(0x47C4,e,self.context,self.owner,480,stack=(i,))
        self.constructing=False
        self.snapshot=self.read(0x11000000,self.arena-0x11000000)
    def call(self,p,*args,**kw):return self.a.call(p,*args,**kw)
    def read(self,p,n):return bytes(self.a.uc.mem_read(p,n))
    def w(self,p):return struct.unpack('<I',self.read(p,4))[0]
    def si(self,p):return struct.unpack('<i',self.read(p,4))[0]
    def b(self,p,v):self.a.uc.mem_write(p,bytes([v&255]))
    def h(self,p,v):self.a.uc.mem_write(p,struct.pack('<H',v&65535))
    def reset(self):
        assert not self.busy;self.a.uc.mem_write(0x11000000,self.snapshot);self.events=[];self.now=0
        self.h(0xC0A0007C,1);self.b(0xC1DCD62A,0)
    def bind(self,i,kind=0,octaves=1,flags=5,resolution=3,gate=50,velocity=128,custom=False):
        e,p=self.engines[i],self.params[i]
        self.h(p,5 if custom else kind);self.b(p+2,(resolution<<2)|(octaves-1));self.b(p+3,flags)
        self.b(p+4,gate);self.b(p+5,velocity);self.b(p+7,127);self.b(p+9,127);self.b(p+10,1)
        self.call(0x5F0C,e,p,self.mods[i],1,stack=(self.pattern if custom else 0,))
        self.call(0x5EB4,e,1);self.call(0x5174,e)
    def note(self,i,n,v):return self.call(0x6458,self.engines[i],n,v)
    def stop(self):
        for e in self.engines:self.call(0x52B0,e,-1)
        balance=Counter()
        for x in self.events:
            k=(x['engine'],x['note']);balance[k]+=1 if x['on'] else -1;assert balance[k]>=0,(x,balance)
        assert not any(balance.values()),balance
        assert all(self.w(self.w(e+0x6C))==0 for e in self.engines)
    def tick(self,wall):
        self.now=wall;self.call(0x2B00);self.call(0x2A64,self.owner)
    def advance_to(self,t):
        self.now=t;self.a.write(self.engines[0],t);self.b(self.engines[0]+0xC,1);self.call(0x2A64,self.owner)

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('arp-preset-generators',0x7BA0,0x83C0),('arp-shared-sync',0x3794,0x3A34),
                       ('arp-sync-request',0x624C,0x6458),('arp-sync-apply',0x6C64,0x6E94),('arp-random-state',0x58FC,0x5960)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);a=r.a
    for state in range(65536):r.h(0xC0A0007C,state);assert r.call(0x58FC)==lfsr(state)
    seen=set();s=1
    while s not in seen:seen.add(s);s=lfsr(s)
    assert s==1
    presets=[];steps=48
    groups=[(60,), (67,60), (67,60,64), (59,62,65,68,71,74,77), (116,117,118,119,120,121,122,123,124,125,126,127)]
    for kind,octaves,sort,keys in itertools.product(range(5),range(1,5),[0,1],groups):
        r.reset();r.bind(0,kind,octaves,4|sort)
        velocity={n:40+j for j,n in enumerate(keys)}
        for n in keys:r.note(0,n,velocity[n])
        r.h(0xC0A0007C,1)
        for step in range(steps):
            r.advance_to(step*120);r.advance_to(step*120+60)
        r.stop()
        ons=[x for x in r.events if x['on']];ordered=sorted(keys) if sort else list(keys)
        expected=expected_notes(kind,ordered,octaves,steps)
        assert [x['note'] for x in ons]==expected,(kind,octaves,sort,keys,[x['note'] for x in ons],expected)
        assert [x['tick'] for x in ons]==list(range(0,steps*120,120))
        offs=[x for x in r.events if not x['on']]
        assert [x['tick'] for x in offs]==list(range(60,steps*120,120))
        # Velocity follows the untransposed key index, including folded high notes.
        key_ids=expected_notes(kind,list(range(len(keys))),octaves,steps)
        # In this ordinal sequence the octave contribution is a multiple of 12.
        expected_vel=[velocity[ordered[k%12]] for k in key_ids]
        assert [x['velocity'] for x in ons]==expected_vel
        presets.append(dict(kind=kind,octaves=octaves,sort=sort,keys=keys,notes=expected,velocities=expected_vel))
    # The internal preset branch ignores Swing, including nonzero MOD Swing.
    swing_checks=0
    for kind,swing,mod in itertools.product(range(5),[-100,0,100],[-64,0,63]):
        r.reset();r.bind(0,kind);r.b(r.params[0]+6,swing);r.b(r.mods[0]+3,mod)
        for step in range(17):assert r.call(0x6994,r.engines[0],step)==step*120;swing_checks+=1
    # Full clock consumer rather than event-boundary injection for representative sequences.
    continuous=[]
    for kind in range(5):
        r.reset();r.bind(0,kind,2)
        for n in [60,64,67]:r.note(0,n,90)
        r.h(0xC0A0007C,1)
        for t in range(24*120):r.tick(t)
        r.stop();ons=[x for x in r.events if x['on']]
        assert [x['note'] for x in ons]==expected_notes(kind,[60,64,67],2,24)
        continuous.append(dict(kind=kind,events=r.events.copy()))
    # Independently validate the shared-phase query, including existing waits.
    phase_checks=0
    r.reset();r.bind(0)
    for elapsed,pending,disabled,bound in itertools.product(range(960),[0,-1,-59,-60,1,420],[0,1],[0,1]):
        e=r.engines[0];a.write(e,elapsed);a.write(e+8,pending);r.b(e+0xD,disabled);a.write(e+0x74,r.params[0] if bound else 0)
        phase=elapsed%480
        expected=0 if disabled or not bound else pending if pending>0 or -59<=pending<0 else (0 if phase==0 else -phase if phase<60 else 480-phase)
        assert r.call(0x624C,e)==expected,(elapsed,pending,disabled,bound,expected)
        phase_checks+=1
    # Two independent presets share the original assignment manager and sync helpers.
    dual=[]
    for sync,trigger in itertools.product([0,1],[1,37,59,60,61,119,120,121,239,479,480,481]):
        r.reset();r.bind(0,0,1,flags=1);r.bind(1,0,1,flags=1|sync*4)
        for n in [60,64,67]:r.note(0,n,90)
        snapshots=[]
        for t in range(960):
            r.now=t
            if t==trigger:
                for n in [72,76,79]:r.note(1,n,100)
                snapshots.append(dict(when='request',tick=t,engine1=[r.si(r.engines[1]+x) for x in [0,8,0x34,0x38,0x3C,0x44,0x5C]],leader=r.w(r.owner+8)))
            r.tick(t)
            if t in [trigger,trigger+1,trigger+120]:
                snapshots.append(dict(when='advance',tick=t,engine1=[r.si(r.engines[1]+x) for x in [0,8,0x34,0x38,0x3C,0x44,0x5C]],leader=r.w(r.owner+8)))
        r.stop();bnotes=[x for x in r.events if x['on'] and x['engine']==1]
        assert bnotes,(sync,trigger,snapshots)
        if sync:
            # Input occurs just before this tick. Restart leaves current and last
            # time both zero on the first dispatch, so its positive-delta guard
            # emits the first note one tick later; subsequent boundaries are exact.
            expected_ticks=[trigger+1]+list(range(trigger+120,960,120))
            assert [x['tick'] for x in bnotes]==expected_ticks,(sync,trigger,bnotes,snapshots)
        else:
            phase=(trigger-1)%480
            delta=0 if phase==0 else -phase if phase<60 else 480-phase
            assert snapshots[0]['engine1'][1]==delta
            assert snapshots[0]['engine1'][-1]==int(delta<0)
            first=trigger if delta<=0 else trigger+delta-1
            second=first+119 if delta>=0 else trigger+120-phase-2
            expected_ticks=[first]+list(range(second,960,120))
            assert [x['tick'] for x in bnotes]==expected_ticks,(sync,trigger,bnotes,snapshots)
        assert [x['note'] for x in bnotes]==[72,76,79]* (len(bnotes)//3)+[72,76,79][:len(bnotes)%3]
        dual.append(dict(key_sync=sync,trigger=trigger,snapshots=snapshots,events=r.events.copy()))
    # Both RANDOM generators advance one global sequence in manager traversal order.
    r.reset();r.bind(0,4,2);r.bind(1,4,3)
    for i,keys in [(0,[60,64,67]),(1,[48,55])]:
        for n in keys:r.note(i,n,90)
    r.h(0xC0A0007C,1)
    for t in range(2880):r.tick(t)
    r.stop();state=1
    positions={0:[n+12*o for o in range(2) for n in [60,64,67]],1:[n+12*o for o in range(3) for n in [48,55]]}
    for x in r.events:
        if x['on']:
            state=lfsr(state);assert x['note']==positions[x['engine']][state%len(positions[x['engine']])]
    assert struct.unpack('<H',r.read(0xC0A0007C,2))[0]==state
    shared_random=r.events.copy()
    # Fixed-note Trigger All Tones retains trigger state differently under Latch.
    latch_cases=[]
    sequence=[(60,70),(64,90),(60,0),(64,0),(67,100),(67,0),(60,80),(60,0)]
    for fixed,all_tones,latch,sync in itertools.product([0,1],repeat=4):
        r.reset();r.b(r.pattern+24,fixed*16+all_tones*32)
        r.bind(0,flags=1+latch*2+sync*4,custom=True)
        states={};keys=[];trigger=-1;trace=[];active_count=0
        for note,velocity in sequence:
            value=states.get(note,255);held=0<value<128
            if velocity:
                if not held:
                    keys=[k for k in keys if 0<states.get(k,255)<128];keys.append(note);keys.sort()
                    states[note]=velocity;active_count+=1
                elif note!=trigger:states[note]=velocity
                if fixed and all_tones and trigger<0:trigger=note
                r.note(0,note,velocity)
            else:
                keep_trigger=latch and fixed and all_tones and (not sync or active_count<=1)
                if held and not keep_trigger:
                    states[note]=value|128;active_count-=1
                    if not latch:keys.remove(note)
                r.call(0x53E4,r.engines[0],note,64)
            e=r.engines[0];v=r.w(e+0x60);k=r.w(e+0x68)
            assert r.w(v+128)==active_count,(fixed,all_tones,latch,sync,note,velocity,r.w(v+128),active_count)
            assert list(r.read(r.w(k),r.w(k+4)))==keys
            for n,value in states.items():assert r.read(v+n,1)[0]==value
            trace.append(dict(note=note,velocity=velocity,keys=keys.copy(),active_count=active_count,values=states.copy()))
        latch_cases.append(dict(fixed=fixed,all_tones=all_tones,latch=latch,key_sync=sync,trace=trace))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),random=dict(states=65536,nonzero_cycle=len(seen),zero_fixed=lfsr(0)==0),
        presets=presets,preset_steps=len(presets)*steps,swing_checks=swing_checks,continuous=continuous,
        phase_checks=phase_checks,dual=dual,shared_random=shared_random,fixed_latch=latch_cases,
        boundaries=['Original constructors, preset dispatch, PRNG, note output table, key input, shared manager and synchronization helpers execute',
                    'Heap, exception registration, critical sections and final output at 0x3644 are intercepted; transport is stopped using real mode getters',
                    'Broad preset cases inject pending elapsed-time boundaries; five continuous presets and dual traces execute the original per-tick consumer',
                    'Both Key Sync states have independent phase, onset and note expectations under input-before-tick ordering; the interrupt/OS schedule is not modeled',
                    'No physical hardware, MIDI output, voice rendering or sequencer recording executes'])
    (OUT/'arpeggio-sync-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,random_states=65536,random_cycle=len(seen),preset_cases=len(presets),preset_steps=len(presets)*steps,
                         swing_checks=swing_checks,continuous=len(continuous),phase_checks=phase_checks,dual=len(dual),
                         shared_random_events=len(shared_random),fixed_latch_cases=len(latch_cases)),indent=2))
if __name__=='__main__':main()
