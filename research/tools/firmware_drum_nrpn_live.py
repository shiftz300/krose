#!/usr/bin/env python3
"""Original MIDI CC/NRPN routing attached to real drum voices and live EGs."""
import argparse,hashlib,itertools,json
from pathlib import Path
from firmware_drum_envelope_live import Rig as LiveRig,compare as compare_live,encoded_sha
from firmware_drum_envelope_times import read,record
from firmware_midi_parameters import FIELDS
from firmware_voice_lfo import PRELOAD,OUT,sha
from program_firmware import Firmware,FW_SHA
from layout import PRODUCT_ROOT as ROOT

def digest(b):return hashlib.sha256(b).hexdigest()
def signed(b):return b if b<128 else b-256
class CCModel:
    def __init__(self,r):
        self.channel=bytearray(read(r.a,r.channel,436));self.keys=bytearray(read(r.a,r.keycontrols,1536));self.controls=bytearray(read(r.a,r.controls,128))
    def send(self,cc,value,source):
        c=self.channel;c[0x82+cc]=value
        if source!=5:c[0x13C+cc]=value
        self.controls[cc]=value;flags=c[0x114]
        if cc in [98,99]:
            flags=(flags&~64)|(0x88 if cc==98 else 0x84)
            if flags&(4 if cc==98 else 8):flags&=~48
        elif cc in [100,101]:
            flags=(flags&127)|(0x42 if cc==100 else 0x41)
            if flags&(1 if cc==100 else 2):flags&=~48
        elif cc in [6,96,97] and flags&0x8C==0x8C:
            high,key=c[0xE5],c[0xE4]
            if high in FIELDS:
                at=12*key+FIELDS[high]
                self.keys[at]=value if cc==6 else max(0,min(127,signed(self.keys[at])+(1 if cc==96 else -1)))
        elif cc in [6,38] and flags&0x43==0x43:
            flags|=16 if cc==6 else 32
            # The corpus uses only the Null/unsupported RPN family here.
            assert c[0xE7] or c[0xE6]>2
        c[0x114]=flags

class Rig(LiveRig):
    def __init__(self,*args):
        self.nrpn_ready=False;self.message_source=0;self.messages=[]
        super().__init__(*args)
        self.channels=0x11040000;self.channel=self.channels+7*436;self.event=0x11047000;self.channel_nodes=0x11047100
        self.a.stubs[0x58E74]=lambda m:0
    def prepare(self,*args):
        self.nrpn_ready=False;super().prepare(*args);a=self.a
        a.write(self.system+0x18,self.channels);a.write(self.system+0x2C,0);a.write(self.mode,3)
        for n in range(16):
            p=self.channels+436*n;a.uc.mem_write(p,bytes(436));a.call(0x26E08C,p,n)
        self.bind_input();a.write(0xC0FE9DC0,0x11047200)
        self.model=CCModel(self);self.messages.clear();self.nrpn_ready=True
    def bind_input(self):
        a=self.a
        a.write(self.channel+0x138,self.keycontrols);a.call(0x26E094,self.channel,1)
        a.write(self.channel_nodes,self.channel_nodes+12,0,self.context)
        a.write(self.channel_nodes+12,self.channel_nodes+12,0,0);a.write(self.channel+0xFC,self.channel_nodes)
        a.write(self.channel_nodes+24,self.channel_nodes+24,0,0);a.write(self.channel+0x108,self.channel_nodes+24)
    def cc(self,cc,value,source=None):
        assert self.nrpn_ready
        source=self.message_source if source is None else source
        before=bytes(self.model.keys);self.model.send(cc,value,source)
        before_other=read(self.a,self.channels,7*436)+read(self.a,self.channel+436,8*436)
        self.a.write(self.event,0,0xB7+(cc<<8)+(value<<16)+(source<<24),0)
        self.a.call(0x271500,self.system,self.event)
        assert read(self.a,self.channel,436)==bytes(self.model.channel),(cc,value,source,'channel')
        assert read(self.a,self.keycontrols,1536)==bytes(self.model.keys),(cc,value,source,'keys')
        assert read(self.a,self.controls,128)==bytes(self.model.controls),(cc,value,source,'controls')
        assert before_other==read(self.a,self.channels,7*436)+read(self.a,self.channel+436,8*436)
        changes=[dict(key=i//12,field=i%12,before=x,after=y) for i,(x,y) in enumerate(zip(before,self.model.keys)) if x!=y]
        self.messages.append(dict(update=self.update,cc=cc,value=value,source=source,flags=self.model.channel[0x114],
            selected_high=self.model.channel[0xE5],selected_key=self.model.channel[0xE4],changes=changes,
            live=self.model.channel[0x82+cc],shadow=self.model.channel[0x13C+cc],keys_sha256=digest(self.model.keys)))
    def write_key(self,key,selector,value,increment=False):
        self.cc(99,selector);self.cc(98,key)
        self.cc((96 if value>0 else 97) if increment else 6,0 if increment else value)

def compare(a,b,positions):
    compare_live(a,b,positions)
    assert a.messages==b.messages and read(a.a,a.channels,16*436)==read(b.a,b.channels,16*436)

def message_matrix(r,raw,smoke):
    r.message_source=0;r.setup_live(record(raw,'F042'),48,8,0);r.capture=False;r.eg_capture=False
    r.a.call(0x26E08C,r.channel,7);r.bind_input();r.model=CCModel(r)
    r.messages.clear();r.update=0
    # Exercise messages before either selector has arrived, then carry the
    # selection state across all complete and partial changes.
    for cc,value in [(6,17),(38,31),(96,127),(97,0),(99,22),(6,27),(98,48),(6,72)]:r.cc(cc,value)
    for source,selector,key,value in itertools.product([0,5],[19,*range(20,32),127],[0,48,127],[0,64,127]):
        r.message_source=source
        r.cc(99,selector);r.cc(98,key);r.cc(6,value);r.cc(38,127-value);r.cc(96,127);r.cc(97,0)
    # Default pan/send -1 goes through the signed increment branch; keep a
    # fresh native reset so this starts from actual untouched default bytes.
    general=list(r.messages);r.setup_live(record(raw,'F042'),48,8,0);r.capture=False;r.eg_capture=False;r.messages.clear()
    for selector in [28,29,30]:r.cc(99,selector);r.cc(98,49);r.cc(96,127);r.cc(97,127)
    defaults=list(r.messages);r.messages.clear()
    # A changed high selector can reuse an already received low selector.
    for cc,value in [(99,22),(98,48),(6,70),(99,23),(6,41),(98,49),(6,42),
                     (101,127),(100,127),(6,99),(99,22),(6,43)]:r.cc(cc,value)
    stale=list(r.messages)
    return dict(messages=general,default_overrides=defaults,selector_retention=stale)

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');p.add_argument('--matrix-only',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    a=Rig(f,raw);b=Rig(f,raw);matrix=message_matrix(a,raw,args.smoke);traces=[]
    choices=[('F042',48)] if args.smoke else [('F033',48),('F042',48),('F068',34)]
    if not args.matrix_only:
        for name,note in choices:
            for batch,source in itertools.product([8] if args.smoke else [1,8],[0,5]):
                for r in [a,b]:r.message_source=source;r.setup_live(record(raw,name),note,batch,0)
                compare(a,b,[0,0,0]);first_voices=list(a.active());primary=next(i for i in first_voices if a.word(a.voices+588*i+0x218)!=2)
                edited=False;retrigger=None;off=None;steps=[]
                for update in range(192 if args.smoke else 1024):
                    positions=[len(a.offsets),len(a.segments),len(a.core_steps)];a.clear();b.clear();events=[]
                    for r in [a,b]:r.update=update;r.phase='MIDI_NRPN'
                    if update==0:
                        for r in [a,b]:r.edit(note,22,0)
                        events.append(['attack',0])
                    state=next((v for v in a.eg_snapshot() if v['voice']==primary),None)
                    if not edited and state and state['stages'][1] in [2,3]:
                        for r in [a,b]:r.edit(note,23,32)
                        events.append(['decay',32]);edited=True
                    if retrigger is None and any(o['kind']=='filter' and o['phase']=='decay' and o['update']>=0 for o in a.offsets):
                        for r in [a,b]:r.start_raw(note,100);r.capture=True
                        retrigger=update;events.append(['on',note,100])
                    if retrigger is not None and update==retrigger+16:
                        for r in [a,b]:r.a.call(0x1F60A4,r.osc,0x80+(note<<8)+(64<<16))
                        off=update;events.append(['off',note,64])
                    compare(a,b,positions)
                    for r in [a,b]:r.clear();r.a.write(r.clock+4,123+20*update)
                    elapsed=[0,1,3,20][update%4];a.a.call(0x1FD3CC,a.manager,elapsed);b.explicit_advance(elapsed);compare(a,b,positions)
                    a.clear();b.clear();a.a.call(0x1FE404,a.manager);b.explicit_poll();compare(a,b,positions)
                    commits=a.verify_commits();steps.append(dict(update=update,elapsed=elapsed,events=events,commits=len(commits),commit_sha256=encoded_sha(commits),
                        core_steps=len(a.core_steps)-positions[2],state=a.eg_snapshot()))
                assert edited and retrigger is not None and off is not None
                traces.append(dict(program=name,note=note,batch=batch,source=source,source_sha256=digest(record(raw,name)),first_voices=first_voices,
                    retrigger_at=retrigger,off_at=off,messages=list(a.messages),key_edits=list(a.key_edits),offsets=list(a.offsets),segments=list(a.segments),core_checks=list(a.core_steps),steps=steps))
                print(json.dumps(dict(trace=len(traces),program=name,batch=batch,source=source,retrigger=retrigger)),flush=True)
    for name,note in choices:
        for batch in [8] if args.smoke else [1,8]:
            pair=[t for t in traces if (t['program'],t['batch'])==(name,batch)]
            if pair:
                assert len(pair)==2
                for field in ['key_edits','offsets','segments','core_checks','steps']:assert pair[0][field]==pair[1][field],(name,batch,field)
    counts=dict(matrix_messages=sum(len(v) for v in matrix.values()),traces=len(traces),updates=sum(len(t['steps']) for t in traces),
        live_messages=sum(len(t['messages']) for t in traces),commits=sum(s['commits'] for t in traces for s in t['steps']),core_steps=sum(len(t['core_checks']) for t in traces),
        segments=sum(len(t['segments']) for t in traces),offsets=sum(len(t['offsets']) for t in traces))
    result=dict(passed=True,smoke_only=args.smoke or args.matrix_only,firmware_sha256=FW_SHA,device_access=False,actual_DSP_audio_executed=False,
        tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),math_sha256=sha(ROOT/'research/tools/voice_math.py'),
        additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_drum_envelope_live.py','firmware_drum_envelope_times.py','firmware_drum_controls.py','firmware_drum_voice_chain.py','firmware_voice_refresh.py','firmware_factory_voice_chain.py','firmware_envelopes.py','firmware_voice_lfo.py','firmware_midi_parameters.py']},
        inputs=[dict(path=str(x.relative_to(ROOT)),sha256=sha(x)) for x in [PRELOAD,OUT/'drum-eg-live-check.json',OUT/'midi-parameters-check.json']],
        counts=counts,matrix=matrix,traces=traces,boundaries=['CC messages execute original271500 event/channel routing,26EC34 dispatch,27422C controller copying and26E7BC/26E85C drum writers; only notification58E74 is supplied',
            'One real drum context is attached to channel7 in a native initialized16-channel array; every CC compares all436 selected-channel bytes,128 live controls and1536 key bytes to independent state arithmetic; other15 channels remain unchanged',
            'Live per-key edits use CC99/98/6 messages, not direct setter invocation. Original raw PCM NoteOn/Off entries, manager/poll, TG responses and independent core step/segment models remain as in the previous continuous check',
            'CC source0/5, partial and retained selectors, Null RPN, unsupported selectors, Data LSB, unit increment/decrement and signed default overrides are exercised',
            'Mode3 with a single primary drum context; no complete raw MIDI note-routing or byte-stream parser, dynamic pedal, host sample-clock, OS, hardware or DSP audio claim'])
    suffix='smoke' if result['smoke_only'] else 'check';path=OUT/('drum-nrpn-live-'+suffix+'.json');path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,counts=counts)))
if __name__=='__main__':main()
