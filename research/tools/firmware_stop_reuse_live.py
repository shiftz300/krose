#!/usr/bin/env python3
"""Continuous all-off/reuse: native RW-zero-page vs portable empty unlink."""
import argparse,itertools,json
from pathlib import Path
from firmware_midi_all_off import Rig,compare,read
from firmware_stop_reuse import ModelRig,check_lists
from firmware_stop_reuse_port import make_unlink_adapter
from firmware_midi_program_load import sha
from firmware_gm_programs import sources,IMAGE,IMAGE_SHA
from firmware_voice_lfo import PRELOAD,OUT,w
from program_firmware import Firmware,BASE,FW_SHA
from layout import PRODUCT_ROOT as ROOT

PAIRS=[((0,0),(0,61)),((2,1),(0,61)),((5,36),(0,0)),((5,42),(0,0)),((10,0),(20,0)),((20,0),(10,0))]
def cold_catalog(r):
    result={}
    for preset,mode,note in itertools.product(sorted({new for old,new in PAIRS}),[0,3],[67,72]):
        r.setup(preset,8,mode,True);event=r.note_and_remember(note,100)
        result[preset,mode,note]=dict(preset=preset,mode=mode,note=note,event=event,startup=r.started.copy())
    assert len(result)==16;return result
def note_again(r,note,cold):
    before_gain=[r.half(r.voices+588*i+0x200) for i in range(r.capacity)];old_capture=r.capture;r.capture=False
    r.a.uc.mem_write(0x111E0000,bytes(0x10000))
    for xs in [r.prepared,r.started,r.sample_starts,r.writes,r.note_events,r.kills,r.releasing,r.osc_calls]:xs.clear()
    from unicorn import UC_HOOK_CODE
    materialized=[];hook=r.a.uc.hook_add(UC_HOOK_CODE,lambda uc,address,size,user:materialized.append(r.prepared[-1].copy()),begin=BASE+0x1F7278,end=BASE+0x1F7278)
    try:
        r.send(0x97,note,100);r.bind_extra();expected=cold['event']['voices'];rows=[];starts={x['address']:x for x in r.started}
        assert len(r.started)==len(materialized)==len(expected)==len(cold['startup'])
        for actual,prepared,wanted,original in zip(r.started,materialized,expected,cold['startup']):
            v=actual['address'];slot=(v-r.voices)//588;pair=r.word(v+0x218);gain=r.half(v+0x200)
            assert pair==wanted['pair'] and prepared['weight']==wanted['weight']
            assert set(actual)==set(original)
            for key in original:
                if key!='address':assert actual[key]==original[key],(key,actual,original)
            assert (r.word(v+0x21C),r.word(v+0x224))==(wanted['program_pointer'],wanted['osc_pointer'])
            assert r.word(v+0x20)==BASE+0x410ABC+64*wanted['sample']
            assert gain==(before_gain[slot] if pair==2 else wanted['gain'])
            if pair==1:
                partner=r.word(v+0x230);assert partner in starts and r.word(partner+0x230)==v
                for at,n in [(0xBC,48),(0x120,48),(0x15C,100),(0xEC,51)]:assert read(r.a,v+at,n)==read(r.a,partner+at,n)
            sample=r.f.data[0x410ABC+64*wanted['sample']:0x410ABC+64*(wanted['sample']+1)]
            offset,boundary=read(r.a,v+0x20A,2);reverse=read(r.a,v+0x20C,1)[0]
            flags=sample[7];start=w(sample,20)
            field=12 if not offset else 56 if offset-boundary+8==7 else 60 if offset-boundary+8==8 else 16 if offset==1 else 32+4*(offset-1)
            loop=w(sample,field)
            if flags&8:
                loop=w(sample,24)
                if flags&32:start=w(sample,12)
                elif reverse:flags|=32
            elif reverse:start=w(sample,28);loop=w(sample,32);flags|=40
            registers={0x200:((flags>>2)&14)|(flags&1),0x208:start,0x20C:(w(sample,24)-1)&0xFFFFFFFF,0x210:loop} if v in r.sample_starts else {}
            assert {off:value for tg,off,value in r.writes if tg==slot and off in registers}==registers
            assert (v in r.sample_starts)==wanted['started']
            r.origins[slot]=(wanted['program_pointer'],wanted['osc_pointer'])
            rows.append(dict(voice_slot=slot,sample=wanted['sample'],weight=prepared['weight'],pair=pair,gain=gain,secondary_gain_before=before_gain[slot] if pair==2 else None,
                started=v in r.sample_starts,sample_registers={hex(k):val for k,val in registers.items()}))
        check_lists(r)
        return dict(note=note,velocity=100,voices=rows,active=r.snapshot(),tg_start_calls=len(r.sample_starts))
    finally:r.a.uc.hook_del(hook);r.capture=old_capture

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');parser.add_argument('--smoke',action='store_true');args=parser.parse_args()
    if not args.verify_arm:return
    f=Firmware();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    raw=PRELOAD.read_bytes();gm=sources();native=Rig(f,raw,gm);model=ModelRig(f,raw,gm);oracle=Rig(f,raw,gm);catalog=cold_catalog(oracle)
    prior_path=OUT/'midi-all-off-check.json';prior=json.loads(prior_path.read_text());assert prior['passed'] and not prior['live_continuity_complete']
    old={(tuple(t['old']),tuple(t['new']),t['controller'],t['pedals'],t['mode']):t for t in prior['live']}
    from unicorn import UC_HOOK_MEM_WRITE
    choices=itertools.product(PAIRS[:1],[120,123],[0,3],[3]) if args.smoke else itertools.product(PAIRS,[120,123],range(4),[0,3])
    traces=[]
    for (first,new),controller,pedals,mode in choices:
        source=5 if pedals&1 else 0;initial=native.setup_stop(first,new,mode,pedals);assert model.setup_stop(first,new,mode,pedals)==initial;compare(native,model)
        a=native.a;a.uc.mem_map(0,0x1000);seed=f.data[:0x1000];a.uc.mem_write(0,seed);writes=[];skipped=[];steps=[]
        hook=a.uc.hook_add(UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:writes.append(dict(address=address,size=size,value=value,pc=hex(a.get('PC')))),begin=0,end=0xFFF)
        model.guard_enabled=True;model.a.stubs[0x272414]=make_unlink_adapter(model.word,model.a.write,skipped)
        previous=old[first,new,controller,pedals,mode];prefix=0
        try:
            for update in range(48):
                events=[]
                for r,explicit in [(native,False),(model,True)]:
                    r.clear_capture();event={}
                    if update in [0,12,32]:event['off']=r.all_off(120 if update==32 else controller,127,source,explicit)
                    if update==8:r.cc(64,0);r.cc(66,0)
                    if update in [20,36]:event['note']=note_again(r,67 if update==20 else 72,catalog[new,mode,67 if update==20 else 72])
                    if update in [24,40]:r.send(0x87,67 if update==24 else 72,64)
                    events.append(event)
                assert events[0]==events[1];compare(native,model);check_lists(native);check_lists(model)
                for r in [native,model]:r.clear_capture();r.a.write(r.clock+4,123+20*update)
                elapsed=[0,1,3,20][update%4];native.a.call(0x1FD3CC,native.manager,elapsed);model.explicit_advance(elapsed);compare(native,model);check_lists(native);check_lists(model)
                native.clear_capture();model.clear_capture();native.a.call(0x1FE404,native.manager);model.explicit_poll();compare(native,model)
                links=check_lists(model);assert links==check_lists(native)
                commits=native.verify_commits();s=dict(update=update,event=events[0],state=native.voice_state(),commits=commits,lists=links);steps.append(s)
                if update<len(previous['steps']):
                    p=previous['steps'][update];assert s['state']==p['state'] and s['commits']==p['commits'],(first,new,controller,pedals,mode,update);prefix+=1
            assert len(steps)==48 and prefix==len(previous['steps'])
            assert [w['address'] for w in writes]==[4,0]*len(skipped)
            assert all(w['size']==4 and w['value']==0 and w['pc'] in ['0xc027242c','0xc0272430'] for w in writes)
            after=read(a,0,0x1000);assert after==(bytes(8)+seed[8:] if writes else seed)
            traces.append(dict(old=first,new=new,controller=controller,pedals=pedals,mode=mode,source=source,initial=initial,steps=steps,
                previous_prefix_updates=prefix,previous_reuse_fault=previous['reuse_fault'],native_zero_page_writes=writes,skipped_empty_nodes=skipped,software_states_and_io_equal=True,
                native_vector_prefix=after[:64].hex(),model_zero_page_mapped=False))
        finally:model.a.stubs.pop(0x272414);model.guard_enabled=False;a.uc.hook_del(hook);a.uc.mem_unmap(0,0x1000)
        print(json.dumps(dict(trace=len(traces),old=first,new=new,controller=controller,pedals=pedals,mode=mode,updates=48,empty_unlinks=len(skipped))),flush=True)
    counts=dict(traces=len(traces),updates=sum(len(t['steps']) for t in traces),commits=sum(len(s['commits']) for t in traces for s in t['steps']),
        note_events=sum('note' in s['event'] for t in traces for s in t['steps']),stop_events=sum('off' in s['event'] for t in traces for s in t['steps']),
        previous_prefix_updates=sum(t['previous_prefix_updates'] for t in traces),previous_fault_traces_completed=sum(bool(t['previous_reuse_fault']) for t in traces),
        skipped_empty_nodes=sum(len(t['skipped_empty_nodes']) for t in traces),native_zero_page_writes=sum(len(t['native_zero_page_writes']) for t in traces),cold_contexts=len(catalog))
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_stop_reuse.py','firmware_stop_reuse_port.py','firmware_midi_all_off.py','firmware_midi_parameters.py','firmware_midi_voice_refresh.py','firmware_midi_voice_handoff.py','firmware_midi_program_load.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py','firmware_voice_refresh.py']},
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA),dict(path=str(prior_path.relative_to(ROOT)),sha256=sha(prior_path)),
            dict(path=str((OUT/'stop-reuse-check.json').relative_to(ROOT)),sha256=sha(OUT/'stop-reuse-check.json'))],counts=counts,cold=list(catalog.values()),traces=traces,portable_continuity_complete=True,
        boundaries=['The original96 live all-off trajectories now run all48 updates: same six Program transitions, CC120/123, modes0/3, allfour pedal combinations, source0/5 assigned by sustain condition and same32-slot pool',
            'Native side executes original MIDI, manager advance and poll with private RW zero-page; model side keeps zero-page unmapped, uses only the indexed-empty-unlink adapter, explicit primary-timbre/Pad stop helpers and independently scheduled original refresh kernels',
            'All prior full software spans, original visit/commit order, TG reads/writes and wait requests compare after each event/advance/poll; all32 candidate/member lists and free counts additionally checked at each phase',
            'Every previously completed update matches its stored native state and commit record; previous failures remain immutable evidence and are reported as completed prefixes only',
            'New notes use16 independently validated cold source contexts covering both new keys and modes; materialized metadata, gains, reused secondary+200 retention, shared controls and TG sample registers checked without clearing live voices',
            'Scratch stack alone is normalized before outer NoteOn; two unknown auxiliary parameter bindings, TG amplitude/ready/score fixtures and storage/display/OS boundaries remain inherited',
            'Private vector-page writes are recorded and match omitted empty-unlink operations; actual device zero-page mapping and native application lifecycle are not established',
            'Complete applies only to this portable96-trace matrix. No actual DSP audio, exhaustive preset/stealing/Mono/Unison or occurrence-rate claim; no product or firmware changes'])
    if not args.smoke:(OUT/'stop-reuse-live-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,smoke_only=args.smoke,counts=counts),indent=2))
if __name__=='__main__':main()
