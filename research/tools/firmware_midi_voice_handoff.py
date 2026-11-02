#!/usr/bin/env python3
"""Real MIDI notes and Program Change share a live native voice pool."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_midi_program_load import Rig as LoadRig,sha,OUT
from firmware_gm_programs import sources,bank_model,IMAGE,IMAGE_SHA,GMDrums
from firmware_drum_voice_chain import Rig as DrumRig
from firmware_factory_voice_chain import Rig as MelodicRig,sb
from firmware_voice_lfo import PRELOAD,h,sh,w
from firmware_inspect import inspect
from program_firmware import Firmware,BASE,FW_SHA
from layout import PRODUCT_ROOT as ROOT

class Rig(LoadRig):
    def __init__(self,f,raw,gm):
        self.note_events=[];self.releasing=[];self.kills=[];self.osc_calls=[];self.note_rows=[]
        super().__init__(f,raw,gm);a=self.a
        a.write(0xC0F55850,0x11078000);a.write(0x11078000+0x38,0x11078100)
        a.write(0xC199946C,0x11079000);a.write(0x11079000+0xF7C,self.mode)
        a.stubs.update({0xD55B4:lambda m:0x11078200,0xD58C0:lambda m:0,0x324CC:lambda m:0,
            0x54C74:lambda m:0,0x54E40:lambda m:0,
            0x2CD2AC:lambda m:5,0x2CD2A0:lambda m:0})
        self.cold_start()
    def cold_start(self,mode=3):
        self.reset(mode=mode);a=self.a;self.capacity=32
        a.uc.mem_write(self.manager,bytes(0x100));a.write(self.manager+4,self.voices)
        a.write(self.manager+0x3C,self.nodes,self.members,self.capacity,0)
        a.write(self.manager+0xCC,self.manager+0xCC,self.manager+0xCC,0,self.waitnodes,self.capacity)
        a.uc.mem_write(self.voices,bytes(self.capacity*588));a.uc.mem_write(0xC165DA38,bytes(24));a.call(0x1FEDE4)
        for i in range(self.capacity):
            v=self.voices+588*i;a.call(0x1F68D4,v);self.put8(v+0x16,i);self.put8(v+0x1A,i);a.write(v+0x1C,self.tg);a.write(v+0x240,0xFFFFFFFF)
            for p in [self.nodes,self.members,self.waitnodes]:a.write(p+12*i,0,0,v)
        a.call(0x1FBF4C,self.manager+12);a.write(0xC1B5848C,0x12345678)
        a.write(0xC04AE3A8,1);self.put8(0xC1DCC2D8+0x1354,0)
        for p in self.ps:
            self.put8(p+0x1E,127);self.put8(p+0x1F,0);self.put8(p+0x21,127);self.put8(p+0x22,1)
        self.context=self.ts[0];self.part=self.ps[0];self.controls=self.cs[0];self.keycontrols=0x11060000
        self.note_events.clear();self.releasing.clear();self.kills.clear();self.osc_calls.clear();self.note_rows.clear()
    def observe(self,uc,address,size,user):
        off=address-BASE;a=self.a
        if off==0x1F62F0:
            self.osc=a.get('R0');self.oscillator=self.oscs[0].index(self.osc);self.patch=self.word(self.context+8);self.record=bytes(a.uc.mem_read(self.patch,2140))
            if self.record[0x508]&7==2:
                encoded=h(self.record,0x566);self.kit=encoded if encoded<58 else encoded-96;self.encoded_kit=encoded
                self.kitptr=self.kitbase+8728*self.kit;self.kitraw=bytes(a.uc.mem_read(self.kitptr,8728));self.special=bool(a.uc.mem_read(0xC1B5719C,1)[0])
                self.remap=list(struct.unpack('<128b',a.uc.mem_read(self.osc+24,128)))
            self.osc_calls.append(dict(osc=self.oscillator,message=a.get('R1'),patch=self.patch))
        if off==0x1F6958:
            slot=(a.get('R0')-self.voices)//588;self.note_events.append(dict(slot=slot,osc=self.oscillator,patch=self.patch))
        elif off==0x1F7CC8:self.releasing.append((a.get('R0')-self.voices)//588)
        elif off==0x1FD53C:self.kills.append((a.get('R1')-self.voices)//588)
        # Preserve inherited native sample/pair/TG observations.
        super().observe(uc,address,size,user)
    def choose(self,bank,program):
        self.cc(0,121 if 10<=bank<20 else 120 if bank==20 else 0)
        self.cc(32,bank-10 if 10<=bank<20 else 0 if bank==20 else bank)
        return self.check_change(program)
    def active_slots(self):
        result=[]
        for osc in self.oscs[0]:
            head=osc+0x490;node=self.word(head);seen=set()
            while node!=head:
                assert node not in seen and len(seen)<self.capacity;seen.add(node)
                v=self.word(node+8);assert v;result.append((v-self.voices)//588);node=self.word(node)
        assert len(result)==len(set(result));return sorted(result)
    def snapshot(self):
        rows=[]
        for slot in self.active_slots():
            v=self.voices+588*slot;rows.append(dict(slot=slot,note=self.a.uc.mem_read(v+0x12,1)[0],flags=self.half(v+0x10),
                program=self.word(v+0x21C),common=self.word(v+0x220),osc_parameters=self.word(v+0x224),sample=self.word(v+0x20),key=self.word(v+0x28),
                key_controls=self.word(v+0x228),release=self.a.uc.mem_read(v+0x20D,1)[0],state_sha256=hashlib.sha256(self.a.uc.mem_read(v,588)).hexdigest()))
            rows[-1].update(delay=sh(bytes(self.a.uc.mem_read(v+0x208,2)),0),wait=self.word(v+0x234),pair=self.word(v+0x218),partner=self.word(v+0x230))
        return rows
    def check_note(self,note,velocity):
        a=self.a;patch=self.word(self.context+8);record=bytes(a.uc.mem_read(patch,2140));expected=[];expected_calls=[]
        self.patch=patch;self.record=record
        for j in range(2 if record[0x508]&7==1 else 1):
            self.osc=self.oscs[0][j];self.oscillator=j
            if record[0x508]&7==2:
                encoded=h(record,0x566);self.kit=encoded if encoded<58 else encoded-96;self.kitptr=self.kitbase+8728*self.kit
                self.kitraw=bytes(a.uc.mem_read(self.kitptr,8728));self.remap=list(struct.unpack('<128b',a.uc.mem_read(self.osc+24,128)));self.special=bool(a.uc.mem_read(0xC1B5719C,1)[0])
                layers=GMDrums.expected_layers(self,note,velocity) if encoded>=96 else DrumRig.expected_layers(self,note,velocity)
            else:layers=MelodicRig.expected_layers(self,note,velocity)
            valid=[];failed=None
            for row in layers:
                if row['layer']==failed:continue
                good=row['valid'] and (row.get('region') is not None if 'region' in row else True)
                if not good:failed=row['layer']
                else:valid.append(dict(osc=j,**row))
            expected+=valid;expected_calls.append(j)
        self.prepared.clear();self.started.clear();self.sample_starts.clear();self.writes.clear();self.note_events.clear();self.kills.clear();self.releasing.clear();self.osc_calls.clear()
        self.send(0x97,note,velocity)
        assert [x['osc'] for x in self.osc_calls]==expected_calls,(self.osc_calls,expected_calls)
        assert len(self.started)==len(expected),(note,velocity,self.started,expected)
        assert len(self.note_events)>=len(self.started)
        starts={x['address']:x for x in self.started};rows=[]
        for actual,wanted in zip(self.started,expected):
            v=actual['address'];slot=(v-self.voices)//588;osc=wanted['osc'];params=patch+0x564+380*osc
            assert (self.word(v+0x21C),self.word(v+0x220),self.word(v+0x224))==(patch,patch+0x520,params)
            assert self.word(v+8)==self.context and self.word(v+12)==self.channel
            if 'region' in wanted:
                region=wanted['region'];rb=self.f.data[0x492C28+20*region:0x492C28+20*(region+1)];sample=h(rb,0)
                desc=record[0x564+380*osc+8*wanted['slot']:0x56C+380*osc+8*wanted['slot']]
                level=desc[4]*wanted['weight']>>15;gain=self.math.multisample_gain(level,sb(rb,8),0)
                assert actual['region_ptr']==BASE+0x492C28+20*region
                assert (actual['layer_level'],actual['root'],actual['tune'],actual['pitch'])==(level,sb(rb,4)<<8,sh(rb,6),wanted['pitch'])
            else:
                sample=wanted['sample'];key=wanted['key'];keyptr=self.kitptr+24+68*key;desc=bytes(a.uc.mem_read(keyptr+12*wanted['slot'],12));drum=self.f.data[0x408BFC+32*wanted['drumsample']:0x408BFC+32*(wanted['drumsample']+1)]
                level=127*wanted['weight']>>15;gain=self.math.multisample_gain(level,sb(desc,4),sb(drum,28))
                assert (actual['key_ptr'],actual['desc_ptr'])==(keyptr,keyptr+12*wanted['slot'])
                assert (actual['layer_level'],actual['root'],actual['tune'],actual['pitch'],actual['level_correction'])==(level,60*256,2*(100*sb(desc,6)+sb(desc,7)),wanted['pitch'],sb(desc,4))
            assert actual['sample_ptr']==BASE+0x410ABC+64*sample
            pair_type=self.word(v+0x218);assert self.half(v+0x200)==(0 if pair_type==2 else gain)
            if pair_type==1:
                partner=self.word(v+0x230);assert partner in starts and self.word(partner+0x230)==v
                for at,n in [(0xBC,48),(0x120,48),(0x15C,100),(0xEC,51)]:assert bytes(a.uc.mem_read(v+at,n))==bytes(a.uc.mem_read(partner+at,n))
            registers={}
            if v in self.sample_starts:
                sample_raw=self.f.data[0x410ABC+64*sample:0x410ABC+64*(sample+1)];offset,boundary=bytes(a.uc.mem_read(v+0x20A,2));reverse=a.uc.mem_read(v+0x20C,1)[0]
                field=12 if not offset else 56 if offset-boundary+8==7 else 60 if offset-boundary+8==8 else 16 if offset==1 else 32+4*(offset-1)
                flags=sample_raw[7];start=w(sample_raw,20);loop=w(sample_raw,field)
                if flags&8:
                    loop=w(sample_raw,24)
                    if flags&32:start=w(sample_raw,12)
                    elif reverse:flags|=32
                elif reverse:start=w(sample_raw,28);loop=w(sample_raw,32);flags|=40
                registers={0x200:((flags>>2)&14)|(flags&1),0x208:start,0x20C:(w(sample_raw,24)-1)&0xFFFFFFFF,0x210:loop}
                assert {off:value for tg,off,value in self.writes if tg==slot and off in registers}==registers
            rows.append(dict(voice_slot=slot,osc=osc,sample=sample,weight=wanted['weight'],gain=self.half(v+0x200),pair=pair_type,program_pointer=patch,osc_pointer=params,started=v in self.sample_starts,sample_registers={hex(k):v for k,v in registers.items()}))
        assert self.word(self.manager+0x48)==self.capacity-len(self.active_slots())
        return dict(note=note,velocity=velocity,voices=rows,active=self.snapshot(),kills=list(self.kills),tg_start_calls=len(self.sample_starts))
    def check_off(self,note):
        a=self.a;before=self.snapshot();expected=[v for v in before if v['note']==note and v['flags']&128];self.releasing.clear()
        amps={v['slot']:bytes(a.uc.mem_read(self.voices+588*v['slot']+0x15C,100)) for v in expected}
        self.send(0x87,note,64);after=self.snapshot();by_slot={v['slot']:v for v in after}
        assert sorted(self.releasing)==sorted(v['slot'] for v in expected),(self.releasing,expected)
        for v in expected:
            flags=(v['flags']&~0x82)|1
            if v['delay']<0:flags|=8
            elif v['release']:
                if v['delay'] or v['wait'] or flags&8:flags=(flags&~9)|4
                else:flags|=5
            out=by_slot[v['slot']];assert out['flags']&0x8D==flags&0x8D,(v,out,flags)
            if v['release'] and v['delay']>=0 and (v['delay'] or v['wait'] or v['flags']&8):assert (out['delay'],out['wait'],out['pair'],out['partner'])==(0,0,0,0)
            if not v['release']:assert amps[v['slot']]==bytes(a.uc.mem_read(self.voices+588*v['slot']+0x15C,100))
        return dict(note=note,called_slots=sorted(self.releasing),voices=after)
    def trace(self,old,new,velocity,mode):
        self.cold_start(mode);self.choose(*old);first=self.check_note(48,velocity)
        self.cc(7,99);self.send(0xE7,0,96)
        voice_pool=bytes(self.a.uc.mem_read(self.voices,588*self.capacity));old_members=self.active_slots()
        change=self.choose(*new);assert bytes(self.a.uc.mem_read(self.voices,588*self.capacity))==voice_pool
        assert self.active_slots()==old_members;old_snapshot=self.snapshot()
        # The channel bend survives; only the timbre's bend is reset by Program Change.
        assert sh(bytes(self.a.uc.mem_read(self.channel+0xFA,2)),0)==16384
        assert [sh(bytes(self.a.uc.mem_read(t+0x94,2)),0) for t in self.ts]==[0,0,16384]
        second=self.check_note(64,velocity);off_old=self.check_off(48);off_new=self.check_off(64)
        # Every still-active voice retains the immutable source assigned at its own NoteOn.
        origins={v['voice_slot']:(v['program_pointer'],v['osc_pointer']) for event in [first,second] for v in event['voices']}
        for v in self.snapshot():assert (v['program'],v['osc_parameters'])==origins[v['slot']]
        return dict(old=list(old),new=list(new),mode=mode,velocity=velocity,first=first,change=change,old_voices_after_change=old_snapshot,
                    pool_unchanged_on_change=True,second=second,off_old=off_old,off_new=off_new)

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('MIDI-note-to-timbre',0x274590,0x2746C8),('MIDI-timbre-to-OSC',0x2737F8,0x2738F0)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm:return
    assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    raw=PRELOAD.read_bytes();gm=sources();r=Rig(f,raw,gm)
    if args.smoke:
        row=r.trace((0,0),(0,61),100,3);print(json.dumps(dict(passed=True,old_voices=len(row['first']['voices']),new_voices=len(row['second']['voices']),pool_unchanged=row['pool_unchanged_on_change'],old_off=row['off_old']['called_slots'],new_off=row['off_new']['called_slots']),indent=2));return
    presets=[(0,0),(0,11),(0,61),(1,97),(2,1),(5,36),(5,42),(10,0),(10,11),(11,0),(20,0),(20,56)]
    traces=[]
    for mode,velocity in itertools.product([0,3],[1,64,127]):
        for old,new in itertools.product(presets,repeat=2):
            try:traces.append(r.trace(old,new,velocity,mode))
            except Exception as error:raise AssertionError(dict(old=old,new=new,velocity=velocity,mode=mode)) from error
        print(json.dumps(dict(mode=mode,velocity=velocity,traces=len(traces))),flush=True)
    counts=dict(traces=len(traces),note_ons=2*len(traces),note_offs=2*len(traces),program_changes=2*len(traces),
        initialized_voices=sum(len(t[event]['voices']) for t in traces for event in ['first','second']),tg_starts=sum(t[event]['tg_start_calls'] for t in traces for event in ['first','second']))
    result=dict(passed=True,smoke_only=False,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_midi_program_load.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py']},
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA)],counts=counts,presets=presets,traces=traces,
        boundaries=['Native271500/26EC34/274590/273D4C/2737F8/1F62F0 and original selection/allocation/control initialization/TG start execute for every NoteOn; NoteOff uses native timbre/OSC/manager release path',
            '32-slot pool is initialized once per trace; no pool, OSC, channel or controller reinitialization occurs between first NoteOn, Program Change, second NoteOn and both NoteOffs',
            'Independent selection/gain/sample-register models inspect all actual voices; every old588-byte slot and all pool slots compare byte-for-byte across Program Change; immutable source pointers persist after later notes and releases',
            'Original Part/Program mode and OSC selection remain active; channel7 enables only primary timbre0 for notes, with two primary timbres receiving Program Change and one secondary retaining controllers',
            'Controlled global equal-temperament data and Part key/velocity ranges; native filtering, mode and controller arithmetic execute',
            'Inherited storage getter/TG/allocator/exception boundaries; additional note-display callbacksD55B4/D58C0/324CC/54C74/54E40 and OS priority get/set2CD2AC/2CD2A0 intercepted',
            'No normal control refresh, voice exhaustion/recycling, application global-channel Program queue, host audio or TG audio execution is claimed'])
    (OUT/'midi-voice-handoff-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=counts),indent=2))
if __name__=='__main__':main()
