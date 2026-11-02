#!/usr/bin/env python3
"""Characterize PCM manager rollback under explicitly injected builder failures."""
import argparse
import hashlib
import itertools
import json
import struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    a=Arm(Firmware());OUT.mkdir(parents=True,exist_ok=True)
    def word(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def half(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def put8(p,x):a.uc.mem_write(p,bytes([x&255]))
    def put16(p,x):a.uc.mem_write(p,struct.pack('<H',x&65535))
    def call(entry,*argv,**kw):return a.call(entry,*argv,**kw)&0xFFFFFFFF
    osc,params,timbre,meta,prog,runtime=0x11000000,0x11001000,0x11002000,0x11003000,0x11004000,0x11006000
    vm,primary,secondary,voices,delaynodes=0x11020000,0x11021000,0x11022000,0x11024000,0x11026000
    assignment=vm+12;delayhead=vm+0xCC
    a.write(osc+8,params);a.write(osc+0x49C,timbre);a.write(timbre+4,meta,prog);a.write(timbre+0x10,runtime)
    put8(params+0x2E,127);put8(prog+0x519,127);put8(prog+0x51B,127)
    for i,bottom in enumerate([100,70,30]):a.uc.mem_write(params+0x20+4*i,bytes([bottom,12,0,0]))
    def voice(i):return voices+588*i
    def reset(order):
        a.uc.mem_write(vm,bytes(0x100));a.uc.mem_write(voices,bytes(8*588))
        a.write(assignment+0x30,primary,secondary,8,0);a.write(delayhead,delayhead,delayhead,0,delaynodes,8)
        for i in range(8):
            for base in [primary,secondary,delaynodes]:a.write(base+12*i,0,0,voice(i))
            put8(voice(i)+0x16,i);put8(voice(i)+0x1A,order[i]);a.write(voice(i)+0x240,0xFFFFFFFF)
        call(0x1FBF4C,assignment)
    a.stubs={k:lambda m:0 for k in [0x275508,0x275564,0x2753DC,0x2DC184,0x2DC1BC,0x272BBC,0x1F68D4,0x272488,0x1F8BF8]}
    a.stubs[0x1FF958]=lambda m:0x4567
    attempts=[];starts=[];current=[0,0];successful=[]
    def prepare(m):
        sp=m.get('SP');layer=word(sp+12);side=word(sp+16);current[:]=[layer,side]
        outcome=outcomes[layer];fail=outcome==('params_first' if side==0 else 'params_second')
        attempts.append(dict(layer=layer,side=side,parameter_result=-1 if fail else 0));return -1 if fail else 0
    def copy(m):put16(m.get('R0')+0x208,delay);return 0
    def start(m):
        layer,side=current;outcome=outcomes[layer];fail=outcome==('start_first' if side==0 else 'start_second')
        index=(m.get('R0')-voices)//588;starts.append(dict(layer=layer,side=side,slot=index,success=not fail))
        if not fail:successful.append(index);put16(m.get('R0')+0x10,0xC0)
        return int(not fail)
    a.stubs.update({0x1F6958:prepare,0x1F716C:copy,0x1F7278:start})
    rows=[];partial_examples=[]
    for stereo in itertools.product([0,1],repeat=2):
        put8(params+9,stereo[0]);put8(params+17,stereo[1])
        options=[['ok','params_first','start_first']+(['params_second','start_second'] if s else []) for s in stereo]
        for outcomes,reverse,delay in itertools.product(itertools.product(*options),[0,1],[0,3]):
            order=list(reversed(range(8))) if reverse else list(range(8));reset(order)
            attempts.clear();starts.clear();successful.clear()
            result=call(0x1FDC8C,vm,0x014C3C90,osc,0,stack=(0xFFFFFFFF,))
            expected=sum(0 if o.endswith('first') else (1 if o.endswith('second') else 1+s) for o,s in zip(outcomes,stereo))
            assert len(successful)==expected and word(assignment+0x3C)==8-expected
            chain=[];ptr=result
            while ptr:
                assert len(chain)<8;chain.append((word(ptr+8)-voices)//588);ptr=word(ptr)
            assert chain==successful[:1]+list(reversed(successful[1:]))
            free=[];ptr=word(assignment)
            while ptr!=assignment:
                assert len(free)<8;free.append((word(ptr+8)-voices)//588);ptr=word(ptr)
            assert len(free)==8-expected and set(free).isdisjoint(successful)
            assert set(free)|set(successful)==set(range(8))
            assert a.uc.mem_read(vm+0xE0,1)[0]==0
            pairs=[]
            for i in successful:
                partner=word(voice(i)+0x230)
                if partner:
                    j=(partner-voices)//588
                    pairs.append(dict(slot=i,pair_type=word(voice(i)+0x218),partner=j,
                        partner_returned=j in successful,reciprocal=word(voice(j)+0x230)==voice(i)))
            row=dict(stereo=list(stereo),outcomes=list(outcomes),reversed_TG_slots=bool(reverse),delay=delay,
                successes=list(successful),returned_chain=chain,available=8-expected,free_slots=free,pairs=pairs,
                parameter_attempts=list(attempts),start_attempts=list(starts))
            rows.append(row)
            if stereo==(1,1) and outcomes in [('params_second','params_first'),('params_second','ok')] and not reverse and not delay:
                partial_examples.append(row)
    # Now replace the injected parameter failure with the actual builder: a
    # synthetic right-side key map contains -1. Factory reachability is separate.
    system,banks,samples,regions,headers=0x11030000,0x11032000,0x11035000,0x11036000,0x11037000
    a.write(timbre+4,meta,prog,prog+0x520,runtime)
    a.write(0xC1743270,system);a.write(system+0x28,banks)
    a.write(banks+0x14,1,4);a.write(banks+0x24,samples,regions)
    for entry in [0x1F6958,0x1F716C,0x1F68D4,0x272488]:a.stubs.pop(entry)
    a.stubs.update({0x2737C8:lambda m:0,0x2753DC:lambda m:0xFFFFFFFF,0x275688:lambda m:0,
        0x272CC0:lambda m:0,0x1F82C0:lambda m:60<<8,0x1E2974:lambda m:0,0x285758:lambda m:1})
    real_success=[]
    a.stubs[0x1F7278]=lambda m:real_success.append((m.get('R0')-voices)//588) or 1
    real_cases=[]
    for second_layer_missing in [0,1]:
        reset(list(range(8)));real_success.clear()
        for layer in range(2):
            slot=layer+1;put8(params+slot*8,1);put8(params+slot*8+1,1);put8(params+slot*8+4,127)
            for side in range(2):
                i=2*layer+side;mapping=osc+12+slot*288+side*144
                a.uc.mem_write(mapping,bytes(144));a.write(mapping,headers+16*i)
                put16(headers+16*i,i);put8(headers+16*i+3,4)
                put16(regions+20*i,0)
                if (layer==0 and side==1) or (layer==1 and second_layer_missing):put8(mapping+12+60,255)
        returned=call(0x1FDC8C,vm,0x014C3C90,osc,0,stack=(0xFFFFFFFF,))
        assert real_success==([0] if second_layer_missing else [0,1,2])
        assert word(assignment+0x3C)==8-len(real_success)
        assert word(voice(0)+0x218)==1 and word(voice(0)+0x230)==voice(1)
        real_cases.append(dict(second_layer_missing=bool(second_layer_missing),successes=list(real_success),
            available=word(assignment+0x3C),first_primary_partner=1,
            partner_returned=1 in real_success,reciprocal=word(voice(1)+0x230)==voice(0),
            first_returned_voice=(word(returned+8)-voices)//588))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,cases=len(rows),rows=rows,
        original_builder_missing_region_cases=real_cases,
        partial_stereo_examples=partial_examples,
        conclusions=['first-side failure skips the second side in that layer',
            'successful voices consume reserved slots; unused tail slots return in reverse order',
            'all cases recover 8 minus successful voices as available and clear the manager busy flag',
            'injected second-side failure can leave a primary pair reference to a returned or repurposed slot'],
        limits=['parameter builder and control initializer failures are injected at function boundaries',
            'two follow-up cases use the original parameter builder with a synthetic missing right-side key map',
            'second-side-only failure reachability in factory ROM or expansion material is not established',
            'do not interpret the synthetic pair-reference outcome as a confirmed device defect',
            'allocator reset, exception-frame helpers and parameter controller getters intercepted'],
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest())
    (OUT/'voice-failures-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(rows),original_builder_missing_region_cases=real_cases),indent=2))
if __name__=='__main__':main()
