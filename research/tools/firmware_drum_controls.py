#!/usr/bin/env python3
"""Original per-key writers, independent pan/send model and drum refresh."""
import argparse,collections,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_drum_voice_chain import Rig as DrumRig,KIT_OFFSET,KIT_STRIDE
from firmware_voice_refresh import Rig as RefreshRig,compare as compare_refresh
from firmware_voice_lfo import sha,PRELOAD,OUT,h,sh,w,s32,s16
from firmware_factory_voice_chain import sb
from program_firmware import Firmware,FW_SHA,BASE
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

FIELDS={20:0,21:1,22:2,23:3,24:4,25:5,26:7,28:8,29:10,30:9}
def clamp(x,low,high):return max(low,min(high,x))

def pan_model(r,v):
    a=r.a;b=bytearray(a.uc.mem_read(v+0x1C0,10));before=bytes(b);p=bytes(a.uc.mem_read(r.word(v+0x224)+0x144,8))
    ctx=r.word(v+8);c=bytes(a.uc.mem_read(ctx+0x2A,3));key=r.word(v+0x28);control=r.word(v+0x228)
    k=bytes(a.uc.mem_read(key,68));q=bytes(a.uc.mem_read(control,12));route=bytes(a.uc.mem_read(v+0x20F,1))[0]
    b[2:4]=b[:2];b[5]=b[4];b[7]=b[6]
    for at,out,scale in [(9,4,c[1]),(10,6,c[2])]:
        value=(q[at] if sb(q,at)>=0 else k[62 if at==9 else 63]) if route&128 else p[6 if at==9 else 7]
        b[out]=(value*scale>>7)&255
    if route&127 not in [0,12]:b[4]=b[6]=0
    random=not c[0];position=b[8] if random else p[5]&127
    if not random:
        if p[5]&128:position=k[60] if sb(q,8)<0 else q[8]
        if position==0:position=b[8];random=True
        part=b[9]
        if part!=64:
            part=max(0,part-1);position=max(0,position-1)
            if position<63:part=min(126,part*position*65>>12)
            elif position>63:part=max(0,126-((126-part)*(126-position)*65>>12))
            position=part+1
    target=(position&255)<<8;depth=sb(p,1);category=s32(r.word(v+0x240));class_note=s32(r.word(v+0x244))
    if depth:
        if category!=-1:source=min(class_note-60,60)*8739>>7
        else:
            assert p[0] in [0,1],('Unhandled controlled pan AMS source',p[0])
            source=sh(bytes(a.uc.mem_read(v+0x1F6,2)),0) if p[0]==1 else 0
        target+=clamp(depth*source*331>>15,-32768,32767)*8
    if category!=-1:
        difference=class_note-s32(r.word(v+0x248))
        if difference<0:target=max(0,target+difference*r.f.data[0x48EF6A]*10)
    if not random:
        value=max(0,c[0]-1)
        if value<63:target=max(target,0)*value*65>>12
        elif value>63:target=32512-(max(32512-target,0)*(126-value)*65>>12)
    target=clamp(target,256,32512);pair=r.word(v+0x218)
    if pair==1:target=2*target-32512 if target>16384 else 256
    elif pair==2:target=2*target-256 if target<16384 else 32512
    struct.pack_into('<H',b,0,target)
    return bytes(b[:8]),dict(pan=target,send1=b[4],send2=b[6],previous_pan=h(before,0),random=bool(random),pair=pair)

class Rig(DrumRig):
    bus_read=RefreshRig.bus_read
    explicit_advance=RefreshRig.explicit_advance
    explicit_poll=RefreshRig.explicit_poll
    verify_commits=RefreshRig.verify_commits
    snapshot=RefreshRig.snapshot
    def __init__(self,f,raw):
        self.capture=False;self.events=[];self.commits=[];self.current_commit=None;self.waits=[];self.active_mask=0;self.score=0x1234
        self.pan_pending={};self.pan_checks=[]
        super().__init__(f,raw);self.coefficients=list(struct.unpack_from('<25H',f.data,0x3A8D40))
        self.a.stubs[0x12F1D0]=lambda a:self.waits.append(a.get('R1')) or 0
    def clear(self):
        super().clear();self.events.clear();self.commits.clear();self.current_commit=None;self.waits.clear();self.pan_pending.clear();self.pan_checks.clear()
    def bus_write(self,a):
        if self.capture and self.current_commit is not None:self.current_commit['writes'].append([a.get('R0')-self.tg,a.get('R1')])
        return super().bus_write(a)
    def observe(self,uc,address,size,user):
        super().observe(uc,address,size,user)
        if not self.capture:return
        off=address-BASE;a=self.a
        labels={0x1F8140:'advance',0x1F969C:'poll',0x1FBD98:'wave',0x1FFDA0:'pitch_refresh',0x1FBD28:'filter_refresh',
                0x1FA9C4:'amp_refresh',0x20119C:'mixer',0x1FF38C:'pitch_target',0x1FB4B0:'filter_target',0x1F9DD4:'amp_target',
                0x1FEDFC:'pan_target',0x1F9828:'commit'}
        if off in labels:self.events.append([labels[off],a.get('R0')])
        if off==0x1FEDFC:self.pan_pending[a.get('R1')]=pan_model(self,a.get('R1'))
        if off==0x1F9828:
            v=a.get('R0');expected,row=self.pan_pending.pop(v);actual=bytes(a.uc.mem_read(v+0x1C0,8))
            assert actual==expected,(hex(v),actual.hex(),expected.hex(),row)
            self.pan_checks.append(dict(voice=(v-self.voices)//588,**row))
            self.current_commit=dict(voice=(v-self.voices)//588,state=bytes(a.uc.mem_read(v,588)).hex(),writes=[]);self.commits.append(self.current_commit)
    def write_key(self,key,selector,value,increment=False):
        self.put8(self.channel+0xE4,key);self.put8(self.channel+0xE5,selector)
        self.a.call(0x26E85C if increment else 0x26E7BC,self.channel,0,value)
    def configure_context(self):
        for off,value in [(0x2A,64),(0x2B,127),(0x2C,127)]:self.put8(self.context+off,value)
    def start_raw(self,note,velocity):
        self.capture=False;self.clear();self.put8(self.context+0x44,note);self.put8(self.context+0x45,velocity)
        self.a.uc.mem_write(0x111E0000,bytes(0x10000));self.a.call(0x1FEDE4)
        self.a.call(0x1F62F0,self.osc,0x90+(note<<8)+(velocity<<16));self.a.call(0x1FEDB8,0xC165DA38)
        result=[]
        for entry in self.started:
            v=entry['address'];key=(entry['key_ptr']-self.kitptr-24)//68;desc=bytes(self.a.uc.mem_read(entry['desc_ptr'],12));q=bytes(self.a.uc.mem_read(self.keycontrols+12*key,12))
            tune=2*(100*(sb(desc,6)+sb(q,4))+sb(desc,7)+sb(q,5)-6464)
            assert entry['tune']==tune,(entry,tune)
            if self.word(v+0x218)!=2:
                cutoff=(sb(desc,10)+sb(q,0)-64)*260;resonance=(sb(desc,11)+sb(q,1)-64)&255
                assert self.half(v+0x11C)==cutoff&65535 and bytes(self.a.uc.mem_read(v+0x11E,1))[0]==resonance
            result.append(dict(voice=(v-self.voices)//588,key=key,tune=tune,sample=self.word(v+0x238)))
        return result
    def setup(self,record,note,velocity,batch,cursor=0):
        self.capture=False;self.active_mask=0;self.prepare(record);self.configure_context();initial=self.start_raw(note,velocity)
        extra=0x110B0000;self.a.uc.mem_write(extra,bytes(12))
        for i in range(8):
            self.a.write(self.voices+588*i+0x1CC,extra);self.a.write(self.voices+588*i+0x1D8,extra+4)
        self.a.write(self.manager+0xE4,8);self.put8(self.manager+0xE8,batch);self.put8(self.manager+0xE1,cursor);self.put8(self.manager+0xE9,cursor)
        self.update_mask();self.clear();self.capture=True;return initial
    def update_mask(self):self.active_mask=sum(1<<bytes(self.a.uc.mem_read(self.voices+588*i+0x1A,1))[0] for i in self.active())
    def event(self,update,note,velocity):
        changes={16:[(26,96),(28,96),(30,100),(29,80)],24:[(24,76),(25,48)],48:[(28,0),(30,0),(29,127)],80:[(26,127),(28,32),(30,127),(29,64)]}
        for selector,value in changes.get(update,[]):self.write_key(note,selector,value)
        if update==32:self.a.call(0x1F60A4,self.osc,0x80+(note<<8)+(64<<16))
        started=[]
        if update==64:
            started=self.start_raw(note,velocity);self.capture=True
        return started

def compare(a,b):
    compare_refresh(a,b)
    for p,n in [(a.keycontrols,128*12),(a.controls,128),(a.part,64)]:assert bytes(a.a.uc.mem_read(p,n))==bytes(b.a.uc.mem_read(p,n)),hex(p)
    assert a.pan_checks==b.pan_checks

def write_matrix(r,smoke=False):
    r.capture=False;expected=bytearray(r.a.uc.mem_read(r.keycontrols,128*12));digest=hashlib.sha256();count=0
    for key,selector,value in itertools.product([0,60,127] if smoke else range(128),[19,*range(20,32)],[0,64,127] if smoke else range(128)):
        r.write_key(key,selector,value)
        if selector in FIELDS:expected[12*key+FIELDS[selector]]=value
        assert bytes(r.a.uc.mem_read(r.keycontrols,128*12))==expected,(key,selector,value)
        digest.update(bytes([key,selector,value]));digest.update(expected);count+=1
    increments=[]
    for key,selector,old,delta in itertools.product([0,60,127],FIELDS,[0,64,127,255],[-127,-1,0,1,127]):
        ptr=r.keycontrols+12*key+FIELDS[selector];r.put8(ptr,old);r.write_key(key,selector,delta,True)
        value=clamp((old if old<128 else old-256)+delta,0,127);actual=bytes(r.a.uc.mem_read(ptr,1))[0]
        assert actual==value;(increments.append(dict(key=key,selector=selector,old=old,delta=delta,value=value)))
    return dict(absolute_cases=count,absolute_sha256=digest.hexdigest(),increment_cases=increments,fields=FIELDS)

def pan_matrix(r,smoke):
    r.capture=False;v=r.voices;p=r.patch+0x564+0x144;state=v+0x1C0;key=r.word(v+0x28);ctl=r.word(v+0x228)
    source_key=bytes(r.a.uc.mem_read(key,68));source_ctl=bytes(r.a.uc.mem_read(ctl,12));source_p=bytes(r.a.uc.mem_read(p,8));source_v=bytes(r.a.uc.mem_read(v,588))
    rows=[];digest=hashlib.sha256();count=0
    combinations=itertools.product([0,64,127] if smoke else range(128),[0,1,32,64,96,127],[1,64,127],range(3),[0,1])
    for position,channel,part,pair,use_key in combinations:
        r.a.uc.mem_write(v,source_v);r.a.uc.mem_write(p,bytes([0,0,0,0,0,64|(128 if use_key else 0),127,127]))
        r.a.uc.mem_write(state,struct.pack('<HH6B',12345,0,12,0,23,0,37,part));r.put8(key+60,position);r.put8(ctl+8,255)
        r.put8(v+0x20F,128);r.a.write(v+0x218,pair)
        r.put8(r.context+0x2A,channel);expected,row=pan_model(r,v);r.a.call(0x1FEDFC,state,v,0)
        actual=bytes(r.a.uc.mem_read(state,8));assert actual==expected,(position,channel,part,pair,use_key,actual,expected)
        row.update(position=position,channel=channel,part=part,use_key=use_key)
        if channel==64 and part==64 and use_key:rows.append(row)
        digest.update(actual);count+=1
    modulation=[]
    for depth,source,category,class_note,class_previous in itertools.product([-99,0,99],[-4096,0,4096],[-1,0],[0,60,127],[0,127]):
        r.a.uc.mem_write(v,source_v);r.a.uc.mem_write(p,bytes([1,depth&255,0,0,0,192,127,127]));r.put8(ctl+8,64)
        r.a.uc.mem_write(v+0x1F6,struct.pack('<h',source));r.a.write(v+0x240,category,class_note,class_previous)
        r.a.uc.mem_write(state,struct.pack('<HH6B',12345,0,12,0,23,0,37,64));r.put8(r.context+0x2A,64)
        expected,row=pan_model(r,v);r.a.call(0x1FEDFC,state,v,0);assert bytes(r.a.uc.mem_read(state,8))==expected
        modulation.append(dict(depth=depth,source=source,category=category,class_note=class_note,class_previous=class_previous,**row))
    sends=[]
    for value,scale,route,use_key,override in itertools.product(range(128),[0,1,64,127,128],[0,1,12,13],[0,1],[-1,0,127]):
        r.a.uc.mem_write(v,source_v);r.a.uc.mem_write(p,bytes([0,0,0,0,0,64,value,127-value]));r.put8(key+62,value);r.put8(key+63,127-value)
        r.put8(ctl+9,override);r.put8(ctl+10,override);r.put8(v+0x20F,route|(128 if use_key else 0))
        r.put8(r.context+0x2B,scale);r.put8(r.context+0x2C,scale)
        expected,row=pan_model(r,v);r.a.call(0x1FEDFC,state,v,0);assert bytes(r.a.uc.mem_read(state,8))==expected
        sends.append(dict(value=value,scale=scale,route=route,use_key=use_key,override=override,send1=row['send1'],send2=row['send2']))
    r.a.uc.mem_write(v,source_v);r.a.uc.mem_write(key,source_key);r.a.uc.mem_write(ctl,source_ctl);r.a.uc.mem_write(p,source_p)
    return dict(position_cases=count,position_sha256=digest.hexdigest(),positions=rows,modulation=modulation,sends=sends)

def latched_controls(a,b,record):
    for r in [a,b]:r.setup(record,48,100,8)
    for selector,value in [(20,96),(21,80),(24,76),(25,48)]:a.write_key(48,selector,value)
    before=bytes(a.a.uc.mem_read(a.voices,8*588));assert before==bytes(b.a.uc.mem_read(b.voices,8*588))
    steps=[]
    for update in range(32):
        for r in [a,b]:
            r.clear();r.a.write(r.clock+4,123+20*update);r.a.call(0x1FD3CC,r.manager,1);r.a.call(0x1FE404,r.manager);r.verify_commits()
        assert bytes(a.a.uc.mem_read(a.voices,8*588))==bytes(b.a.uc.mem_read(b.voices,8*588))
        assert a.writes==b.writes and a.reads==b.reads and a.events==b.events
        steps.append(dict(update=update,identical_commits=len(a.commits),identical_writes=len(a.writes)))
    new=[]
    for r in [a,b]:
        created=r.start_raw(48,100);v=r.voices+588*created[0]['voice']
        new.append(dict(voices=created,cutoff=s16(r.half(v+0x11C)),resonance=sb(bytes(r.a.uc.mem_read(v+0x11E,1)),0)))
    assert new[0]['voices'][0]['tune']-new[1]['voices'][0]['tune']==2368
    assert s16(new[0]['cutoff']-new[1]['cutoff'])==8320 and new[0]['resonance']-new[1]['resonance']==16
    return dict(program='F042',note=48,steps=steps,retrigger_changed=new[0],retrigger_baseline=new[1],
        boundary='Original per-key writer plus normal refresh; excludes separate parameter-change callbacks outside this path')

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('drum-control-fields',0x26E63C,0x26E6D0),('drum-control-writers',0x26E7BC,0x26E910),
                       ('drum-pan-sends',0x1FEDFC,0x1FF124),('drum-filter-offsets',0x1FB79C,0x1FB86C)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory=json.loads((OUT/'drum-voice-chain-check.json').read_text());assert factory['passed'] and not factory['smoke_only']
    a=Rig(f,raw);b=Rig(f,raw)
    def record(name):
        index=(ord(name[0])-65)*128+int(name[1:]);return raw[0x1EF220+2140*index:0x1EF220+2140*(index+1)]
    a.setup(record('F042'),48,100,8);a.capture=False
    writers=write_matrix(a,args.smoke);a.setup(record('F042'),48,100,8);a.capture=False;pans=pan_matrix(a,args.smoke)
    latched=latched_controls(a,b,record('F042'));choices={}
    for kit in factory['kits']:
        rows=[x for x in factory['factory'] if x['program']==kit['program'] and x['velocity']==100 and x['voices']]
        preferred=next((x for x in rows if x['note']==48),rows[0]);choices[kit['program'],preferred['note']]=preferred
        stereo=next((x for x in rows if any(v['pair_type']==1 for v in x['voices'])),None)
        if stereo:choices[kit['program'],stereo['note']]=stereo
        for row in rows:
            if any(v['release'] or v['reverse'] or v['key_flags']&2 for v in row['voices']):choices[row['program'],row['note']]=row
    if args.smoke:choices={('F042',48):next(x for x in factory['factory'] if (x['program'],x['note'],x['velocity'])==('F042',48,100))}
    traces=[]
    for (name,note),choice in sorted(choices.items()):
        for batch in ([3] if args.smoke else [1,3,8]):
            cursor=7 if batch==3 else 0;initial=a.setup(record(name),note,100,batch,cursor);b.setup(record(name),note,100,batch,cursor);compare(a,b);steps=[]
            for update in range(96):
                a.clear();b.clear();new=[]
                for r in [a,b]:
                    started=r.event(update,note,100);r.a.write(r.clock+4,123+20*update)
                    if r is a:new=started
                compare(a,b);a.clear();b.clear();elapsed=[0,1,3,20][update%4]
                a.a.call(0x1FD3CC,a.manager,elapsed);b.explicit_advance(elapsed);compare(a,b)
                a.clear();b.clear();a.a.call(0x1FE404,a.manager);b.explicit_poll();compare(a,b)
                checked=a.verify_commits();steps.append(dict(update=update,elapsed=elapsed,commits=checked,pan=list(a.pan_checks),new_voices=new,active=a.active(),**a.snapshot()))
                a.update_mask();b.update_mask()
            traces.append(dict(program=name,note=note,batch=batch,initial_cursor=cursor,initial=initial,steps=steps));print('Drum refreshed',name,note,batch,flush=True)
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_drum_voice_chain.py','firmware_voice_refresh.py','firmware_factory_voice_chain.py','firmware_voice_lfo.py','voice_math.py']},
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str((OUT/'drum-voice-chain-check.json').relative_to(ROOT)),sha256=sha(OUT/'drum-voice-chain-check.json'))],
        writers=writers,pan=pans,traces=traces,latched_controls=latched,boundaries=['Original per-key absolute/increment writers execute on private channel/128-key records; full MIDI NRPN byte intake is outside this check',
            'Independent pan/send equations check both control stages, random-position retention, override fallback, AMS/classified branches, stereo remap and bus send suppression',
            'Native drum advance/poll/batch is compared against explicit original-kernel scheduling, including all voice/list/controller/PRNG state and TG read/write/wait order',
            'Per-key events alter volume/pan/sends and coarse/fine tuning, execute original note-off and retrigger; new voices independently check tuning and drum filter offsets',
            'Pan/send targets and all normal TG amp/pitch/filter target/step words additionally compare independent arithmetic',
            'Two auxiliary parameter pointers at voice+1CC/+1D8 are explicitly bound to private zero parameters as in the prior refresh check; production binding source remains unresolved',
            'TG active masks reflect fixture OSC lists; status/ready reads are zero and running amplitude/score readbacks fixed16384/0x1234, startup/retrigger reads amplitude zero',
            'Eight private slots and fixed clock/elapsed schedule; no OS/hardware/audio, no physical-time or transfer-function claim'])
    target=OUT/('drum-controls-smoke.json' if args.smoke else 'drum-controls-check.json');target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,absolute_writes=writers['absolute_cases'],increments=len(writers['increment_cases']),pan_positions=pans['position_cases'],pan_modulation=len(pans['modulation']),sends=len(pans['sends']),
        traces=len(traces),updates=sum(len(t['steps']) for t in traces),commits=sum(len(s['commits']) for t in traces for s in t['steps'])),indent=2))
if __name__=='__main__':main()
