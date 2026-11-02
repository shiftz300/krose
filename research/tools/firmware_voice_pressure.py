#!/usr/bin/env python3
"""Real MIDI exhaustion with native refresh and independently checked selection."""
import argparse,hashlib,itertools,json
from pathlib import Path
from firmware_midi_all_off import Rig,compare,read,pad_seed
from firmware_stop_reuse import ModelRig,check_lists
from firmware_stop_reuse_port import make_unlink_adapter
from firmware_gm_programs import sources,IMAGE,IMAGE_SHA
from firmware_voice_lfo import PRELOAD,OUT
from firmware_midi_program_load import sha
from program_firmware import Firmware,BASE,FW_SHA
from layout import PRODUCT_ROOT as ROOT

PRESETS=[(0,0),(0,11),(0,61),(20,0)]
KEYS=list(range(36,84))
CAPACITY=120
NOTE_SEQUENCE=KEYS*3
def score_values(profile):
    values=[0,4,5,9,300,300,65535,1000]
    return [0x1234]*CAPACITY if profile=='equal' else [values[(13*i+i//8)%len(values)] for i in range(CAPACITY)]

class SelectionObserver:
    def __init__(self,r):
        self.r=r;self.selections=[];self.pending=None;self.reclaims=[];self.reclaim=None
        from unicorn import UC_HOOK_CODE
        self.hooks=[r.a.uc.hook_add(UC_HOOK_CODE,self.observe,begin=BASE+off,end=BASE+off)
            for off in [0x1FC7F0,0x1FC884,0x1FC89C,0x1F8BF8,0x1FC9B4,0x1FC9CC]]
    def observe(self,uc,address,size,user):
        r=self.r;a=r.a;off=address-BASE
        if off==0x1FC7F0:
            assert self.pending is None
            p=a.get('R1');rows=[];seen=set()
            while r.word(p+8):
                assert p not in seen and len(seen)<r.capacity;seen.add(p)
                v=r.word(p+8);slot=(v-r.voices)//588;tg=read(a,v+0x1A,1)[0]
                assert 0<=slot<r.capacity
                rows.append(dict(node=p,slot=slot,score=r.half(v+0x23C),active=bool(r.active_mask&(1<<tg))))
                p=r.word(p)
            expected=rows[0]['node'] if rows else 0;best=65535
            for row in rows:
                if row['active'] and row['score']<best:
                    expected=row['node'];best=row['score']
                    if best<=4:break
            self.pending=dict(candidates=rows,expected_node=expected)
        elif off==0x1FC884:
            assert self.pending is not None and a.get('R0')==self.pending['expected_node'],self.pending
            d=self.pending;rows=d['candidates']
            self.selections.append(dict(slots=[x['slot'] for x in rows],scores=[x['score'] for x in rows],active=[x['active'] for x in rows],
                selected_slot=next((x['slot'] for x in rows if x['node']==d['expected_node']),None)))
            self.pending=None
        elif off==0x1FC89C:
            assert self.reclaim is None
            v=a.get('R1');pair=r.word(v+0x218);partner=r.word(v+0x230)
            expected=([partner,v] if pair==2 else [v,partner]) if pair and partner else [v]
            self.reclaim=dict(slot=(v-r.voices)//588,available_before=r.word(r.manager+0x48),pair=pair,
                partner=(partner-r.voices)//588 if partner else None,was_active=bool(r.half(v+0x10)),
                expected_resets=[(p-r.voices)//588 for p in expected],resets=[])
            r.reclaimed_gains[(v-r.voices)//588]=r.half(v+0x200)
        elif off==0x1F8BF8 and self.reclaim is not None:
            self.reclaim['resets'].append((a.get('R0')-r.voices)//588)
        elif off in [0x1FC9B4,0x1FC9CC] and self.reclaim is not None:
            row=self.reclaim;assert row['resets']==row['expected_resets'],row
            for slot in row['resets']:
                v=r.voices+588*slot
                assert (r.half(v+0x10),r.word(v+0x218),r.word(v+0x230))==(0,0,0)
            row['available_after']=r.word(r.manager+0x48);self.reclaims.append(row);self.reclaim=None

class PressureRig(Rig):
    def __init__(self,*args):
        self.scores=[0x1234]*CAPACITY;self.command_mask=0;self.stop_acknowledgements=[];self.start_acknowledgements=[];self.reclaimed_gains={};super().__init__(*args)
    def observe(self,uc,address,size,user):
        before=self.active_mask;super().observe(uc,address,size,user)
        # Driver queues the actual start mask; activity begins at command2,
        # after any close/reset inside the parameter-programming entry.
        if address==BASE+0x1F9028:self.active_mask=before
    def cold_start(self,mode=3):
        # The inherited32-slot region cannot fit120 voices without overlapping
        # its node arrays. All live and cold references use these private spans.
        self.voices=0x110C0000;self.nodes=0x110E0000;self.members=0x110E1000;self.waitnodes=0x110E2000
        super().cold_start(mode);self.capacity=CAPACITY;a=self.a
        a.write(self.manager+0x3C,self.nodes,self.members,self.capacity,0)
        a.write(self.manager+0xCC,self.manager+0xCC,self.manager+0xCC,0,self.waitnodes,self.capacity)
        a.uc.mem_write(self.voices,bytes(self.capacity*588));a.call(0x1FEDE4)
        for i in range(self.capacity):
            v=self.voices+588*i;a.call(0x1F68D4,v);self.put8(v+0x16,i);self.put8(v+0x1A,i);a.write(v+0x1C,self.tg);a.write(v+0x240,0xFFFFFFFF)
            for p in [self.nodes,self.members,self.waitnodes]:a.write(p+12*i,0,0,v)
        a.call(0x1FBF4C,self.manager+12)
    def bus_write(self,a):
        off=a.get('R0')-self.tg;value=a.get('R1')
        if off in [0x230,0x234,0x238,0x23C]:
            shift=(off-0x230)*8;self.command_mask=(self.command_mask&~(0xFFFFFFFF<<shift))|(value<<shift)
        if off==0x22C:
            if value==1:
                before=self.active_mask;self.active_mask&=~self.command_mask
                self.stop_acknowledgements.append(dict(mask=self.command_mask,before=before,after=self.active_mask))
            elif value==2:
                before=self.active_mask;self.active_mask|=self.command_mask
                self.start_acknowledgements.append(dict(mask=self.command_mask,before=before,after=self.active_mask))
            self.command_mask=0
        return super().bus_write(a)
    def bus_read(self,a):
        if a.get('R0')-self.tg==0x428:
            self.reads.append(0x428);return self.scores[self.current_slot]
        return super().bus_read(a)
    def verify_commits(self):
        all_rows=self.commits;old_score=self.score;result=[]
        try:
            for row in all_rows:
                self.commits=[row];self.score=self.scores[row['voice']]
                result+=super().verify_commits()
                result[-1]['score_readback']=self.score
        finally:self.commits=all_rows;self.score=old_score
        return result

class PressureModel(PressureRig,ModelRig):pass

def catalog(r,presets):
    result={}
    for preset,note in itertools.product(presets,KEYS+[86,88]):
        r.setup(preset,8,3,True);event=r.note_and_remember(note,100)
        result[preset,note]=dict(event=event,startup=r.started.copy())
    return result

def pressure_note(r,note,cold):
    """Validate each construction before later OSCs may steal that same slot."""
    old_capture=r.capture;r.capture=False;r.a.uc.mem_write(0x111E0000,bytes(0x10000))
    for xs in [r.prepared,r.started,r.sample_starts,r.writes,r.note_events,r.kills,r.releasing,r.osc_calls]:xs.clear()
    from unicorn import UC_HOOK_CODE
    entries=[];starts=[];current_start=[None]
    def observe(uc,address,size,user):
        off=address-BASE;a=r.a
        if off==0x1F7278:
            v=a.get('R0');slot=(v-r.voices)//588
            entries.append(dict(address=v,slot=slot,prepared=r.prepared[-1].copy(),program=r.word(v+0x21C),osc=r.word(v+0x224),
                sample=r.word(v+0x20),gain=r.half(v+0x200),gain_before=r.reclaimed_gains[slot]))
        elif off==0x1F77C8:
            assert entries[-1]['address']==a.get('R6') and a.get('R0')==1
            entries[-1]['gain']=r.half(a.get('R6')+0x200)
        elif off==0x1F9028:
            v=a.get('R0');index=next(i for i in reversed(range(len(entries))) if entries[i]['address']==v)
            assert current_start[0] is None
            row=dict(index=index,start=len(r.writes));starts.append(row);current_start[0]=row
        elif off==0x1F9404:
            assert current_start[0] is not None
            current_start[0]['end']=len(r.writes);current_start[0]=None
    hooks=[r.a.uc.hook_add(UC_HOOK_CODE,observe,begin=BASE+off,end=BASE+off) for off in [0x1F7278,0x1F77C8,0x1F9028,0x1F9404]]
    try:
        r.send(0x97,note,100);r.bind_extra();wanted=cold['event']['voices']
        assert current_start[0] is None and len(entries)==len(r.started)==len(wanted)==len(cold['startup'])
        latest={entry['slot']:i for i,entry in enumerate(entries)};active=set(r.active_slots());rows=[]
        for index,(entry,actual,expected,original) in enumerate(zip(entries,r.started,wanted,cold['startup'])):
            v=entry['address'];slot=entry['slot'];pair=expected['pair']
            assert entry['program']==expected['program_pointer'] and entry['osc']==expected['osc_pointer']
            assert entry['sample']==BASE+0x410ABC+64*expected['sample'] and entry['prepared']['weight']==expected['weight']
            assert set(actual)==set(original)
            for key in original:
                if key!='address':assert actual[key]==original[key],(key,index,actual,original)
            assert entry['gain']==(entry['gain_before'] if pair==2 else expected['gain']),(index,entry,expected)
            sample_starts=[s for s in starts if s['index']==index];assert len(sample_starts)==int(expected['started'])
            registers={int(k,16):val for k,val in expected['sample_registers'].items()}
            for start in sample_starts:
                assert {off:val for tg,off,val in r.writes[start['start']:start['end']] if tg==slot and off in registers}==registers
            survives=slot in active and latest[slot]==index
            if survives:
                assert (r.word(v+0x21C),r.word(v+0x224),r.word(v+0x20),r.half(v+0x200))==(entry['program'],entry['osc'],entry['sample'],entry['gain'])
                assert r.word(v+0x218)==pair
                if pair==1:
                    partner=r.word(v+0x230);assert (partner-r.voices)//588 in active and r.word(partner+0x230)==v
                    for at,n in [(0xBC,48),(0x120,48),(0x15C,100),(0xEC,51)]:assert read(r.a,v+at,n)==read(r.a,partner+at,n)
            r.origins[slot]=(entry['program'],entry['osc'])
            rows.append(dict(construction=index,voice_slot=slot,sample=expected['sample'],osc=expected['osc'],weight=expected['weight'],pair=pair,gain=entry['gain'],
                gain_before=entry['gain_before'],started=bool(sample_starts),survived=survives,overwritten_by=latest[slot] if latest[slot]!=index else None,
                program_pointer=entry['program'],osc_pointer=entry['osc'],sample_registers={hex(k):v for k,v in registers.items()}))
        check_lists(r)
        return dict(note=note,velocity=100,voices=rows,tg_start_calls=len(starts),surviving_new_voices=sum(row['survived'] for row in rows),
            reused_within_call=sorted(slot for slot in latest if sum(e['slot']==slot for e in entries)>1))
    finally:
        for hook in hooks:r.a.uc.hook_del(hook)
        r.capture=old_capture

def compact_state(r):
    state=r.voice_state();voices=state.pop('voices')
    state.update(active_slots=[v['slot'] for v in voices],key_on_slots=[v['slot'] for v in voices if v['flags']&128],
        maximum_amp=max((v['amp'] for v in voices),default=0),
        control_state_sha256=hashlib.sha256(json.dumps(voices,sort_keys=True).encode()).hexdigest(),
        voice_pool_sha256=hashlib.sha256(read(r.a,r.voices,588*r.capacity)).hexdigest())
    return state

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');p.add_argument('--probe-failure',action='store_true')
    p.add_argument('--preset',nargs=2,type=int);p.add_argument('--merge',action='store_true');args=p.parse_args()
    if args.merge:
        parts=[];part_inputs=[]
        for preset in PRESETS:
            path=OUT/f'voice-pressure-part-{preset[0]}-{preset[1]}.json';part=json.loads(path.read_text())
            assert part['passed'] and not part['smoke_only'] and part['partial_preset']==list(preset) and part['tool_sha256']==sha(Path(__file__))
            for name,digest in part['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            for row in part['inputs']:assert row['sha256']==sha(ROOT/row['path'])
            assert part['counts']['traces']==8 and len(part['traces'])==8;parts.append(part)
            part_inputs.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path)))
        result=parts[0].copy();result['partial_preset']=None
        result['traces']=[t for part in parts for t in part['traces']];result['cold']=[t for part in parts for t in part['cold']]
        result['counts']={key:sum(part['counts'][key] for part in parts) for key in parts[0]['counts']}
        result['inputs']=parts[0]['inputs']+part_inputs
        (OUT/'voice-pressure-check.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(passed=True,counts=result['counts']),indent=2));return
    if not args.verify_arm:return
    f=Firmware();raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    gm=sources();native=PressureRig(f,raw,gm);model=PressureModel(f,raw,gm);oracle=Rig(f,raw,gm)
    presets=[tuple(args.preset)] if args.preset else [(0,11)] if args.probe_failure else PRESETS[:1] if args.smoke else PRESETS
    assert all(preset in PRESETS for preset in presets);cold=catalog(oracle,presets)
    observers=[SelectionObserver(r) for r in [native,model]]
    choices=[((0,11),1,False,'equal')] if args.probe_failure else [(presets[0],8,True,'varied')] if args.smoke else itertools.product(presets,[1,8],[False,True],['equal','varied'])
    from unicorn import UC_HOOK_MEM_WRITE
    traces=[]
    for preset,batch,pedal,profile in choices:
        for r,o in zip([native,model],observers):
            r.scores=score_values(profile);r.command_mask=0;r.setup(preset,batch,3,pedal);o.selections.clear();o.reclaims.clear();r.stop_acknowledgements.clear();r.start_acknowledgements.clear()
            r.put8(0xC1DCC2D8+0x1350,7)
            for ptr in [0x11079000,0xC165E21C,0xC17456AC]:r.put8(ptr+0x4F6,64)
            pad_seed(r.a)
            if pedal:r.cc(64,127)
        compare(native,model);a=native.a;a.uc.mem_map(0,0x1000);seed=f.data[:0x1000];a.uc.mem_write(0,seed);writes=[];skipped=[]
        hook=a.uc.hook_add(UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:writes.append(dict(address=address,size=size,value=value,pc=hex(a.get('PC')))),begin=0,end=0xFFF)
        model.guard_enabled=True;model.a.stubs[0x272414]=make_unlink_adapter(model.word,model.a.write,skipped);steps=[]
        try:
            nnotes=len(NOTE_SEQUENCE)
            for update in range(nnotes+32):
                results=[];selection_start=len(observers[0].selections);reclaim_start=len(observers[0].reclaims)
                for r,explicit in [(native,False),(model,True)]:
                    r.clear_capture();event={}
                    if update<nnotes:
                        note=NOTE_SEQUENCE[update];event['note']=pressure_note(r,note,cold[preset,note])
                    if update==nnotes:
                        for note in NOTE_SEQUENCE+[48]:r.send(0x87,note,64)
                        event['off_all_keys']=True
                    if update==nnotes+4:r.cc(64,0);event['pedal_off']=True
                    if update==nnotes+8:event['off']=r.all_off(120,127,0,explicit)
                    if update in [nnotes+12,nnotes+20]:
                        note=86 if update==nnotes+12 else 88;event['note']=pressure_note(r,note,cold[preset,note])
                    if update in [nnotes+16,nnotes+24]:r.send(0x87,86 if update==nnotes+16 else 88,64)
                    results.append(event)
                assert results[0]==results[1];compare(native,model);check_lists(native);check_lists(model)
                assert observers[0].selections==observers[1].selections and observers[0].reclaims==observers[1].reclaims
                assert native.stop_acknowledgements==model.stop_acknowledgements
                assert native.start_acknowledgements==model.start_acknowledgements
                for r in [native,model]:r.clear_capture();r.a.write(r.clock+4,123+20*update)
                elapsed=[0,1,3,20][update%4];native.a.call(0x1FD3CC,native.manager,elapsed);model.explicit_advance(elapsed);compare(native,model)
                native.clear_capture();model.clear_capture();native.a.call(0x1FE404,native.manager);model.explicit_poll();compare(native,model)
                links=check_lists(native);assert links==check_lists(model)
                steps.append(dict(update=update,event=results[0],state=compact_state(native),lists=links,commits=native.verify_commits(),
                    selection_range=[selection_start,len(observers[0].selections)],reclaim_range=[reclaim_start,len(observers[0].reclaims)]))
            assert all(o.pending is None and o.reclaim is None for o in observers)
            assert [w['address'] for w in writes]==[4,0]*len(skipped)
            assert all(w['size']==4 and w['value']==0 and w['pc'] in ['0xc027242c','0xc0272430'] for w in writes)
            assert read(a,0,0x1000)==(bytes(8)+seed[8:] if writes else seed)
            pressure=[row for row in observers[0].reclaims if row['was_active']]
            if preset!=(20,0):
                assert any(s['state']['available']==0 for s in steps[:nnotes])
                assert pressure and any(row['available_before']==0 for row in pressure)
            assert steps[nnotes+8]['state']['available']==CAPACITY
            traces.append(dict(preset=preset,batch=batch,pedal=pedal,score_profile=profile,capacity=CAPACITY,scores=native.scores,steps=steps,
                selections=observers[0].selections.copy(),reclaims=observers[0].reclaims.copy(),
                stop_acknowledgements=native.stop_acknowledgements.copy(),start_acknowledgements=native.start_acknowledgements.copy(),
                native_zero_page_writes=writes,skipped_empty_nodes=skipped,software_states_and_io_equal=True))
        except Exception as error:
            failure=dict(passed=False,preset=preset,batch=batch,pedal=pedal,profile=profile,update=update,firmware_sha256=FW_SHA,tool_sha256=sha(Path(__file__)),
                expected=cold.get((preset,NOTE_SEQUENCE[update] if update<nnotes else 86)),started=native.started,prepared=native.prepared,note_events=native.note_events,
                final_slots=[dict(address=x['address'],slot=(x['address']-native.voices)//588,program=native.word(x['address']+0x21C),osc=native.word(x['address']+0x224),pair=native.word(x['address']+0x218)) for x in native.started],
                selections=observers[0].selections[selection_start:],reclaims=observers[0].reclaims[reclaim_start:])
            (OUT/f'voice-pressure-failure-{preset[0]}-{preset[1]}.json').write_text(json.dumps(failure,indent=2)+'\n')
            raise AssertionError(dict(preset=preset,batch=batch,pedal=pedal,profile=profile,update=update)) from error
        finally:model.a.stubs.pop(0x272414);model.guard_enabled=False;a.uc.hook_del(hook);a.uc.mem_unmap(0,0x1000)
        print(json.dumps(dict(trace=len(traces),preset=preset,batch=batch,pedal=pedal,profile=profile,updates=len(steps),active_reclaims=len(pressure))),flush=True)
    counts=dict(traces=len(traces),updates=sum(len(t['steps']) for t in traces),commits=sum(len(s['commits']) for t in traces for s in t['steps']),
        note_events=sum('note' in s['event'] for t in traces for s in t['steps']),selection_calls=sum(len(t['selections']) for t in traces),
        reclaims=sum(len(t['reclaims']) for t in traces),active_reclaims=sum(r['was_active'] for t in traces for r in t['reclaims']),
        paired_active_reclaims=sum(r['was_active'] and r['pair']!=0 for t in traces for r in t['reclaims']),
        stop_acknowledgements=sum(len(t['stop_acknowledgements']) for t in traces),
        start_acknowledgements=sum(len(t['start_acknowledgements']) for t in traces),
        intranote_reuse_events=sum(bool(s['event'].get('note',{}).get('reused_within_call')) for t in traces for s in t['steps']),
        overwritten_constructions=sum(row['overwritten_by'] is not None for t in traces for s in t['steps'] for row in s['event'].get('note',{}).get('voices',[])),
        discarded_constructions=sum(not row['survived'] for t in traces for s in t['steps'] for row in s['event'].get('note',{}).get('voices',[])),
        native_zero_page_writes=sum(len(t['native_zero_page_writes']) for t in traces),skipped_empty_nodes=sum(len(t['skipped_empty_nodes']) for t in traces),cold_contexts=len(cold))
    helpers=['firmware_stop_reuse_live.py','firmware_stop_reuse.py','firmware_stop_reuse_port.py','firmware_midi_all_off.py','firmware_midi_parameters.py','firmware_midi_voice_refresh.py','firmware_midi_voice_handoff.py','firmware_midi_program_load.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py','firmware_voice_refresh.py']
    result=dict(passed=True,smoke_only=args.smoke or args.probe_failure,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in helpers},inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA)],
        partial_preset=args.preset,counts=counts,traces=traces,cold=[dict(preset=k[0],note=k[1],**v) for k,v in cold.items()],
        boundaries=['120-slot same live pool receives144 consecutive real MIDI NoteOns with normal original advance/poll between each; four factory/GM choices, mode3, batch1/8, sustain off/on and two controlled TG score profiles',
            'Native manager scheduling compares after every event/advance/poll against independently ordered original kernels; all inherited full software spans, TG I/O, event order, commits and lists compare',
            'Every original1FC7F0 candidate selection independently computed from actual ordered candidate nodes, cached unsigned scores and controlled active bits; strict lower score, early exit <=4, first-node fallback',
            'Original pair reclaim/reset executes; observed reset order, cleared flags/pair fields and free count recorded. At each note reused source metadata, gain retention, stereo control copying and TG sample words compare against independently checked cold contexts',
            'Source metadata is checked at each1F7278 entry, gain at control-init return1F77C8 and TG sample writes inside each1F9028..1F9404 invocation; a later OSC can steal an earlier allocation in the same NoteOn, so only latest still-active constructions are checked as final survivors',
            'TG score readback varies by actual selected slot; independent control-word arithmetic still checks every commit. Active/ready/amplitude inputs remain controlled, no physical meaning assigned to score',
            'The bus fixture acknowledges original22C command1 by immediately clearing its latched230..23C target bits, and command2 by setting those bits. Activity is not asserted at parameter-programming entry. This chosen completion response lets original reclaim wait loops terminate; it does not establish silicon command latency or internal TG semantics',
            'After144 notes, release every occurrence of tested keys, drop sustain, CC120, then two further notes and releases in the same pool; zero-page native writes and portable empty-unlink omission remain explicitly paired',
            'Private voice/node spans relocated to nonoverlapping memory for120 voices. Cold references and live calls normalize only scratch stack before outer NoteOn. Unknown auxiliary bindings remain inherited; no original DSP audio, physical timing, Mono/Unison or exhaustive preset claim',
            'Research-only additions, frozen helpers and product files unchanged'])
    if not args.smoke and not args.probe_failure:
        destination=OUT/(f'voice-pressure-part-{args.preset[0]}-{args.preset[1]}.json' if args.preset else 'voice-pressure-check.json')
        destination.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,smoke_only=result['smoke_only'],counts=counts),indent=2))
if __name__=='__main__':main()
