#!/usr/bin/env python3
"""Original third-engine step sequencer: normalization, Accent and transport."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Firmware,FW_SHA
from firmware_arpeggio_sync import Rig
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def modulate(v,m,hi=127,lo=1):
    return v-((-m*(v-lo))>>6) if m<0 else v+(((m+1)*(hi-v))>>6) if m>0 else v
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('step-normalize',0x28C7E4,0x28C8D0),('step-start-stop',0x3D98,0x3DF8),
                       ('step-velocity',0x7238,0x72A0),('step-progress',0x6018,0x624C)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);a=r.a;e=r.engines[2];p=r.params[2];m=r.mods[2]
    normalized=[]
    for resolution in range(8):
        r.reset();r.b(p+2,resolution*4+3);r.b(p+3,255)
        r.call(0x28C87C,p)
        expected=struct.pack('<H',5)+bytes([resolution*4,3,80,129,0,127,0,127,1,0])
        assert r.read(p,12)==expected
        normalized.append(r.read(p,12).hex())
    # Two velocity stages: all steps first, then Accent on marked steps only.
    velocity_cases=0
    r.reset();r.bind(2,custom=True)
    for velocity,global_mod,accent,marked in itertools.product(range(1,128),[-64,-1,0,1,63],[-64,-1,0,1,63],[0,1]):
        r.b(m+2,global_mod);r.b(m+1,accent)
        expected=modulate(modulate(velocity,global_mod),accent if marked else 0)
        assert r.call(0x7238,e,velocity,marked)==expected
        velocity_cases+=1
    # Original progress notifier executes against an inactive recording context.
    # Only its external parameter query is captured; +44 increment remains original.
    queries=[]
    def query(x):queries.append([x.get('R1'),x.get('R2')]);return 0
    a.stubs[0x206C54]=query
    def setup(length=4,resolution=3,accent=32,global_mod=0):
        r.reset()
        a.write(0xC0F55730,0x11007300);r.b(0x11007304,1)
        a.write(0xC1439604,0x11007000);a.write(0x11007008,0x11007100);a.write(0x11007104,0)
        a.write(0xC143A300,0x11007200);a.write(0x11007238,0xC00EFEC0)
        r.call(0x27580C,r.pattern);r.b(r.pattern+25,length)
        a.uc.mem_write(r.pattern+28,bytes([36,38,42]+[60]*9))
        for step in range(64):
            mask=[1,2,4,7][step%4];vel=[64,80,96,112][step%4]
            a.uc.mem_write(r.pattern+40+step*8,struct.pack('<bBBbHBB',0,50,vel,0,mask,step%2,0))
        r.b(p+2,resolution*4);r.call(0x28C87C,p)
        r.b(m+1,accent);r.b(m+2,global_mod)
        r.call(0x5F0C,e,p,m,1,stack=(r.pattern,));r.call(0x5174,e)
        assert r.w(e+0x74)==p and r.w(e+0x78)==r.pattern
        r.call(0x3D98,r.owner,1)
        assert r.w(r.w(e+0x60)+128)==1
    traces=[]
    for length,resolution,accent,global_mod in itertools.product([1,4,16],[1,3,7],[-64,0,63],[-32,0,32]):
        setup(length,resolution,accent,global_mod)
        period=[40,60,80,120,160,240,320,480][resolution]
        # At each step boundary and its gate endpoint execute the original manager.
        for step in range(length*2):
            for tick in [max(1,step*period),step*period+period*80//100]:
                r.now=tick;a.write(e,tick);r.b(e+12,1);r.call(0x2A64,r.owner)
        r.call(0x3D98,r.owner,0);r.stop()
        ons=[x for x in r.events if x['on']]
        expected=[]
        for j in range(length*2):
            step=j%length;mask=[1,2,4,7][step%4];vel=[64,80,96,112][step%4]
            vel=modulate(modulate(vel,global_mod),accent if step%2 else 0)
            for tone,note in enumerate([36,38,42]):
                if mask&(1<<tone):expected.append((max(1,j*period),note,vel))
        got=[(x['tick'],x['note'],x['velocity']) for x in ons]
        assert got==expected,(length,resolution,accent,global_mod,got,expected)
        offs=[x for x in r.events if not x['on']]
        assert [(x['tick'],x['note']) for x in offs]==[((t//period)*period+period*80//100,n) for t,n,v in expected]
        assert r.w(r.w(e+0x68)+4)==0 and r.w(r.w(e+0x60)+128)==0
        traces.append(dict(length=length,resolution=resolution,accent=accent,velocity_mod=global_mod,events=r.events.copy()))
    # Per-tick run includes start, asynchronous stop, restart and complete release.
    setup();r.events=[]
    for t in range(961):
        r.now=t
        if t==187:r.call(0x3D98,r.owner,0)
        if t==301:r.call(0x3D98,r.owner,1)
        r.tick(t)
    r.call(0x3D98,r.owner,0);r.stop();transport=r.events.copy()
    assert not any(187<x['tick']<301 for x in transport)
    assert any(x['tick']==187 and not x['on'] for x in transport)
    assert any(x['tick']>=301 and x['on'] for x in transport)
    source=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all';raw=source.read_bytes()
    assert sha(source)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory=[];unique=set();factory_steps=0
    for index in range(768):
        base=0x1EF220+2140*index;block=raw[base+0x298:base+0x298+572];pattern=block[20:]
        assert len(pattern)==552 and pattern[24]==48 and 1<=pattern[25]<=64
        resolution=(block[10]>>2)&7;length=pattern[25]
        accent=struct.unpack('<b',block[5:6])[0];global_mod=struct.unpack('<b',block[6:7])[0]
        assert block[7]==0
        setup(length,resolution,accent,global_mod);a.uc.mem_write(r.pattern,pattern)
        period=[40,60,80,120,160,240,320,480][resolution];expected=[]
        for step in range(length):
            s=pattern[40+step*8:48+step*8];assert s[0]==s[3]==0
            mask=int.from_bytes(s[4:6],'little');vel=modulate(modulate(s[2],global_mod),accent if s[6] else 0)
            for tone in range(12):
                if mask&(1<<tone):expected.append((max(1,step*period),pattern[28+tone]&127,vel))
            for tick in [max(1,step*period),step*period+period*80//100]:
                r.now=tick;a.write(e,tick);r.b(e+12,1);r.call(0x2A64,r.owner)
        r.call(0x3D98,r.owner,0);r.stop()
        ons=[x for x in r.events if x['on']]
        assert [(x['tick'],x['note'],x['velocity']) for x in ons]==expected,index
        unique.add(pattern);factory_steps+=length
        factory.append(dict(program=chr(65+index//128)+f'{index%128:03}',name=raw[base:base+24].decode().rstrip(),
            offset=base+0x298,block_sha256=hashlib.sha256(block).hexdigest(),pattern_sha256=hashlib.sha256(pattern).hexdigest(),
            length=length,resolution=resolution,notes=[x&127 for x in pattern[28:40]],
            events=len(r.events),first_events=r.events[:8],events_sha256=hashlib.sha256(json.dumps(r.events,sort_keys=True).encode()).hexdigest()))
    assert queries and all(x==[0x2B,0xF5] for x in queries)
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={'firmware_arpeggio_sync.py':sha(ROOT/'research/tools/firmware_arpeggio_sync.py')},
        inputs=[dict(path=str(source.relative_to(ROOT)),sha256=sha(source))],
        normalized=normalized,velocity_cases=velocity_cases,traces=traces,transport=transport,progress_queries=len(queries),
        factory=dict(programs=factory,unique_patterns=len(unique),steps=factory_steps),
        boundaries=['Third engine uses original control normalization, fixed-note Pattern initialization, velocity/Accent arithmetic, step decode and output table',
                    'Start/stop wrapper 0x3D98 and per-tick manager execute; range cases inject event boundaries',
                    'Recording context remains inactive; parameter query 0x206C54 returns zero; original progress callback increments the step counter',
                    'Heap, critical sections and output assignment intercepted as in the fingerprinted Rig helper',
                    'Factory Program step-block slices execute directly; full bank loader, active recording and physical audio remain outside this check'])
    (OUT/'step-sequencer-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,normalization=len(normalized),velocity_cases=velocity_cases,playback_cases=len(traces),transport_events=len(transport),factory_programs=len(factory),factory_steps=factory_steps),indent=2))
if __name__=='__main__':main()
