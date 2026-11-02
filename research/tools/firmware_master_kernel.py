#!/usr/bin/env python3
"""Native Mastering Limiter initialization and its25-word window constraints."""
import argparse,cmath,contextlib,hashlib,io,json,math,struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_hall_operands import visible,decode,relocated,storage
from firmware_inspect import inspect
from firmware_midi_program_load import sha
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
Q=8388607
def code_buffer(slot):return 0xC0FEB1C8+8*(32+124*slot)
def expected_program(words,slot):
    result=[relocated(v,slot) for v in words]
    if slot in [5,6]:
        for pc in [108,110,112,113]:result[pc]=(result[pc]&~511)|14
    return result
def fir_stream(signal,weights,blocks):
    history=[[0.,0.] for _ in weights];output=[];position=0;block=0
    while position<len(signal):
        end=min(len(signal),position+blocks[block%len(blocks)]);block+=1
        for x in signal[position:end]:
            history=[list(x)]+history[:-1]
            output.append([sum(h[channel]*w for h,w in zip(history,weights)) for channel in range(2)])
        position=end
    return output
def reference(window):
    weights=[v/Q for v in window]
    signal=[[.73*math.sin(i*.113)+.09*math.cos(i*.019),.43*math.cos(i*.079)-.12*math.sin(i*.31)] for i in range(512)]
    output=fir_stream(signal,weights,[512]);ragged=fir_stream(signal,weights,[1,7,13,64,3,25])
    assert output==ragged
    maximum=0.
    for n,frame in enumerate(output):
        for channel in range(2):
            expected=sum(weights[k]*signal[n-k][channel] for k in range(min(n+1,len(weights))))
            maximum=max(maximum,abs(frame[channel]-expected))
    assert maximum<1e-14
    impulse=fir_stream([[1.,0.]]+[[0.,0.]]*127,weights,[3,17])
    assert [x[0] for x in impulse[:25]]==weights and all(x==[0.,0.] for x in impulse[25:])
    assert all(x[1]==0 for x in impulse)
    step=[sum(weights[:min(n+1,25)]) for n in range(64)]
    assert all(a<=b for a,b in zip(step,step[1:])) and step[-1]==sum(weights)
    curves=[]
    for n in range(129):
        radians=math.pi*n/128;response=sum(w*cmath.exp(-1j*radians*k) for k,w in enumerate(weights))
        assert abs((response*cmath.exp(1j*radians*12)).imag)<1e-13
        curves.append(dict(fraction_of_nyquist=n/128,magnitude=abs(response),real=response.real,imag=response.imag))
    return dict(kind='host25_tap_FIR_candidate_only',frames=512,channels=2,block_sizes_equal=True,channels_isolated=True,
        max_direct_convolution_error=maximum,weights=weights,impulse=[x[0] for x in impulse],step=step,curves=curves,
        weights_divisor=Q,alternative_binary_Q23_dc_gain=sum(window)/(1<<23),
        dc_gain=sum(weights),centroid=sum(i*w for i,w in enumerate(weights))/sum(weights),group_delay_frames=12,
        original_DSP_audio_executed=False,original_limiter_algorithm_verified=False)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args()
    f=Firmware();e=f.effect(5);raw=f.data[e['code_offset']:e['code_offset']+8*e['code_words_64']];words=visible(raw)
    initial=[f.u32(e['constants_offset']+4*i) for i in range(e['constant_words_32'])]
    assert len(words)==123 and len(initial)==37
    window=initial[1:26];analytic=[Q*(1-math.cos(2*math.pi*(i+1)/26))/26 for i in range(25)]
    assert window==window[::-1] and window==[math.floor(x) for x in analytic] and sum(window)==8388599
    for name,lo,hi in [('master-kernel-slot-init',0x80BC8,0x80C88),('master-kernel-MFX-fields',0x9BAC8,0x9BC20)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f);ctx=0x11008000;request=0x11009000;params={}
    def getter(m):
        assert m.get('R0')==777 and m.get('R2')==m.get('R3')==0
        return params[m.get('R1')]
    a.stubs[0xD5AC4]=getter
    def constants(slot):return list(struct.unpack('<80I',a.uc.mem_read(0xC0FE9DC8+320*slot,320)))
    def initialize(slot):
        a.uc.mem_write(ctx,b'\x01\x01'+bytes(30));a.uc.mem_write(0xC0FE9DC8,bytes(2560))
        a.call(0x5A51C,ctx,slot,2,BASE+e['definition_offset'])
        assert constants(slot)==initial+[0]*43
        assert bytes(a.uc.mem_read(code_buffer(slot),123*8))==raw
        a.call(0x80BC8,ctx,slot)
        actual=visible(bytes(a.uc.mem_read(code_buffer(slot),123*8)));expected=expected_program(words,slot)
        assert actual==expected
        base=f.u32(0x38CCE8+4*slot);want=initial.copy();want[30:34]=[base,base+25,base+24,base+49]
        assert constants(slot)==want+[0]*43
        return actual,want
    slots=[]
    for slot in range(7):
        actual,values=initialize(slot);generic=[relocated(v,slot) for v in words]
        changed=[dict(pc=i,before=f'{x:012x}',after=f'{y:012x}',c_before=decode(x)['c'],c_after=decode(y)['c']) for i,(x,y) in enumerate(zip(generic,actual)) if x!=y]
        assert [x['pc'] for x in changed]==([108,110,112,113] if slot in [5,6] else [])
        slots.append(dict(slot=slot,base=values[30],constants=values,program_sha256=hashlib.sha256(storage(actual)).hexdigest(),
            container_sha256=hashlib.sha256(bytes(a.uc.mem_read(code_buffer(slot),123*8))).hexdigest(),mfx_modified=changed,
            address_intervals=[[values[30],values[32]],[values[31],values[33]]],items=[dict(pc=i,**decode(v)) for i,v in enumerate(actual)]))
    parent_path=OUT/'limiters-check.json';parent=json.loads(parent_path.read_text());assert parent['passed']
    assert parent['tool_sha256']==sha(ROOT/'research/tools/firmware_limiters.py')
    for row in parent['inputs']:assert row['sha256']==sha(ROOT/row['path'])
    source_path=ROOT/parent['inputs'][0]['path'];preload=source_path.read_bytes();factory=[];callbacks=0
    for row in parent['factory']:
        if row['effect']!=5:continue
        slot=int(row['slot'][-1])+(4 if row['slot'].startswith('MFX') else -1)
        source=preload[row['source_offset']:row['source_offset']+2140]
        assert hashlib.sha256(source).hexdigest()==row['source_sha256']
        values=[f.read_value(source,row['payload_offset']+p['payload_offset'],p['descriptor']) for p in e['parameters']]
        assert values==row['parameters'];params.clear();params.update(enumerate(values));initialize(slot)
        for index,value in enumerate(values):
            a.uc.mem_write(request,bytes(40));a.write(request,777,0,value,slot,ctx,1,0)
            a.call(e['parameters'][index]['descriptor']['callback'],20,request);callbacks+=1
            assert constants(slot)[1:26]==window
        expected=row['words'].copy();expected[30:34]=slots[slot]['constants'][30:34]
        assert constants(slot)==expected+[0]*(80-len(expected))
        program=bytes(a.uc.mem_read(code_buffer(slot),123*8));assert visible(program)==expected_program(words,slot)
        factory.append(dict(program=row['program'],slot=slot,source_offset=row['source_offset'],source_sha256=row['source_sha256'],parameters=values,
            constants=expected,program_sha256=hashlib.sha256(storage(visible(program))).hexdigest(),container_sha256=hashlib.sha256(program).hexdigest(),window_unchanged=True))
    assert len(factory)==94 and callbacks==564
    items=[dict(pc=i,visible48=f'{v:012x}',**decode(v)) for i,v in enumerate(words)]
    references=[dict(index=index,value=initial[index],a_items=[r['pc'] for r in items if r['a']==index and (r['format']<0x5000 or r['flag2'])],
        b_items=[r['pc'] for r in items if r['b']==index and (r['format']!=0x5000 or r['flag2'])]) for index in range(37)]
    host=reference(window)
    result=dict(passed=True,smoke_only=False,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_hall_operands.py','firmware_inspect.py','firmware_midi_program_load.py']},
        inputs=[dict(path=str(parent_path.relative_to(ROOT)),sha256=sha(parent_path)),*parent['inputs']],
        counts=dict(slots=7,program_items=123,window_words=25,factory_slots=len(factory),factory_callbacks=callbacks,host_frames=512,frequency_points=129),
        definition=e['definition_offset'],source_program_sha256=hashlib.sha256(raw).hexdigest(),initial_constants=initial,window=window,
        analytic_window=analytic,maximum_quantization_error=max(x-v for x,v in zip(analytic,window)),window_sum=sum(window),
        slots=slots,items=items,references=references,factory=factory,host_reference=host,actual_audio_algorithm_verified=False,
        boundaries=['Native5A51C code/constants loading,80BC8 full initializer,9B510 generic relocation, both9BAC8 MFX rewrites and AA8F4 address-base getter execute; only decoded parameter getterD5AC4 is supplied',
            'All seven initialized123-item programs compare to decoded integer relocation plus exact low9-bit C=14 changes at108/110/112/113 for MFX slots; full80-word constant buffers compare',
            'Program hashes use canonical visible48 storage with the ignored container halfword zeroed; raw64 container hashes are retained separately. The original upload does not transmit container bits16..31',
            'All94 factory mastering-limiter slots rerun original initialization and allsix callbacks at their actual slot; source bytes and prior result fingerprints checked;37 values and code compare after updates',
            'Stored constants1..25 exactly equal floor(Q23*(1-cos(2*pi*(i+1)/26))/26), have symmetry and sumQ23-8, and remain unchanged through564 factory callbacks',
            'Initializer sets address words30..33 to base,base+25,base+24,base+49. This proves two inclusive25-address-unit intervals; address units, read/write ordering, lookahead and plugin latency are not established',
            'A/B references are encoding references under the previously native-verified relocation gates, without assuming arithmetic operations or state/audio roles',
            'Host FIR candidate uses these numeric words only: independent convolution, block consistency, isolated channels, impulse/step and linear-phase properties are checked. It is not an executed TG program or a recovered limiter detector/gain path',
            'No DSP instruction execution, hardware access, OS startup, downloads or product changes; detector, nonlinear curve, actual window role, timing and full audio remain unresolved'])
    (OUT/'master-kernel-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,counts=result['counts'],window_sum=sum(window),maximum_quantization_error=result['maximum_quantization_error']),indent=2))
if __name__=='__main__':main()
