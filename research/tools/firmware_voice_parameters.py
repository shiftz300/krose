#!/usr/bin/env python3
"""Recover PCM voice parameter assembly with original ARM and synthetic banks."""
import argparse
import contextlib
import hashlib
import io
import json
import struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('voice-parameter-builder',0x1F68D4,0x1F7278),('multisample-region-lookup',0x1F5B24,0x1F5BAC),
                      ('voice-TG-refresh',0x1F9828,0x1F9A5C),('voice-score-read',0x12E6E0,0x12E730),
                      ('voice-start-initial-score',0x1F9028,0x1F90B0)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f)
    def word(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def put8(p,v):a.uc.mem_write(p,bytes([v&255]))
    def put16(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def call(entry,*argv,**kw):return a.call(entry,*argv,**kw)&0xFFFFFFFF
    osc,params,timbre,meta,prog,runtime,selection,temp,dest=(0x11000000,0x11001000,0x11002000,
        0x11003000,0x11004000,0x11006000,0x11007000,0x11008000,0x11009000)
    system,banks,samples,regions,header=0x11030000,0x11032000,0x11035000,0x11036000,0x11037000
    a.write(osc+8,params);a.write(osc+0x49C,timbre)
    a.write(timbre+4,meta,prog,prog+0x520,runtime)
    a.write(0xC1743270,system);a.write(system+0x28,banks)
    a.write(banks+0x14,1,1);a.write(banks+0x24,samples,regions)
    a.write(osc+12,header);put16(header,0);put8(header+3,4)
    a.uc.mem_write(osc+24,bytes(128));put8(osc+12+0x8C,0)
    put16(regions,0);put8(regions+2,0);put8(regions+4,-2);put16(regions+6,-17);put8(regions+8,5)
    a.stubs={0x2737C8:lambda m:0,0x2753DC:lambda m:0xFFFFFFFF,
             0x275688:lambda m:0,0x272CC0:lambda m:0,
             0x1F82C0:lambda m:60<<8,0x1E2974:lambda m:0,
             0x285758:lambda m:1}
    cases=0;examples=[]
    for flags in range(4):
        for level in [0,1,64,127]:
            for gain in [0,1,16384,32768]:
                for reverse in [0,1]:
                    for start in [0,3,4,5,15]:
                        a.uc.mem_write(temp,bytes(588));a.uc.mem_write(dest,b'\xa5'*588)
                        a.uc.mem_write(params,bytes(380));put8(params,flags);put8(params+4,level)
                        put8(params+5,start|(reverse<<7))
                        put16(selection,60);put16(selection+2,60<<8);put16(selection+4,gain)
                        a.write(selection+8,params,osc+12,0,0)
                        call(0x1F68D4,temp)
                        result=call(0x1F6958,temp,osc,60,100,stack=(0,0xFFFFFFFF,selection,0,0))
                        if flags==0:
                            assert result==0xFFFFFFFF
                        else:
                            assert result==1
                            assert word(temp+0x20)==samples and word(temp+0x22C)==regions
                            assert word(temp+0x21C)==prog and word(temp+0x224)==params
                            assert a.uc.mem_read(temp+0x20C,1)[0]==reverse
                            assert a.uc.mem_read(temp+0x20A,1)[0]==(start if start<=4 else 0)
                            assert a.uc.mem_read(0xC165D9A4,1)[0]==(level*gain)>>15
                            assert word(0xC165D9B0)==0xFFFFFE00 and word(0xC165D9AC)==0xFFFFFFEF
                            call(0x1F716C,dest,temp)
                            for off,size in [(4,12),(0x12,1),(0x14,1),(0x20,12),(0x84,53),
                                             (0x20A,5),(0x21C,20),(0x238,4),(0x244,8)]:
                                assert bytes(a.uc.mem_read(dest+off,size))==bytes(a.uc.mem_read(temp+off,size)),hex(off)
                            # Hardware identity/list fields survive the parameter copy.
                            for off,size in [(0,4),(0x16,8),(0x218,4),(0x230,8),(0x240,4)]:
                                assert bytes(a.uc.mem_read(dest+off,size))==b'\xa5'*size,hex(off)
                        cases+=1
                        if flags==1 and level==127 and start==5:
                            examples.append(dict(weight=gain,reverse=reverse,result=hex(result),level_after_crossfade=(level*gain)>>15))
    # Region remap -1 and missing sample count are separate early failure conditions.
    failures=[]
    put8(params,1)
    for no_region,no_sample in [(1,0),(0,1)]:
        put8(osc+24+60,255 if no_region else 0);a.write(banks+0x14,0 if no_sample else 1)
        result=call(0x1F6958,temp,osc,60,100,stack=(0,0xFFFFFFFF,selection,0,0))
        assert result==0xFFFFFFFF
        failures.append(dict(region_map_missing=bool(no_region),sample_missing=bool(no_sample),result=-1))
    # Follow the allocator's +0x23c score back to TG readback, keeping physical
    # register values in synthetic RAM. Unrelated control writes are intercepted.
    tg=0x11040000;score_cases=0
    a.uc.mem_write(temp,bytes(588));a.write(temp+0x1C,tg);a.write(temp+0x224,params)
    put8(0xC104728C,1)
    a.stubs={k:lambda m:0 for k in [0x12C6B8,0x12CC44,0x12D288,0x12CE64,0x12CEE4,
        0x12D22C,0x12CC78,0x12DE0C,0x12C894,0x12DE5C]}
    for value in [0,1,4,32767,65535,0xDEADBEEF]:
        put16(tg+0x428,value>>16);put16(tg+0x42A,value)
        for slot in range(128):
            assert call(0x12E6E0,tg,slot)==(value if slot<120 else 0)
        for active in [0,1]:
            a.uc.mem_write(tg+0x240,(b'\xff' if active else b'\x00')*32)
            for slot in range(120):
                put8(temp+0x1A,slot);put16(temp+0x23C,0xA55A)
                call(0x1F9828,temp)
                actual=int.from_bytes(a.uc.mem_read(temp+0x23C,2),'little')
                assert actual==(value&65535 if active else 0xA55A)
                score_cases+=1
    score=dict(refresh_cases=score_cases,readback_cases=6*128,
        refresh_entry='0x1f9828',readback_entry='0x12e6e0',
        source='select TG slot via register +0x400; read +0x428 twice; keep second read low16',
        inactive='leave cached score unchanged when TG status bit is zero',
        slot_limit='readback helper returns0 for slots >=120',
        initial_score='0x7fff, from static instructions at 0x1f9064..0x1f9070',
        interpretation='hardware readback cache; physical quantity still unresolved',
        boundaries='TG bus-mode helper and unrelated control writes intercepted; synthetic memory reads/writes only')
    result=dict(passed=True,firmware_sha256=FW_SHA,tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),device_access=False,
        cases=cases,examples=examples,failure_cases=failures,allocation_score=score,
        conclusions={'melodic_descriptor_admission':'descriptor byte0 &3 must be nonzero',
          'level_after_crossfade':'uint8((descriptor_level * selected_gain_q15) >>15)',
          'region_mapping':'128 signed byte key entries; -1 rejects; 20-byte region records',
          'sample_metadata':'synthetic ordinary bank uses 64-byte entries; alternate branch uses 100-byte entries',
          'start_offset':'low nibble of descriptor +5; reset0 if above region header limit',
          'reverse':'descriptor +5 bit7, subject to Tone Adjust and reverse capability checks',
          'parameter_copy':'0x1f716c copies parameter subsets while preserving TG/list identity'},
        intercepted=['Tone Adjust offset unset','MIDI override gate disabled','fixed pitch result 60<<8',
          'bank-id mapping returns0','reverse capability succeeds','mono/hold predicates disabled'],
        scope='Original melodic parameter builder, region lookup and parameter copy; synthetic ordinary bank; no TG start or audio')
    (OUT/'voice-parameters-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=cases,failure_cases=len(failures),score_refresh_cases=score_cases),indent=2))
if __name__=='__main__':main()
