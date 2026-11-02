#!/usr/bin/env python3
"""Native CC120/123 routing, note pools and live voice stop/release."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_midi_parameters import Rig as ParameterRig
from firmware_midi_voice_refresh import Rig as RefreshRig,compare as compare_live
from firmware_gm_programs import sources,IMAGE,IMAGE_SHA
from firmware_voice_lfo import PRELOAD,OUT
from firmware_midi_program_load import sha
from program_firmware import Firmware,BASE,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
PAD=0xC1B58364
def read(a,p,n):return bytes(a.uc.mem_read(p,n))
def pad_seed(a):
    for i,slot in enumerate([0,3,7,15]):
        p=PAD+0x20*i;a.uc.mem_write(p+0xB8,bytes([40+i,90+i,slot,50+i,16+i]))
def pad_model(before,enabled):
    out=bytearray(before)
    if enabled:
        for i in range(4):
            p=0x20*i;out[p+1]=out[p];out[p+3]=255;out[p+4]|=4
    return bytes(out)
def pool_model(before,pool,nodes,node_bytes,count=10):
    p=bytearray(before);q=bytearray(node_bytes);head=pool+12
    struct.pack_into('<6I',p,0,pool,pool,0,nodes if count else head,nodes+12*(count-1) if count else head,0)
    for i in range(count):struct.pack_into('<II',q,12*i,nodes+12*(i+1) if i+1<count else head,nodes+12*(i-1) if i else head)
    return bytes(p),bytes(q)
class CoreRig(ParameterRig):
    def __init__(self,f):
        super().__init__(f);self.pools=[0x1100E000+256*i for i in range(3)];self.keynodes=[p+64 for p in self.pools];self.storage=0x1100F000
        self.a.write(0xC199946C,self.storage);self.a.write(self.storage+0xF7C,self.mode);self.a.write(self.system+0x14,0)
        self.display=[]
        for off in [0x54C74,0x54E40]:self.a.stubs[off]=lambda m,off=off:self.display.append([off,m.get('R1')]) or 0
        self.base_channels=self.channels
    def seed(self,seed=0,channel=7,mode=3,flags=64,counts=(2,3),blocked=False):
        a=self.a;old=self.channel;self.channel=self.base_channels+436*channel
        if old!=self.channel:a.uc.mem_write(self.channel,read(a,old,436))
        self.byte(self.channel,channel);a.write(self.mode,mode);a.write(self.system+0x2C,int(blocked));self.byte(0xC1DCC2D8+0x1350,7)
        for storage in [self.storage,0xC165E21C,0xC17456AC]:self.byte(storage+0x4F6,flags);self.byte(storage+0x766,3)
        for off,n in [(1,129),(0x82,120),(0x118,32),(0x13C,120)]:a.uc.mem_write(self.channel+off,bytes((seed*43+off+i*17)&255 for i in range(n)))
        for i,t in enumerate(self.timbres):
            a.write(t+0x24,self.pools[i]);a.uc.mem_write(t+0x46,struct.pack('<H',counts[i] if i<2 else 11));self.byte(t+0x96,77)
            a.uc.mem_write(self.pools[i],bytes((seed+i+j*11)&255 for j in range(32)));a.write(self.pools[i]+0x18,self.keynodes[i]);self.byte(self.pools[i]+0x1C,10)
            a.uc.mem_write(self.keynodes[i],bytes((seed+i+j*23)&255 for j in range(120)))
        pad_seed(a);self.pad_enabled=channel==(7 if mode not in [0,3] or flags&64 else 3);self.display.clear()
    def check(self,controller,value=0,source=0,blocked=False):
        a=self.a;spans=[(self.base_channels,16*436),(self.keys,1536),(PAD+0xB8,128)]
        spans += [(p,n) for i,t in enumerate(self.timbres) for p,n in [(t,256),(self.parts[i],64),(self.controls[i],128),(self.pools[i],32),(self.keynodes[i],120)]]
        before={p:read(a,p,n) for p,n in spans};wanted=before.copy();self.display.clear()
        if not blocked:
            wanted[PAD+0xB8]=pad_model(before[PAD+0xB8],self.pad_enabled)
            for i in range(2):
                t=self.timbres[i];b=bytearray(before[t]);count=struct.unpack_from('<H',b,0x46)[0]
                if count:struct.pack_into('<H',b,0x46,0);b[0x96]=1
                wanted[t]=bytes(b)
                if controller==123:wanted[self.pools[i]],wanted[self.keynodes[i]]=pool_model(before[self.pools[i]],self.pools[i],self.keynodes[i],before[self.keynodes[i]])
        a.write(self.event,0,(0xB0+(self.channel-self.base_channels)//436)+(controller<<8)+(value<<16)+(source<<24),0);a.call(0x271500,self.system,self.event)
        for p,n in spans:assert read(a,p,n)==wanted[p],(controller,hex(p),[(i,x,y) for i,(x,y) in enumerate(zip(read(a,p,n),wanted[p])) if x!=y][:8])
        expected=[] if blocked else [[off,i] for i in range(2) if struct.unpack_from('<H',before[self.timbres[i]],0x46)[0] for off in [0x54C74,0x54E40]]
        assert self.display==expected,(self.display,expected)
        return dict(controller=controller,value=value,source=source,channel=(self.channel-self.base_channels)//436,mode=struct.unpack('<I',read(a,self.mode,4))[0],pad_changed=wanted[PAD+0xB8]!=before[PAD+0xB8],blocked=blocked,
            channel_preserved=True,part_and_controllers_preserved=True,secondary_preserved=True,display=self.display.copy())
class Rig(RefreshRig):
    def __init__(self,*args):
        self.stop_ops=[];self.bad_unlinks=[];super().__init__(*args)
    def observe(self,uc,address,size,user):
        super().observe(uc,address,size,user);off=address-BASE
        if off in [0x273130,0x2732A0,0x1F67C4]:self.stop_ops.append([off,self.a.get('R0'),self.a.get('R2') if off==0x1F67C4 else None])
        if off==0x272414:
            head=self.a.get('R0');root=self.word(head);index=self.a.get('R1');node=root+12*index
            if 0x11000000<=node<0x11200000 and (not self.word(node) or not self.word(node+4)):
                self.bad_unlinks.append(dict(unlinked_index=index,head=hex(head),root=hex(root),caller=hex(self.a.get('LR')),available=self.word(self.manager+0x48),node=[self.word(node+i) for i in [0,4,8]]))
    def setup_stop(self,old,new,mode,pedals):
        initial=self.setup(old,8,mode,True)
        self.put8(0xC1DCC2D8+0x1350,7)
        for p in [0x11079000,0xC165E21C,0xC17456AC]:self.put8(p+0x4F6,64)
        self.cc(7,99);self.cc(11,73);self.send(0xE7,127,127)
        if pedals&1:self.cc(64,127)
        if pedals&2:self.cc(66,127)
        change=self.choose(*new);second=self.note_and_remember(64,100);self.send(0x87,48,64);pad_seed(self.a)
        self.clear_capture();self.stop_ops.clear();self.bad_unlinks.clear();return dict(first=initial,change=change,second=second)
    def all_off(self,controller,value,source,explicit=False):
        a=self.a;before=self.snapshot();pressed=sorted(v['slot'] for v in before if v['flags']&128)
        parts=[read(a,p,64) for p in self.ps];ctrl=[read(a,c,128) for c in self.cs];channel=read(a,self.channel,436);keys=read(a,self.keycontrols,1536)
        pad=read(a,PAD+0xB8,128);pools=[read(a,p,32) for p in self.pools];keynodes=[read(a,0x1105A000+128*i,120) for i in range(3)]
        secondary=read(a,self.ts[2],152);self.releasing.clear();self.kills.clear();self.stop_ops.clear()
        if explicit:
            for t in self.ts[:2]:a.call(0x2732A0 if controller==120 else 0x273130,t)
            a.call(0x2C7978 if controller==120 else 0x2C78AC,PAD,7)
        else:self.cc(controller,value,source)
        assert read(a,self.channel,436)==channel and read(a,self.keycontrols,1536)==keys
        assert read(a,self.ts[2],152)==secondary
        for i in range(3):assert read(a,self.ps[i],64)==parts[i] and read(a,self.cs[i],128)==ctrl[i]
        assert read(a,PAD+0xB8,128)==pad_model(pad,True)
        if controller==120:
            assert sorted(self.kills)==sorted(v['slot'] for v in before) and not self.releasing
            assert not self.active_slots() and not self.active_mask and self.word(self.manager+0x48)==self.capacity
            for i in range(3):assert read(a,self.pools[i],32)==pools[i] and read(a,0x1105A000+128*i,120)==keynodes[i]
        else:
            assert sorted(self.releasing)==pressed and not self.kills,(self.releasing,pressed,self.kills)
            after={v['slot']:v for v in self.snapshot()};assert set(after)=={v['slot'] for v in before}
            assert all(not after[i]['flags']&128 for i in pressed)
            for i in range(2):
                p,q=pool_model(pools[i],self.pools[i],0x1105A000+128*i,keynodes[i]);assert read(a,self.pools[i],32)==p and read(a,0x1105A000+128*i,120)==q
        return dict(controller=controller,value=value,source=source,before=before,after=self.snapshot(),released=list(self.releasing),killed=list(self.kills),operations=self.stop_ops.copy(),
            channel_preserved=True,controllers_preserved=True,available=self.word(self.manager+0x48),tg_active_mask=self.active_mask,pad_after=read(a,PAD+0xB8,128).hex())
def compare(a,b):
    compare_live(a,b);assert read(a.a,PAD+0xB8,128)==read(b.a,PAD+0xB8,128)
def live_matrix(f,smoke):
    assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    raw=PRELOAD.read_bytes();gm=sources();a=Rig(f,raw,gm);b=Rig(f,raw,gm);traces=[]
    pairs=[((0,0),(0,61)),((2,1),(0,61)),((5,36),(0,0)),((5,42),(0,0)),((10,0),(20,0)),((20,0),(10,0))]
    choices=itertools.product(pairs[:1],[120,123],[0,3],[3]) if smoke else itertools.product(pairs,[120,123],range(4),[0,3])
    for (old,new),controller,pedals,mode in choices:
        source=5 if pedals&1 else 0;initial=a.setup_stop(old,new,mode,pedals);b.setup_stop(old,new,mode,pedals);compare(a,b);steps=[];reuse_fault=None
        for update in range(48):
            events=[]
            for r,explicit in [(a,False),(b,True)]:
                r.clear_capture();event={}
                if update in [0,12,32]:event['off']=r.all_off(120 if update==32 else controller,127,source,explicit)
                if update==8:r.cc(64,0);r.cc(66,0)
                if update in [20,36]:
                    try:event['note']=r.note_and_remember(67 if update==20 else 72,100)
                    except RuntimeError as error:
                        fault=r.a.memory_fault
                        assert fault==dict(access=20,address='0x4',bytes=4,pc='0xc027242c') and r.bad_unlinks,(fault,r.bad_unlinks)
                        last=r.bad_unlinks[-1];assert last['head']==hex(r.manager+0x40) and last['node'][:2]==[0,0] and last['caller']=='0xc01fc760'
                        event['reuse_fault']=dict(update=update,note=67 if update==20 else 72,memory_fault=fault,unlinked=last,
                            voice_pairs=[dict(slot=i,flags=r.half(r.voices+588*i+0x10),pair=r.word(r.voices+588*i+0x218),partner=r.word(r.voices+588*i+0x230)) for i in range(r.capacity) if r.word(r.voices+588*i+0x218)])
                if update in [24,40]:r.send(0x87,67 if update==24 else 72,64)
                events.append(event)
            compare(a,b);assert events[0]==events[1],(update,events)
            if 'reuse_fault' in events[0]:reuse_fault=events[0]['reuse_fault'];break
            for r in [a,b]:r.clear_capture();r.a.write(r.clock+4,123+20*update)
            elapsed=[0,1,3,20][update%4];a.a.call(0x1FD3CC,a.manager,elapsed);b.explicit_advance(elapsed);compare(a,b)
            a.clear_capture();b.clear_capture();a.a.call(0x1FE404,a.manager);b.explicit_poll();compare(a,b)
            steps.append(dict(update=update,event=events[0],state=a.voice_state(),commits=a.verify_commits()))
        traces.append(dict(old=old,new=new,controller=controller,pedals=pedals,mode=mode,source=source,initial=initial,steps=steps,reuse_fault=reuse_fault))
        print(json.dumps(dict(trace=len(traces),old=old,new=new,controller=controller,pedals=pedals,mode=mode,updates=len(steps),reuse_fault=bool(reuse_fault))),flush=True)
    return traces
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');parser.add_argument('--smoke',action='store_true');args=parser.parse_args();f=Firmware()
    for name,lo,hi in [('MIDI-all-off-dispatch',0x26FCA4,0x26FD3C),('MIDI-all-off-timbres',0x273130,0x2732F8),('MIDI-all-off-OSC',0x1F67C4,0x1F6884),('MIDI-all-off-voices',0x1FDC2C,0x1FDC88),('MIDI-all-off-pads',0x2C78AC,0x2C7980)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm:return
    r=CoreRig(f);counts={};digest=hashlib.sha256()
    def case(controller,value=0,source=0,**kw):
        r.seed(**kw);row=r.check(controller,value,source,kw.get('blocked',False));digest.update(json.dumps(row,sort_keys=True).encode());return row
    if args.smoke:
        for controller in [120,123]:case(controller,127,5)
    else:
        n=0
        for controller,value,source in itertools.product([120,123],range(128),[0,1,5,8]):case(controller,value,source,seed=value);n+=1
        counts['values_sources']=n;n=0
        for controller,channel,mode,flags,source in itertools.product([120,123],range(16),range(6),[0,64],[0,5]):case(controller,127,source,channel=channel,mode=mode,flags=flags);n+=1
        counts['channels_modes']=n;n=0
        for controller,x,y in itertools.product([120,123],[0,1,32768,65535],[0,1,32768,65535]):case(controller,counts=(x,y));n+=1
        counts['key_counters']=n;n=0
        for controller,channel,source in itertools.product([120,123],range(16),[0,5]):case(controller,127,source,channel=channel,blocked=True);n+=1
        counts['blocked_system']=n
    live=live_matrix(f,args.smoke);counts.update(live_traces=len(live),live_updates=sum(len(t['steps']) for t in live),live_commits=sum(len(s['commits']) for t in live for s in t['steps']),reuse_faults=sum(bool(t['reuse_fault']) for t in live))
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_midi_parameters.py','firmware_midi_voice_refresh.py','firmware_midi_voice_handoff.py','firmware_midi_program_load.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py','firmware_voice_refresh.py']},
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA)],counts=counts,matrix_sha256=digest.hexdigest(),live=live,live_continuity_complete=not counts['reuse_faults'],
        boundaries=['Native271500/26EC34 dispatch, primary273130/2732A0, OSC virtual message3/4 and original release/hard-stop/list recycling execute',
            'Independent full-state core model covers all16 channel records, three timbres/Parts/controllers, note-pool list links and nodes, drum controls and four Pad request slots; OSC registry capacity0 only in the core matrix',
            'CC120/123 value and source do not alter the control action; controller bytes, bend, pressure and channel key bitmaps are retained; secondary timbre is not traversed',
            'Original Pad channel selection and four-slot stop-request marking execute on existing private storage/config, with independent byte model; no Pad audio task executes',
            'Live96 traces attempt up to48 updates with immutable real factory/GM records, same32-slot pool, six Program transitions, both commands, allfour pedal combinations and modes0/3; source0/5 assigned by sustain condition, not a full Cartesian source matrix',
            'Native outer CC compares against explicit primary-timbre and Pad helper order; per-voice release/hard-stop slot sets, preservation, pool links and reuse also checked independently; all original advance/poll phases compare',
            'Inherited TG readback, private auxiliary parameters, stack normalization, storage/allocation/display/OS boundaries remain; no actual DSP audio or complete front-end byte parser',
            'All Sound Off does not reset controllers or clear the timbre note pool; All Notes Off rebuilds that pool and observes pedal/drum release rules; negative KeyOff-delay presets and exhaustive voice stealing remain outside this matrix',
            'Native and explicit schedules can both hit an unmapped null-next membership unlink during stereo reuse after CC120: this is retained as an unresolved private-fixture reproduction, not repaired, not counted as continuity success and not evidence of a physical-instrument crash'])
    if not args.smoke:(OUT/'midi-all-off-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,smoke_only=args.smoke,counts=counts),indent=2))
if __name__=='__main__':main()
