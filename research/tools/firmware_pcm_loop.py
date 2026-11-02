#!/usr/bin/env python3
"""Measure loop-end/history ambiguity using recovered predictor arithmetic."""
import argparse,ctypes,hashlib,json,struct,subprocess,sys,wave
from pathlib import Path
import numpy as np
from decode_korg_pcm import load_lut,FW_SHA
from firmware_expansion_pcm import read_library
from test_korg_pcm import FirmwareFeedback
from program_firmware import Firmware
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
BUILD=ROOT/'research/build/pcm-loop-probe'
LIMIT=2147483647
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def reference(raw,a1,a2,lut,previous,older):
    values=[]
    for code in raw:
        product=a1*previous+a2*older;prediction=(abs(product)//16384)*(-1 if product<0 else 1)
        prediction=max(-LIMIT,min(LIMIT,prediction));value=max(-LIMIT,min(LIMIT,prediction+lut[(code+128)&255]*65536))
        values.append(value);older,previous=previous,value
    return values,(previous,older)
class Decoder:
    def __init__(self,lut):
        BUILD.mkdir(parents=True,exist_ok=True);self.path=BUILD/('pcm-loop.dylib' if sys.platform=='darwin' else 'pcm-loop.so')
        subprocess.run(['cc','-std=c99','-O3','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'research/tools/firmware_pcm_loop.c'),'-o',str(self.path)],check=True)
        lib=ctypes.CDLL(str(self.path));self.fn=lib.pcm_decode_stateful;self.fn.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int16,ctypes.c_int16,ctypes.c_void_p,ctypes.c_int32,ctypes.c_int32,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p];self.fn.restype=None
        self.cold=lib.korg_pcm_decode;self.cold.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int16,ctypes.c_int16,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p];self.cold.restype=None
        self.lut=(ctypes.c_int16*256)(*lut)
    def decode(self,raw,coefficients,state=(0,0)):
        output=np.empty(len(raw),dtype=np.int32);after=(ctypes.c_int32*2)();counts=(ctypes.c_uint64*2)()
        self.fn(raw,len(raw),*coefficients,self.lut,*state,output.ctypes.data,after,counts)
        return output,tuple(after),list(counts)
    def baseline(self,raw,coefficients):
        result=np.empty(len(raw),dtype=np.int32);counts=(ctypes.c_uint64*2)();self.cold(raw,len(raw),*coefficients,self.lut,result.ctypes.data,counts)
        own,_,own_counts=self.decode(raw,coefficients);assert np.array_equal(own,result) and own_counts==list(counts);return result
def corpus():
    manifest=ROOT/'research/output/Factory_ROM_WAV/manifest.json';d=json.loads(manifest.read_text());rom_path=ROOT/d['ROM'];rom=rom_path.read_bytes();assert sha(rom_path)==d['ROM_sha256']
    rows=[];inputs=[manifest,rom_path]
    for s in d['samples']:
        if s['encoding']!='predictive8' or s['frames']-s['loop_start_relative']<=1:continue
        lo,hi=s['source_byte_range'];raw=rom[lo:hi];assert hashlib.sha256(raw).hexdigest()==s['source_sha256']
        rows.append(dict(library='ROM',sample=s['sample_id'],flags=s['flags'],raw=raw,loop=s['loop_start_relative'],coefficients=s['coefficients_q14'],wav=ROOT/'research/output/Factory_ROM_WAV'/s['file'],wav_sha256=s['wav_sha256']))
    for number in [1,2,4]:
        lib=read_library(number);inputs.extend(lib['inputs'])
        if number==1:
            exported=ROOT/'research/output/OASYS_Piano_WAV/manifest.json';mapping={x['sample_id']-10000:dict(path=exported.parent/x['file'],sha256=x['wav_sha256']) for x in json.loads(exported.read_text())['samples']}
        else:
            exported=OUT/'expansion-pcm-check.json';saved=next(x for x in json.loads(exported.read_text())['exports'] if x['library']==number)
            mapping={x['id']:dict(path=ROOT/x['file'],sha256=x['sha256']) for x in saved['samples']}
        inputs.append(exported)
        for s in lib['samples']:
            if s['frames']-s['loop']<=1:continue
            desc=bytes.fromhex(s['descriptor_hex']);assert desc[7]&1
            raw=lib['decoded_bytes'][s['offset']:s['offset']+s['frames']];assert hashlib.sha256(raw).hexdigest()==s['sha256']
            record=mapping[s['id']]
            rows.append(dict(library=f'EXPCM{number:03d}',sample=s['id'],flags=desc[7],raw=raw,loop=s['loop'],coefficients=list(struct.unpack_from('<hh',desc,8)),wav=record['path'],wav_sha256=record['sha256']))
    return rows,inputs
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args()
    Firmware();lut=load_lut();decoder=Decoder(lut);sources,inputs=corpus();selected=sources[:4] if args.smoke else sources
    rows=[];raw_map={};max_rms=-1;witness=None;total_frames=0;prefix_checks=0
    for source in selected:
        raw=source['raw'];coefficients=source['coefficients'];baseline=decoder.baseline(raw,coefficients);loop=source['loop'];assert 0<=loop<len(raw)-1
        path=source['wav'];assert sha(path)==source['wav_sha256'];inputs.append(path)
        with wave.open(str(path)) as stream:
            assert stream.getnchannels()==1 and stream.getsampwidth()==3 and stream.getnframes()==len(raw);wav=stream.readframes(len(raw))
        b=np.frombuffer(wav,dtype=np.uint8).reshape(-1,3).astype(np.int32);back=b[:,0]|b[:,1]<<8|b[:,2]<<16;back=(back<<8)>>8;assert np.array_equal(back,baseline>>8)
        key=(source['library'],source['sample']);raw_map[key]=source;cuts=[]
        for excluded_end_frames in [0,1]:
            end=len(raw)-excluded_end_frames;segment=raw[loop:end];expected=baseline[loop:end];assert len(segment)>0
            saved=(int(baseline[loop-1]) if loop else 0,int(baseline[loop-2]) if loop>1 else 0)
            restored,_,_=decoder.decode(segment,coefficients,saved);assert np.array_equal(restored,expected)
            state=(int(baseline[end-1]),int(baseline[end-2]) if end>1 else 0);initial=state;cycles=[]
            for cycle in range(3):
                before=state;actual,state,saturations=decoder.decode(segment,coefficients,state)
                check,_=reference(segment[:16],*coefficients,lut,*before);assert check==actual[:16].tolist();prefix_checks+=len(check)
                difference=actual.astype(np.int64)-expected.astype(np.int64);rms=float(np.sqrt(np.mean((difference/2**31)**2)))
                cycles.append(dict(cycle=cycle+1,initial_state=list(before),final_state=list(state),different_q31_frames=int(np.count_nonzero(difference)),different_pcm24_frames=int(np.count_nonzero((actual>>8)!=(expected>>8))),max_abs_q31_difference=int(np.max(np.abs(difference))),rms_difference=rms,saturations=saturations))
                total_frames+=len(segment)
                if cycle==0 and rms>max_rms:
                    max_rms=rms;witness=dict(library=source['library'],sample=source['sample'],excluded_end_frames=excluded_end_frames,loop=loop,
                        baseline_prefix=expected[:128].tolist(),carry_prefix=actual[:128].tolist(),rms_difference=rms)
            cuts.append(dict(excluded_end_frames=excluded_end_frames,end_exclusive=end,loop_frames=len(segment),saved_preloop_state=list(saved),first_carry_state=list(initial),cycles=cycles))
        rows.append(dict(library=source['library'],sample=source['sample'],flags=source['flags'],frames=len(raw),loop=loop,coefficients=coefficients,source_sha256=hashlib.sha256(raw).hexdigest(),
            wav_path=str(path.relative_to(ROOT)),wav_sha256=sha(path),cuts=cuts))
    arm_points=[]
    if args.verify_arm:
        arm=FirmwareFeedback();representatives={}
        for row in rows:representatives.setdefault((row['library'],row['flags']),row)
        representatives['max_difference']=next(x for x in rows if (x['library'],x['sample'])==(witness['library'],witness['sample']))
        for row in {(x['library'],x['sample']):x for x in representatives.values()}.values():
            source=raw_map[row['library'],row['sample']];raw=source['raw']
            for cut in row['cuts']:
                segment=raw[row['loop']:cut['end_exclusive']]
                for label,state in [('restore',cut['saved_preloop_state']),('carry1',cut['cycles'][0]['initial_state']),('carry3',cut['cycles'][2]['initial_state'])]:
                    expected,_=reference(segment[:8],*row['coefficients'],lut,*state);previous,older=state
                    for i,(code,wanted) in enumerate(zip(segment[:8],expected)):
                        actual=arm.step(code,*row['coefficients'],previous,older);assert actual==wanted
                        arm_points.append(dict(library=row['library'],sample=row['sample'],excluded_end_frames=cut['excluded_end_frames'],history=label,index=i,code=code,previous=previous,older=older,value=actual));older,previous=previous,actual
    groups=[]
    for library in sorted({r['library'] for r in rows}):
        for excluded in [0,1]:
            cases=[r['cuts'][excluded] for r in rows if r['library']==library]
            groups.append(dict(library=library,excluded_end_frames=excluded,samples=len(cases),different_pcm24_samples=sum(c['cycles'][0]['different_pcm24_frames']>0 for c in cases),
                maximum_rms_difference=max(c['cycles'][0]['rms_difference'] for c in cases)))
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_pcm_loop.c','korg_pcm_decode.c','decode_korg_pcm.py','firmware_expansion_pcm.py','test_korg_pcm.py']},
        inputs=[dict(path=str(path.relative_to(ROOT)),sha256=sha(path)) for path in dict.fromkeys(inputs)],counts=dict(samples=len(rows),baseline_frames=sum(r['frames'] for r in rows),carry_frames=total_frames,python_prefix_points=prefix_checks,arm_points=len(arm_points)),rows=rows,groups=groups,witness=witness,arm_points=arm_points,TG_loop_state_policy_verified=False,
        boundaries=['All predictive descriptors with non-single-point source intervals are included; eligibility follows metadata span and does not assert that every Program actually uses forward looping',
            'Recovered encoder feedback arithmetic compares zero-history stateful C with the frozen decoder for every source frame, PCM24 with existing WAV, independent Python prefixes for each supplied state and selected original ARM feedback points',
            'Two explicit endpoint candidates retain the full exported span or exclude its final source frame; CPU end-minus1 upload motivates the latter, without determining TG inclusive/exclusive endpoint or interpolation behavior',
            'For each endpoint, restoring pre-loop reconstructed history exactly reproduces the decoded PCM segment. Carrying the prior endpoint history processes three additional cycles and exposes differences; neither policy is identified as actual TG behavior',
            'RMS and different-frame statistics measure candidate-model sensitivity, not error against an instrument; no mode, reverse, fractional stepping, interpolation, filter, effects or hardware output executes',
            'Inputs and product assets unchanged. The study constrains loop assumptions and records remaining evidence needs; a passing predictor check does not prove a TG loop restart policy'])
    if not args.smoke:
        assert args.verify_arm and arm_points;(OUT/'pcm-loop-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,smoke_only=args.smoke,counts=result['counts'],groups=groups,witness=witness and {k:witness[k] for k in ['library','sample','excluded_end_frames','rms_difference']}),indent=2))
if __name__=='__main__':main()
