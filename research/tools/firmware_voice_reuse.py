#!/usr/bin/env python3
"""Original ARM stereo stealing, mono/legato predicates and live voice retuning."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from voice_firmware import VoiceOracle
from voice_math import VoiceMath
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('stereo-voice-steal',0x1FC89C,0x1FC9D0),('mono-legato-predicates',0x272BBC,0x272D0C),
                       ('legato-voice-retune',0x1F7B68,0x1F7CC8),('portamento-state',0x1F8140,0x1F841C)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f)
    def word(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def half(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def put8(p,x):a.uc.mem_write(p,bytes([x&255]))
    def put16(p,x):a.uc.mem_write(p,struct.pack('<H',x&65535))
    def call(entry,*argv,**kw):return a.call(entry,*argv,**kw)&0xFFFFFFFF
    manager,primary,nodes,voices,osc=0x11000000,0x11001000,0x11002000,0x11004000,0x11008000
    head=osc+0x490;stops=[]
    def voice(i):return voices+588*i
    a.stubs={0x1F8BF8:lambda m:stops.append((m.get('R0')-voices)//588) or 0,0x12D350:lambda m:1}
    steal=[]
    for reverse,target in itertools.product([0,1],range(8)):
        a.uc.mem_write(manager,bytes(0xC0));a.uc.mem_write(voices,bytes(8*588))
        a.write(manager+0x30,primary,nodes,8,0);a.write(head,head,head,0)
        order=list(reversed(range(8))) if reverse else list(range(8))
        for i in range(8):
            for base in [primary,nodes]:a.write(base+12*i,0,0,voice(i))
            put8(voice(i)+0x16,i);put8(voice(i)+0x1A,order[i]);a.write(voice(i)+0x240,0xFFFFFFFF)
        call(0x1FBF4C,manager)
        for i in range(8):
            assert call(0x1FC9D0,manager)==voice(i)
            a.write(nodes+12*i,0,0,voice(i));call(0x1F61F8,osc,nodes+12*i)
        for i in range(0,8,2):
            left,right=sorted([i,i+1],key=lambda j:order[j])
            a.write(voice(left)+0x218,1);a.write(voice(right)+0x218,2)
            a.write(voice(left)+0x230,voice(right));a.write(voice(right)+0x230,voice(left))
            put8(voice(left)+0x18,order[right]);put8(voice(right)+0x18,255)
        for i in range(8):put16(voice(i)+0x10,0xC0);put16(voice(i)+0x23C,0 if i==target else 100+i)
        assert word(manager+0x3C)==0;stops.clear()
        assert call(0x1FC9D0,manager)==voice(target)
        partner=target^1;expected_stops=sorted([target,partner],key=lambda i:order[i])
        assert stops==expected_stops and word(manager+0x3C)==1
        for i in [target,partner]:
            assert half(voice(i)+0x10)==0 and word(voice(i)+0x218)==0 and word(voice(i)+0x230)==0
            assert a.uc.mem_read(voice(i)+0x18,1)[0]==255
            assert word(nodes+12*i)==0 and word(nodes+12*i+4)==0
        # The selected member is immediately reused; the partner becomes free.
        assert word(word(manager)+8)==voice(partner)
        a.write(nodes+12*target,0,0,voice(target));call(0x1F61F8,osc,nodes+12*target)
        assert call(0x1FC9D0,manager)==voice(partner) and word(manager+0x3C)==0
        steal.append(dict(target=target,partner=partner,reversed_TG_order=bool(reverse),reset_order=expected_stops,
            available_after_steal=1,next_acquired=partner))
    # Exhaust the two predicates with raw program/mode bits, retaining their
    # meaning separately from the UI labels until the descriptor map is checked.
    timbre,meta,patch=0x11010000,0x11011000,0x11012000;a.write(timbre+4,meta,patch)
    predicate_cases=0
    for mode,program_mono,legato,offset,override in itertools.product(range(8),[0,1],[0,1],[0,1],range(4)):
        put8(patch+0x508,mode|(program_mono<<7));put8(patch+0x509,(legato<<4)|(offset<<5));put8(meta+0x1C,override)
        mono=False if mode==3 else (bool(program_mono) if override==0 else override>1)
        reuse=False if mode==3 else (((program_mono and legato) if override==0 else override==3) and not offset)
        assert call(0x272CC0,timbre)==int(mono)
        assert call(0x272BBC,timbre)==int(reuse)
        predicate_cases+=1
    # Manager fast path: existing key-on voice + reuse predicate performs retune
    # and returns an empty new-voice chain. The alternate path selects layers.
    a.stubs={0x2DC184:lambda m:0,0x2DC1BC:lambda m:0}
    a.write(osc+0x49C,timbre);events=[];old=voices
    a.stubs[0x1F7B68]=lambda m:events.append(('retune',m.get('R0'),m.get('R2'),m.get('R3'))) or 1
    a.stubs[0x1FD718]=lambda m:events.append(('layers',)) or 0
    dispatch_cases=0
    for override,legato,offset,key_on,existing,note in itertools.product(range(4),[0,1],[0,1],[0,1],[0,1],[0,60,127]):
        put8(patch+0x508,0x80);put8(patch+0x509,(legato<<4)|(offset<<5));put8(meta+0x1C,override)
        put16(old+0x10,0x80 if key_on else 0);events.clear()
        assert call(0x1FDC8C,manager,0x640090+(note<<8),osc,old if existing else 0,stack=(0xFFFF,))==0
        reuse=((bool(legato) if override==0 else override==3) and not offset)
        expected=[('retune',old,note,0xFFFFFFFF)] if reuse and key_on and existing else [('layers',)]
        assert events==expected,(override,legato,offset,key_on,existing,note,events,expected)
        dispatch_cases+=1
    # Full retune body after original complete control initialization; sample,
    # envelopes and LFO state must survive a pitch/key-tracking change.
    oracle=VoiceOracle();a=oracle.arm;math=VoiceMath(f);v=oracle.voice;oscobj=0x11040000
    a.stubs[0x275564]=lambda m:0
    tg_starts=[];a.stubs[0x1F9028]=lambda m:tg_starts.append(m.get('R0')) or 0
    sample,region,clock=0x11050000,0x11051000,0x11052000
    raw_region=f.data[0x492C28:0x492C28+20];sample_index=struct.unpack_from('<H',raw_region)[0]
    a.uc.mem_write(sample,f.data[0x410ABC+sample_index*64:0x410ABC+(sample_index+1)*64]);a.uc.mem_write(region,raw_region)
    retune=[]
    for oscillator,note,transpose in itertools.product([0,1],[0,12,48,60,72,108,127],[-24,0,24]):
        oracle.initialize(60,85,oscillator);a.write(v+0x0C,oracle.controls)
        a.write(v+0x20,sample);a.write(v+0x22C,region);a.write(oracle.context+0x10,oracle.controls)
        a.write(0xC1B5720C,clock);a.write(clock,0,123)
        a.write(0xC165D9B4,60);a.write(0xC165D9B0,raw_region[4]<<8)
        a.write(0xC165D9AC,struct.unpack_from('<h',raw_region,6)[0]);a.write(0xC165D9A8,60<<8);a.write(0xC165D9A0,64)
        put8(0xC165D9A4,127);put8(0xC165D9A5,0);put8(0xC165D9B8,0)
        assert call(0x1F7278,v,oracle.runtime,0)==1
        put8(oracle.part+7,transpose);put8(oracle.context+0x2E,0)
        put16(v+0x10,0xC0);a.write(v+0x218,1);a.write(v+0x230,0x11060000)
        for _ in range(3):oracle.advance()
        before=bytes(a.uc.mem_read(v,588))
        tg_starts.clear()
        assert call(0x1F7B68,v,oscobj,note,0xFFFFFFFF)==1
        assert not tg_starts
        folded=note+transpose
        while folded<0:folded+=12
        while folded>127:folded-=12
        block=oracle.program[0x564+380*oscillator:0x564+380*(oscillator+1)]
        tracking=[math.keyboard_tracking(block[0xFC:0x103],folded),math.keyboard_tracking(block[0x13C:0x143],folded,True),
            math.keyboard_tracking(oracle.program[0x554:0x55B],folded),math.keyboard_tracking(oracle.program[0x55C:0x563],folded)]
        assert [oracle.s16(v+off) for off in [0x204,0x206,0x212,0x214]]==tracking
        assert oracle.byte(v+0x12)==note and oracle.byte(v+0x14)==85 and oracle.byte(v+0x13)&1
        for off,size in [(0x10,2),(0x14,1),(0x20,12),(0x2C,88),(0xBC,48),(0x120,48),(0x15C,100),(0x218,4),(0x230,4)]:
            assert bytes(a.uc.mem_read(v+off,size))==before[off:off+size],(hex(off),oscillator,note,transpose)
        retune.append(dict(oscillator=oscillator+1,note=note,transpose=transpose,tracking_note=folded,velocity_preserved=85,
            EG_state_preserved=True,LFO_state_preserved=True,sample_and_pair_preserved=True))
    # Portamento initial state and progression use the original coefficient
    # table. Controller override -1 selects the OSC value; nonnegative overrides
    # replace it. No duration in seconds is inferred from this arithmetic test.
    coefficients=list(struct.unpack_from('<128i',f.data,0x3FD380));portamento_cases=0;trajectory=[]
    for speed,scaled,previous,target,override in itertools.product(range(128),[0,1],[-1,0,60*256,120*256],
        [0,60*256,127*256],[-1,64]):
        put8(oracle.context+0x2E,override);put8(oracle.osc+0x80,scaled<<2);put8(oracle.osc+0x81,speed)
        k=coefficients[speed if override<0 else override]
        returned=call(0x1F82C0,v,previous,target,oracle.osc+0x68)
        if not k or previous==-1:position=step=limit=0;expected_return=target
        else:
            step=max(1,k*abs(target-previous)//3072) if scaled else k
            if target>=previous:position=(previous-target)*256;limit=0;expected_return=target
            else:position=0;limit=(target-previous)*256;step=-step;expected_return=previous
        signed=lambda off:struct.unpack('<i',a.uc.mem_read(v+off,4))[0]
        assert [signed(off) for off in [0x88,0x8C,0x90]]==[position,step,limit]
        assert returned==expected_return
        # The delayed-voice branch advances only the glide state. Verify initial
        # steps and a separately seeded final boundary for representative cases.
        if speed in [1,64,127] and previous==60*256 and target in [0,127*256] and override==-1:
            put16(v+0x10,0);put16(v+0x208,1);states=[]
            for _ in range(3):
                if step:
                    position+=step
                    if step>0 and position>0:position=step=0
                    elif step<0 and position<limit:position=limit;step=0
                call(0x1F8140,v)
                assert [signed(0x88),signed(0x8C)]==[position,step]
                states.append([position,step])
            if step:
                # Landing exactly on the limit retains the step for one visit.
                edge=0 if step>0 else limit;a.write(v+0x88,edge-step,step,limit)
                call(0x1F8140,v);assert [signed(0x88),signed(0x8C)]==[edge,step]
                call(0x1F8140,v);assert [signed(0x88),signed(0x8C)]==[edge,0]
            trajectory.append(dict(speed=speed,scaled=bool(scaled),previous=previous,target=target,first_three=states))
        portamento_cases+=1
    glide_series=[]
    for scaled,interval in itertools.product([0,1],[12,24]):
        put8(oracle.context+0x2E,255);put8(oracle.osc+0x80,scaled<<2);put8(oracle.osc+0x81,64)
        returned=call(0x1F82C0,v,60*256,(60+interval)*256,oracle.osc+0x68)
        put16(v+0x10,0);put16(v+0x208,1);series=[]
        for visit in range(256):
            position=struct.unpack('<i',a.uc.mem_read(v+0x88,4))[0]
            step=struct.unpack('<i',a.uc.mem_read(v+0x8C,4))[0]
            series.append(dict(visit=visit,pitch_q16=returned*256+position,step=step))
            if not step:break
            call(0x1F8140,v)
        assert not series[-1]['step'] and series[-1]['pitch_q16']==(60+interval)*65536
        glide_series.append(dict(scaled=bool(scaled),interval=interval,speed=64,series=series))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,stereo_steal_cases=steal,
        predicate_cases=predicate_cases,manager_dispatch_cases=dispatch_cases,retune_cases=retune,
        portamento_cases=portamento_cases,portamento_coefficients=coefficients,portamento_trajectories=trajectory,glide_series=glide_series,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        additional_helpers={n:hashlib.sha256((ROOT/'research/tools'/n).read_bytes()).hexdigest() for n in ['voice_firmware.py','voice_math.py']},
        inputs=[dict(path='research/output/kep-analysis/Concert_SE_Grand/program.bin',sha256=hashlib.sha256(oracle.program).hexdigest())],
        boundaries=['TG reset body and active status intercepted in steal cases',
            'manager dispatch intercepts retune and layer selector; retune body tested separately',
            'retune follows full original control initialization using Concert parameters and one independent real ROM region/sample',
            'Tone Adjust and external MIDI gates fixed; retune fixture disables portamento; standalone glide tested separately; no TG audio'])
    (OUT/'voice-reuse-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,stereo_steal_cases=len(steal),predicate_cases=predicate_cases,
        manager_dispatch_cases=dispatch_cases,retune_cases=len(retune),portamento_cases=portamento_cases),indent=2))
if __name__=='__main__':main()
