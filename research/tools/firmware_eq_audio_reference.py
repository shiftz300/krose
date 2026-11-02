#!/usr/bin/env python3
"""Executable host cascade from recovered native EQ coefficients; no TG emulation."""
import hashlib,json,math,struct,wave
from pathlib import Path
import numpy as np
from program_firmware import FW_SHA
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
AUDIO=ROOT/'research/output/EQ_reference_audio'
RATE=48000;Q23=8388607
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def signed(x,bits):return x-(1<<bits) if x&(1<<(bits-1)) else x
def coefficients(band):
    words=band['native'][0];scale=band['scale']
    if band['precision']:
        raw=[((hi<<8)|(lo>>15))&0xFFFFFFFF for hi,lo in zip(words[::2],words[1::2])]
        result=[signed(v,32)*2.**(scale-1-30) for v in raw]
    else:result=[signed(v,24)*2.**(scale-1-22) for v in words]
    assert result==band['coefficients'][0];return result
def pole(c):
    a,b=c[3:];return max(abs(complex(a+s*np.lib.scimath.sqrt(a*a+4*b))/2) for s in [-1,1])
def transfer(sections,frequencies,trim):
    z=np.exp(-2j*np.pi*np.asarray(frequencies)/RATE);result=np.full(len(z),complex(trim))
    for b0,b1,b2,f1,f2 in sections:result*=((b0+b1*z+b2*z*z)/(1-f1*z-f2*z*z))
    return result
class Cascade:
    def __init__(self,sections,channels):
        self.sections=sections;self.state=[[[0.,0.] for _ in range(channels)] for _ in sections];self.channels=channels
    def process(self,block):
        result=np.asarray(block,dtype=np.float64).copy();assert result.ndim==2 and result.shape[1]==self.channels
        for i,(b0,b1,b2,f1,f2) in enumerate(self.sections):
            for channel in range(self.channels):
                z1,z2=self.state[i][channel];values=[]
                for x in result[:,channel].tolist():
                    y=b0*x+z1;z1=b1*x+f1*y+z2;z2=b2*x+f2*y;values.append(y)
                self.state[i][channel]=[z1,z2];result[:,channel]=values
        return result
def direct_form_one(block,sections):
    result=np.asarray(block,dtype=np.float64).copy()
    for b0,b1,b2,f1,f2 in sections:
        for channel in range(result.shape[1]):
            x1=x2=y1=y2=0.;values=[]
            for x in result[:,channel].tolist():
                y=b0*x+b1*x1+b2*x2+f1*y1+f2*y2;values.append(y);x2,x1,y2,y1=x1,x,y1,y
            result[:,channel]=values
    return result
def read24(path):
    with wave.open(str(path)) as stream:
        assert stream.getframerate()==RATE and stream.getsampwidth()==3 and stream.getnchannels()==1
        count=stream.getnframes();raw=stream.readframes(count)
    b=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3).astype(np.int32)
    values=b[:,0]|(b[:,1]<<8)|(b[:,2]<<16);values=np.where(values&0x800000,values-0x1000000,values)
    return values.astype(np.float64)/2**23
def write24(path,signal):
    clipped=int(np.count_nonzero((signal>=1)|(signal<-1)));assert not clipped
    integers=np.rint(signal*2**23).astype(np.int32);assert np.max(integers)<2**23 and np.min(integers)>=-2**23
    u=integers.astype(np.uint32)&0xFFFFFF;packed=np.stack([u&255,(u>>8)&255,(u>>16)&255],axis=-1).astype(np.uint8).tobytes()
    with wave.open(str(path),'wb') as stream:stream.setparams((2,3,RATE,len(signal),'NONE','not compressed'));stream.writeframes(packed)
    with wave.open(str(path)) as stream:
        assert stream.getparams()[:4]==(2,3,RATE,len(signal)) and stream.readframes(len(signal))==packed
    return dict(path=str(path.relative_to(ROOT)),sha256=sha(path),frames=len(signal),channels=2,sample_rate=RATE,sample_width=3,clipped_samples=clipped,
        peak=float(np.max(np.abs(signal))),rms=np.sqrt(np.mean(signal*signal,axis=0)).tolist(),tail_peak=float(np.max(np.abs(signal[-4096:]))))
def main():
    source=OUT/'parametric-eq-check.json';original=json.loads(source.read_text());assert original['passed'] and original['firmware_sha256']==FW_SHA and len(original['factory'])==331
    rng=np.random.default_rng(0x4B525332);stimulus=rng.uniform(-.01,.01,(2048,2));stimulus[0,0]+=.25;stimulus[31,1]-=.125
    sizes=[1,7,64,257,3,128,511];models=[];max_error=0.
    for index,row in enumerate(original['factory']):
        sections=[coefficients(b) for b in row['bands']];radii=[pole(c) for c in sections];assert max(radii)<1
        trim=(row['parameters'][0]*Q23//100)/Q23;input_signal=stimulus*trim
        contiguous=Cascade(sections,2).process(input_signal);assert np.all(np.isfinite(contiguous))
        rig=Cascade(sections,2);chunks=[];position=0;n=0
        while position<len(stimulus):
            length=sizes[n%len(sizes)];chunks.append(rig.process(input_signal[position:position+length]));position+=length;n+=1
        streamed=np.concatenate(chunks);assert np.array_equal(contiguous,streamed)
        independently=direct_form_one(input_signal,sections);error=float(np.max(np.abs(contiguous-independently))/max(1.,np.max(np.abs(contiguous))))
        assert error<1e-7,(row['program'],row['slot'],error);max_error=max(max_error,error)
        isolated=input_signal.copy();isolated[:,1]=0;isolated=Cascade(sections,2).process(isolated);assert np.count_nonzero(isolated[:,1])==0
        assert np.array_equal(isolated[:,0],contiguous[:,0])
        models.append(dict(index=index,program=row['program'],slot=row['slot'],source_sha256=row['source_sha256'],parameters=row['parameters'],
            sections=sections,trim=trim,pole_radii=radii,direct_form_relative_error=error,block_sizes_equal=True,channels_isolated=True))
    examples=[]
    for low,high in [(0,0),(1,0),(0,1),(1,1)]:
        examples.append(next(x for x in models if x['parameters'][1:3]==[low,high] and x['parameters'][4]==0 and x['parameters'][17]==100))
    stress=max((x for x in models if x['index'] not in {v['index'] for v in examples}),key=lambda x:max(x['pole_radii']))
    length=262144;bins=np.unique(np.rint(np.geomspace(20,20000,121)*length/RATE).astype(int));frequencies=bins*RATE/length;impulses=[];curves=[]
    for model in examples+[stress]:
        impulse=np.zeros((length,1));impulse[0,0]=model['trim'];audio=Cascade(model['sections'],1).process(impulse)[:,0];actual=np.fft.rfft(audio)[bins]
        expected=transfer(model['sections'],frequencies,model['trim']);errors=np.abs(actual-expected)/np.maximum(np.abs(expected),1e-10)
        assert np.max(errors)<1e-5,(model['index'],float(np.max(errors)))
        impulses.append(dict(index=model['index'],program=model['program'],slot=model['slot'],frames=length,frequency_points=len(bins),
            maximum_relative_complex_error=float(np.max(errors)),tail_peak=float(np.max(np.abs(audio[-4096:])))))
        if model in examples:
            curves.append(dict(index=model['index'],program=model['program'],slot=model['slot'],low_shelf=model['parameters'][1],high_shelf=model['parameters'][2],
                frequencies=frequencies.tolist(),analytic_db=(20*np.log10(np.maximum(np.abs(expected),1e-12))).tolist(),impulse_db=(20*np.log10(np.maximum(np.abs(actual),1e-12))).tolist()))
    input_paths=[ROOT/f'research/output/Factory_ROM_WAV/samples/{i:04d}.wav' for i in [2445,2446]]
    left,right=map(read24,input_paths);assert len(left)==len(right)==55340;input_audio=np.column_stack([left,right]);input_audio=np.concatenate([input_audio,np.zeros((RATE,2))])
    rendered=[input_audio]+[Cascade(m['sections'],2).process(input_audio*m['trim']) for m in examples]
    common_gain=.9/max(float(np.max(np.abs(x))) for x in rendered);AUDIO.mkdir(parents=True,exist_ok=True);clips=[]
    for i,signal in enumerate(rendered):
        name='source-strings' if not i else f"strings-eq-{examples[i-1]['program']}-{examples[i-1]['slot']}"
        row=write24(AUDIO/(name+'.wav'),signal*common_gain);row.update(kind='source' if not i else 'host_eq_reference',model_index=None if not i else examples[i-1]['index'],pre_export_peak=float(np.max(np.abs(signal))))
        clips.append(row)
    inputs=[source,*input_paths,ROOT/'research/output/Factory_ROM_WAV/manifest.json']
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),numpy_version=np.__version__,
        inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in inputs],models=models,impulses=impulses,curves=curves,clips=clips,common_export_gain=common_gain,
        max_direct_form_relative_error=max_error,counts=dict(factory_coefficient_sets=len(models),stream_frames=2048,impulse_models=len(impulses),impulse_frames=length,frequency_points=len(bins),audio_clips=len(clips),audio_frames_per_clip=len(input_audio)),
        boundaries=['Host float64 reference cascade realizes four recovered normalized sections in B1..B4 order with independent state per channel; original native coefficient words are decoded again and checked against the frozen ARM result',
            'All331 enabled factory EQ coefficient sets select B2 base endpoint0, apply recovered Trim and compare contiguous/ragged-block processing, an independently written direct-form-I realization and channel isolation',
            'Five full-cascade impulses compare FFT bins against the product of analytic section transfers, including four mode combinations and a high-pole-radius case; this verifies host arithmetic, not a decoded TG instruction execution',
            'Five48kHz stereoPCM24 clips use existing source samples2445/2446 with55340 frames plus48000 zero tail frames; no resampling, pitch, loop, EG, other effect or preset voice rendering',
            'Four example coefficient sets have B2 Amount0 and Wet100. The host reference uses pure processed output, with each original Trim and one common export gain across allfive clips; no separate loudness matching or nonlinear clipping',
            'Labels name the source of EQ parameters, not a reconstructed Program. TG state layout, B2 modulation, dry/wet mixing, saturation, exact fixed-point rounding and physical audio equivalence remain unproven; product/assets untouched'])
    (OUT/'eq-audio-reference-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=result['counts'],max_direct_form_relative_error=max_error,maximum_impulse_error=max(x['maximum_relative_complex_error'] for x in impulses),common_export_gain=common_gain),indent=2))
if __name__=='__main__':main()
