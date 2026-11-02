#!/usr/bin/env python3
"""P4EQ native payload binding and falsifiable B2 audio candidates; no DSP VM."""
import argparse,cmath,contextlib,hashlib,io,json,math,struct
from pathlib import Path
from program_firmware import Firmware,BASE,FW_SHA
from firmware_parametric_eq import EqRig,response
from firmware_hall_operands import visible,decode,relocated,storage
from firmware_inspect import inspect
from firmware_voice_lfo import PRELOAD,OUT,sha
from layout import PRODUCT_ROOT as ROOT

def code_address(slot):return 0xC0FEB1C8+8*(32+124*slot)
def expected_code(words,slot):
    result=[relocated(v,slot) for v in words]
    if slot in [5,6]:
        for pc in [55,106]:result[pc]=(result[pc]-(1<<41))&((1<<48)-1)
    return result
def slot_number(name):return int(name[-1])+(4 if name.startswith('MFX') else -1)
def df1(c,x,s):
    x1,x2,y1,y2=s;y=c[0]*x+c[1]*x1+c[2]*x2+c[3]*y1+c[4]*y2
    return y,[x,x1,y,y1]
def transposed_reference(c,frames):
    states=[[0.,0.] for _ in range(2)];result=[]
    for frame in frames:
        row=[]
        for channel,x in enumerate(frame):
            z1,z2=states[channel];y=c[0]*x+z1
            states[channel]=[c[1]*x+c[3]*y+z2,c[2]*x+c[4]*y];row.append(y)
        result.append(row)
    return result
class Candidate:
    def __init__(self,a,b,parallel):self.a,self.b,self.parallel=a,b,parallel;self.states=[[[0.]*4 for _ in range(2)] for _ in range(2)]
    def process(self,frames,weights):
        output=[]
        for frame,w in zip(frames,weights):
            c=[(1-w)*a+w*b for a,b in zip(self.a,self.b)];row=[]
            for channel,x in enumerate(frame):
                a,self.states[0][channel]=df1(self.a if self.parallel else c,x,self.states[0][channel])
                if self.parallel:
                    b,self.states[1][channel]=df1(self.b,x,self.states[1][channel]);a=(1-w)*a+w*b
                assert math.isfinite(a);row.append(a)
            output.append(row)
        return output
def host_candidates(parent):
    rows=[];frequencies=[20*1000**(i/128) for i in range(129)]
    signal=[[.17*(i==0)+.013*math.sin(i*.117),-.11*(i==37)+.009*math.cos(i*.081)] for i in range(512)]
    weights=[0. if i<128 else (i-128)/128 if i<256 else 1. for i in range(512)]
    for source in parent['factory']:
        band=source['bands'][1];a,b=band['coefficients']
        if a==b:continue
        g=band['gain'];other=max(-36,min(36,g+band['delta']))
        category='both_nonnegative' if min(g,other)>=0 else 'both_negative' if max(g,other)<0 else 'cross_zero'
        static=[]
        for w in [.25,.5,.75]:
            c=[(1-w)*x+w*y for x,y in zip(a,b)];curve=[]
            for hz in frequencies:
                p=(1-w)*response(a,hz)+w*response(b,hz);q=response(c,hz)
                curve.append(dict(hz=hz,parallel_db=20*math.log10(max(abs(p),1e-15)),coefficient_db=20*math.log10(max(abs(q),1e-15)),complex_difference=abs(p-q)))
            static.append(dict(weight=w,maximum_complex_difference=max(x['complex_difference'] for x in curve),maximum_db_difference=max(abs(x['parallel_db']-x['coefficient_db']) for x in curve),curves=curve))
        outputs=[]
        for parallel in [True,False]:
            whole=Candidate(a,b,parallel).process(signal,weights);r=Candidate(a,b,parallel);ragged=[];position=n=0;sizes=[1,7,64,3,129,11]
            while position<len(signal):
                end=min(len(signal),position+sizes[n%len(sizes)]);ragged+=r.process(signal[position:end],weights[position:end]);position=end;n+=1
            assert whole==ragged
            outputs.append(whole)
        for endpoint in [0.,1.]:
            lhs=Candidate(a,b,True).process(signal,[endpoint]*512);rhs=Candidate(a,b,False).process(signal,[endpoint]*512);assert lhs==rhs
        ra,rb=transposed_reference(a,signal),transposed_reference(b,signal)
        parallel_error=max(abs(outputs[0][i][channel]-((1-w)*ra[i][channel]+w*rb[i][channel])) for i,w in enumerate(weights) for channel in range(2))
        midpoint=Candidate(a,b,False).process(signal,[.5]*512);rc=transposed_reference([(x+y)/2 for x,y in zip(a,b)],signal)
        midpoint_error=max(abs(x-y) for p,q in zip(midpoint,rc) for x,y in zip(p,q))
        assert parallel_error<1e-9 and midpoint_error<1e-9
        delta=[[x-y for x,y in zip(p,q)] for p,q in zip(*outputs)]
        rows.append(dict(program=source['program'],slot=source['slot'],source_sha256=source['source_sha256'],gain=g,other_gain=other,category=category,
            coefficients=[a,b],feedback_words_equal=a[3:]==b[3:],static=static,block_sizes_equal=True,constant_endpoints_equal=True,
            parallel_transposed_reference_error=parallel_error,midpoint_transposed_reference_error=midpoint_error,
            dynamic_maximum_difference=max(abs(v) for row in delta for v in row),dynamic_rms_difference=math.sqrt(sum(v*v for row in delta for v in row)/1024),
            dynamic_parallel=outputs[0],dynamic_coefficient=outputs[1]))
    assert len(rows)==61
    return dict(kind='two_unverified_host_candidates',actual_DSP_executed=False,frames=512,channels=2,weights=weights,input=signal,frequency_points=129,
        rows=rows,boundary='Parallel model runs both endpoint DF-I filters continuously and mixes output. Coefficient model interpolates five coefficients per frame with one DF-I history. Weight timing and both algorithms are hypotheses.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();r=EqRig(f);a=r.a;e=f.effect(7);raw=f.data[e['code_offset']:e['code_offset']+8*e['code_words_64']];words=visible(raw)
    initial=[f.u32(e['constants_offset']+4*i) for i in range(e['constant_words_32'])];assert len(words)==118 and len(initial)==50
    params={};ctx=r.ctx;request=0x1100A000
    def getter(m):
        assert m.get('R0')==777 and m.get('R2')==m.get('R3')==0
        return params[m.get('R1')]
    a.stubs[0xD5AC4]=getter
    def constants(slot):return list(struct.unpack('<80I',a.uc.mem_read(0xC0FE9DC8+320*slot,320)))
    def initialize(effect,slot):
        a.uc.mem_write(ctx,b'\x01\x01'+bytes(30));a.uc.mem_write(0xC0FE9DC8,bytes(2560))
        a.call(0x5A51C,ctx,slot,2,BASE+effect['definition_offset']);a.call(effect['arm_functions'][0],ctx,slot)
    slots=[];empty=[]
    for slot in range(7):
        initialize(e,slot);actual=visible(bytes(a.uc.mem_read(code_address(slot),118*8)))
        expected=expected_code(words,slot);assert actual==expected and constants(slot)==initial+[0]*30
        generic=[relocated(v,slot) for v in words]
        slots.append(dict(slot=slot,program_sha256=hashlib.sha256(storage(actual)).hexdigest(),mfx_modified=[i for i,(x,y) in enumerate(zip(generic,actual)) if x!=y]))
        no=f.effect(0);initialize(no,slot)
        no_words=visible(f.data[no['code_offset']:no['code_offset']+no['code_words_64']*8]);actual=visible(bytes(a.uc.mem_read(code_address(slot),8*8)))
        assert actual==[relocated(v,slot) for v in no_words]
        assert constants(slot)==([0 if slot in [5,6] else 8388607]+[0]*79)
        empty.append(dict(slot=slot,word0=constants(slot)[0],program_sha256=hashlib.sha256(storage(actual)).hexdigest()))
    parent_path=OUT/'parametric-eq-check.json';parent=json.loads(parent_path.read_text());assert parent['passed'] and parent['tool_sha256']==sha(ROOT/'research/tools/firmware_parametric_eq.py')
    source=PRELOAD.read_bytes();assert sha(PRELOAD)==parent['inputs'][0]['sha256'];factory=[];callbacks=0
    for old in parent['factory'][:1] if args.smoke else parent['factory']:
        slot=slot_number(old['slot']);record=source[old['source_offset']:old['source_offset']+2140]
        assert hashlib.sha256(record).hexdigest()==old['source_sha256']
        values=[f.read_value(record,old['payload_offset']+p['payload_offset'],p['descriptor']) for p in e['parameters']];assert values==old['parameters']
        params.clear();params.update(enumerate(values));initialize(e,slot)
        for index,value in enumerate(values):
            a.uc.mem_write(request,bytes(40));a.write(request,777,0,value,slot,ctx,1,0)
            a.call(e['parameters'][index]['descriptor']['callback'],20,request);callbacks+=1
        want=initial+[0]*30;want[0]=values[0]*8388607//100;want[1]=values[17]*8388607//100
        for band,starts in zip(old['bands'],[[2],[12,22],[32],[37]]):
            for start,native in zip(starts,band['native']):want[start:start+len(native)]=native
        want[44]=old['bands'][2]['scale'];want[45]=old['bands'][3]['scale']
        assert constants(slot)==want,(old['program'],old['slot'],[(i,x,y) for i,(x,y) in enumerate(zip(constants(slot),want)) if x!=y])
        program=visible(bytes(a.uc.mem_read(code_address(slot),118*8)));assert program==expected_code(words,slot)
        factory.append(dict(program=old['program'],slot=old['slot'],slot_number=slot,source_sha256=old['source_sha256'],parameters=values,constants=want,
            program_sha256=hashlib.sha256(storage(program)).hexdigest()))
    items=[dict(pc=i,visible48=f'{v:012x}',**decode(v)) for i,v in enumerate(words)];mirrors=[]
    for pc in range(7,53):
        left=decode(words[pc]);right=decode(words[pc+51]);expected=left.copy()
        if expected['b']!=768:expected['b']+=30
        if expected['c']==32:expected['c']=33
        assert right==expected,(pc,left,right)
        mirrors.append(dict(left=pc,right=pc+51,b_left=left['b'],b_right=right['b']))
    references=[]
    for start,end in [(12,22),(22,32)]:
        uses=[x for x in items if start<=x['a']<end and (x['format']<0x5000 or x['flag2'])]
        references.append(dict(constants=list(range(start,end)),left_items=[x['pc'] for x in uses if x['pc']<53],right_items=[x['pc'] for x in uses if x['pc']>=53],
            left_b_fields=sorted({x['b'] for x in uses if x['pc']<53}),right_b_fields=sorted({x['b'] for x in uses if x['pc']>=53})))
    host=host_candidates(parent)
    for name,lo,hi in [('eq-b2-slot-init',0x879FC,0x87A44),('eq-empty-slot-init',0x82580,0x825DC)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,actual_DSP_audio_executed=False,
        tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_parametric_eq.py','firmware_hall_operands.py','firmware_inspect.py','firmware_voice_lfo.py']},
        inputs=[dict(path=str(x.relative_to(ROOT)),sha256=sha(x)) for x in [parent_path,PRELOAD]],
        counts=dict(slots=7,empty_slots=7,program_items=118,mirror_pairs=46,factory_slots=len(factory),callbacks=callbacks,nonidentical_endpoint_slots=61),
        initial_constants=initial,items=items,slots=slots,empty_slots=empty,factory=factory,mirrors=mirrors,endpoint_references=references,
        extra_local_a_indices=sorted({x['a'] for x in items if 50<=x['a']<640}),host_candidates=host,
        boundaries=['Original P4EQ and NoEffect load/initialization execute at allseven slots. P4EQ MFX fixups subtract bit41 at55/106; complete118-item canonical48 programs and80-word constants compare',
            'All331 factory P4EQ slots execute20 native parameter callbacks with decoded getterD5AC4 supplied; complete80-word output matches earlier independently checked coefficient/scale values. Code remains unchanged by parameter callbacks',
            'Fortysix pairs share the exact visible48 form after B-field +30 and input selector32-to33; A/B read/write direction, arithmetic opcodes and pipeline timing are not inferred',
            'Both endpoint constant ranges12..21/22..31 have separate program reference sets. Local A50/51 exceed the50 initialized constants; their runtime state role remains unknown',
            'NoEffect initializes word0 toQ23 in IFX andzero in MFX. This proves a control-level slot distinction, not the silicon transfer function or a rule to silence all bypasses',
            'Host comparisons cover all61 nonidentical B2 endpoint slots with two explicit, unverified arithmetic hypotheses. They do not identify actual DSP interpolation, state mapping, smoothing or rounding',
            'No hardware, audio capture, OS, full instruction-set emulation or product changes'])
    (OUT/('eq-b2-program-smoke.json' if args.smoke else 'eq-b2-program-check.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,counts=result['counts'],candidate_max_db_difference=max(s['maximum_db_difference'] for row in host['rows'] for s in row['static']))))
if __name__=='__main__':main()
