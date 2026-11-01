#!/usr/bin/env python3
"""Verify Concert filter control port against original ARM; export fixtures.

Never executes TG audio. Hz/Q interpretation belongs to a separate host model.
"""
from layout import PRODUCT_ROOT
import contextlib
import hashlib
import json
import struct
from program_firmware import ROOT, FW_SHA, BASE
from firmware_inspect import inspect
from filter_firmware import FilterOracle
from filter_math import FilterMath


def equal(arm, port, context):
    for key in port:
        assert arm[key]==port[key],(context,key,arm,port)


def record(state):
    return struct.pack('<8HhHI2h',*(state['A']+state['B']),state['eg_level'],state['eg_stage'],state['eg_duration'],*state['mixers'])


def main():
    oracle=FilterOracle();math=FilterMath(oracle.firmware,oracle.program)
    folder=ROOT/'research/derived/firmware/KROSS2_V124/voice';folder.mkdir(exist_ok=True)
    grid=bytearray(b'K2FILT01'+struct.pack('<4I',2,128,127,28));selected=[]
    for osc in range(2):
        for note in range(128):
            for velocity in range(1,128):
                a=oracle.initialize_filter(note,velocity,osc);b=math.start(note,velocity,osc)
                equal(a,b,(osc,note,velocity));grid.extend(record(a))
                if note in (24,60,84,108) and velocity in (1,40,85,86,100,106,107,127):
                    selected.append(dict(oscillator=osc,note=note,velocity=velocity,**a))
            if note%32==0:print('Filter sweep',osc,note,flush=True)
    trajectory=bytearray(b'K2FLTRC1');traces=[];trace_count=0;checked_steps=0
    for osc in range(2):
        for note,velocity in ((36,40),(60,100),(96,127)):
            oracle.initialize_filter(note,velocity,osc);math.start(note,velocity,osc)
            previous=None;selected_trace=[]
            for tick in range(2200):
                if tick==500:
                    equal(oracle.release_filter(),math.release(),('release',osc,note,velocity))
                a=oracle.advance_filter();b=math.advance();equal(a,b,('trace',osc,note,velocity,tick));checked_steps+=1
                if tick%8==0 or a['eg_stage']!=previous or tick in (499,500):
                    trajectory.extend(struct.pack('<6I',osc,note,velocity,tick,500,0)+record(a));trace_count+=1
                    selected_trace.append(dict(tick=tick,**a))
                previous=a['eg_stage']
                if tick>505 and a['eg_stage']==6:break
            assert a['eg_stage']==6
            traces.append(dict(oscillator=osc,note=note,velocity=velocity,note_off_tick=500,states=selected_trace))
    trajectory[8:8]=struct.pack('<I',trace_count)

    # Mutate only synthetic Program RAM, verify every raw frequency/resonance
    # index independently of factory values and clarify the previous mislabels.
    mutations=0
    for offset in (0xA3,0xA4,0xC7,0xC8):
        for value in range(100):
            oracle.initialize_filter(60,100,0);math.start(60,100,0)
            oracle.arm.uc.mem_write(oracle.osc+offset,bytes([value]))
            changed=bytearray(math.osc);changed[offset]=value;math.osc=bytes(changed)
            oracle.arm.call(0x1FB4B0,oracle.voice+0xEC,oracle.voice,0,0)
            equal(oracle.filter_snapshot(),math.snapshot(),('raw_parameter',offset,value));mutations+=1
    injected=0
    for mixer in (-24576,-4096,-1,0,1,4096,24576):
        oracle.initialize_filter(60,100,0);math.start(60,100,0)
        oracle.arm.uc.mem_write(oracle.voice+0x1FE,struct.pack('<h',mixer));math.sources[2]=mixer
        oracle.arm.call(0x1FB4B0,oracle.voice+0xEC,oracle.voice,0,0)
        equal(oracle.filter_snapshot(),math.snapshot(),('Mixer2 boundary injection',mixer));injected+=1

    # Execute the real filter update packer; replace only MMIO bus endpoints.
    arm=oracle.arm;writes=[];bus=0x60000000;old=0x11080000;new=old+0x20
    arm.stubs={0x1326B4:lambda _:0,0x132690:lambda a:writes.append([a.get('R0')-bus,a.get('R1')]) or 0}
    commands=[]
    for branch in (0,1):
        for units in (0,1,5,24,100):
            before=[32767,14172,208,32767];after=[32767,27557,520,4864]
            arm.uc.mem_write(old,struct.pack('<4H',*before));arm.uc.mem_write(new,struct.pack('<4H',*after));writes.clear()
            arm.call(0x12D088,bus,branch,old,new,stack=(units,))
            coefficient=65535 if units==0 else 65535//(32*min(units,24))
            steps=[]
            for x,y in zip(before,after):
                value=(coefficient*(y-x))>>16;steps.append(value+(1 if value>=0 else -1))
            base=0x388+branch*0x20
            expected=[[base+4,(steps[1]<<8)&0xffffffff],[base,after[1]<<8],
                      [base+12,(steps[2]<<8)&0xffffffff],[base+8,after[2]<<8],
                      [base+20,((steps[0]&65535)<<16)|after[0]],
                      [base+24,((steps[3]&65535)<<16)|after[3]]]
            assert writes==expected,(branch,units,writes,expected)
            commands.append(dict(branch=branch,units=units,before=before,after=after,writes=list(writes)))

    grid_path=folder/'concert-filter-map.bin';grid_path.write_bytes(grid)
    trace_path=folder/'concert-filter-traces.bin';trace_path.write_bytes(trajectory)
    result={'firmware_sha256':FW_SHA,'program_sha256':hashlib.sha256(oracle.program).hexdigest(),
            'tool_sha256':{name:hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in
              ('program_firmware.py','voice_firmware.py','voice_math.py','filter_firmware.py','filter_math.py','probe_concert_filter.py')},
            'context_count':32512,'trace_steps_compared':checked_steps,'trace_fixture_records':trace_count,
            'raw_parameter_mutations':mutations,'Mixer2_injected_boundaries':injected,'TG_filter_commands':commands,
            'map':{'path':str(grid_path.relative_to(PRODUCT_ROOT)),'sha256':hashlib.sha256(grid).hexdigest(),
                   'header':'K2FILT01 + u32(2,128,127,28); order oscillator,note,velocity',
                   'record':'LE 8HhHI2h: A(trim,cutoff,resonance,output),B(...),EGlevel,EGstage,EGduration,Mixer1,Mixer2'},
            'traces':{'path':str(trace_path.relative_to(PRODUCT_ROOT)),'sha256':hashlib.sha256(trajectory).hexdigest(),
                      'header':'K2FLTRC1 + u32 count; each record 6I(osc,note,velocity,tick,offtick,reserved)+map record'},
            'selected_contexts':selected,'selected_traces':traces,
            'corrected_factory_fields':{'A':{'trim':99,'output':99,'frequency':9,'resonance':0},
                                        'B':{'trim':99,'output':0,'frequency':30,'resonance':9}},
            'scope':['Original Filter EG, cutoff/resonance/output controls and factory velocity/keytracking/Mixer AMS execute in ARM',
                     'External Tone Adjust0, MIDI override disabled, mute open, no physical instrument or TG audio execution',
                     'External KnobMod1, mod wheel, ribbon, LFO/audio contributions and sample offsets zero',
                     '400 raw-field mutations use synthetic Program RAM; 7 Mixer2 tests explicitly inject source boundary',
                     'Cutoff/resonance words are not Hz/Q; TG internal transfer law remains unresolved',
                     'TG command tests stub only read/write bus; they do not prove silicon filter audio behavior']}
    (folder/'concert-filters.json').write_text(json.dumps(result,indent=2)+'\n')
    verification={k:v for k,v in result.items() if k not in ('selected_contexts','selected_traces')}
    (ROOT/'research/derived/verification/concert-filter-arm-comparison.json').write_text(json.dumps(verification,indent=2)+'\n')
    with (folder/'filter-control.arm.txt').open('w') as out,contextlib.redirect_stdout(out):
        for start,end in ((0x1FB250,0x1FBD98),(0x12CEE4,0x12D22C)):
            inspect(oracle.firmware.data,start,end)
    print('PASS',32512,'filter contexts,',checked_steps,'trace steps,',mutations,'raw parameters,',injected,'injections and',len(commands),'TG commands')


if __name__=='__main__':main()
