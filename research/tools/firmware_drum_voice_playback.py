#!/usr/bin/env python3
"""Native PPAT playback through local ingress into real MIDI drum voices."""
import argparse,hashlib,itertools,json,struct
from collections import Counter
from pathlib import Path
from firmware_voice_pressure import PressureRig
from firmware_midi_voice_handoff import Rig as HandoffRig
from firmware_midi_all_off import compare as compare_voice,read
from firmware_stop_reuse import ModelRig,check_lists
from firmware_stop_reuse_port import make_unlink_adapter
from firmware_drum_voice_chain import Rig as DrumRig
from firmware_factory_voice_chain import sb
from firmware_gm_programs import sources,IMAGE,IMAGE_SHA
from firmware_voice_lfo import PRELOAD,OUT
from firmware_midi_program_load import sha
from program_firmware import Firmware,BASE,FW_SHA
from layout import PRODUCT_ROOT as ROOT

PPAT=ROOT/'research/firmware/KROSS2_V124/KROSS2SY/PPAT.BIN'
def digest(b):return hashlib.sha256(b).hexdigest()
def packed_sha(x):return digest(json.dumps(x,sort_keys=True,separators=(',',':')).encode())
class Synth(PressureRig):
    guard_enabled=False
    def __init__(self,*args):
        self.now=-1;self.music_events=[];self.dispatched=[];self.constructed=[];self.source_pending=None;self.current_note=0;self.current_velocity=0
        self.zero_writes=[];self.skipped=[];self.generator=False;self.tg_pending=None;self.quiet_mask=0;self.zero_amplitude_responses=[]
        super().__init__(*args);a=self.a
        a.uc.mem_map(0x13000000,0x10000);self.track=0x13000000;self.desc=0x13001000;self.stream=0x13002000
        self.ppat=PPAT.read_bytes()[64:];self.ppat_base=struct.unpack_from('<I',self.ppat)[0];a.uc.mem_write(self.ppat_base,self.ppat)
        a.stubs[0x2AA44]=lambda m:0 # cache/display notification; native local ingress still executes
        from unicorn import UC_HOOK_MEM_WRITE
        a.uc.mem_map(0,0x1000);a.uc.mem_write(0,self.f.data[:0x1000])
        a.uc.hook_add(UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:self.zero_writes.append(dict(address=address,size=size,value=value,pc=hex(a.get('PC')))),begin=0,end=0xFFF)
    def cold_start(self,mode=3):
        # Keep the proven32-slot layout. PressureRig's120-slot node span would
        # overlap the factory drum-kit buffer at110E0000 for these presets.
        HandoffRig.cold_start(self,mode)
    def note_and_remember(self,*args):return None # no manual note before Pattern playback
    def bus_read(self,a):
        if a.get('R0')-self.tg==0x42C:
            self.reads.append(0x42C)
            return 16384 if self.active_mask&(1<<self.current_slot) and not self.quiet_mask&(1<<self.current_slot) else 0
        return super().bus_read(a)
    def bus_write(self,a):
        if a.get('R0')-self.tg==0x418:
            target=a.get('R1')&65535;bit=1<<self.current_slot
            if target:self.quiet_mask&=~bit
            else:
                self.quiet_mask|=bit
                self.zero_amplitude_responses.append(dict(tick=self.now,slot=self.current_slot,word=a.get('R1')))
        return super().bus_write(a)
    def observe(self,uc,address,size,user):
        super().observe(uc,address,size,user);off=address-BASE;a=self.a
        if off==0x1F62F0:
            message=a.get('R1');self.current_note=(message>>8)&255;self.current_velocity=(message>>16)&255
        if not self.generator:return
        if off==0x2BD7B4:
            self.music_events.append(dict(tick=self.now,status=a.get('R1')&255,note=a.get('R2')&255,velocity=a.get('R3')&255))
        elif off==0x271500:
            p=a.get('R1');raw=read(a,p+4,8)
            self.dispatched.append(dict(tick=self.now,status=raw[0],note=raw[1],velocity=raw[2],source=raw[3]))
        elif off==0x1F7278:
            v=a.get('R0');prepared=self.prepared[-1]
            expected=next(x for x in DrumRig.expected_layers(self,self.current_note,self.current_velocity) if
                all(x[k]==prepared[k] for k in ['layer','side','slot','key','weight']))
            assert expected['valid'];start=self.started[-1];key=self.kitptr+24+68*expected['key'];desc=read(a,key+12*expected['slot'],12)
            sample=expected['sample'];drum=self.f.data[0x408BFC+32*expected['drumsample']:0x408BFC+32*(expected['drumsample']+1)]
            level=127*expected['weight']>>15;gain=self.math.multisample_gain(level,sb(desc,4),sb(drum,28))
            assert (start['sample_ptr'],start['key_ptr'],start['desc_ptr'])==(BASE+0x410ABC+64*sample,key,key+12*expected['slot'])
            assert (start['root'],start['tune'],start['pitch'],start['layer_level'],start['level_correction'],start['max_level'])==(
                15360,2*(100*sb(desc,6)+sb(desc,7)),expected['pitch'],level,sb(desc,4),drum[28])
            slot=(v-self.voices)//588;self.origins[slot]=(self.word(v+0x21C),self.word(v+0x224))
            row=dict(tick=self.now,slot=slot,note=self.current_note,velocity=self.current_velocity,key=expected['key'],sample=sample,
                layer=expected['slot'],side=expected['side'],weight=expected['weight'],gain_before=self.half(v+0x200),expected_gain=gain,
                program_pointer=self.word(v+0x21C),osc_pointer=self.word(v+0x224))
            self.constructed.append(row);self.source_pending=(v,row)
        elif off==0x1F77C8:
            v,row=self.source_pending;assert a.get('R6')==v and a.get('R0')==1
            pair=self.word(v+0x218);gain=self.half(v+0x200);assert gain==(row['gain_before'] if pair==2 else row['expected_gain'])
            row.update(pair=pair,gain=gain);self.source_pending=None
        elif off==0x1F9028:
            v=a.get('R0');slot=(v-self.voices)//588;row=next(r for r in reversed(self.constructed) if r['slot']==slot)
            sample=self.f.data[0x410ABC+64*row['sample']:0x410ABC+64*(row['sample']+1)]
            offset,boundary=read(a,v+0x20A,2);reverse=read(a,v+0x20C,1)[0]
            def word(i):return int.from_bytes(sample[i:i+4],'little')
            field=12 if not offset else 56 if offset-boundary+8==7 else 60 if offset-boundary+8==8 else 16 if offset==1 else 32+4*(offset-1)
            flags=sample[7];start=word(20);loop=word(field)
            if flags&8:
                loop=word(24)
                if flags&32:start=word(12)
                elif reverse:flags|=32
            elif reverse:start=word(28);loop=word(32);flags|=40
            expected={0x200:((flags>>2)&14)|(flags&1),0x208:start,0x20C:(word(24)-1)&0xFFFFFFFF,0x210:loop}
            assert self.tg_pending is None
            self.tg_pending=(len(self.writes),row,expected)
            row.update(start_offset=offset,start_boundary=boundary,reverse=reverse)
        elif off==0x1F9404:
            first,row,expected=self.tg_pending
            actual={offset:value for slot,offset,value in self.writes[first:] if slot==row['slot'] and offset in expected}
            assert actual==expected,(row,actual,expected)
            row['sample_registers']={hex(k):v for k,v in expected.items()};self.tg_pending=None
    def setup_track(self,preset,batch,index,synthetic):
        self.generator=False;self.command_mask=0;self.quiet_mask=0;self.zero_amplitude_responses.clear();self.setup(preset,batch,3,False);self.now=-1
        a=self.a;self.music_events.clear();self.dispatched.clear();self.constructed.clear();self.zero_writes.clear();self.skipped.clear()
        if not self.guard_enabled:a.uc.mem_write(0,self.f.data[:0x1000])
        a.uc.mem_write(self.ppat_base,self.ppat)
        a.uc.mem_write(self.track,bytes(0x164));a.uc.mem_write(self.desc,bytes(8))
        self.put8(0xC1DCC2D8+4,0);self.put8(0xC1DCC2D8+0x1350,7);self.put8(0xC1DCD62A,0);a.write(0xC1716398,1)
        if synthetic:
            sequence=[(36,90,60,0),(38,100,120,120),(42,110,3000,1800)]
            stream=struct.pack('<BBBBHH',1,0,0,19,4,0)+b''.join(struct.pack('<BBBBHH',9,0,*v) for v in sequence)+bytes([3])+bytes(7)
            a.uc.mem_write(self.stream,stream);entry=self.ppat_base+4+32*799;a.write(entry+28,self.stream);self.put8(entry+24,1)
        a.call(0x2456C4,self.track,0)
        self.put8(self.desc,index&255);self.put8(self.desc+4,0x80+(index>>8));self.put8(self.desc+2,0x31)
        assert a.call(0x245760,self.track,self.desc,0,7)==1
        a.call(0x2458C0,self.track,0);assert self.half(self.track+0x1C)==1920
        self.generator=True;self.clear_capture()
    def track_tick(self,tick,delta):
        self.now=tick;self.a.uc.mem_write(0x111E0000,bytes(0x10000))
        try:self.a.call(0x2462B8,self.track,delta)
        except Exception:
            print(json.dumps(dict(failed_tick=tick,events=self.music_events[-4:],constructed=len(self.constructed),last_writes=self.writes[-24:],last_reads=self.reads[-12:],active_mask=hex(self.active_mask),command_mask=hex(self.command_mask))),flush=True)
            raise
        self.bind_extra()
    def track_stop(self):
        self.a.uc.mem_write(0x111E0000,bytes(0x10000));self.a.call(0x245A44,self.track)
        assert read(self.a,self.track+0x32,1)==b'\0'

class Model(Synth,ModelRig):
    def __init__(self,*args):
        super().__init__(*args);self.a.uc.mem_unmap(0,0x1000)
def compare(a,b):
    compare_voice(a,b)
    assert read(a.a,a.track,0x164)==read(b.a,b.track,0x164)
    assert a.music_events==b.music_events and a.dispatched==b.dispatched and a.constructed==b.constructed
    assert a.start_acknowledgements==b.start_acknowledgements and a.stop_acknowledgements==b.stop_acknowledgements
    assert a.quiet_mask==b.quiet_mask and a.zero_amplitude_responses==b.zero_amplitude_responses
    assert a.source_pending is b.source_pending is a.tg_pending is b.tg_pending is None

def expected_ons(catalog,index,synthetic):
    if synthetic:
        return [(cycle*1920+t+int(cycle>0 and t==0),note,velocity) for cycle in range(2) for note,velocity,t in [(36,90,0),(38,100,120),(42,110,1800)]]
    row=catalog['patterns'][index];result=[]
    for bar in row['bars']:
        for data in bar['events']:
            r=bytes.fromhex(data);time=struct.unpack_from('<H',r,6)[0]
            if time<1920:result.append((bar['number']*1920+time,r[2],r[3]))
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();raw=PRELOAD.read_bytes();gm=sources();assert sha(PPAT)=='1f734fb8ffd41efa030079f9436753dae7e10e5cf7ac05a42921c28cc6592135'
    catalog_path=OUT/'drum-patterns.json';catalog=json.loads(catalog_path.read_text());a=Synth(f,raw,gm);b=Model(f,raw,gm)
    b.guard_enabled=True;b.a.stubs[0x272414]=make_unlink_adapter(b.word,b.a.write,b.skipped)
    choices=[((5,42),8,799,True)] if args.smoke else itertools.product([(5,33),(5,42)],[4,16],[(799,True),(799,False),(31,False)])
    traces=[]
    for choice in choices:
        if args.smoke:preset,batch,index,synthetic=choice
        else:preset,batch,(index,synthetic)=choice
        length=3840 if synthetic else len(catalog['patterns'][index]['bars'])*1920
        a.setup_track(preset,batch,index,synthetic);b.setup_track(preset,batch,index,synthetic);compare(a,b)
        steps=[];event_counts=[];elapsed=0
        for tick in range(length):
            a.clear_capture();b.clear_capture();before=len(a.music_events)
            a.track_tick(tick,int(tick!=0));b.track_tick(tick,int(tick!=0));compare(a,b)
            if len(a.music_events)>before:event_counts.append(dict(tick=tick,count=len(a.music_events)-before,active=len(a.active_slots())))
            if tick%8==0:
                for r in [a,b]:r.clear_capture();r.a.write(r.clock+4,123+tick)
                a.a.call(0x1FD3CC,a.manager,elapsed);b.explicit_advance(elapsed);compare(a,b)
                a.clear_capture();b.clear_capture();a.a.call(0x1FE404,a.manager);b.explicit_poll();compare(a,b)
                commits=a.verify_commits();links=check_lists(a);assert links==check_lists(b)
                steps.append(dict(tick=tick,elapsed=elapsed,commits=len(commits),commit_sha256=packed_sha(commits),active=len(a.active_slots()),available=links['available'],
                    state_sha256=digest(read(a.a,a.voices,588*a.capacity))))
                elapsed=8
        a.now=b.now=length-1;a.clear_capture();b.clear_capture();a.track_stop();b.track_stop();compare(a,b)
        ons=[(e['tick'],e['note'],e['velocity']) for e in a.music_events if e['status']&240==144]
        assert ons==expected_ons(catalog,index,synthetic),(preset,index,ons[:8],expected_ons(catalog,index,synthetic)[:8])
        assert all((e['status']&15)==7 for e in a.music_events)
        assert a.dispatched==[dict(**e,source=1) for e in a.music_events]
        balance=Counter()
        for e in a.music_events:
            balance[e['note']]+=1 if e['status']&240==144 else -1;assert balance[e['note']]>=0
        assert not any(balance.values())
        before_cleanup=len(a.active_slots());a.generator=b.generator=False;a.clear_capture();b.clear_capture();a.cc(120,0);b.cc(120,0);compare(a,b)
        assert not a.active_slots() and not b.active_slots() and a.word(a.manager+0x48)==b.word(b.manager+0x48)==32
        assert [r['address'] for r in a.zero_writes]==[4,0]*len(b.skipped)
        assert all(r['size']==4 and r['value']==0 and r['pc'] in ['0xc027242c','0xc0272430'] for r in a.zero_writes)
        traces.append(dict(program='F'+str(preset[1]).zfill(3),pattern=index,synthetic=synthetic,batch=batch,ticks=length,
            music_events=list(a.music_events),dispatched=list(a.dispatched),constructed=list(a.constructed),event_groups=event_counts,steps=steps,
            voices_before_cleanup=before_cleanup,empty_unlinks=len(b.skipped),native_zero_page_writes=len(a.zero_writes),cleanup_available=32,
            zero_amplitude_responses=list(a.zero_amplitude_responses)))
        print(json.dumps(dict(trace=len(traces),program=traces[-1]['program'],pattern=index,synthetic=synthetic,batch=batch,note_ons=len(ons),voices=len(a.constructed))),flush=True)
    counts=dict(traces=len(traces),ticks=sum(t['ticks'] for t in traces),updates=sum(len(t['steps']) for t in traces),
        music_events=sum(len(t['music_events']) for t in traces),voices=sum(len(t['constructed']) for t in traces),starts=sum('sample_registers' in v for t in traces for v in t['constructed']),
        commits=sum(s['commits'] for t in traces for s in t['steps']),empty_unlinks=sum(t['empty_unlinks'] for t in traces))
    inputs=[PRELOAD,IMAGE,PPAT,catalog_path,OUT/'drum-playback-check.json',OUT/'voice-pressure-check.json',OUT/'drum-voice-playback-feedback-failure.json',OUT/'drum-voice-playback-active-only-fixture.py']
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,actual_DSP_audio_executed=False,
        tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),math_sha256=sha(ROOT/'research/tools/voice_math.py'),
        additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_voice_pressure.py','firmware_midi_all_off.py','firmware_midi_voice_refresh.py','firmware_midi_voice_handoff.py','firmware_midi_program_load.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_voice_refresh.py','firmware_stop_reuse.py','firmware_stop_reuse_port.py','firmware_voice_lfo.py']},
        inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in inputs],counts=counts,traces=traces,
        boundaries=['Same ARM/private memory executes original PPAT bind/tick/note table/loop/stop ->244A60 ->2BD7B4 local ingress ->271500 MIDI/timbre/OSC ->real drum selection/allocation/control/TG start',
            'Local ingress2BD7B4 is not intercepted. Original code writes source1 and dispatches channel7 events. Cache/display2AA44 is supplied; preprocessing bit2 remains off and external wire output disabled',
            'Independent source equations check every materialized sample,layer,weight,tune,root and primary gain; secondary gain retention is checked against the word at gain-kernel entry. Every observed sample start additionally compares mode/start/end/loop register words',
            'Original32-slot sound manager advance/poll every8 musical ticks compares full software state and TG I/O against explicit original-kernel scheduling. This is a controlled schedule, not physical-time or host-frame calibration',
            'Original NoteOff permissions are preserved. Track stop balances generated notes; separate final CC120 is an explicit fixture cleanup and is not attributed to track stop',
            'Native side maps private RW zero-page, portable side omits only empty indexed unlink stores. Writes must match4/0 pairs. Actual device zero-page mapping remains unknown',
            'TG commands1/2 have immediate mask responses. Amplitude readback is16384 for active slots,0 for inactive slots or after an amplitude target0 write. A nonzero target cancels that override. Ramp-to-zero completion is immediate fixture feedback, not measured chip timing; score is controlled',
            'Track-level output is integrated; keyboard/Latch manager, Arp, shared central clock, active recording, OS scheduling and DSP audio are not included'])
    (OUT/('drum-voice-playback-smoke.json' if args.smoke else 'drum-voice-playback-check.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=counts)))
if __name__=='__main__':main()
