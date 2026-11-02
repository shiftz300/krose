#!/usr/bin/env python3
"""Real factory voices: native batched refresh vs explicit kernel scheduling."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_factory_voice_chain import Rig as FactoryRig
from firmware_voice_lfo import h,sh,w,s32,sha,PRELOAD,OUT
from program_firmware import Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

class Rig(FactoryRig):
    def __init__(self,f):
        self.capture=False;self.events=[];self.commits=[];self.current_commit=None;self.waits=[];self.active_mask=0;self.score=0x1234
        super().__init__(f);self.coefficients=list(struct.unpack_from('<25H',f.data,0x3A8D40))
        self.a.stubs[0x12F1D0]=lambda a:self.waits.append(a.get('R1')) or 0
    def bus_read(self,a):
        offset=a.get('R0')-self.tg;assert 0<=offset<0x4000,(hex(a.get('R0')),hex(a.get('LR')));self.reads.append(offset)
        if offset in [0x240,0x244,0x248,0x24C]:return (self.active_mask>>((offset-0x240)*8))&0xFFFFFFFF
        if offset==0x428:return self.score
        if offset==0x42C:return 16384 if self.capture else 0
        return 0
    def bus_write(self,a):
        if self.capture and self.current_commit is not None:self.current_commit['writes'].append([a.get('R0')-self.tg,a.get('R1')])
        return super().bus_write(a)
    def observe(self,uc,address,size,user):
        super().observe(uc,address,size,user)
        if not self.capture:return
        off=address-0xC0000000;a=self.a
        labels={0x1F8140:'advance',0x1F969C:'poll',0x1FBD98:'wave',0x1FFDA0:'pitch_refresh',0x1FBD28:'filter_refresh',
                0x1FA9C4:'amp_refresh',0x20119C:'mixer',0x1FF38C:'pitch_target',0x1FB4B0:'filter_target',0x1F9DD4:'amp_target',
                0x1FEDFC:'pan_target',0x1F9828:'commit'}
        if off in labels:self.events.append([labels[off],a.get('R0')])
        if off==0x1F9828:
            v=a.get('R0');b=bytes(a.uc.mem_read(v,588));self.current_commit=dict(voice=(v-self.voices)//588,state=b.hex(),writes=[])
            self.commits.append(self.current_commit)
    def setup(self,record,osc,note,velocity,batch,cursor=0,pedal=False,extra_variant=0):
        self.capture=False;self.active_mask=0;self.a.write(self.clock,0,123);self.prepare(record,osc)
        self.a.call(0x1FEDE4)
        self.a.write(self.osc+0x490,self.osc+0x490,self.osc+0x490,0)
        if pedal:self.pedal(127,request=False)
        self.a.uc.mem_write(0x111E0000,bytes(0x10000));self.a.uc.mem_write(0xC165D9F8,bytes(64))
        initial=self.note(note,velocity)
        if initial['returned_chain']:
            self.a.call(0x1F61F8,self.osc,self.members+12*initial['returned_chain'][0])
        self.a.call(0x1FEDB8,0xC165DA38)
        # Two auxiliary control blocks are not bound by the inspected startup
        # path. Supply explicit private parameters, retain original computation,
        # and test their influence on submitted audio controls separately.
        self.extra_parameters=0x110B0000
        self.a.uc.mem_write(self.extra_parameters,bytes([127,0,0,0,14,99,0,0,14,(-99)&255,0,0]) if extra_variant else bytes(12))
        for i in range(8):
            self.a.write(self.voices+588*i+0x1CC,self.extra_parameters)
            self.a.write(self.voices+588*i+0x1D8,self.extra_parameters+4)
        self.a.write(self.manager+0xE4,8);self.put8(self.manager+0xE8,batch);self.put8(self.manager+0xE1,cursor);self.put8(self.manager+0xE9,cursor)
        self.active_mask=sum(1<<v['tg_slot'] for v in initial['voices']);self.clear();self.capture=True
        return initial
    def clear(self):
        self.events.clear();self.commits.clear();self.current_commit=None;self.writes.clear();self.reads.clear();self.waits.clear()
    def pedal(self,value,request=True):
        self.put8(self.part+0x19,4);self.put8(self.controls+64,value);self.a.write(self.context+0x3C,1)
        if request:self.a.call(0x1F5E44 if value>=80 else 0x1F5E98,self.osc)
    def event(self,update,pedal):
        self.current_commit=None
        if update==32:self.a.call(0x1F60A4,self.osc,0x80+(self.note_number<<8)+(64<<16))
        if update==64 and pedal:self.pedal(0)
        if update==80:
            self.a.write(self.context+0x34,(1<<7)|(1<<11));self.put8(self.controls+7,91);self.put8(self.controls+11,73)
    def explicit_advance(self,elapsed):
        a=self.a;m=self.manager
        if bytes(a.uc.mem_read(m+0xE0,1))[0]:return
        a.call(0x1FCECC,m+0xCC,elapsed)
        first=bytes(a.uc.mem_read(m+0xE1,1))[0];batch=bytes(a.uc.mem_read(m+0xE8,1))[0];n=self.word(m+0xE4);last=min(first+batch,n)
        for i in range(first,last):a.call(0x1F8140,self.voices+588*i)
        self.put8(m+0xE1,0 if last>=n else last)
    def explicit_poll(self):
        a=self.a;m=self.manager;cursor=first=bytes(a.uc.mem_read(m+0xE9,1))[0];budget=bytes(a.uc.mem_read(m+0xE8,1))[0]
        count=self.word(m+0xE4);collected=[]
        while True:
            v=self.voices+588*cursor;ret=a.call(0x1F969C,v)&255;self.put8(m+0xE0,1)
            if ret&1:
                a.call(0x1FCF6C,m+0xCC,v);a.call(0x1FC600,m+12,v);a.call(0x1FC738,m+12,v)
            if ret&2:budget-=1
            if ret&4:
                a.call(0x1FCF6C,m+0xCC,v)
                if self.word(v+0x218)==1 and self.word(v+0x230):a.call(0x1FCF6C,m+0xCC,self.word(v+0x230))
            cursor=(cursor+1)%count;self.put8(m+0xE0,0)
            if ret&8:
                a.write(0xC165D9F8+4*len(collected),v);collected.append((v,int(bool(ret&1))))
            if cursor==first or budget<=0:break
        self.put8(m+0xE9,cursor);waves=[]
        for v,_ in collected:
            second=a.call(0x1FBD98,v+0x58);first=a.call(0x1FBD98,v+0x2C);waves.append((first,second))
        for function,offset in [(0x1FFDA0,0xBC),(0x1FBD28,0x120),(0x1FA9C4,0x15C)]:
            for v,_ in collected:a.call(function,v+offset,v)
        for offset in [0x1F0,0x1F8]:
            for v,_ in collected:a.call(0x20119C,v+offset,v,0)
        for (v,_),(first,second) in zip(collected,waves):a.call(0x1FF38C,v+0x84,v,self.word(v+0xC),first,stack=(second,))
        for (v,_),(first,second) in zip(collected,waves):a.call(0x1FB4B0,v+0xEC,v,first,second)
        for v,_ in collected:
            parameter=self.word(v+0x1CC);self.a.uc.mem_write(v+0x1D4,bytes(a.uc.mem_read(v+0x1D6,2)))
            result=a.call(0x200F04,bytes(a.uc.mem_read(parameter,1))[0]&127);a.uc.mem_write(v+0x1D6,struct.pack('<H',result&65535))
        for v,_ in collected:a.call(0x20010C,v+0x1D8,v)
        for (v,_),(first,second) in zip(collected,waves):a.call(0x1F9DD4,v+0x150,v,first,second)
        for v,finished in collected:a.call(0x1FEDFC,v+0x1C0,v,finished)
        for v,_ in collected:a.call(0x1F9828,v)
        a.call(0x1FE398,m)
    def verify_commits(self):
        result=[]
        for row in self.commits:
            b=bytes.fromhex(row['state']);flags=b[0x13];expected={}
            old,target=h(b,0x152),h(b,0x150);amp_time=1 if flags&8 else 24
            if target!=old:
                p=s32(self.coefficients[min(amp_time,24)]*(target-old))>>16;step=p+(1 if p>=0 else -1)
                expected[0x418]=((step&65535)<<16)|target
            else:assert all(off!=0x418 for off,_ in row['writes'])
            pitch_time=0 if flags&1 else w(b,0xD8) if flags&16 else 24
            previous,current=w(b,0x98),w(b,0x9C);factor=self.coefficients[min(pitch_time,24)]>>4
            p=s32(factor*s32(current-previous))>>12;step=p+(1 if p>=0 else -1)
            expected.update({0x214:step&0xFFFFFFFF,0x218:current})
            route=sb(b,0x116);a_mode=sb(b,0xFC);b_mode=sb(b,0x110);param=self.word(self.voices+588*row['voice']+0x224)
            p=bytes(self.a.uc.mem_read(param,380));a_flag=p[0xA0]>>7;b_flag=p[0xC4]>>7
            mode=(0 if a_flag else 1) if route==0 else (2 if a_flag else 3) if route==1 else (6 if a_flag else 7) if route==2 else (0 if a_flag else 3)
            if route in [1,2] and b_flag:mode&=1 if route==1 else 5
            expected.update({0x380:mode,0x398:a_mode&0xFFFFFFFF,0x3B8:(a_mode if route==3 else b_mode)&0xFFFFFFFF})
            filter_times=[]
            for bank in range(2):
                time=1 if flags&(1<<(bank+1)) else w(b,0x13C) if flags&(1<<(bank+5)) else 24
                filter_times.append(time);factor=self.coefficients[min(time,24)];at=0xEC+20*bank
                targets=[h(b,at+2*i) for i in range(4)];previous=[h(b,at+8+2*i) for i in range(4)]
                steps=[]
                for now,old in zip(targets,previous):
                    product=s32(factor*(now-old))>>16;steps.append(product+(1 if product>=0 else -1))
                base=0x20*bank
                expected.update({0x38C+base:(steps[1]<<8)&0xFFFFFFFF,0x388+base:targets[1]<<8,
                    0x394+base:(steps[2]<<8)&0xFFFFFFFF,0x390+base:targets[2]<<8,
                    0x39C+base:((steps[0]&65535)<<16)|targets[0],0x3A0+base:((steps[3]&65535)<<16)|targets[3]})
            actual={off:value for off,value in row['writes'] if off in expected}
            assert actual==expected,(row['voice'],{hex(k):(actual.get(k),v) for k,v in expected.items() if actual.get(k)!=v})
            assert self.half(self.voices+588*row['voice']+0x23C)==self.score
            result.append(dict(voice=row['voice'],flags=flags,amp=target,amp_previous=h(b,0x152),pitch=current,
                               amp_time=amp_time,pitch_time=pitch_time,filter_times=filter_times,registers={hex(k):v for k,v in expected.items()}))
        return result
    def snapshot(self):
        return dict(cursor_advance=bytes(self.a.uc.mem_read(self.manager+0xE1,1))[0],cursor_poll=bytes(self.a.uc.mem_read(self.manager+0xE9,1))[0],
                    available=self.word(self.manager+0x48),voices=[dict(slot=i,flags=self.half(self.voices+588*i+0x10),
                    amp=self.half(self.voices+588*i+0x150),eg=[sh(bytes(self.a.uc.mem_read(self.voices+588*i+off,2)),0) for off in [0xBC,0x120,0x15C]],
                    stages=[bytes(self.a.uc.mem_read(self.voices+588*i+off+6,1))[0] for off in [0xBC,0x120,0x15C]]) for i in range(8)])

def sb(b,o):return struct.unpack_from('<b',b,o)[0]
def compare(a,b):
    for address,size in [(a.manager,0x100),(a.voices,8*588),(a.nodes,8*12),(a.members,8*12),(a.waitnodes,8*12),
                         (a.osc,0x500),(a.context,0x200),(a.channel,0x200),(0xC165D9F8,64),(0xC1B5848C,4)]:
        left=bytes(a.a.uc.mem_read(address,size));right=bytes(b.a.uc.mem_read(address,size))
        assert left==right,(hex(address),[(i,x,y) for i,(x,y) in enumerate(zip(left,right)) if x!=y][:16])
    assert a.writes==b.writes and a.reads==b.reads and a.waits==b.waits
    assert a.events==b.events,(a.events,b.events)
    assert a.commits==b.commits

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('voice-refresh-batch',0x1FE404,0x1FE808),('voice-refresh-TG',0x1F9828,0x1F9A5C),
                       ('voice-refresh-pitch-step',0x12CE64,0x12CEB8),('voice-refresh-filter-steps',0x12D088,0x12D238)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    a=Rig(f);b=Rig(f);raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory=json.loads((OUT/'factory-voice-chain-check.json').read_text());assert factory['passed'] and not factory['smoke_only']
    choices={(0,0),(0,1),(11,0),(45,1),(74,0)};wave_reps={};route_reps={};delay_reps={}
    for row in factory['factory']:
        if not row['voices']:continue
        index=(ord(row['program'][0])-65)*128+int(row['program'][1:]);osc=row['oscillator']-1;off=0x1EF220+2140*index
        record=raw[off:off+2140];block=record[0x564+380*osc:0x564+380*(osc+1)]
        for at in [0x30,0x4C]:wave_reps.setdefault(block[at]&63,(index,osc))
        route_reps.setdefault(block[0x88]&3,(index,osc))
        delay=row['voices'][0]['delay'];delay_reps.setdefault('keyoff' if delay<0 else 'wait' if delay else 'immediate',(index,osc))
    choices.update(wave_reps.values());choices.update(route_reps.values());choices.update(delay_reps.values())
    if args.smoke:choices={(11,0)}
    traces=[];busy_cases=[];auxiliary_influence=[];controlled_commits=[]
    for index,osc in sorted(choices):
        offset=0x1EF220+2140*index;record=raw[offset:offset+2140];block=record[0x564+380*osc:0x564+380*(osc+1)]
        low,high=sorted(record[0x518+2*osc:0x51A+2*osc]);vl,vh=sorted(block[0x2D:0x2F]);note=(low+high)//2;velocity=max(1,(vl+vh)//2)
        if index==11:velocity=105
        for batch in ([3] if args.smoke else [1,3,8]):
            cursor=7 if batch==3 else 0;pedal=bool(index==0 or block[0x2C]&128)
            initial=a.setup(record,osc,note,velocity,batch,cursor,pedal);b.setup(record,osc,note,velocity,batch,cursor,pedal);compare(a,b)
            steps=[]
            for update in range(16 if args.smoke else 128):
                a.clear();b.clear()
                for rig in [a,b]:rig.event(update,pedal);rig.a.write(rig.clock+4,123+20*update)
                elapsed=[0,1,3,20][update%4];a.a.call(0x1FD3CC,a.manager,elapsed);b.explicit_advance(elapsed);compare(a,b)
                a.clear();b.clear();a.a.call(0x1FE404,a.manager);b.explicit_poll();compare(a,b)
                commits=a.verify_commits();steps.append(dict(update=update,elapsed=elapsed,visits=[(p-a.voices)//588 for name,p in a.events if name=='poll'],
                    commits=commits,waits=list(a.waits),**a.snapshot()))
            traces.append(dict(program=chr(65+index//128)+str(index%128).zfill(3),oscillator=osc+1,batch=batch,initial_cursor=cursor,
                               note=note,velocity=velocity,pedal=pedal,source_offset=offset,source_sha256=hashlib.sha256(record).hexdigest(),initial=initial,steps=steps))
            print('Refreshed',traces[-1]['program'],'OSC',osc+1,'batch',batch,flush=True)
    # The original advance entry must leave both waiting and voice state alone when busy.
    for batch,cursor in itertools.product([1,3,8],[0,7]):
        record=raw[0x1EF220:0x1EF220+2140];a.setup(record,0,63,100,batch,cursor);b.setup(record,0,63,100,batch,cursor)
        for rig in [a,b]:rig.clear();rig.put8(rig.manager+0xE0,1)
        a.a.call(0x1FD3CC,a.manager,20);b.explicit_advance(20);compare(a,b);assert not a.events
        busy_cases.append(dict(batch=batch,cursor=cursor))
    record=raw[0x1EF220+2140*11:0x1EF220+2140*12];a.setup(record,0,63,105,8)
    v=a.voices;saved=bytes(a.a.uc.mem_read(v,588))
    for flags,marker,direction in itertools.product(range(128),[0,1,2,24,5000],[-1,0,1]):
        a.a.uc.mem_write(v,saved);a.put8(v+0x13,flags)
        a.a.write(v+0xD8,marker);a.a.write(v+0x13C,marker)
        a.a.uc.mem_write(v+0x150,struct.pack('<HH',10000,10000-direction*1234))
        a.a.write(v+0x98,100000,100000+direction*10000)
        for bank in range(2):
            targets=[10000,8000,12000,2000];previous=[x-direction*100 for x in targets]
            a.a.uc.mem_write(v+0xEC+20*bank,struct.pack('<8H',*targets,*previous))
        a.clear();a.a.call(0x1F9828,v);checked=a.verify_commits();assert len(checked)==1
        controlled_commits.append(dict(flags=flags,marker=marker,direction=direction,**{k:checked[0][k] for k in ['amp_time','pitch_time','filter_times','registers']}))
    for index,osc in sorted(choices)[:8]:
        offset=0x1EF220+2140*index;record=raw[offset:offset+2140]
        for rig,variant in [(a,0),(b,1)]:rig.setup(record,osc,63,100,8,extra_variant=variant)
        changed=False;steps=[]
        for update in range(16):
            for rig in [a,b]:
                rig.clear();rig.a.write(rig.clock+4,123+20*update);rig.a.call(0x1FD3CC,rig.manager,1);rig.a.call(0x1FE404,rig.manager)
            assert a.writes==b.writes and a.reads==b.reads and a.events==b.events and a.waits==b.waits
            for i in range(8):
                left=bytes(a.a.uc.mem_read(a.voices+588*i,588));right=bytes(b.a.uc.mem_read(b.voices+588*i,588))
                assert left[:0x1CC]==right[:0x1CC] and left[0x1F0:]==right[0x1F0:]
                changed=changed or left[0x1CC:0x1F0]!=right[0x1CC:0x1F0]
            steps.append(dict(update=update,identical_writes=len(a.writes),identical_commits=len(a.commits)))
        auxiliary_influence.append(dict(program=chr(65+index//128)+str(index%128).zfill(3),oscillator=osc+1,auxiliary_state_changed=changed,steps=steps))
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),
                helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_factory_voice_chain.py','firmware_voice_lfo.py','voice_math.py']},
                inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str((OUT/'factory-voice-chain-check.json').relative_to(ROOT)),sha256=sha(OUT/'factory-voice-chain-check.json'))],
                traces=traces,busy_cases=busy_cases,controlled_commits=controlled_commits,coefficient_table=a.coefficients,auxiliary_influence=auxiliary_influence,wave_representatives=wave_reps,filter_route_representatives=route_reps,delay_representatives=delay_reps,
                boundaries=['Native advance and poll/batch manager entries execute on real factory sample/voice chains; comparison manually schedules original kernels in decoded phase order',
                    'All voice bytes, manager/list/controller state, collected pointers, PRNG, observed entry order, TG read/write sequence and wait requests compare after each phase',
                    'This integration comparison is not an independent model of every synthesis kernel; prior EG/LFO/Mixer models remain separate evidence',
                    'Auxiliary blocks at voice+1CC/+1D8 require two parameter bindings not populated by the inspected startup chain; private test parameters are explicit, with a separate influence comparison, actual binding source unresolved',
                    'Independent arithmetic additionally checks every normal TG amp/pitch/filter step and target word, routing mode and score cache',
                    'Separate direct-refresh matrix sets all128 change-flag patterns, five duration markers and three difference signs on one real initialized voice; it checks encoding branches, not factory reachability',
                    'TG active flags, ready/idle state, amplitude readback16384 and score0x1234 are supplied; fixed callback clock and elapsed schedules do not establish physical time',
                    'Fresh synthetic eight-slot pool, zeroed startup scratch stack, reset fixture clock, neutral part transpose and configured controller changes; no full MIDI parser/OS/device/audio executes; timer spin wait only records its requested value'])
    destination=OUT/('voice-refresh-smoke.json' if args.smoke else 'voice-refresh-check.json');destination.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,traces=len(traces),updates=sum(len(t['steps']) for t in traces),busy_cases=len(busy_cases),
                         commits=sum(len(p['commits']) for t in traces for p in t['steps']),wave_kinds=len(wave_reps),filter_routes=len(route_reps),
                         auxiliary_influence_cases=len(auxiliary_influence),controlled_commit_cases=len(controlled_commits)),indent=2))
if __name__=='__main__':main()
