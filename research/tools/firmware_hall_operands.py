#!/usr/bin/env python3
"""Hall-only visible operand relocation and address-reference constraints."""
import argparse,contextlib,hashlib,io,json,struct
from pathlib import Path
from program_firmware import Firmware,BASE,FW_SHA
from firmware_hall import HallRig
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
MASK48=(1<<48)-1
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def visible(data):return [(lo&65535)<<32|hi for lo,hi in struct.iter_unpack('<II',data)]
def storage(words):return b''.join(struct.pack('<II',v>>32,v&0xFFFFFFFF) for v in words)
def decode(v):
    hi=v&0xFFFFFFFF;low=v>>32
    return dict(a=(hi>>19)&1023,b=(hi>>9)&1023,c=hi&511,upper=hi>>29,low=low,format=low&0x7000,flag2=bool(low&4))
def relocated(v,slot):
    if slot<=0:return v
    hi=v&0xFFFFFFFF;low=v>>32;kind=low&0x7000;flag=bool(low&4)
    def add(value,shift,mask):
        nonlocal hi
        hi=(hi&~mask)|((hi+(value<<shift))&mask)
    if (kind<0x5000 or flag) and ((hi>>19)&1023)<640:add(80*slot,19,0x1FF80000)
    if (kind!=0x5000 or flag) and ((hi>>9)&1023)<640:add(80*slot,9,0x7FE00)
    if kind>=0x6000 and not flag:add(124*slot,19,0x1FF80000)
    control=hi&0x1F0
    if control in [0x20,0x60] and not hi&0x10:add(2*slot,0,15)
    if hi&0x100 and not hi&0x10:add(2*slot,0,15)
    return (low<<32)|hi

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware();r=HallRig(f);a=r.a;a.stubs.clear();e=r.definition
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream):inspect(f.data,0x9B510,0x9B960)
    (OUT/'hall-local-operands.arm.txt').write_text(stream.getvalue())
    raw=f.data[e['code_offset']:e['code_offset']+8*e['code_words_64']];words=visible(raw);assert len(words)==121
    initial=r.initial;references=[]
    for pc,v in enumerate(words):
        x=decode(v);references.append(dict(pc=pc,visible48=f'{v:012x}',**x,a_initial=initial[x['a']] if x['a']<len(initial) else None))
    if not args.verify_arm:return
    def buffer(slot):return 0xC0FEB1C8+8*(32+124*slot)
    def run(items,slot):
        padded=items+[0]*(124-len(items));assert len(padded)==124
        a.uc.mem_write(buffer(slot),storage(padded));a.call(0x9B510,r.ctx,slot,1)
        actual=visible(bytes(a.uc.mem_read(buffer(slot),124*8)));wanted=[relocated(v,slot) for v in padded]
        assert actual==wanted,(slot,[(n,hex(x),hex(y)) for n,(x,y) in enumerate(zip(actual,wanted)) if x!=y][:8])
        return actual
    slots=[]
    for slot in range(7):
        generic=run(words,slot);a.uc.mem_write(buffer(slot),bytes(124*8));r.reset(True,slot);a.call(0x7ADE0,r.ctx,slot)
        native=visible(bytes(a.uc.mem_read(buffer(slot),121*8)));expected=[relocated(v,slot) for v in words]
        if slot in [5,6]:
            assert (f.u32(0x9B954),f.u32(0x9B958))==(0,0x200)
            for pc in [103,106]:expected[pc]=(expected[pc]-(1<<41))&MASK48
        assert native==expected,(slot,[(pc,hex(x),hex(y)) for pc,(x,y) in enumerate(zip(native,expected)) if x!=y])
        # Original code initializer relocates all25 address constants, but keeps
        # the pre-delay selector0 separate until its parameter callback runs.
        constants=r.words();base=f.u32(0x38CCE8+4*slot)
        assert constants[0]==initial[0]
        assert constants[1:26]==[v+base for v in initial[1:26]]
        slots.append(dict(slot=slot,base=base,generic_sha256=hashlib.sha256(storage(generic[:121])).hexdigest(),
            native_sha256=hashlib.sha256(storage(native)).hexdigest(),mfx_modified=[pc for pc,(x,y) in enumerate(zip(generic,native)) if x!=y],
            words=[dict(pc=pc,**decode(v)) for pc,v in enumerate(native)]))
    # Exercise every visible bit around actual Hall forms, with no DSP audio
    # execution or attempt to name an unproven arithmetic operation.
    representatives=[0,1,6,14,22,25,31,39,49,80,105,116,117]
    probes=[words[pc]^(1<<bit) for pc in representatives for bit in range(48)]
    digest=hashlib.sha256();probe_cases=0
    for slot in range(1,7):
        for n in range(0,len(probes),124):
            items=probes[n:n+124];actual=run(items,slot);probe_cases+=len(items)
            digest.update(storage(actual[:len(items)]))
    address_refs=[]
    for index in range(26):
        uses=[r['pc'] for r in references if r['a']==index]
        address_refs.append(dict(index=index,value=initial[index],program_items=uses))
    missing=sorted({x['a'] for x in references if x['a']>=61 and x['a']!=768})
    assert missing==[62,63]
    boundaries=[0,1248,1249,2879,2880,8330,8331,13609,13610,18456,18457,23255,23256,24358,24359,26181]
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={'firmware_hall.py':sha(ROOT/'research/tools/firmware_hall.py'),'firmware_chorus.py':sha(ROOT/'research/tools/firmware_chorus.py')},
        counts=dict(hall_items=121,slots=7,visible_bit_probes=probe_cases,representative_forms=len(representatives)),definition=e['definition_offset'],
        source_code_sha256=hashlib.sha256(raw).hexdigest(),initial_constants=initial,items=references,slots=slots,address_references=address_refs,
        extra_local_indices=missing,probe_sha256=digest.hexdigest(),address_boundaries=boundaries,
        boundaries=['Original9B510 relocation, full7ADE0 Hall initialization and two MFX9B8B8 fixups execute; no stubs in this run',
            'Visible48 is container.low16 shifted32 OR container.high32; container bits16..31 are excluded consistently with the earlier original-upload transport evidence',
            'Two10-bit fields at high32 bits19..28 and9..18 relocate local indices by80*slot under decoded format conditions; selector low4 relocates applicable input/output fields by2*slot',
            'The format6/7 field-A path adds124*slot; this is a program-block reference constraint, not an identified audio arithmetic operation',
            'Seven real slots compare all121 Hall program items against independent integer fields; 3744 one-bit probes around13 actual Hall forms compare the original relocation branch',
            'All25 stored delay/address constants are relocated by original initialization; each listed index-to-item use is an encoding reference without a proven read/write or sample-timing interpretation',
            'Indices62/63 exceed the61 initial constant values; their state role, DSP accumulator behavior, read/write timing, diffusion/coupling/damping math and actual Hall audio remain unresolved'])
    (OUT/'hall-local-operands-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=result['counts'],extra_indices=missing),indent=2))
if __name__=='__main__':main()
