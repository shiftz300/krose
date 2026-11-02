#!/usr/bin/env python3
"""Native oscillator pedal release -> allocator/state -> EG/TG command boundary."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_pedal_envelopes import Rig as PedalRig,program
from firmware_envelopes import OFFSETS,q64
from firmware_voice_lfo_integration import note_adjust
from firmware_voice_lfo import h,sh,w,ph,pw,s32,sha,OUT,PRELOAD
from program_firmware import Firmware,FW_SHA,BASE
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

class Rig(PedalRig):
    def __init__(self,f):
        self.bus_writes=[];self.bus_reads=[];self.visits=[];self.readback=12345
        super().__init__(f)
        self.a.stubs.update({0x132690:self.bus_write,0x1326B4:self.bus_read})
        from unicorn import UC_HOOK_CODE
        self.observed={0x1FD4F4:'manager',0x1F7CC8:'release_state',0x1F8AF4:'amp_commit',
                       0x1FE8FC:'classification',0x1F80D0:'deferred_egs',0x1FCF6C:'cancel_wait'}
        self.hook=self.a.uc.hook_add(UC_HOOK_CODE,self.observe)
        self.coefficients=list(struct.unpack_from('<25H',f.data,0x3A8D40))
    def observe(self,uc,address,size,user):
        if address-BASE in self.observed:self.visits.append(self.observed[address-BASE])
    def bus_write(self,a):
        self.bus_writes.append([a.get('R0')-self.tg,a.get('R1')]);return 0
    def bus_read(self,a):
        offset=a.get('R0')-self.tg;self.bus_reads.append(offset)
        return self.readback if offset==0x42C else 0
    def word(self,p):return w(bytes(self.a.uc.mem_read(p,4)),0)
    def put8(self,p,x):self.a.uc.mem_write(p,bytes([x&255]))
    def put16(self,p,x):self.a.uc.mem_write(p,struct.pack('<H',x&65535))
    def pedal(self,*args,**kwargs):
        super().pedal(*args,**kwargs)
        self.a.write(self.context+0x3C,int(self.pedal_enabled)|(int(getattr(self,'sost',False))<<2))
    def sostenuto(self,enabled):
        self.sost=enabled;self.a.write(self.context+0x3C,int(self.pedal_enabled)|(int(enabled)<<2))
        self.put8(self.controls+66,127 if enabled else 0)
        if enabled:self.cc[66]=127
        else:self.cc.pop(66,None)
    def prepare(self,record,osc):
        super().prepare(record,osc)
        self.manager=0x11060000;self.primary=0x11061000;self.members=0x11062000
        self.waitnodes=0x11063000;self.channel=0x11064000;self.tg=0x60000000
        a=self.a;self.assignment=self.manager+12;head=self.assignment
        a.uc.mem_write(self.manager,bytes(0x100));a.uc.mem_write(self.channel,bytes(0x200))
        a.write(head+0x30,self.primary,self.members,1,0)
        for node in [self.primary,self.members,self.waitnodes]:a.write(node,0,0,self.voice)
        a.call(0x1FBF4C,head)
        # Explicit one-active-voice fixture, after allocation and attachment.
        # Native list operation moves its primary node out of the candidate list.
        a.call(0x272414,head+0x30,0);a.call(0x272470,head+12,self.primary);a.write(head+0x3C,0)
        a.write(self.manager+0xCC,self.manager+0xCC,self.manager+0xCC,0,self.waitnodes,1)
        a.write(self.oscruntime+0x48C,self.manager);a.write(self.oscruntime+0x49C,self.context)
        a.write(self.context+8,self.program);a.write(self.context+0x10,self.channel)
        a.write(self.voice+0x0C,self.channel);a.write(self.voice+0x1C,self.tg)
        a.write(self.voice+0x240,0xFFFFFFFF);self.put8(self.voice+0x16,0);self.put8(self.voice+0x17,0)
        self.put8(self.voice+0x18,255);self.put8(self.voice+0x1A,7);self.put8(self.voice+0x20D,1)
        self.put8(0xC104728C,1);self.put8(0xC1DCC2D9,0);a.uc.mem_write(0xC0F53884,bytes(32))
        self.voice_bits=0x80;self.put16(self.voice+0x10,self.voice_bits)
        self.delay=self.ticks=0;self.sost=False;self.latched=False;self.allowed=1
        self.category=-1;self.class_note=60;self.class_offset=0;self.threshold=109;self.class_down=False
        self.candidates=[];self.active=[0];self.waiting=False
        self.bus_writes.clear();self.bus_reads.clear();self.visits.clear()
    def configure(self,flags=0x80,allowed=1,delay=0,ticks=0,sost=False,latched=False,category=-1,
                  class_note=60,class_offset=0,threshold=109,class_down=False):
        self.voice_bits=flags;self.allowed=allowed;self.delay=delay;self.ticks=ticks;self.sost=sost;self.latched=latched
        self.category=category;self.class_note=class_note;self.class_offset=class_offset;self.threshold=threshold;self.class_down=class_down
        self.put16(self.voice+0x10,flags);self.put8(self.voice+0x20D,allowed);self.put16(self.voice+0x208,delay)
        self.a.write(self.voice+0x234,ticks);self.a.write(self.voice+0x240,category,class_note)
        self.a.uc.mem_write(self.channel+0x128,bytes(16))
        if latched:self.a.write(self.channel+0x128+4*(self.note//32),1<<(self.note%32))
        self.sostenuto(sost)
        self.put8(0xC1DCC2D9,class_offset);self.a.uc.mem_write(0xC0F53884,bytes(32))
        index=class_note-class_offset;assert 0<=index<256
        if class_down:self.a.write(0xC0F53884+4*(index//32),1<<(index%32))
        raw=self.record[0x508]
        self.put8(self.program+0x508,(raw|64) if threshold!=109 else (raw&~64));self.put8(self.program+0x50D,threshold)
        if delay>0 or ticks:
            self.waiting=True;self.a.call(0x272470,self.manager+0xCC,self.waitnodes)
    def queue(self,head):
        result=[];p=self.word(head)
        while p!=head:
            assert len(result)<2
            assert self.word(self.word(p)+4)==p and self.word(self.word(p+4))==p
            result.append(0);p=self.word(p)
        return result
    def compare_flow(self):
        self.compare_egs();self.check();self.compare_mixers()
        assert self.queue(self.assignment)==self.candidates
        assert self.queue(self.assignment+12)==self.active
        assert self.queue(self.manager+0xCC)==([0] if self.waiting else [])
        assert self.word(self.assignment+0x3C)==0
        assert bytes(self.a.uc.mem_read(self.manager+0xE0,1))==b'\x00'
        assert struct.unpack('<h',self.a.uc.mem_read(self.voice+0x208,2))[0]==self.delay
        assert self.word(self.voice+0x234)==self.ticks
    def amp_release_model(self):
        e=self.envelopes[2];e.release();e.advance()
        self.eg_levels=[sh(b,0) for b in self.eg_states]
        self.model_amp([sh(b,0) for b in self.states])
        target=h(self.amp,0);cached=self.readback
        if target==cached:cached=cached-1 if cached else 1
        ph(self.amp,2,cached);duration=w(e.b,28)
        product=s32(self.coefficients[min(duration,24)]*(target-cached))>>16
        step=product+(1 if product>=0 else -1)
        expected=((step&65535)<<16)|target
        self.voice_bits&=~0x10
        return dict(target=target,cached=cached,duration=duration,step=step,word=expected)
    def manager_model(self):
        if self.category==-1:self.candidates=[0];self.active=[]
        self.voice_bits=(self.voice_bits&~0x82)|1
        if self.latched and self.sost:self.voice_bits|=0x100;return 'sostenuto_hold',None
        if self.pedal_enabled and self.pedal_value>=80:self.voice_bits|=3;return 'damper_hold',None
        if self.delay<0:
            self.voice_bits|=8;self.delay=self.ticks=0;return 'key_off_trigger',None
        if not self.allowed:return 'release_disabled',None
        if self.delay or self.ticks or self.voice_bits&8:
            self.voice_bits=(self.voice_bits&~9)|4;self.delay=self.ticks=0;self.waiting=False
            return 'cancel_before_start',None
        self.voice_bits|=5;return 'start_release',self.amp_release_model()
    def event(self,event):
        self.bus_writes.clear();self.bus_reads.clear();self.visits.clear();expected=[];branch='none';command=None
        if event=='note_off':
            assert self.category==-1
            self.a.call(0x1F60A4,self.oscruntime,0x80+(self.note<<8)+(64<<16))
            if self.voice_bits&0x80:branch,command=self.manager_model();expected=['manager','release_state']
        elif event=='damper_on':
            self.a.call(0x1F5E44,self.oscruntime)
            if self.osc_bytes()[0x2C]&128 and not self.voice_bits&1:self.eg_states[2][50]=1;branch='auxiliary_on'
        elif event=='damper_off':
            self.a.call(0x1F5E98,self.oscruntime)
            if self.osc_bytes()[0x2C]&128:
                if self.voice_bits&1 and self.allowed:branch,command=self.manager_model();expected=['manager','release_state']
                else:self.eg_states[2][51]=1;branch='auxiliary_off'
            elif self.voice_bits&2:branch,command=self.manager_model();expected=['manager','release_state']
            elif self.category!=-1:
                expected=['classification'];index=self.class_note-self.class_offset
                if self.threshold>index and not self.class_down:
                    branch,command=self.manager_model();expected+=['manager','release_state']
                else:branch='classified_keep'
        else:
            assert event in ['sostenuto_on','sostenuto_off']
            self.a.call(0x1F5F4C,self.oscruntime,int(event=='sostenuto_on'))
            if event=='sostenuto_on':
                if self.voice_bits&2:self.voice_bits|=0x100;branch='sostenuto_mark'
            elif self.voice_bits&1:branch,command=self.manager_model();expected=['manager','release_state']
        if command:expected+=['amp_commit']
        if branch=='cancel_before_start':expected+=['cancel_wait']
        assert self.visits==expected,(event,branch,self.visits,expected)
        assert [x[1] for x in self.bus_writes if x[0]==0x418]==([command['word']] if command else [])
        assert self.bus_reads.count(0x42C)==(2 if command else 0)
        self.compare_flow()
        return dict(event=event,branch=branch,voice_status=self.voice_bits,amp_stage=self.eg_states[2][6],
                    amp_level=sh(self.eg_states[2],0),aux_on=self.eg_states[2][50],aux_off=self.eg_states[2][51],
                    candidates=list(self.candidates),active=list(self.active),command=command,
                    visits=list(self.visits),bus_writes=list(self.bus_writes))
    def tick(self,clock):
        self.a.write(self.clock+4,clock);self.visits.clear();self.a.call(0x1F8140,self.voice)
        expected=[]
        if self.voice_bits&0x81 and not self.delay and not self.ticks:
            if self.voice_bits&0x40:
                if self.voice_bits&4:self.envelopes[0].setup(3);self.envelopes[2].release()
                self.voice_bits&=~0x40
            elif self.voice_bits&4:
                self.voice_bits&=~4
                for e in self.envelopes:e.release()
                expected=['deferred_egs']
            else:
                self.voice_bits|=0x10
                for kind,e in enumerate(self.envelopes):
                    stage=e.b[6];e.advance()
                    if kind==2 and stage==7 and (not self.osc_bytes()[0x2C]&128 or self.voice_bits&1):
                        e.b[6]=6;self.voice_bits|=32
                for slot in [1,0]:
                    p=self.params(slot);scale=min(0x7FFFFFFF,self.factor(slot,16,20)*self.factor(slot,24)>>8)
                    frozen=self.ta[25+4*slot];frozen=bool(frozen if frozen>=0 else p[0]&64)
                    note=note_adjust(p[12]&15,self.ta[22+4*slot])
                    self.m.advance(self.states[slot],p[0]&63,scale,frozen,self.scalar(slot,p[1],0),p[12]>>7,note,p[13],clock)
        assert self.visits==expected,(self.visits,expected)
        self.compare_flow()
        if self.voice_bits&0x10:
            values=[0,0]
            for slot in [1,0]:values[slot]=self.wave(slot)
            self.refresh_egs()
            for slot in range(2):self.update_mixer(slot)
            self.eg_levels=[sh(b,0) for b in self.eg_states];self.targets(values)
        self.compare_flow()
        return dict(voice_status=self.voice_bits,stages=[b[6] for b in self.eg_states],levels=[sh(b,0) for b in self.eg_states],
                    amp=h(self.amp,0),aux_level=sh(self.eg_states[2],52),remaining=[q64(b,16) for b in self.eg_states])

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('pedal-release-classification',0x1FE834,0x1FE93C),('pedal-release-tick',0x1F80D0,0x1F8294),
                       ('pedal-release-manager',0x1FD4F4,0x1FD53C),('pedal-release-commit',0x1F8AF4,0x1F8BF8)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);branches=[]
    # Original manager, original controller gate and original release EG/TG body.
    for auxiliary,cc,enabled,sost,latched,allowed,delay,ticks,ready in itertools.product(
            range(2),[0,64,79,80,81,127],range(2),range(2),range(2),[0,1,-1],[-1,0,3],[0,5],range(2)):
        r.prepare(program(auxiliary=bool(auxiliary)),0);r.pedal(cc,enabled=bool(enabled));r.initialize_all()
        r.configure(flags=0x80|(8 if ready else 0),allowed=allowed,delay=delay,ticks=ticks,sost=bool(sost),latched=bool(latched))
        result=r.event('note_off');branches.append(dict(auxiliary=auxiliary,cc64=cc,enabled=enabled,sost=sost,latched=latched,
            allowed=allowed,delay=delay,ticks=ticks,ready=ready,**result))
    off=[]
    for auxiliary,flags,allowed,category in itertools.product(range(2),[0,1,2,3,0x80,0x81,0x82,0x83],[0,1,-1],[-1,0]):
        r.prepare(program(auxiliary=bool(auxiliary)),0);r.pedal(0);r.initialize_all()
        r.configure(flags=flags,allowed=allowed,category=category);off.append(dict(auxiliary=auxiliary,input_flags=flags,allowed=allowed,category=category,**r.event('damper_off')))
    classified=[]
    for threshold,offset,key,held in itertools.product([32,109],[0,7],[0,31,32,63,64,108,109,127],range(2)):
        if key<offset:continue
        r.prepare(program(auxiliary=False),0);r.pedal(0);r.initialize_all()
        r.configure(flags=0x80,category=0,class_note=key,class_offset=offset,threshold=threshold,class_down=bool(held))
        classified.append(dict(threshold=threshold,offset=offset,key=key,held=held,**r.event('damper_off')))
    on=[]
    for auxiliary,flags in itertools.product(range(2),[0,1,2,3,0x80,0x81,0x82,0x83]):
        r.prepare(program(auxiliary=bool(auxiliary)),0);r.pedal(127);r.initialize_all();r.configure(flags=flags)
        on.append(dict(auxiliary=auxiliary,input_flags=flags,events=[r.event('damper_on'),r.event('sostenuto_on')]))
    ticks=[]
    for flags,delay,wait in itertools.product([0,0x80,1,5,0xC0,0x45,0xA0,0x41],[-1,0,3],[0,5]):
        r.prepare(program(),0);r.pedal(0);r.initialize_all();r.configure(flags=flags,delay=delay,ticks=wait)
        ticks.append(dict(input_flags=flags,delay=delay,wait=wait,state=r.tick(0)))
    traces=[]
    for auxiliary,special,enabled,sost in itertools.product(range(2),range(2),range(2),range(2)):
        r.prepare(program(auxiliary=bool(auxiliary)),0);r.pedal(127,enabled=bool(enabled),special=bool(special));r.initialize_all()
        r.configure(sost=bool(sost),latched=bool(sost));steps=[];events=[]
        for update in range(192):
            if update==16:events.append(dict(update=update,**r.event('note_off')))
            if update==64:
                r.pedal(0,enabled=bool(enabled),special=bool(special));events.append(dict(update=update,**r.event('damper_off')))
            if update==96 and sost:
                r.sostenuto(False)
                events.append(dict(update=update,**r.event('sostenuto_off')))
            steps.append(dict(update=update,cc64=r.pedal_value,**r.tick(20*update)))
        traces.append(dict(auxiliary=auxiliary,special=special,enabled=enabled,sost=sost,events=events,steps=steps))
    # Equality nudge and sign of the final submitted step use the modeled target.
    commits=[]
    for auxiliary,readback in itertools.product(range(2),[0,1,12345,32767,'target']):
        r.prepare(program(auxiliary=bool(auxiliary)),0);r.pedal(0);r.initialize_all();r.configure()
        for update in range(8):r.tick(update*20)
        if readback=='target':
            r.event('note_off');target=h(r.amp,0)
            r.prepare(program(auxiliary=bool(auxiliary)),0);r.pedal(0);r.initialize_all();r.configure()
            for update in range(8):r.tick(update*20)
            r.readback=target
        else:r.readback=readback
        commits.append(dict(auxiliary=auxiliary,readback=r.readback,**r.event('note_off')))
        r.readback=12345
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory=[]
    for index,osc in itertools.product(range(768),range(2)):
        offset=0x1EF220+2140*index;record=raw[offset:offset+2140]
        if not record[0x564+380*osc+0x2C]&128:continue
        for special in range(2):
            r.prepare(record,osc);r.pedal(127,special=bool(special));r.initialize_all();r.configure();steps=[];events=[]
            for update in range(128):
                if update==16:events.append(dict(update=update,**r.event('note_off')))
                if update==64:
                    r.pedal(0,special=bool(special));events.append(dict(update=update,**r.event('damper_off')))
                steps.append(dict(update=update,cc64=r.pedal_value,**r.tick(20*update)))
            factory.append(dict(program=chr(65+index//128)+str(index%128).zfill(3),oscillator=osc+1,special=special,
                                source_offset=offset,source_sha256=hashlib.sha256(record).hexdigest(),events=events,steps=steps))
    helpers=['voice_math.py','firmware_voice_lfo.py','firmware_voice_lfo_integration.py','firmware_lfo_targets.py',
             'firmware_ams_mixers.py','firmware_envelopes.py','firmware_pedal_envelopes.py']
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),
                helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),additional_helpers={name:sha(ROOT/'research/tools'/name) for name in helpers},
                inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],
                branches=branches,damper_off=off,classified=classified,pedal_on=on,tick_gates=ticks,traces=traces,commits=commits,factory=factory,
                boundaries=['Original oscillator Note Off, damper and sostenuto release, classification, manager, controller gate, EG release and TG programming execute in private RAM',
                    'Only primitive TG bus read/write are intercepted, in addition to the inherited firmware assertion trap; instruction hooks observe entries without replacing computation',
                    'One explicitly active voice and synthetic allocator/OSC/controller/sample/pitch contexts; real voice admission, factory sample assembly and stereo pairing are not covered',
                    'Native voice tick is compared with independent EG/LFO state models; later waveform/mixer/target calls retain prior explicit fixture ordering',
                    'TG readback is supplied by fixture; submitted words are verified, no chip stepping, final audio or physical duration inferred',
                    'Classification bitmaps and offsets are controlled; user-facing meaning and production population of classification fields remain unresolved',
                    'Factory follow-up includes all16 stored auxiliary-flag OSCs in both controlled runtime table modes; actual OSC activation and audibility are not inferred',
                    'No OS, device, network or product code executes'])
    (OUT/'pedal-release-flow-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,note_off_cases=len(branches),damper_off_cases=len(off),classification_cases=len(classified),
                         pedal_on_cases=len(on),tick_gate_cases=len(ticks),continuous_traces=len(traces),continuous_updates=192*len(traces),
                         tg_commit_cases=len(commits),factory_traces=len(factory),factory_updates=128*len(factory)),indent=2))
if __name__=='__main__':main()
