#!/usr/bin/env python3
"""Stereo Chorus local program references and IFX/MFX initialization."""
import argparse,contextlib,hashlib,io,json,struct
from pathlib import Path
from firmware_chorus import ChorusRig,sha
from firmware_hall_operands import visible,storage,decode,relocated,MASK48
from firmware_inspect import inspect
from program_firmware import Firmware,FW_SHA,BASE
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def buffer(slot):return 0xC0FEB1C8+8*(32+124*slot)
def adjusted(items,slot):
    result=[relocated(v,slot) for v in items]
    if slot in [5,6]:
        for first,second in [(59,60),(61,62)]:
            result[first]=(result[first]+(1<<43))&MASK48
            result[second]=(result[second]-(1<<43))&MASK48
    return result
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');parser.add_argument('--smoke',action='store_true');args=parser.parse_args()
    f=Firmware();e=f.effect(64);raw=f.data[e['code_offset']:e['code_offset']+8*e['code_words_64']];words=visible(raw)
    assert len(words)==106 and e['constant_words_32']==27
    items=[dict(pc=pc,visible48=f'{v:012x}',**decode(v)) for pc,v in enumerate(words)]
    for name,lo,hi in [('chorus-slot-program',0x6793C,0x679C8),('chorus-mfx-program',0x9B960,0x9BAC8),('chorus-wave-label',0x9B3CC,0x9B3EC)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm:return
    r=ChorusRig(f);a=r.a;a.stubs.clear();slots=[];initial=[f.u32(e['constants_offset']+4*i) for i in range(27)]
    assert (f.u32(0x9BABC),f.u32(0x9BAC0))==(0,0x800)
    for slot in range(7):
        r.reset(True,slot);loaded=visible(bytes(a.uc.mem_read(buffer(slot),106*8)));assert loaded==words
        a.call(0x6793C,r.ctx,slot);actual=visible(bytes(a.uc.mem_read(buffer(slot),106*8)));expected=adjusted(words,slot)
        assert actual==expected,(slot,[(pc,hex(x),hex(y)) for pc,(x,y) in enumerate(zip(actual,expected)) if x!=y])
        base=f.u32(0x38CCE8+4*slot);want=initial.copy();want[1]=base;want[2]=base+2881
        assert r.words()==want+[0]*53
        generic=[relocated(v,slot) for v in words]
        changed=[dict(pc=pc,before=f'{x:012x}',after=f'{y:012x}') for pc,(x,y) in enumerate(zip(generic,actual)) if x!=y]
        assert [x['pc'] for x in changed]==([59,60,61,62] if slot in [5,6] else [])
        slots.append(dict(slot=slot,base=base,right_base=base+2881,constants=want,mfx_modified=changed,
            code_sha256=hashlib.sha256(storage(actual)).hexdigest(),items=[dict(pc=pc,**decode(v)) for pc,v in enumerate(actual)]))
    # A complete visible-bit neighbourhood of the actual Chorus program, not
    # an assertion that every mutated item is a valid DSP instruction.
    probes=[v^(1<<bit) for v in words[:1 if args.smoke else 106] for bit in range(48)]
    digest=hashlib.sha256();count=0
    for slot in range(1,7):
        for offset in range(0,len(probes),124):
            batch=probes[offset:offset+124];padded=batch+[0]*(124-len(batch));a.uc.mem_write(buffer(slot),storage(padded));a.call(0x9B510,r.ctx,slot,1)
            actual=visible(bytes(a.uc.mem_read(buffer(slot),124*8)));wanted=[relocated(v,slot) for v in padded]
            assert actual==wanted,(slot,offset);count+=len(batch);digest.update(storage(actual[:len(batch)]))
    labels=[]
    def record_label(machine):
        pointer=machine.get('R1')-BASE;labels.append(f.string(pointer));return 0
    a.stubs[0xE5FC4]=record_label
    for raw_value in [0,1]:a.call(0x9B3CC,0,raw_value)
    assert labels==['Tri','Sine'];a.stubs.clear()
    source=OUT/'chorus-check.json';parent=json.loads(source.read_text());assert parent['passed'] and parent['tool_sha256']==sha(ROOT/'research/tools/firmware_chorus.py')
    for row in parent['inputs']:assert sha(ROOT/row['path'])==row['sha256']
    factory=[]
    for row in parent['factory']:
        slot=int(row['slot'][-1])+(4 if row['slot'].startswith('MFX') else -1)
        assert row['words'][1:3]==slots[slot]['constants'][1:3]
        factory.append(dict(program=row['program'],slot=slot,source_offset=row['source_offset'],source_sha256=row['source_sha256'],code_sha256=slots[slot]['code_sha256']))
    assert len(factory)==309
    references=[dict(index=i,initial=initial[i],
        a_items=[r['pc'] for r in items if r['a']==i and (r['format']<0x5000 or r['flag2'])],
        nonlocal_a_items=[r['pc'] for r in items if r['a']==i and not (r['format']<0x5000 or r['flag2'])],
        b_items=[r['pc'] for r in items if r['b']==i]) for i in range(27)]
    assert references[0]['nonlocal_a_items']==[0,64]
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_chorus.py','firmware_hall_operands.py','firmware_hall.py']},
        inputs=[dict(path=str(source.relative_to(ROOT)),sha256=sha(source)),*parent['inputs']],
        counts=dict(program_items=106,slots=7,visible_bit_probes=count,factory_slots=len(factory),wave_labels=len(labels)),definition=e['definition_offset'],
        source_code_sha256=hashlib.sha256(raw).hexdigest(),items=items,slots=slots,references=references,wave_labels=labels,factory=factory,probe_sha256=digest.hexdigest(),
        b_indices_without_initial_values=sorted({r['b'] for r in items if 27<=r['b']<640}),fixed_b_indices=sorted({r['b'] for r in items if r['b']>=640}),
        boundaries=['Native5A51C buffered code/constants load,6793C initializer,9B510 relocation, both9B960 MFX fixups and AA8F4 delay-base getter execute without stubs',
            'Visible fields reuse the previously native-verified Hall relocation model; seven complete real Chorus programs and all27 initialized values compare against independent integers',
            'All106 original items times48 visible-bit mutations times6 nonzero slots exercise relocation; mutated words need not be valid arithmetic instructions',
            'Only display string sink E5FC4 is intercepted for two9B3CC selector-label calls; Tri/Sine names prove parameter intent, not the DSP waveform implementation',
            '309 factory records are source/hash-bound to the completed control matrix and assigned the native-initialized slot program; the callbacks are not rerun here',
            'A-field uses connect known parameter words to program positions only when eligible under the native relocation format; A0 at format5 items0/64 is excluded; B-field uses are recorded separately and do not establish a signal dependency graph',
            'MFX changes are exact plus/minus2^43 payload edits at59/60 and61/62; no gain/dry-path arithmetic is inferred from this encoding change',
            'Delay read/write semantics, fractional interpolation, modulation sampling, accumulator precision/rounding and full audio remain unresolved'])
    if not args.smoke:(OUT/'chorus-program-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,smoke_only=args.smoke,counts=result['counts'],fixed_b=result['fixed_b_indices'],extra_b=result['b_indices_without_initial_values']),indent=2))
if __name__=='__main__':main()
