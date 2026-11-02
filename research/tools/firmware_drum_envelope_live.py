#!/usr/bin/env python3
"""Native continuous drum EG editing: manager vs explicit kernel scheduling."""
import argparse,hashlib,json,struct
from pathlib import Path
from firmware_drum_envelope_times import Rig as TimeRig,read,record,KINDS
from firmware_drum_controls import compare as compare_native
from firmware_voice_lfo import PRELOAD,OUT,sha
from program_firmware import Firmware,BASE,FW_SHA
from layout import PRODUCT_ROOT as ROOT

PHASES={0:'attack',1:'attack',2:'decay',3:'decay',4:'slope',5:'slope',6:'sustain',7:'end',8:'release',9:'release'}
CHOICES=[('F033',48),('F036',48),('F042',48),('F068',34)]
def digest(b):return hashlib.sha256(b).hexdigest()
def encoded_sha(value):return digest(json.dumps(value,sort_keys=True,separators=(',',':')).encode())

class Rig(TimeRig):
    def __init__(self,*args):
        self.update=-1;self.core_steps=[];self.step_pending=None;self.key_edits=[];self.start_key=48
        self.command_mask=0;self.acknowledgements=[]
        super().__init__(*args)
    def bus_write(self,a):
        off=a.get('R0')-self.tg;value=a.get('R1')
        if off in [0x230,0x234,0x238,0x23C]:
            shift=(off-0x230)*8;self.command_mask=(self.command_mask&~(0xFFFFFFFF<<shift))|(value<<shift)
        if off==0x22C:
            before=self.active_mask
            if value==1:self.active_mask&=~self.command_mask
            elif value==2:self.active_mask|=self.command_mask
            if value in [1,2]:self.acknowledgements.append(dict(update=self.update,command=value,mask=self.command_mask,before=before,after=self.active_mask))
            self.command_mask=0
        return super().bus_write(a)
    def observe(self,uc,address,size,user):
        before_o=len(self.offsets);before_s=len(self.segments)
        super().observe(uc,address,size,user)
        if not self.eg_capture:return
        a=self.a;off=address-BASE
        for row in self.offsets[before_o:]:
            row['phase']='decay' if row['helper']=='decay' else 'attack';row['update']=self.update
        for row in self.segments[before_s:]:
            row['phase']=PHASES[row['stage']];row['update']=self.update
        if off==0x1FAC24:
            p=a.get('R0');slot,relative=divmod(p-self.voices,588)
            if not 0<=slot<8 or relative not in KINDS:return
            assert self.step_pending is None
            # Dynamic pedal time scaling has a separate validated module; the
            # selected no-pedal trajectory must take the plain core branch.
            assert a.get('R1')==0,(self.update,slot,KINDS[relative],hex(a.get('R1')))
            b=bytearray(read(a,p,48));before=bytes(b);done=self.core.step(b)
            self.step_pending=(p,bytes(b),done,dict(update=self.update,voice=slot,kind=KINDS[relative],
                stage=before[6],before_sha256=digest(before),after_sha256=digest(b),done=done,
                remaining_before=struct.unpack_from('<q',before,16)[0],remaining_after=struct.unpack_from('<q',b,16)[0],
                level=struct.unpack_from('<h',b,0)[0]))
        if off==0x1FAE44 and self.step_pending:
            p,expected,done,row=self.step_pending
            assert read(a,p,48)==expected and a.get('R0')==int(done),(row,read(a,p,48).hex(),expected.hex(),a.get('R0'))
            self.core_steps.append(row);self.step_pending=None
    def configure_context(self):
        super().configure_context()
        self.write_key(self.start_key,22,72);self.write_key(self.start_key,23,80)
    def setup_live(self,source,note,batch,cursor):
        self.eg_capture=False;self.start_key=note;self.update=-1
        self.offsets.clear();self.segments.clear();self.core_steps.clear();self.key_edits.clear()
        self.command_mask=0;self.acknowledgements.clear()
        self.pending.clear();self.core_pending=None;self.step_pending=None
        # Capture original construction and its initial EG step, too.
        self.eg_capture=True;self.phase='initial'
        initial=self.setup(source,note,100,batch,cursor)
        assert initial and not self.pending and self.core_pending is self.step_pending is None
        return initial
    def edit(self,note,selector,value):
        before=b''.join(self.state(self.voices+588*i) for i in range(8))
        self.write_key(note,selector,value)
        after=b''.join(self.state(self.voices+588*i) for i in range(8));assert after==before
        row=dict(update=self.update,selector=selector,value=value,eg_sha256=digest(before),immediate_eg_bytes_unchanged=True)
        self.key_edits.append(row);return row
    def eg_snapshot(self):
        result=[]
        for slot in self.active():
            v=self.voices+588*slot
            result.append(dict(voice=slot,pair=self.word(v+0x218),note=read(self.a,v+0x12,1)[0],
                stages=[read(self.a,v+o+6,1)[0] for o in [0x120,0x15C]],
                levels=[struct.unpack('<h',read(self.a,v+o,2))[0] for o in [0x120,0x15C]],
                remaining=[struct.unpack('<q',read(self.a,v+o+16,8))[0] for o in [0x120,0x15C]],
                durations=[self.word(v+o+24) for o in [0x120,0x15C]]))
        return result

def compare(a,b,positions):
    compare_native(a,b)
    assert a.key_edits==b.key_edits
    assert a.acknowledgements==b.acknowledgements and a.active_mask==b.active_mask
    for name,first in zip(['offsets','segments','core_steps'],positions):
        assert getattr(a,name)[first:]==getattr(b,name)[first:],(name,first)
    assert not a.pending and not b.pending and a.core_pending is b.core_pending is a.step_pending is b.step_pending is None

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    a=Rig(f,raw);b=Rig(f,raw);traces=[]
    choices=[('F042',48)] if args.smoke else CHOICES
    for name,note in choices:
        source=record(raw,name)
        for batch in ([8] if args.smoke else [1,3,8]):
            cursor=7 if batch==3 else 0
            for variant in ['early','late']:
                initial=a.setup_live(source,note,batch,cursor);b.setup_live(source,note,batch,cursor);compare(a,b,[0,0,0])
                first_voices=list(a.active());primary=next(i for i in first_voices if a.word(a.voices+588*i+0x218)!=2)
                edited_decay=False;retrigger_at=None;off_at=None;steps=[]
                for update in range(256 if args.smoke else 1536):
                    positions=[len(a.offsets),len(a.segments),len(a.core_steps)]
                    a.clear();b.clear();events=[]
                    for r in [a,b]:r.update=update;r.phase='continuous'
                    if update==0:
                        for r in [a,b]:r.edit(note,22,0)
                        events.append(['attack',0])
                    state=a.eg_snapshot();old=next((v for v in state if v['voice']==primary),None)
                    # Early changes before the first manager advance; late
                    # waits until the original Amp has entered Decay.
                    trigger=(variant=='early' and update==0) or (variant=='late' and old and old['stages'][1] in [2,3])
                    if trigger and not edited_decay:
                        value=48 if variant=='early' else 32
                        for r in [a,b]:r.edit(note,23,value)
                        events.append(['decay',value]);edited_decay=True
                    seen_filter=any(o['kind']=='filter' and o['phase']=='decay' and o['update']>=0 for o in a.offsets)
                    if seen_filter and retrigger_at is None:
                        for r in [a,b]:
                            r.start_raw(note,100);r.capture=True
                        retrigger_at=update;events.append(['on',note,100])
                    if retrigger_at is not None and update==retrigger_at+16:
                        for r in [a,b]:r.a.call(0x1F60A4,r.osc,0x80+(note<<8)+(64<<16))
                        off_at=update;events.append(['off',note,64])
                    compare(a,b,positions)
                    for r in [a,b]:r.clear();r.a.write(r.clock+4,123+20*update)
                    elapsed=[0,1,3,20][update%4]
                    a.a.call(0x1FD3CC,a.manager,elapsed);b.explicit_advance(elapsed);compare(a,b,positions)
                    a.clear();b.clear();a.a.call(0x1FE404,a.manager);b.explicit_poll();compare(a,b,positions)
                    commits=a.verify_commits()
                    steps.append(dict(update=update,elapsed=elapsed,events=events,commits=len(commits),commit_sha256=encoded_sha(commits),
                        core_steps=len(a.core_steps)-positions[2],state=a.eg_snapshot()))
                assert edited_decay
                if not args.smoke and variant=='late':assert retrigger_at is not None and off_at is not None,(name,note,batch,variant,'missing natural filter Decay')
                assert any(s['kind']=='amp' and s['phase']=='decay' for s in a.segments)
                if variant=='late':assert any(s['kind']=='filter' and s['phase']=='decay' for s in a.segments if s['update']>=0) or args.smoke
                traces.append(dict(program=name,note=note,batch=batch,initial_cursor=cursor,variant=variant,source_sha256=digest(source),
                    source_offset=0x1EF220+2140*((ord(name[0])-65)*128+int(name[1:])),initial=initial,first_voices=first_voices,
                    retrigger_at=retrigger_at,off_at=off_at,key_edits=list(a.key_edits),offsets=list(a.offsets),segments=list(a.segments),
                    core_checks=list(a.core_steps),acknowledgements=list(a.acknowledgements),steps=steps))
                print(json.dumps(dict(trace=len(traces),program=name,batch=batch,variant=variant,retrigger_at=retrigger_at,
                    core_steps=len(a.core_steps),segments=len(a.segments))),flush=True)
    inputs=[PRELOAD,OUT/'drum-eg-times-check.json',OUT/'drum-voice-chain-check.json']
    counts=dict(traces=len(traces),updates=sum(len(t['steps']) for t in traces),commits=sum(s['commits'] for t in traces for s in t['steps']),
        offsets=sum(len(t['offsets']) for t in traces),segments=sum(len(t['segments']) for t in traces),core_steps=sum(len(t['core_checks']) for t in traces),
        immediate_edits=sum(len(t['key_edits']) for t in traces),retriggers=sum(t['retrigger_at'] is not None for t in traces))
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        math_sha256=sha(ROOT/'research/tools/voice_math.py'),additional_helpers={n:sha(ROOT/'research/tools'/n) for n in
        ['firmware_drum_envelope_times.py','firmware_drum_controls.py','firmware_drum_voice_chain.py','firmware_voice_refresh.py','firmware_factory_voice_chain.py','firmware_envelopes.py','firmware_voice_lfo.py']},
        inputs=[dict(path=str(x.relative_to(ROOT)),sha256=sha(x)) for x in inputs],counts=counts,traces=traces,actual_DSP_audio_executed=False,
        boundaries=['Original drum construction, per-key writers, normal batched advance/poll and note-off/retrigger execute; no phase-byte or time-state injection',
            'Native manager compares every update to explicit original-kernel scheduling: all eight voice/list/controller/PRNG state, TG read/write/wait order and commit state match',
            'All observed Filter/Amp core steps take the no-dynamic-pedal branch and compare full48 native bytes and completion flag against independent Core.step; segment setup compares Core.segment',
            'Attack72/Decay80 are set through original per-key writers before initial NoteOn. Attack0 is written before first normal update; Decay48 is early, Decay32 waits for Amp Decay in late traces',
            'Retrigger occurs after original first Filter Decay is observed; subsequent raw NoteOff follows16 manager updates later and respects original drum release permissions',
            'Elapsed schedule and eight-slot cursors are controlled; TG commands1/2 immediately clear/set the latched mask as in the pressure fixture. Score/amplitude readback and two private auxiliary bindings remain controlled',
            'No OS, hardware/audio, MIDI byte routing or host sample-clock claim; mode combinations, dynamic pedal scaling and complete audio remain outside this result'])
    path=OUT/('drum-eg-live-smoke.json' if args.smoke else 'drum-eg-live-check.json')
    path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=counts)))
if __name__=='__main__':main()
