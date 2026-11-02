#!/usr/bin/env python3
"""Original MIDI mono/legato/Unison with real source voices and continuous poll."""
import argparse,hashlib,itertools,json,struct
from pathlib import Path
from firmware_voice_pressure import PressureRig,PressureModel,SelectionObserver
from firmware_midi_all_off import compare,read,pad_seed
from firmware_stop_reuse import check_lists
from firmware_stop_reuse_port import make_unlink_adapter
from firmware_mono_keys import Model
from firmware_factory_voice_chain import Rig as MelodicRig,sb
from firmware_voice_lfo import PRELOAD,OUT,h,sh,w
from firmware_gm_programs import sources,IMAGE,IMAGE_SHA
from firmware_midi_program_load import sha
from program_firmware import Firmware,BASE,FW_SHA
from layout import PRODUCT_ROOT as ROOT

BASE_PRESETS=[(3,24),(3,9),(3,46)]
UNISON_PRESETS=[(3,17),(3,15),(5,6),(5,110)]
PRESERVED=[(0x10,2),(0x14,1),(0x20,12),(0x2C,88),(0xBC,48),(0x120,48),(0x15C,100),(0x218,4),(0x230,4)]
def digest(b):return hashlib.sha256(b).hexdigest()
def region_for_pitch(f,multisample,pitch):
    first,count=struct.unpack_from('<HB',f.data,0x48F5CC+28*multisample);previous=-1;query=pitch>>8
    for index in range(count):
        top=sb(f.data,0x492C28+20*(first+index)+3)
        if (previous<query<=top and top>0) or (query==0 and top==0):return first+index
        previous=top
    return None
def actions(pedal):
    d={0:('on',60,40),4:('on',64,80),8:('on',62,100),12:('off',62,64),16:('off',64,64),20:('off',60,64),
        24:('on',48,55),28:('on',84,120),32:('cc',64,127 if pedal else 0),36:('off',84,64),40:('off',48,64),44:('cc',64,0),
        80:('on',60,30),84:('on',60,90),88:('off',60,64),92:('off',60,64),96:('on',67,70),100:('cc',123,127),
        104:('on',72,111),108:('off',72,64),112:('cc',120,127),116:('on',55,66),120:('off',55,64),124:('cc',123,127),128:('cc',120,127)}
    d.update({48+i:('on',36+i,40+5*i) for i in range(12)})
    d.update({64+i:('off',36+i,64) for i in range(12)})
    return d

class MonoRig(PressureRig):
    def __init__(self,*args):
        self.wrapper=[];self.created=[];self.retunes=[];self.retune_pending=None;self.glides=[];self.glide_pending=None;self.latest_glide=None;super().__init__(*args)
    def note_and_remember(self,*args):return None # setup deliberately begins with no pressed key
    def setup_mono(self,preset,priority,pedal):
        ptr,source=self.catalog[preset];self.a.uc.mem_write(ptr,source)
        self.command_mask=0;self.setup(preset,8,3,True);a=self.a
        for i,pool in enumerate(self.pools):
            nodes=0x1105A000+128*i;payload=0x1105B000+64*i;a.uc.mem_write(payload,bytes(40))
            for j in range(10):a.write(nodes+12*j,0,0,payload+4*j)
            a.call(0x270210,pool)
        patch=self.word(self.context+8);original=read(a,patch,2140);assert original[0x508]&128
        value=(original[0x509]&~12)|(priority<<2);self.put8(patch+0x509,value)
        self.put8(0xC1DCC2D8+0x1350,7)
        for p in [0x11079000,0xC165E21C,0xC17456AC]:self.put8(p+0x4F6,64)
        pad_seed(a);self.wrapper.clear();self.created.clear();self.retunes.clear();self.stop_acknowledgements.clear();self.start_acknowledgements.clear()
        self.clear_capture();self.capture=True
        return dict(name=original[:16].decode('ascii').strip(),source_sha256=digest(original),runtime_sha256=digest(read(a,patch,2140)),
            priority=priority,raw_legato=bool(original[0x509]&16),reuse=bool(original[0x509]&16) and not bool(original[0x509]&32),
            source_control_bytes=list(original[0x508:0x50D]),
            offset=bool(original[0x509]&32),unison=(original[0x50A]&7) if original[0x50A]&128 else 0,
            edits=[] if value==original[0x509] else [dict(offset='0x509',before=original[0x509],after=value)])
    def observe(self,uc,address,size,user):
        super().observe(uc,address,size,user);off=address-BASE;a=self.a
        if not hasattr(self,'context'):return
        if off in [0x272D0C,0x2737F8,0x272C3C] and a.get('R0')==self.context:
            if off==0x272D0C:self.wrapper.append(['reset'])
            else:
                x=a.get('R1');self.wrapper.append(['on' if off==0x2737F8 else 'off',x&0xF0,(x>>8)&255,(x>>16)&255])
        if off==0x1F62F0:
            x=a.get('R1');self.current_note=(x>>8)&255;self.current_velocity=(x>>16)&255
        elif off==0x1F7278:
            v=a.get('R0');slot=(v-self.voices)//588;p=self.prepared[-1]
            candidates=MelodicRig.expected_layers(self,self.current_note,self.current_velocity)
            expected=next(x for x in candidates if x['slot']==p['slot'] and x['side']==p['side'])
            assert expected['valid'] and expected['weight']==p['weight']
            glide=self.latest_glide;assert glide is not None and glide['target']==expected['pitch'],(glide,expected)
            region=region_for_pitch(self.f,expected['multisample'],glide['initial_pitch']);assert region is not None
            rb=self.f.data[0x492C28+20*region:0x492C28+20*(region+1)];sample=h(rb,0)
            descriptor=self.record[0x564+380*self.oscillator+8*p['slot']:0x56C+380*self.oscillator+8*p['slot']]
            level=descriptor[4]*expected['weight']>>15;gain=self.math.multisample_gain(level,sb(rb,8),0)
            actual=self.started[-1]
            assert (actual['sample_ptr'],actual['region_ptr'])==(BASE+0x410ABC+64*sample,BASE+0x492C28+20*region),(self.current_note,self.current_velocity,actual,expected,self.latest_glide)
            assert (actual['layer_level'],actual['root'],actual['tune'],actual['pitch'])==(level,sb(rb,4)<<8,sh(rb,6),glide['initial_pitch']),(self.current_note,self.current_velocity,actual,expected,glide)
            self.origins[slot]=(self.word(v+0x21C),self.word(v+0x224))
            self.created.append(dict(slot=slot,osc=self.oscillator,note=self.current_note,velocity=self.current_velocity,
                sample=sample,region=region,target_region=expected['region'],multisample=expected['multisample'],side=p['side'],weight=p['weight'],expected_gain=gain,gain_before=self.reclaimed_gains[slot],
                source_pointer=self.word(v+0x21C),osc_pointer=self.word(v+0x224),pitch_target=expected['pitch'],initial_pitch=actual['pitch'],glide_index=len(self.glides)-1))
        elif off==0x1F77C8:
            v=a.get('R6');slot=(v-self.voices)//588;row=self.created[-1];assert row['slot']==slot and a.get('R0')==1
            row['gain']=self.half(v+0x200);assert row['gain']==(row['gain_before'] if row['side']==1 else row['expected_gain']),row
            row['unison_index']=read(a,v+0xB0,1)[0];row['unison_count']=read(a,v+0xB1,1)[0]
        elif off==0x1F7B68:
            assert self.retune_pending is None
            v=a.get('R0');self.retune_pending=dict(address=v,note=a.get('R2')&255,before=read(a,v,588),starts=len(self.sample_starts))
        elif off==0x1F7CBC:
            row=self.retune_pending;assert row and a.get('R4')==row['address'] and a.get('R0')==1
            v=row['address'];before=row['before'];after=read(a,v,588)
            assert all(after[o:o+n]==before[o:o+n] for o,n in PRESERVED)
            assert len(self.sample_starts)==row['starts'] and after[0x12]==row['note']
            param=self.word(v+0x224);common=self.word(v+0x220);params=read(a,param,380);cm=read(a,common,68)
            transpose=int.from_bytes(read(a,self.part+7,1),'little',signed=True);folded=row['note']+transpose
            while folded<0:folded+=12
            while folded>127:folded-=12
            wanted=[self.math.keyboard_tracking(params[0xFC:0x103],folded),self.math.keyboard_tracking(params[0x13C:0x143],folded,True),
                self.math.keyboard_tracking(cm[0x34:0x3B],folded),self.math.keyboard_tracking(cm[0x3C:0x43],folded)]
            got=[sh(after,o) for o in [0x204,0x206,0x212,0x214]];assert got==wanted,(got,wanted)
            self.retunes.append(dict(slot=(v-self.voices)//588,old_note=before[0x12],new_note=row['note'],velocity_before=before[0x14],velocity_after=after[0x14],
                sample=w(after,0x20),region=w(after,0x22C),tracking=got,tracking_expected=wanted,
                preserved_sha256=digest(b''.join(before[o:o+n] for o,n in PRESERVED)),after_preserved_sha256=digest(b''.join(after[o:o+n] for o,n in PRESERVED)),tg_starts=0))
            self.retune_pending=None
        elif off==0x1F82C0:
            assert self.glide_pending is None
            v=a.get('R0');previous=a.get('R1');target=a.get('R2');block=a.get('R3')
            if previous&0x80000000:previous-=2**32
            if target&0x80000000:target-=2**32
            context=self.word(v+8);override=int.from_bytes(read(a,context+0x2E,1),'little',signed=True)
            speed=read(a,block+0x19,1)[0] if override==-1 else override;assert 0<=speed<128
            coefficient=int.from_bytes(self.f.data[0x3FD380+4*speed:0x3FD384+4*speed],'little',signed=True)
            scaled=bool(read(a,block+0x18,1)[0]&4)
            if not coefficient or previous==-1:position=step=limit=0;initial=target
            else:
                step=max(1,coefficient*abs(target-previous)//3072) if scaled else coefficient
                if target>=previous:position=(previous-target)*256;limit=0;initial=target
                else:position=0;limit=(target-previous)*256;step=-step;initial=previous
            slot=(v-self.voices)//588
            self.glide_pending=dict(address=v,slot=slot if 0<=slot<self.capacity else None,temporary=not 0<=slot<self.capacity,previous=previous,target=target,speed=speed,coefficient=coefficient,
                scaled=scaled,position=position,step=step,limit=limit,initial_pitch=initial,retune=self.retune_pending is not None)
        elif off==0x1F8414:
            row=self.glide_pending;assert row is not None and a.get('R6')==row['address'] and a.get('R0')==row['initial_pitch']&0xFFFFFFFF
            assert list(struct.unpack('<3i',read(a,row['address']+0x88,12)))==[row['position'],row['step'],row['limit']],row
            self.latest_glide={k:v for k,v in row.items() if k!='address'};self.glides.append(self.latest_glide);self.glide_pending=None

class MonoModel(MonoRig,PressureModel):pass

def keys(r):
    pool=r.pools[0];nodes=0x1105A000;seen=set();lists=[]
    for head in [pool,pool+12]:
        p=r.word(head);prev=head;local=[]
        while p!=head:
            assert nodes<=p<nodes+120 and (p-nodes)%12==0 and p not in seen;seen.add(p)
            assert r.word(p+4)==prev;local.append(read(r.a,r.word(p+8),1)[0]);prev=p;p=r.word(p)
        assert r.word(head+4)==prev;lists.append(local)
    assert len(seen)==10
    return lists[0],read(r.a,pool+0x1D,1)[0]
def compare_full(a,b):
    compare(a,b)
    assert read(a.a,0x1105B000,192)==read(b.a,0x1105B000,192)
    assert a.wrapper==b.wrapper and a.created==b.created and a.retunes==b.retunes and a.glides==b.glides
    assert a.start_acknowledgements==b.start_acknowledgements and a.stop_acknowledgements==b.stop_acknowledgements

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');p.add_argument('--preset',nargs=2,type=int);args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    gm=sources();native=MonoRig(f,raw,gm);model=MonoModel(f,raw,gm);observers=[SelectionObserver(r) for r in [native,model]]
    choices=[(tuple(args.preset),2,pedal) for pedal in [False,True]] if args.preset else [((3,9),2,True)] if args.smoke else [(preset,priority,pedal) for preset in BASE_PRESETS for priority,pedal in itertools.product(range(3),[False,True])]+[(preset,2,pedal) for preset in UNISON_PRESETS for pedal in [False,True]]
    from unicorn import UC_HOOK_MEM_WRITE
    traces=[]
    for preset,priority,pedal in choices:
        setup=native.setup_mono(preset,priority,pedal);assert model.setup_mono(preset,priority,pedal)==setup;compare_full(native,model)
        key_model=Model(10,priority,setup['raw_legato']);count=0;a=native.a;a.uc.mem_map(0,0x1000);a.uc.mem_write(0,f.data[:0x1000]);low=[];skipped=[]
        hook=a.uc.hook_add(UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:low.append(dict(address=address,size=size,value=value,pc=hex(a.get('PC')))),begin=0,end=0xFFF)
        model.guard_enabled=True;model.a.stubs[0x272414]=make_unlink_adapter(model.word,model.a.write,skipped);steps=[]
        try:
            for update in range(160):
                event=actions(pedal).get(update);expected=[]
                if event:
                    kind,note,velocity=event
                    if kind=='on':
                        selected,first=key_model.on(note,velocity);count+=1
                        if (selected and not setup['reuse']) or first:expected.append(['reset'])
                        if selected:expected.append(['on',0x90,note,velocity])
                    elif kind=='off':
                        if not setup['reuse']:expected.append(['off',0x80,note,velocity])
                        fallback=key_model.off(note);count=max(0,count-1)
                        if fallback is not None:
                            if not setup['reuse']:expected.append(['reset'])
                            expected.append(['on',0x80,fallback,key_model.velocity])
                        elif setup['reuse'] and not key_model.keys:expected.append(['off',0x80,note,velocity])
                    elif note==123:key_model.keys.clear();count=0
                    elif note==120:count=0
                for r in [native,model]:
                    r.clear_capture();r.wrapper.clear();r.created.clear();r.retunes.clear();r.glides.clear();r.latest_glide=None;r.started.clear();r.sample_starts.clear();r.prepared.clear()
                    if event:
                        old_capture=r.capture;r.capture=False
                        if event[0]=='on':r.a.uc.mem_write(0x111E0000,bytes(0x10000))
                        try:r.send(0x97 if event[0]=='on' else 0x87 if event[0]=='off' else 0xB7,event[1],event[2]);r.bind_extra()
                        finally:r.capture=old_capture
                    assert r.wrapper==expected,(update,event,r.wrapper,expected)
                    assert keys(r)==(key_model.keys,key_model.velocity),(update,keys(r),key_model.keys,key_model.velocity)
                    assert r.half(r.context+0x46)==count,(update,count,r.half(r.context+0x46))
                compare_full(native,model);check_lists(native);check_lists(model)
                event_data=dict(input=event,dispatch=native.wrapper.copy(),keys=key_model.keys.copy(),cached_velocity=key_model.velocity,count=count,
                    created=native.created.copy(),retunes=native.retunes.copy(),glides=native.glides.copy())
                for r in [native,model]:r.clear_capture();r.a.write(r.clock+4,123+20*update)
                elapsed=[0,1,3,20][update%4];native.a.call(0x1FD3CC,native.manager,elapsed);model.explicit_advance(elapsed);compare_full(native,model)
                native.clear_capture();model.clear_capture();native.a.call(0x1FE404,native.manager);model.explicit_poll();compare_full(native,model)
                assert check_lists(native)==check_lists(model);state=native.voice_state()
                steps.append(dict(update=update,event=event_data,commits=native.verify_commits(),state=state))
            assert [x['address'] for x in low]==[4,0]*len(skipped)
            assert all(x['size']==4 and x['value']==0 and x['pc'] in ['0xc027242c','0xc0272430'] for x in low)
            assert not native.active_slots() and native.word(native.manager+0x48)==120
            assert native.retune_pending is None and model.retune_pending is None and native.glide_pending is None and model.glide_pending is None
            for r in [native,model]:assert digest(read(r.a,r.word(r.context+8),2140))==setup['runtime_sha256']
            traces.append(dict(preset=preset,priority=priority,pedal=pedal,setup=setup,steps=steps,native_zero_page_writes=low,skipped_empty_nodes=skipped))
        except Exception as error:raise AssertionError(dict(preset=preset,priority=priority,pedal=pedal,update=update)) from error
        finally:model.a.stubs.pop(0x272414);model.guard_enabled=False;a.uc.hook_del(hook);a.uc.mem_unmap(0,0x1000)
        print(json.dumps(dict(trace=len(traces),preset=preset,priority=priority,pedal=pedal,retunes=sum(len(s['event']['retunes']) for s in steps))),flush=True)
    counts=dict(traces=len(traces),updates=sum(len(t['steps']) for t in traces),commits=sum(len(s['commits']) for t in traces for s in t['steps']),
        created=sum(len(s['event']['created']) for t in traces for s in t['steps']),retunes=sum(len(s['event']['retunes']) for t in traces for s in t['steps']),
        glides=sum(len(s['event']['glides']) for t in traces for s in t['steps']),
        glide_affected_constructions=sum(v['initial_pitch']!=v['pitch_target'] for t in traces for s in t['steps'] for v in s['event']['created']),
        glide_changed_regions=sum(v['region']!=v['target_region'] for t in traces for s in t['steps'] for v in s['event']['created']),
        overflow_insertions=sum(bool(s['event']['input'] and s['event']['input'][0]=='on' and i and len(t['steps'][i-1]['event']['keys'])==10) for t in traces for i,s in enumerate(t['steps'])),
        native_zero_page_writes=sum(len(t['native_zero_page_writes']) for t in traces),skipped_empty_nodes=sum(len(t['skipped_empty_nodes']) for t in traces))
    helpers=['firmware_voice_pressure.py','firmware_mono_keys.py','firmware_stop_reuse.py','firmware_stop_reuse_port.py','firmware_midi_all_off.py','firmware_midi_parameters.py','firmware_midi_voice_refresh.py','firmware_midi_voice_handoff.py','firmware_midi_program_load.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py','firmware_voice_refresh.py']
    result=dict(passed=True,smoke_only=args.smoke or bool(args.preset),firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in helpers},inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA)],counts=counts,traces=traces,
        boundaries=['Original outer MIDI/timbre priority/OSC/reset/mono-retune/Unison and actual factory selection/control initialization execute in the same120-slot pool; real factory Program records except explicitly recorded private priority-bit edits',
            'Independent10-key list model checks Low/High/Last, duplicate presses, overflow and fallback dispatch; each original retune checks sample/region/velocity/EG/LFO/pair preservation and independent keyboard tracking with no TG restart inside the retune',
            'Fresh constructions check real source layers, samples, metadata, gains and Unison fields; no cold-rendered audio comparison is claimed',
            'Every original glide initialization compares independent coefficient/mode/previous/target arithmetic, return pitch and position/step/limit. Sample regions are queried using that returned pitch before voice control initialization; hypothetical target-only regions are retained for comparison',
            'Normal native manager advance/poll compares after each phase to explicit original-kernel scheduling; all inherited software spans plus actual key payloads, TG I/O, entry order and control arithmetic compare',
            'Inherited controlled TG start/stop acknowledgement, ready/amplitude/score, auxiliary bindings, scratch-stack normalization and portable empty-unlink boundary remain explicit; no physical time or silicon audio claim',
            'Mode3/channel7/single primary timbre only; multiple timbres, all presets and hardware audio remain incomplete; no product or frozen helper changes'])
    if not args.smoke and not args.preset:(OUT/'mono-live-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,smoke_only=result['smoke_only'],counts=counts),indent=2))
if __name__=='__main__':main()
