#!/usr/bin/env python3
"""Original complete PCM control initialization, stopping at TG start boundary."""
import argparse
import contextlib
import hashlib
import io
import json
import struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_inspect import inspect
from voice_math import VoiceMath
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    s=io.StringIO()
    with contextlib.redirect_stdout(s):inspect(f.data,0x1F7278,0x1F7808)
    (OUT/'voice-control-initialization.arm.txt').write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f);math=VoiceMath(f)
    program_path=ROOT/'research/output/kep-analysis/Concert_SE_Grand/program.bin'
    data=program_path.read_bytes();assert hashlib.sha256(data).hexdigest()=='a52ae2deebe0a0997bb50d50b3b26c1e40bd278567068e6afc85ae20e09222e4'
    catalog=ROOT/'research/derived/firmware/KROSS2_V124/rom/catalog'
    sample_path=catalog/'sample-descriptors.json';region_path=catalog/'key-regions.json'
    samples=json.loads(sample_path.read_text());regions=json.loads(region_path.read_text())
    # A real region/descriptor exercises pitch arithmetic; it is not claimed to
    # be the Concert program's selected multisample for every synthetic note.
    region_record=regions[0];sample_record=samples[region_record['sample_index_raw']]
    region_raw=bytes.fromhex(region_record['raw_hex']);sample_raw=bytes.fromhex(sample_record['raw_hex'])
    voice,context,part,params,patch,runtime,controls,mode,settings=[0x11010000+i*0x2000 for i in range(9)]
    sample,region,clock,secondary=0x11040000,0x11041000,0x11042000,0x11043000
    def word(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def half(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def signedhalf(p):return struct.unpack('<h',a.uc.mem_read(p,2))[0]
    def put8(p,v):a.uc.mem_write(p,bytes([v&255]))
    def put16(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def call(entry,*argv,**kw):return a.call(entry,*argv,**kw)&0xFFFFFFFF
    starts=[]
    a.stubs={0x2753DC:lambda m:0,0x2737C8:lambda m:0,0x2DF2C:lambda m:1,
        0x1F9028:lambda m:starts.append((m.get('R0'),m.get('R1'))) or 0}
    a.uc.mem_write(patch,data);a.uc.mem_write(sample,sample_raw);a.uc.mem_write(region,region_raw)
    a.write(context+4,part);a.write(context+0x10,controls);a.write(context+0x8C,controls)
    put8(part+5,127);put16(context+0x30,65535);put16(context+0x32,65535)
    a.write(0xC199BD3C,mode);a.write(mode,4);a.write(0xC1743270,settings);a.write(0xC0F5389C,settings)
    a.write(0xC1B5720C,clock);a.write(clock,0,123)
    a.write(0xC165D9B0,region_record['root_key_candidate']<<8)
    a.write(0xC165D9AC,struct.unpack_from('<h',region_raw,6)[0]);a.write(0xC165D9A0,64)
    put8(0xC165D9A5,0);put8(0xC165D9B8,0)
    def initialize(note,velocity,level,pair=0):
        a.uc.mem_write(voice,bytes(588));a.write(voice+4,runtime,context,controls)
        a.write(voice+0x20,sample);a.write(voice+0x21C,patch,patch+0x520,params)
        a.write(voice+0x22C,region);a.write(voice+0x218,pair);a.write(voice+0x240,0xFFFFFFFF)
        put8(voice+0x12,note);put8(voice+0x14,velocity)
        a.write(0xC165D9B4,note);a.write(0xC165D9A8,note<<8);put8(0xC165D9A4,level)
        starts.clear();return call(0x1F7278,voice,runtime,0)
    cases=0;examples=[]
    for oscillator in range(2):
        block=data[0x564+380*oscillator:0x564+380*(oscillator+1)]
        a.uc.mem_write(params,block)
        for note in range(128):
            for velocity in range(128):
                level=119 if velocity<107 else 127
                assert initialize(note,velocity,level)==1
                assert half(voice+0x10)==0xC0 and starts==[(voice,sample)]
                expected_multisample=math.multisample_gain(level)
                assert half(voice+0x200)==expected_multisample
                expected_factor=(math.velocity_gain(velocity,70)*expected_multisample)>>16
                assert half(voice+0x156)==expected_factor,(oscillator,note,velocity,half(voice+0x156),expected_factor)
                tracking=[math.keyboard_tracking(block[0xFC:0x103],note),math.keyboard_tracking(block[0x13C:0x143],note,True),
                    math.keyboard_tracking(data[0x554:0x55B],note),math.keyboard_tracking(data[0x55C:0x563],note)]
                assert [signedhalf(voice+o) for o in [0x204,0x206,0x212,0x214]]==tracking
                # Full path initializes both LFO owner pointers and both AMS mixers.
                assert word(voice+0x4C)==voice and word(voice+0x78)==voice
                if note in [24,60,96] and velocity in [0,85,86,106,107,127]:
                    examples.append(dict(oscillator=oscillator+1,note=note,processed_velocity=velocity,
                        amp_velocity_factor=half(voice+0x156),amp_gain=half(voice+0x150),
                        amp_EG_level=signedhalf(voice+0x15C),amp_EG_stage=a.uc.mem_read(voice+0x162,1)[0],
                        LFOs=[signedhalf(voice+0x2C),signedhalf(voice+0x58)],
                        AMS_mixers=[signedhalf(voice+0x1F6),signedhalf(voice+0x1FE)]))
                cases+=1
        print('Initialized oscillator',oscillator+1,flush=True)
    # Delay fields suppress immediate hardware start; stereo second side copies
    # the primary's time-varying states and repairs its two LFO owner pointers.
    delay_table=struct.unpack_from('<98h',f.data,0x406226)
    delay_cases=[]
    for osc_delay,part_delay in [(0,0),(1,0),(0,1),(12,20),(97,0),(0,97)]:
        put8(params+0x2C,osc_delay);put8(part+0x0A,part_delay);put8(part+0x0C,0)
        assert initialize(60,100,119,1)==1
        expected=-1 if -1 in [delay_table[osc_delay],delay_table[part_delay]] else delay_table[osc_delay]+delay_table[part_delay]
        assert signedhalf(voice+0x208)==expected and word(voice+0x234)==0
        assert starts==([(voice,sample)] if expected==0 else [])
        primary_bytes=bytes(a.uc.mem_read(voice,588))
        a.uc.mem_write(secondary,primary_bytes);a.write(secondary+0x218,2)
        starts.clear();assert call(0x1F7278,secondary,runtime,voice)==1
        assert starts==([(secondary,sample)] if expected==0 else [])
        for off,size in [(0xBC,48),(0x120,48),(0x15C,100),(0x84,53),(0xEC,51),(0x150,10),
                         (0x1CC,12),(0x1D8,24),(0x1F0,16),(0x204,6),(0x20F,6),(0x234,4)]:
            assert bytes(a.uc.mem_read(secondary+off,size))==bytes(a.uc.mem_read(voice+off,size)),hex(off)
        assert word(secondary+0x4C)==secondary and word(secondary+0x78)==secondary
        delay_cases.append(dict(OSC_delay_index=osc_delay,timbre_delay_index=part_delay,delay_visits=expected,
            secondary_copies_control_state=True))
    result=dict(passed=True,firmware_sha256=FW_SHA,cases=cases,examples=examples,delay_and_stereo_cases=delay_cases,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        math_sha256=hashlib.sha256((ROOT/'research/tools/voice_math.py').read_bytes()).hexdigest(),
        inputs=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [program_path,sample_path,region_path]],
        region_fixture=region_record['index'],sample_fixture=sample_record['index'],device_access=False,
        original_control_blocks=['output routing','keyboard tracking','both LFO initializers','AMS mixer initialization',
            'pitch/filter/amplitude EG','pitch','filter','multisample gain','pan/output','amp control','delay setup','stereo state copy'],
        intercepted=['Tone Adjust getter zero','external MIDI override disabled','mute gate open','TG start 0x1f9028'],
        limits=['Concert parameter fixture with one independently selected real region/sample, not exact full Concert selection',
            'Processed velocity is supplied directly; earlier velocity normalization is outside this entry',
            'TG write/start body and audio not executed','tempo-synchronized timbre delay branch not covered'])
    (OUT/'voice-start-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=cases,delay_and_stereo_cases=len(delay_cases)),indent=2))
if __name__=='__main__':main()
