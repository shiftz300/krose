#!/usr/bin/env python3
"""MIDI Program changes with continuous native voice advance and TG polling."""
import argparse,hashlib,itertools,json,struct
from pathlib import Path
from firmware_midi_voice_handoff import Rig as HandoffRig
from firmware_voice_refresh import Rig as RefreshRig
from firmware_gm_programs import sources,IMAGE,IMAGE_SHA
from firmware_voice_lfo import PRELOAD,OUT,h,sh,w,s32
from firmware_midi_program_load import sha
from program_firmware import Firmware,BASE,FW_SHA
from layout import PRODUCT_ROOT as ROOT
LABELS={0x1F8140:'advance',0x1F969C:'poll',0x1FBD98:'wave',0x1FFDA0:'pitch_refresh',0x1FBD28:'filter_refresh',
        0x1FA9C4:'amp_refresh',0x20119C:'mixer',0x1FF38C:'pitch_target',0x1FB4B0:'filter_target',0x1F9DD4:'amp_target',
        0x1FEDFC:'pan_target',0x1F9828:'commit'}

class Rig(HandoffRig):
    bus_read=RefreshRig.bus_read
    explicit_advance=RefreshRig.explicit_advance
    explicit_poll=RefreshRig.explicit_poll
    verify_commits=RefreshRig.verify_commits
    def __init__(self,f,raw,gm):
        self.capture=False;self.events=[];self.commits=[];self.current_commit=None;self.waits=[];self.active_mask=0;self.score=0x1234;self.origins={}
        super().__init__(f,raw,gm);self.coefficients=list(struct.unpack_from('<25H',f.data,0x3A8D40))
        self.extra=0x110B0000;self.a.stubs[0x12F1D0]=lambda m:self.waits.append(m.get('R1')) or 0
        # Assignment getters execute on private unassigned switch objects/config.
        self.a.write(0xC0F53878,0x1107B000);self.a.write(0xC0F53874,0x1107B020)
        self.a.uc.mem_write(0x1107B000,bytes(64));self.a.uc.mem_write(0xC1DCC2D8+6,bytes(2))
        self.a.uc.mem_write(0xC199BD40,b'\xff\xff')  # no registered UI parameter namespace
    def bus_write(self,a):
        if self.capture and self.current_commit is not None:self.current_commit['writes'].append([a.get('R0')-self.tg,a.get('R1')])
        return super().bus_write(a)
    def observe(self,uc,address,size,user):
        super().observe(uc,address,size,user);off=address-BASE;a=self.a
        if off in [0x1F9028,0x1F9A5C]:
            slot=a.uc.mem_read(a.get('R0')+0x1A,1)[0]
            if off==0x1F9028:self.active_mask|=1<<slot
            else:self.active_mask&=~(1<<slot)
        if not self.capture:return
        if off in LABELS:self.events.append([LABELS[off],a.get('R0')])
        if off==0x1F9828:
            v=a.get('R0');self.current_commit=dict(voice=(v-self.voices)//588,state=bytes(a.uc.mem_read(v,588)).hex(),writes=[]);self.commits.append(self.current_commit)
    def clear_capture(self):
        self.events.clear();self.commits.clear();self.current_commit=None;self.waits.clear();self.writes.clear();self.reads.clear()
    def bind_extra(self):
        # Two pre-existing unknown parameter bindings remain explicit fixture data.
        self.a.uc.mem_write(self.extra,bytes(12))
        for i in range(self.capacity):
            self.a.write(self.voices+588*i+0x1CC,self.extra);self.a.write(self.voices+588*i+0x1D8,self.extra+4)
    def note_and_remember(self,note,velocity):
        old_capture=self.capture;self.capture=False
        # Match the existing startup fixture: unused PCM fields can copy stale
        # local stack words. Normalize only scratch stack before the outer call.
        self.a.uc.mem_write(0x111E0000,bytes(0x10000))
        result=self.check_note(note,velocity);self.bind_extra()
        for row in result['voices']:self.origins[row['voice_slot']]=(row['program_pointer'],row['osc_pointer'])
        self.capture=old_capture;return result
    def setup(self,old,batch,mode,pedal):
        self.capture=False;self.active_mask=0;self.origins={};self.cold_start(mode);self.a.write(self.clock,0,123)
        self.a.uc.mem_write(0xC165D9F8,bytes(64))
        for t,p in zip(self.ts,self.ps):
            self.put8(p+6,2);self.put8(p+0xE,64);self.put8(p+0xF,127);self.put8(p+0x10,127)
            self.put8(p+0x19,5 if pedal else 1);self.put8(p+0x1B,16);self.put8(p+0x1D,255)
            self.a.call(0x2736F8,t,p,self.channel)
            mask=(1<<128)-1
            for cc in [1,2,16,64,65]:mask&=~(1<<cc)
            if pedal:mask|=1<<64
            assert bytes(self.a.uc.mem_read(t+0x34,16))==mask.to_bytes(16,'little')
            for cc in [7,11,74]:assert self.a.call(0x2737C8,t,cc)==1
            assert self.a.call(0x2737C8,t,64)==int(pedal)
        self.choose(*old)
        initial=self.note_and_remember(48,100);self.a.write(self.manager+0xE4,self.capacity);self.put8(self.manager+0xE8,batch)
        self.put8(self.manager+0xE1,31 if batch==3 else 0);self.put8(self.manager+0xE9,31 if batch==3 else 0)
        self.clear_capture();self.capture=True;return initial
    def apply_event(self,update,new,pedal):
        self.current_commit=None;result={}
        if update==8:self.cc(7,99)
        if update==12:self.send(0xE7,127,127)
        if update==16 and pedal:self.cc(64,127)
        if update==24:
            before=bytes(self.a.uc.mem_read(self.voices,588*self.capacity));result['change']=self.choose(*new)
            assert bytes(self.a.uc.mem_read(self.voices,588*self.capacity))==before
        if update==28:result['note']=self.note_and_remember(64,100)
        if update==40:self.cc(74,96);self.cc(11,73)
        if update in [48,56]:
            note=48 if update==48 else 64;self.send(0x87,note,64);result['off']=note
        if update==64 and pedal:self.cc(64,0)
        if update==80:self.send(0xE7,0,64)
        return result
    def state(self):
        # Preserve LoadRig's state interface used by its Program Change model.
        return super().state()
    def voice_state(self):
        result=[]
        for i in self.active_slots():
            v=self.voices+588*i;flags=self.half(v+0x10)
            assert (self.word(v+0x21C),self.word(v+0x224))==self.origins[i]
            result.append(dict(slot=i,flags=flags,program=self.word(v+0x21C),osc=self.word(v+0x224),amp=self.half(v+0x150),pitch=self.word(v+0x9C),
                filter=[self.half(v+off) for off in [0xEC,0xEE,0x100,0x102]],eg_stages=[self.a.uc.mem_read(v+off+6,1)[0] for off in [0xBC,0x120,0x15C]],
                sample=self.word(v+0x238),delay=sh(bytes(self.a.uc.mem_read(v+0x208,2)),0)))
        return dict(advance=self.a.uc.mem_read(self.manager+0xE1,1)[0],poll=self.a.uc.mem_read(self.manager+0xE9,1)[0],available=self.word(self.manager+0x48),
                    channel_bend=sh(bytes(self.a.uc.mem_read(self.channel+0xFA,2)),0),timbre_bend=sh(bytes(self.a.uc.mem_read(self.context+0x94,2)),0),
                    controllers={str(cc):self.a.uc.mem_read(self.controls+cc,1)[0] for cc in [7,11,64,74]},volume=self.a.uc.mem_read(self.context+0x2D,1)[0],voices=result)

def compare(a,b):
    spans=[(a.manager,0x100),(a.voices,a.capacity*588),(a.nodes,a.capacity*12),(a.members,a.capacity*12),(a.waitnodes,a.capacity*12),
           (a.channels,16*436),(a.keycontrols,1536),(0xC165D9A0,0xB0),(0xC1B5848C,4),(a.system,0x60)]
    for i in range(3):
        spans.extend([(a.ts[i],152),(a.ps[i],64),(a.cs[i],128),(a.pools[i],32),(a.osc_nodes[i],24),(0x1105A000+128*i,120)])
        spans.extend((o,0x500) for o in a.oscs[i])
    for ptr,size in spans:
        left=bytes(a.a.uc.mem_read(ptr,size));right=bytes(b.a.uc.mem_read(ptr,size))
        assert left==right,(hex(ptr),[(i,x,y) for i,(x,y) in enumerate(zip(left,right)) if x!=y][:12])
    assert a.writes==b.writes and a.reads==b.reads and a.waits==b.waits
    assert a.events==b.events and a.commits==b.commits and a.active_mask==b.active_mask

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    raw=PRELOAD.read_bytes();gm=sources();a=Rig(f,raw,gm);b=Rig(f,raw,gm)
    pairs=[((0,0),(0,61)),((0,61),(0,0)),((0,11),(5,42)),((5,42),(0,11)),((10,0),(20,0)),((20,0),(10,0))]
    choices=[(pairs[0],8,3,True)] if args.smoke else itertools.product(pairs,[1,3,8],[0,3],[False,True])
    traces=[]
    for (old,new),batch,mode,pedal in choices:
        try:
            initial=a.setup(old,batch,mode,pedal);b.setup(old,batch,mode,pedal);compare(a,b);steps=[]
            for update in range(96):
                a.clear_capture();b.clear_capture();event_a=a.apply_event(update,new,pedal);event_b=b.apply_event(update,new,pedal);compare(a,b);assert event_a==event_b,(event_a,event_b)
                for r in [a,b]:r.clear_capture();r.a.write(r.clock+4,123+20*update)
                elapsed=[0,1,3,20][update%4];a.a.call(0x1FD3CC,a.manager,elapsed);b.explicit_advance(elapsed);compare(a,b)
                a.clear_capture();b.clear_capture();a.a.call(0x1FE404,a.manager);b.explicit_poll();compare(a,b)
                commits=a.verify_commits();steps.append(dict(update=update,elapsed=elapsed,event=event_a,commits=commits,visits=[(ptr-a.voices)//588 for name,ptr in a.events if name=='poll'],state=a.voice_state()))
            assert any(v['amp'] for step in steps for v in step['state']['voices'])
            assert all(s['state']['volume']==99 for s in steps[8:])
            assert all(s['state']['controllers']['11']==73 and s['state']['controllers']['74']==96 for s in steps[40:])
            assert steps[12]['state']['timbre_bend']==32767 and steps[24]['state']['timbre_bend']==0
            assert steps[24]['state']['channel_bend']==32767
            traces.append(dict(old=old,new=new,mode=mode,batch=batch,pedal=pedal,initial=initial,steps=steps))
            print(json.dumps(dict(trace=len(traces),old=old,new=new,mode=mode,batch=batch,pedal=pedal)),flush=True)
        except Exception as error:raise AssertionError(dict(old=old,new=new,mode=mode,batch=batch,pedal=pedal,update=update if 'update' in locals() else -1)) from error
    counts=dict(traces=len(traces),updates=sum(len(t['steps']) for t in traces),commits=sum(len(s['commits']) for t in traces for s in t['steps']))
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_midi_voice_handoff.py','firmware_midi_program_load.py','firmware_voice_refresh.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py']},
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA)],counts=counts,traces=traces,
        boundaries=['Same native MIDI/Program/voice fixture runs continuous events, original manager advance and normal batched poll; reference independently schedules the original kernels in decoded phase order',
            'After every MIDI event, advance and poll phase, all32 voices and pool lists, all6 OSCs, three timbres/Parts/controllers, sixteen channels, drum controls, scratch and PRNG are compared, along with native entry order, TG reads/writes and wait requests',
            'TG amplitude16384, score0x1234, ready and active masks are controlled; this is control scheduling and encoding, not actual DSP audio or an independent model of all synthesis kernels',
            'Original2736F8 Part/channel attachment and27338C controller masks execute; Part bend range2, pan64, sends127, other-CC enable and selected sustain permission are explicit; original assignment getters return unassigned from controlled source objects/config',
            'Two auxiliary parameter pointers at voice+1CC/+1D8 remain explicit private zero blocks after each NoteOn; actual binding source is unresolved',
            'Only scratch stack111E0000..111EFFFF is zeroed before each outer MIDI NoteOn, as in earlier startup fixtures; all live voice/OSC/controller state remains intact',
            'Inherited offline storage/allocation/TG/notification/OS-priority boundaries remain; timer spin records requested waits only',
            'No global-channel application Program queue, DSP audio, full patch set, exhaustive voice stealing or physical timing claim'])
    destination=OUT/('midi-voice-refresh-smoke.json' if args.smoke else 'midi-voice-refresh-check.json');destination.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=counts),indent=2))
if __name__=='__main__':main()
