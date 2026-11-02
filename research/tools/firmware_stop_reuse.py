#!/usr/bin/env python3
"""Minimal native stereo stop/reuse diagnosis; experimental edits stay explicit."""
import argparse,collections,contextlib,io,itertools,json,struct
from pathlib import Path
from firmware_midi_all_off import Rig,read
from firmware_midi_voice_refresh import compare as compare_live
from firmware_stop_reuse_port import make_unlink_adapter
from firmware_midi_program_load import sha
from firmware_gm_programs import sources,IMAGE,IMAGE_SHA
from firmware_voice_lfo import PRELOAD,OUT
from firmware_inspect import inspect
from program_firmware import Firmware,BASE,FW_SHA
from layout import PRODUCT_ROOT as ROOT
HARD=['cc120','timbre','osc','list','slots']
class ModelRig(Rig):
    guard_enabled=False
    def observe(self,uc,address,size,user):
        if self.guard_enabled and address==BASE+0x272414:return
        super().observe(uc,address,size,user)
def state(r):
    rows=[]
    for i in range(r.capacity):
        v=r.voices+588*i;node=r.members+12*i
        rows.append(dict(slot=i,flags=r.half(v+0x10),pair=r.word(v+0x218),partner=r.word(v+0x230),member=[r.word(node),r.word(node+4)]))
    return dict(available=r.word(r.manager+0x48),active=r.active_slots(),tg_active=r.active_mask,voices=rows)
def check_lists(r):
    seen=set();assignment=r.manager+12
    for offset in [0,12,24,36]:
        head=assignment+offset;p=r.word(head);previous=head;local=set()
        while p!=head:
            assert r.nodes<=p<r.nodes+12*r.capacity and (p-r.nodes)%12==0 and p not in seen
            assert r.word(p+4)==previous;seen.add(p);local.add(p);previous=p;p=r.word(p)
        assert r.word(head+4)==previous
    assert len(seen)==r.capacity
    active=set(r.active_slots());assert r.word(r.manager+0x48)==r.capacity-len(active)
    for i in range(r.capacity):
        node=r.members+12*i
        assert bool(r.word(node))==bool(r.word(node+4))==(i in active)
    return dict(candidate_nodes=len(seen),active_nodes=len(active),available=r.word(r.manager+0x48))
def stop(r,action):
    if action in ['cc120','cc123']:r.cc(120 if action=='cc120' else 123,0)
    elif action=='timbre':r.a.call(0x2732A0,r.context)
    elif action=='osc':
        for osc in r.oscs[0]:r.a.call(0x1F67C4,osc,r.context,4,0)
    elif action=='list':
        for osc in r.oscs[0]:r.a.call(0x1FDC2C,r.manager,r.word(osc+0x490))
    elif action=='slots':
        for slot in r.active_slots():r.a.call(0x1FD53C,r.manager,r.voices+588*slot)
    else:assert action=='none'
def case(r,preset,mode,velocity,action,perturbation='none'):
    initial=r.setup(preset,8,mode,False);r.bad_unlinks.clear();r.stop_ops.clear();r.kills.clear();r.releasing.clear()
    before=state(r);check_lists(r);stop(r,action);after=state(r);links=check_lists(r)
    paired=[v for v in before['voices'] if v['slot'] in before['active'] and v['pair'] and v['partner']]
    if action in HARD:
        assert after['active']==[] and after['available']==r.capacity and after['tg_active']==0,(preset,mode,velocity,action,after['active'],after['available'],hex(after['tg_active']))
        assert sorted(r.kills)==before['active']
        for v in before['voices']:
            if v['slot'] not in before['active']:continue
            out=after['voices'][v['slot']];assert out['flags']==0 and out['member']==[0,0]
            assert (out['pair'],out['partner'])==(v['pair'],v['partner'])
    else:assert after['active']==before['active']
    # These counterfactual edits test the two guards in1FC89C. They are never
    # installed as a recovery rule, applied to native baselines, or called a fix.
    edits=[]
    if perturbation!='none':
        assert action=='cc120' and paired
        fields={'clear_type':[0x218],'clear_partner':[0x230],'clear_both':[0x218,0x230]}[perturbation]
        pool_before=read(r.a,r.voices,588*r.capacity);lists_before=[read(r.a,p,n) for p,n in [(r.manager,0x100),(r.nodes,12*r.capacity),(r.members,12*r.capacity),(r.waitnodes,12*r.capacity)]]
        expected=bytearray(pool_before)
        for v in paired:
            for offset in fields:
                at=588*v['slot']+offset;old=expected[at:at+4];expected[at:at+4]=bytes(4);r.a.write(r.voices+at,0)
                edits.append(dict(slot=v['slot'],offset=hex(offset),before=old.hex(),after='00000000'))
        assert read(r.a,r.voices,588*r.capacity)==bytes(expected)
        assert lists_before==[read(r.a,p,n) for p,n in [(r.manager,0x100),(r.nodes,12*r.capacity),(r.members,12*r.capacity),(r.waitnodes,12*r.capacity)]]
    r.bad_unlinks.clear();r.kills.clear();r.clear_capture();fault=None;note=None
    try:note=r.note_and_remember(67,velocity)
    except RuntimeError:
        fault=r.a.memory_fault
        assert fault==dict(access=20,address='0x4',bytes=4,pc='0xc027242c') and r.bad_unlinks
        last=r.bad_unlinks[-1];assert last['head']==hex(r.manager+0x40) and last['caller']=='0xc01fc760' and last['node'][:2]==[0,0]
        fault=dict(memory=fault,unlink=last,partial=state(r))
    expected_fault=bool(paired) and action in HARD and perturbation=='none'
    assert bool(fault)==expected_fault,(preset,mode,velocity,action,perturbation,paired,fault)
    if not fault:
        final_lists=check_lists(r);active=set(r.active_slots())
        for v in r.snapshot():
            if v['pair']:
                other=(v['partner']-r.voices)//588;assert other in active
                assert r.word(v['partner']+0x230)==r.voices+588*v['slot']
    else:final_lists=None
    return dict(preset=preset,mode=mode,velocity=velocity,action=action,perturbation=perturbation,initial=initial,before=before,after_stop=after,after_stop_lists=links,
        paired_slots=[v['slot'] for v in paired],edits=edits,reuse_fault=fault,note=note,startup=r.started.copy(),final=state(r),final_lists=final_lists)
def zero_page_probe(r,preset,f):
    r.setup(preset,8,3,False);r.bad_unlinks.clear();stop(r,'cc120');stopped=state(r);check_lists(r)
    assert not stopped['active'] and any(v['pair'] and v['partner'] for v in stopped['voices'])
    from unicorn import UC_HOOK_MEM_WRITE
    a=r.a;writes=[];a.uc.mem_map(0,0x1000);seed=f.data[:0x1000];a.uc.mem_write(0,seed)
    hook=a.uc.hook_add(UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:writes.append(dict(address=address,size=size,value=value,pc=hex(a.get('PC')))),begin=0,end=0xFFF)
    try:
        note=r.note_and_remember(67,100);links=check_lists(r);after=read(a,0,0x1000)
        assert writes and r.bad_unlinks
        assert all(x['size']==4 and x['value']==0 and (x['address'],x['pc']) in [(4,'0xc027242c'),(0,'0xc0272430')] for x in writes),writes
        assert after[:8]==bytes(8) and after[8:]==seed[8:]
        result=dict(preset=preset,mode=3,velocity=100,native_pair_fields_unchanged_before_reuse=True,stopped=stopped,note=note,final=state(r),final_lists=links,
            page_mapping='Private RW page0, seeded from the first4096 application-image bytes; actual runtime zero-page mapping is not established',
            vector_before=seed[:64].hex(),vector_after=after[:64].hex(),writes=writes,empty_unlinks=r.bad_unlinks.copy())
    finally:a.uc.hook_del(hook);a.uc.mem_unmap(0,0x1000)
    return result
def queued_reuse_probe(r,pedals):
    initial=r.setup_stop((2,1),(0,61),3,pedals);r.all_off(120,127,5 if pedals&1 else 0);stopped=state(r);check_lists(r);attempts=[]
    for note in [67,68,69,70]:
        r.bad_unlinks.clear()
        try:
            event=r.note_and_remember(note,100);attempts.append(dict(note=note,result=event,lists=check_lists(r),fault=None))
        except RuntimeError:
            assert r.a.memory_fault==dict(access=20,address='0x4',bytes=4,pc='0xc027242c') and r.bad_unlinks
            attempts.append(dict(note=note,result=None,lists=None,fault=dict(memory=r.a.memory_fault,unlink=r.bad_unlinks[-1],partial=state(r))));break
    assert len(attempts)==3 and [v['voice_slot'] for x in attempts[:2] for v in x['result']['voices']]==[2,3]
    assert attempts[2]['note']==69 and attempts[2]['fault']
    return dict(old=[2,1],new=[0,61],mode=3,pedals=pedals,initial=initial,stopped=stopped,attempts=attempts)
def reuse_note(r,note,velocity,cold):
    # The older cold-start checker assumes secondary+200 is0. Native75D0
    # copies shared controls but leaves that field untouched on reuse.
    before_gain=[r.half(r.voices+588*i+0x200) for i in range(r.capacity)]
    old_capture=r.capture;r.capture=False;r.a.uc.mem_write(0x111E0000,bytes(0x10000))
    for xs in [r.prepared,r.started,r.sample_starts,r.writes,r.note_events,r.kills,r.releasing,r.osc_calls]:xs.clear()
    from unicorn import UC_HOOK_CODE
    materialized=[]
    hook=r.a.uc.hook_add(UC_HOOK_CODE,lambda uc,address,size,user:materialized.append(r.prepared[-1].copy()),begin=BASE+0x1F7278,end=BASE+0x1F7278)
    try:
        r.send(0x97,note,velocity);r.bind_extra();expected=cold['note']['voices'];rows=[];starts={x['address']:x for x in r.started}
        assert len(r.started)==len(materialized)==len(expected)==len(cold['startup']),(len(r.started),len(materialized),len(expected),len(cold['startup']))
        for actual,prepared,wanted,original in zip(r.started,materialized,expected,cold['startup']):
            v=actual['address'];slot=(v-r.voices)//588;pair=r.word(v+0x218);gain=r.half(v+0x200)
            assert pair==wanted['pair'] and prepared['weight']==wanted['weight']
            for key in ['sample_ptr','region_ptr','layer_level','root','tune','pitch']:assert actual[key]==original[key],(key,actual,original)
            assert (r.word(v+0x21C),r.word(v+0x224))==(wanted['program_pointer'],wanted['osc_pointer'])
            assert r.word(v+0x20)==BASE+0x410ABC+64*wanted['sample']
            assert gain==(before_gain[slot] if pair==2 else wanted['gain']),(slot,pair,gain,before_gain[slot],wanted['gain'])
            if pair==1:
                partner=r.word(v+0x230);assert partner in starts and r.word(partner+0x230)==v
                for at,n in [(0xBC,48),(0x120,48),(0x15C,100),(0xEC,51)]:assert read(r.a,v+at,n)==read(r.a,partner+at,n)
            assert (v in r.sample_starts)==wanted['started']
            registers={int(k,16):value for k,value in wanted['sample_registers'].items()}
            assert {off:value for tg,off,value in r.writes if tg==slot and off in registers}==registers
            r.origins[slot]=(wanted['program_pointer'],wanted['osc_pointer'])
            rows.append(dict(voice_slot=slot,sample=wanted['sample'],weight=prepared['weight'],pair=pair,gain=gain,secondary_gain_before=before_gain[slot] if pair==2 else None,started=v in r.sample_starts))
        assert r.word(r.manager+0x48)==r.capacity-len(r.active_slots())
        return dict(note=note,velocity=velocity,voices=rows,active=r.snapshot(),tg_start_calls=len(r.sample_starts))
    finally:r.a.uc.hook_del(hook);r.capture=old_capture
def portable_matrix(f,raw,gm,smoke,baseline=None):
    native=Rig(f,raw,gm);model=ModelRig(f,raw,gm);rows=[];oracle=Rig(f,raw,gm) if baseline is None else None
    choices=[((0,0),3,100)] if smoke else itertools.product([(0,0),(2,1),(10,0)],[0,3],[1,64,100,127])
    from unicorn import UC_HOOK_MEM_WRITE
    for preset,mode,velocity in choices:
        if baseline is None:
            oracle.setup(preset,8,mode,False);cold=dict(note=oracle.note_and_remember(67,velocity),startup=oracle.started.copy())
        else:cold=next(x for x in baseline if tuple(x['preset'])==preset and x['mode']==mode and x['velocity']==velocity and x['action']=='none')
        native.setup(preset,8,mode,False);model.setup(preset,8,mode,False);compare_live(native,model)
        stop(native,'cc120');stop(model,'cc120');compare_live(native,model)
        a=native.a;a.uc.mem_map(0,0x1000);a.uc.mem_write(0,f.data[:0x1000]);writes=[];skipped=[]
        hook=a.uc.hook_add(UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:writes.append(dict(address=address,size=size,value=value,pc=hex(a.get('PC')))),begin=0,end=0xFFF)
        model.guard_enabled=True;model.a.stubs[0x272414]=make_unlink_adapter(model.word,model.a.write,skipped)
        try:
            native.clear_capture();model.clear_capture()
            try:first=reuse_note(native,67,velocity,cold);second=reuse_note(model,67,velocity,cold)
            except AssertionError as error:
                raise AssertionError(dict(preset=preset,mode=mode,velocity=velocity,started=[dict(slot=(x['address']-native.voices)//588,pair=native.word(x['address']+0x218),gain=native.half(x['address']+0x200)) for x in native.started])) from error
            assert first==second;compare_live(native,model);assert state(native)==state(model)
            assert check_lists(native)==check_lists(model)
            assert skipped and len(writes)==2*len(skipped)
            assert all(x['size']==4 and x['value']==0 and x['address'] in [0,4] for x in writes)
            rows.append(dict(preset=preset,mode=mode,velocity=velocity,note=first,skipped_empty_nodes=skipped,native_zero_page_writes=writes,
                software_states_equal=True,io_equal=True,lists=check_lists(model),final=state(model)))
        finally:
            model.a.stubs.pop(0x272414);model.guard_enabled=False;a.uc.hook_del(hook);a.uc.mem_unmap(0,0x1000)
    return rows
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');parser.add_argument('--smoke',action='store_true');parser.add_argument('--portable-only',action='store_true');args=parser.parse_args();f=Firmware()
    for name,lo,hi in [('stop-reuse-pair-reset',0x1FC89C,0x1FC9D0),('stop-reuse-hard-stop',0x1FD53C,0x1FD594),('stop-reuse-member-remove',0x1FC738,0x1FC76C),('stop-reuse-node-unlink',0x272414,0x272438),('stop-reuse-secondary-copy',0x1F75D0,0x1F77C8)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b';gm=sources();r=Rig(f,raw,gm)
    if args.portable_only:
        rows=portable_matrix(f,raw,gm,args.smoke);print(json.dumps(dict(portable_cases=len(rows)),indent=2));return
    presets=[(0,0),(0,61),(2,1),(5,42),(10,0),(20,0)]
    choices=itertools.product(presets[:2],[3],[100],['none','cc123',*HARD]) if args.smoke else itertools.product(presets,[0,3],[1,64,100,127],['none','cc123',*HARD])
    baseline=[]
    for preset,mode,velocity,action in choices:
        baseline.append(case(r,preset,mode,velocity,action))
        if len(baseline)%28==0:print(json.dumps(dict(baseline=len(baseline),faults=sum(bool(x['reuse_fault']) for x in baseline))),flush=True)
    probes=[case(r,preset,3,100,'cc120',perturbation) for preset in (presets[:1] if args.smoke else [presets[0],presets[4]]) for perturbation in ['clear_type','clear_partner','clear_both']]
    zero_page=[zero_page_probe(r,preset,f) for preset in (presets[:1] if args.smoke else [presets[0],presets[4]])]
    queued=[queued_reuse_probe(r,pedals) for pedals in ([0] if args.smoke else [0,3])]
    portable=portable_matrix(f,raw,gm,args.smoke,baseline)
    counts=dict(baseline_cases=len(baseline),paired_baselines=sum(bool(x['paired_slots']) for x in baseline),reuse_faults=sum(bool(x['reuse_fault']) for x in baseline),counterfactual_cases=len(probes),counterfactual_reuses=sum(x['reuse_fault'] is None for x in probes),
        zero_page_cases=len(zero_page),zero_page_reuses=len(zero_page),zero_page_writes=sum(len(x['writes']) for x in zero_page),
        queued_cases=len(queued),queued_successful_notes=sum(x['fault'] is None for t in queued for x in t['attempts']),queued_faults=sum(x['fault'] is not None for t in queued for x in t['attempts']),
        portable_cases=len(portable),portable_skipped_empty_nodes=sum(len(x['skipped_empty_nodes']) for x in portable),portable_native_zero_writes=sum(len(x['native_zero_page_writes']) for x in portable))
    parent=OUT/'midi-all-off-check.json';old=json.loads(parent.read_text());assert old['passed'] and not old['live_continuity_complete']
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_stop_reuse_port.py','firmware_midi_all_off.py','firmware_midi_parameters.py','firmware_midi_voice_refresh.py','firmware_midi_voice_handoff.py','firmware_midi_program_load.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py','firmware_voice_refresh.py']},
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA),dict(path=str(parent.relative_to(ROOT)),sha256=sha(parent))],
        counts=counts,baseline=baseline,counterfactual=probes,zero_page=zero_page,queued=queued,portable=portable,portable_unlink_verified=True,live_continuity_complete=False,
        boundaries=['Real native Program and firstNoteOn48 immediately followed by selected stop andNoteOn67; no Program Change, modulation, manager advance/poll or pedal events between notes',
            'Six real factory/GM choices, modes0/3, four velocities and seven baseline actions; native slot, list, OSC, timbre and MIDI hard-stop entry points compared with no-stop andCC123 controls',
            'Native code and source records are not patched; post-stop membership/free-count and all four candidate list links checked independently; successful reacquisition checks active stereo pair symmetry',
            'Original hard-stop retains pair type/partner while clearing flags and membership; native1FC89C may unconditionally remove that already-unlinked partner when reacquiring a freed stereo slot',
            'Counterfactuals modify only type+218 and/or partner+230 in already-freed test voices; every changed byte recorded and all lists/manager bytes preserved; these are causal probes, not firmware behavior or a deployed recovery',
            'Separate zero-page probes leave all native pair fields intact and allow original writes on a private RW page0 seeded with application bytes; NoteOn returns with valid lists, but original instructions write zeros to0/4 and change the first two seeded vectors',
            'Writable zero-page probes establish mapping-sensitive continuation and the exact low writes; they do not establish the device memory map, correct vector preservation, valid application lifecycle or a recovered native cleanup routine',
            'Separate C001-to-A061 queued probes retain the earlier live setup: first two new notes reuse unpaired slots2/3, while the third reaches a stale paired slot and reproduces the null write; the earlier16 completed timelines did not establish every free-slot reuse',
            'Portable unlink adapter models the original indexed-list writes and return registers, but omits stores to0/4 when both links are0; no pair fields are pre-cleared.24 real cases compare all prior full software spans and TG reads/writes against original instructions with private writable zero-page, after hard stop and reacquisition',
            'Portable adapter is a research host model only. Its bounded equivalence does not prove actual device zero-page mapping, complete native cleanup, every stop/reuse trajectory, hardware audio or a product fix',
            'Reused secondary+200 retains its previous word rather than the cold-start0; native75D0 copies shared control blocks without this field. New reuse checker verifies this retention, primary gain, full source metadata, shared control copies and TG sample-register expectations from independently validated cold baselines, without rewriting the secondary word',
            'Inherited private32-pool setup, TG readback and notification/storage/auxiliary boundaries remain; original full application lifecycle and hardware audio are not established',
            'A positive check means observed boundaries and failures match the scoped assertions; full stereo stop/reuse remains incomplete and no physical-instrument crash is claimed'])
    if not args.smoke:(OUT/'stop-reuse-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,smoke_only=args.smoke,counts=counts),indent=2))
if __name__=='__main__':main()
