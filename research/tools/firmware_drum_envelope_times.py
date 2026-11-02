#!/usr/bin/env python3
"""Drum-key EG time offsets: native helpers and actual stage-entry consumption."""
import argparse, contextlib, hashlib, io, itertools, json, struct
from pathlib import Path
from firmware_drum_controls import Rig as DrumRig
from firmware_envelopes import Core
from firmware_voice_lfo import PRELOAD, OUT, sha, s32
from firmware_factory_voice_chain import sb
from firmware_inspect import inspect
from program_firmware import Firmware, Arm, BASE, FW_SHA
from layout import PRODUCT_ROOT as ROOT

HELPERS = {0x1FAF6C: ('amp_attack', 8, 2),
           0x1FBC60: ('filter_attack', 8, 2),
           0x1FAFD8: ('decay', 9, 3)}
KINDS = {0x120: 'filter', 0x15C: 'amp'}
def clip(x): return max(0, min(99, x))
def read(a, p, n): return bytes(a.uc.mem_read(p, n))
def record(raw, name):
    i = (ord(name[0])-65)*128+int(name[1:])
    return raw[0x1EF220+2140*i:0x1EF220+2140*(i+1)]

def helper_matrix(f):
    a = Arm(f); v=0x11010000; desc=0x11011000; ctl=0x11012000; region=0x11013000
    # Only the upstream shared attack transform is supplied. The native drum/
    # melodic offset branch and clamp execute. Real upstream calls run below.
    a.stubs[0x274A10] = lambda m: m.get('R1')
    a.stubs[0x274B70] = lambda m: m.get('R1')
    a.write(v+0x24,desc);a.write(v+0x228,ctl);a.write(v+0x22C,region)
    digest=hashlib.sha256();count=0;examples=[]
    for off, (label, d, q) in HELPERS.items():
        for base, layer, key in itertools.product(range(100),[-99,-64,-1,0,1,63,99],range(128)):
            a.uc.mem_write(desc+d,bytes([layer&255]));a.uc.mem_write(ctl+q,bytes([key]))
            a.write(v+0x24,desc)
            actual=a.call(off,0,v,base,base,stack=(base,))
            expected=clip(base+layer+key-64)
            assert actual==expected,(label,base,layer,key,actual,expected)
            digest.update(struct.pack('<IiiiI',off,base,layer,key,actual));count+=1
            if base==50 and layer==0 and key in [0,32,64,96,127]:
                examples.append(dict(helper=label,base=base,layer=layer,key=key,result=actual))
        # Distinguish the non-drum region fallback from per-key controls.
        for base, delta, has_region in itertools.product([0,1,50,98,99],[-128,-1,0,1,127],[False,True]):
            a.write(v+0x24,0);a.write(v+0x22C,region if has_region else 0)
            a.uc.mem_write(region+(14 if label=='decay' else 13),bytes([delta&255]))
            actual=a.call(off,0,v,base,base,stack=(base,))
            expected=clip(base+(delta if has_region else 0));assert actual==expected
            digest.update(struct.pack('<IiiiI',off,base,delta,has_region,actual));count+=1
    return dict(cases=count,sha256=digest.hexdigest(),examples=examples,
                upstream_attack_transform='identity fixture only in this isolated matrix')

class Rig(DrumRig):
    def __init__(self,*args):
        self.eg_capture=False;self.pending=[];self.segments=[];self.offsets=[];self.core_pending=None;self.phase='setup'
        super().__init__(*args);self.core=Core(self.f)
    def observe(self,uc,address,size,user):
        super().observe(uc,address,size,user)
        if not self.eg_capture:return
        a=self.a;off=address-BASE
        if self.pending and address==self.pending[-1]['return_address']:
            row=self.pending.pop();value=a.get('R0');expected=clip(row['shared_base']+row['layer']+row['key']-64)
            assert value==expected,(row,value,expected)
            self.offsets.append({k:v for k,v in row.items() if k not in ['return_address','voice_address']}|dict(result=value,phase=self.phase))
        if off in HELPERS:
            label,d,q=HELPERS[off];v=a.get('R1');desc=self.word(v+0x24);ctl=self.word(v+0x228)
            assert desc and ctl
            self.pending.append(dict(helper=label,kind=KINDS[(a.get('R0')-v)%588],voice=(v-self.voices)//588,voice_address=v,
                layer=sb(read(a,desc+d,1),0),key=sb(read(a,ctl+q,1),0),shared_base=a.get('R2'),return_address=a.get('LR')))
        if off in [0x1FAF88,0x1FBC7C]:
            assert self.pending;self.pending[-1]['shared_base']=a.get('R0')
        if off==0x1FB0AC:
            p=a.get('R0');slot=(p-self.voices)//588;relative=(p-self.voices)%588
            if relative not in KINDS:return
            assert self.core_pending is None
            b=bytearray(read(a,p,48));time=a.get('R1');amount=s32(a.get('R2'));curve=a.get('R3')
            self.core.segment(b,time,curve,amount)
            self.core_pending=(p,bytes(b),dict(voice=slot,kind=KINDS[relative],phase=self.phase,
                stage=read(a,p+6,1)[0],time_index=time,amount=amount,curve=curve,
                duration=struct.unpack_from('<I',b,24)[0]))
        if off==0x1FB118 and self.core_pending:
            p,expected,row=self.core_pending;assert read(a,p,48)==expected,(row,read(a,p,48).hex(),expected.hex())
            self.segments.append(row);self.core_pending=None
    def state(self,v):return read(self.a,v+0x120,48)+read(self.a,v+0x15C,100)
    def phase_call(self,v,kind,phase):
        p=v+(0x120 if kind=='filter' else 0x15C)
        self.phase=phase
        if phase=='attack':
            self.a.call(0x1FB8C4 if kind=='filter' else 0x1FA300,p,v)
            self.a.call(0x1FBCCC if kind=='filter' else 0x1FA928,p,v)
        elif phase in ['decay','slope']:
            self.put8(p+6,0 if phase=='decay' else 2)
            self.a.call(0x1FBAF8 if kind=='filter' else 0x1FA6C0,p,v)
        else:self.a.call(0x1FBAA0 if kind=='filter' else 0x1FA664,p,v)

def phase_matrix(r,raw,factory,smoke):
    choices=[]
    for kit in factory['kits']:
        rows=[x for x in factory['factory'] if x['program']==kit['program'] and x['velocity']==100 and x['voices']]
        choices.append(next((x for x in rows if x['note']==48),rows[0]))
    if smoke:choices=choices[:1]
    traces=[]
    for choice in choices:
        name,note=choice['program'],choice['note'];r.eg_capture=False
        r.setup(record(raw,name),note,100,8);r.capture=False;r.eg_capture=True
        active=r.active();assert active
        for key_attack,key_decay in itertools.product([0,64,127],repeat=2):
            r.offsets.clear();r.segments.clear();before=[r.state(r.voices+588*i) for i in active]
            r.write_key(note,22,key_attack);r.write_key(note,23,key_decay)
            assert before==[r.state(r.voices+588*i) for i in active]
            for i in active:
                v=r.voices+588*i
                for kind,phase in itertools.product(['filter','amp'],['attack','decay','slope','release']):
                    r.phase_call(v,kind,phase)
            assert not r.pending and r.core_pending is None
            expected={(i,kind,phase) for i in active for kind in ['filter','amp'] for phase in ['attack','decay','slope','release']}
            assert {(x['voice'],x['kind'],x['phase']) for x in r.segments}==expected
            assert len(r.offsets)==4*len(active),(name,note,r.offsets)
            assert all(x['key']==(key_decay if x['helper']=='decay' else key_attack) for x in r.offsets)
            for x in r.offsets:
                target=next(s for s in r.segments if (s['voice'],s['kind'],s['phase'])==(x['voice'],x['kind'],x['phase']))
                assert target['time_index']==x['result'],(x,target)
            traces.append(dict(program=name,note=note,key_attack=key_attack,key_decay=key_decay,voices=active,
                immediate_eg_bytes_unchanged=True,offsets=list(r.offsets),segments=list(r.segments)))
        current=traces[-9:]
        for i,kind,phase in itertools.product(active,['filter','amp'],['slope','release']):
            indices={s['time_index'] for t in current for s in t['segments'] if (s['voice'],s['kind'],s['phase'])==(i,kind,phase)}
            assert len(indices)==1,(name,i,kind,phase,indices)
        print(json.dumps(dict(program=name,phase_traces=len(traces))),flush=True)
    r.eg_capture=False
    return traces

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args()
    f=Firmware()
    if not args.verify_arm:return
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory_path=OUT/'drum-voice-chain-check.json';factory=json.loads(factory_path.read_text());assert factory['passed'] and not factory['smoke_only']
    matrix=helper_matrix(f);r=Rig(f,raw);traces=phase_matrix(r,raw,factory,args.smoke)
    for name,lo,hi in [('drum-eg-time-offsets',0x1FAF6C,0x1FB02C),('drum-filter-attack-time',0x1FBC60,0x1FBCCC)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,
        tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),math_sha256=sha(ROOT/'research/tools/voice_math.py'),
        additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_drum_controls.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_envelopes.py','firmware_voice_lfo.py','firmware_inspect.py']},
        inputs=[dict(path=str(x.relative_to(ROOT)),sha256=sha(x)) for x in [PRELOAD,factory_path]],
        counts=dict(helper_cases=matrix['cases'],kits=len({x['program'] for x in traces}),phase_traces=len(traces),
            offset_calls=sum(len(x['offsets']) for x in traces),segment_calls=sum(len(x['segments']) for x in traces)),
        helper_matrix=matrix,traces=traces,actual_DSP_audio_executed=False,
        boundaries=['Isolated offset matrix supplies upstream shared attack transforms as identity; drum/melodic offset branches and clamps execute natively',
            'Factory stage matrix executes original per-key writers, native drum construction, shared transforms and all four Filter/Amp phase entries. Phase transitions are explicitly invoked, not naturally elapsed',
            'Each native offset result compares clip(shared-base + signed layer + signed key -64,0,99); shared-base is captured after original shared transform, not replaced in factory checks',
            'Each observed segment compares all48 native state bytes to independent Core.segment including duration and curve arithmetic',
            'Immediate writer effect compares full48 filter and100 amp EG bytes; pitch EG, normal continuous poll timing, hardware, audio and other editor callbacks are outside this result'])
    target=OUT/('drum-eg-times-smoke.json' if args.smoke else 'drum-eg-times-check.json')
    target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=result['counts'])))
if __name__=='__main__':main()
