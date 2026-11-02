#!/usr/bin/env python3
"""Ablate two auxiliary poll phases; compare all other live state and TG I/O."""
import argparse,contextlib,io,itertools,json
from pathlib import Path
from firmware_midi_voice_refresh import Rig
from firmware_gm_programs import sources,IMAGE,IMAGE_SHA
from firmware_voice_lfo import PRELOAD,OUT
from firmware_midi_program_load import sha
from firmware_inspect import inspect
from program_firmware import Firmware,BASE,FW_SHA
from layout import PRODUCT_ROOT as ROOT

PAIRS=[((0,0),(0,61)),((0,61),(0,0)),((0,11),(5,42)),((5,42),(0,11)),((10,0),(20,0)),((20,0),(10,0))]
START,END=0x1FE6F0,0x1FE75C
def masked(b):return b[:0x1CC]+bytes(0x24)+b[0x1F0:]
def scrub(value):
    if isinstance(value,dict):return {k:scrub(v) for k,v in value.items() if k!='state_sha256'}
    if isinstance(value,list):return [scrub(x) for x in value]
    return value
def spans(r):
    result=[(r.manager,0x100),(r.nodes,r.capacity*12),(r.members,r.capacity*12),(r.waitnodes,r.capacity*12),
        (r.channels,16*436),(r.keycontrols,1536),(0xC165D9A0,0xB0),(0xC1B5848C,4),(r.system,0x60)]
    for i in range(3):
        result.extend([(r.ts[i],152),(r.ps[i],64),(r.cs[i],128),(r.pools[i],32),(r.osc_nodes[i],24),(0x1105A000+128*i,120)])
        result.extend((o,500) for o in r.oscs[i])
    return result
def compare(native,omitted):
    for address,size in spans(native):
        left=bytes(native.a.uc.mem_read(address,size));right=bytes(omitted.a.uc.mem_read(address,size));assert left==right,hex(address)
    changed=0
    for i in range(native.capacity):
        v=native.voices+588*i;left=bytes(native.a.uc.mem_read(v,588));right=bytes(omitted.a.uc.mem_read(v,588))
        assert masked(left)==masked(right),(i,[(k,x,y) for k,(x,y) in enumerate(zip(left,right)) if x!=y and not 0x1CC<=k<0x1F0])
        changed+=left[0x1CC:0x1F0]!=right[0x1CC:0x1F0]
    assert native.writes==omitted.writes and native.reads==omitted.reads and native.waits==omitted.waits
    assert native.events==omitted.events and native.active_mask==omitted.active_mask
    assert len(native.commits)==len(omitted.commits)
    for left,right in zip(native.commits,omitted.commits):
        assert left['voice']==right['voice'] and left['writes']==right['writes']
        assert masked(bytes.fromhex(left['state']))==masked(bytes.fromhex(right['state']))
    return changed

class OmittedRig(Rig):
    def __init__(self,*args):
        super().__init__(*args);self.skipped=[];self.in_poll=False;self.auxiliary_reads=[]
        from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
        def skip(uc,address,size,user):
            assert self.in_poll
            self.skipped.append(dict(poll_cursor=self.a.uc.mem_read(self.manager+0xE9,1)[0],pc=hex(address)))
            self.a.set('PC',BASE+END)
        def read(uc,access,address,size,value,user):
            if not self.in_poll:return
            lo=address-self.voices;slot,offset=divmod(lo,588)
            if 0<=slot<self.capacity and offset<0x1F0 and offset+size>0x1CC:
                self.auxiliary_reads.append(dict(slot=slot,offset=offset,size=size,pc=hex(self.a.get('PC'))))
        self.skip_hook=self.a.uc.hook_add(UC_HOOK_CODE,skip,begin=BASE+START,end=BASE+START)
        self.read_hook=self.a.uc.hook_add(UC_HOOK_MEM_READ,read,begin=self.voices,end=self.voices+588*self.capacity-1)
    def bind_extra(self):pass  # No invented parameter pointers in this branch.
    def poll(self):
        self.in_poll=True
        try:self.a.call(0x1FE404,self.manager)
        finally:self.in_poll=False

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    gm=sources();native=Rig(f,raw,gm);omitted=OmittedRig(f,raw,gm)
    prior_path=OUT/'midi-voice-refresh-check.json';prior=json.loads(prior_path.read_text());assert prior['passed'] and not prior['smoke_only']
    previous={(tuple(t['old']),tuple(t['new']),t['batch'],t['mode'],t['pedal']):t for t in prior['traces']}
    choices=[(PAIRS[0],8,3,True)] if args.smoke else itertools.product(PAIRS,[1,3,8],[0,3],[False,True])
    traces=[]
    for (old,new),batch,mode,pedal in choices:
        initial=native.setup(old,batch,mode,pedal);other=omitted.setup(old,batch,mode,pedal);assert scrub(initial)==scrub(other);compare(native,omitted)
        omitted.skipped.clear();omitted.auxiliary_reads.clear();steps=[];reference=previous[old,new,batch,mode,pedal]
        for update in range(96):
            native.clear_capture();omitted.clear_capture();first=native.apply_event(update,new,pedal);second=omitted.apply_event(update,new,pedal)
            assert scrub(first)==scrub(second);assert first==reference['steps'][update]['event'];compare(native,omitted)
            for r in [native,omitted]:r.clear_capture();r.a.write(r.clock+4,123+20*update)
            elapsed=[0,1,3,20][update%4];native.a.call(0x1FD3CC,native.manager,elapsed);omitted.a.call(0x1FD3CC,omitted.manager,elapsed);compare(native,omitted)
            native.clear_capture();omitted.clear_capture();native.a.call(0x1FE404,native.manager);omitted.poll();different=compare(native,omitted)
            commits=native.verify_commits();assert commits==omitted.verify_commits();state=native.voice_state();assert state==omitted.voice_state()
            expected=reference['steps'][update];assert state==expected['state'] and commits==expected['commits']
            assert not omitted.auxiliary_reads,omitted.auxiliary_reads[:8]
            steps.append(dict(update=update,state=state,commits=commits,auxiliary_blocks_different=different,skipped_phases=len(omitted.skipped)))
        assert any(s['auxiliary_blocks_different'] for s in steps)
        traces.append(dict(old=old,new=new,batch=batch,mode=mode,pedal=pedal,steps=steps,skipped=omitted.skipped.copy(),outside_auxiliary_reads=omitted.auxiliary_reads.copy(),state_and_io_equal_outside_auxiliary=True))
        print(json.dumps(dict(trace=len(traces),old=old,new=new,batch=batch,mode=mode,pedal=pedal)),flush=True)
    for name,lo,hi in [('auxiliary-poll-phases',0x1FE6F0,0x1FE75C),('auxiliary-targets',0x20006C,0x200130),
                       ('auxiliary-scalar',0x200F04,0x200F94),('auxiliary-modulation-getter',0x1F8608,0x1F8790),('auxiliary-TG-commit',0x1F9828,0x1F9A5C)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    counts=dict(traces=len(traces),updates=sum(len(t['steps']) for t in traces),commits=sum(len(s['commits']) for t in traces for s in t['steps']),
        skipped_phase_entries=sum(len(t['skipped']) for t in traces),outside_auxiliary_reads=sum(len(t['outside_auxiliary_reads']) for t in traces))
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_midi_voice_refresh.py','firmware_midi_voice_handoff.py','firmware_midi_program_load.py','firmware_voice_refresh.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py','firmware_inspect.py']},
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA),dict(path=str(prior_path.relative_to(ROOT)),sha256=sha(prior_path))],
        counts=counts,traces=traces,omitted_range=[hex(BASE+START),hex(BASE+END)],masked_voice_range=['0x1cc','0x1f0'],
        boundaries=['Research-only PC redirection skips exactly two original auxiliary phases,1FE6F0..1FE75C; no product/firmware edits and no fake parameter bindings on omitted side',
            'Control side retains original auxiliary computation with frozen zero parameter fixture; comparison masks only voice1CC..1EF and compares every other voice byte plus full existing fixture spans, event/commit order and TG I/O',
            'The original72 MIDI/Program/pedal trajectories execute both native manager advance and poll on each side; every96-update reference state/commit and reference MIDI event matches the frozen earlier result',
            'Memory read hook around all32 voices records zero reads of the omitted interval by the remaining original poll; the generic modulation-source getter and TG commit are saved as static corroboration',
            'This establishes dispensability for the tested normal-refresh/plugin control path. It does not establish original parameter provenance, absence of all possible firmware consumers, exhaustive voices or silicon audio',
            'TG ready/amplitude/score and assignment source fixtures are unchanged; actual DSP interpolation/filter/effect audio and true control timebase remain incomplete'])
    if not args.smoke:(OUT/'voice-auxiliary-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,smoke_only=args.smoke,counts=counts),indent=2))
if __name__=='__main__':main()
