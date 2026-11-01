#!/usr/bin/env python3
"""Render clearly labelled source-waveform auditions, not full Program replicas.

The Concert player remains unchanged. A fixed shared gain and simple note gate
are used for choosing sample families; no original Program FX/AMS are implied.
"""
import argparse
import array
import hashlib
import json
import math
import struct
import sys
import wave
from pathlib import Path

from program_firmware import Firmware, ROOT, FW_SHA
from decode_korg_pcm import Decoder, decode_reference, load_lut

CHOICES=[
    ('mark_i',2,[4],'E.P. Mark I source wave, v5'),
    ('mark_v',2,[12],'E.P. Mark V source wave, v5'),
    ('dynomy',2,[20],'E.P. DynoMy source wave, v5'),
    ('200a',2,[28],'E.P. 200A source wave, v5'),
    ('hype_saw',4,[1,2],'Hype Saw source wave, stereo'),
    ('atmos_choir',4,[7,8],'Atmos Choir source wave, stereo'),
    ('slina_wave3',4,[15],'Slina Wave 3 source wave, mono'),
    ('kalimba2',4,[0],'Kalimba 2 source wave, mono'),
]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args()
    fw=Firmware();lut=load_lut();decoder=Decoder(lut,ROOT/'build/sound-preview')
    oracle=None
    if args.verify_arm:
        from test_korg_pcm import FirmwareFeedback
        oracle=FirmwareFeedback()
    output=ROOT/'output/Sound_Selection/waveforms';output.mkdir(parents=True,exist_ok=True)
    libraries={n:json.loads((ROOT/f'research/derived/kep/EXPCM{n:03d}/library.json').read_text()) for n in (2,4)}
    data={n:(ROOT/lib['decoded']).read_bytes() for n,lib in libraries.items()}
    cache={};sources=[];compared=0

    def sample(libid,msid,note):
        lib=libraries[libid];ms=lib['multisamples'][msid]
        r=next((r for r in ms['regions'] if r['top']>=note),ms['regions'][-1]);s=lib['samples'][r['sample_id']]
        key=(libid,s['id'])
        if key not in cache:
            nonlocal compared
            raw=bytes.fromhex(s['descriptor_hex']);native=data[libid][s['offset']:s['offset']+s['frames']]
            assert hashlib.sha256(native).hexdigest()==s['sha256']
            # The waveform previews intentionally cover only this previously
            # decoded descriptor flag. Other 0x21/0x51/0x61 cases stay unresolved.
            assert raw[7]==0x11,(key,hex(raw[7]))
            a1,a2=struct.unpack_from('<2h',raw,8);audio,counts=decoder.decode(native,a1,a2)
            assert counts==[0,0]
            expected,_=decode_reference(native[:1024],a1,a2,lut)
            assert audio[:len(expected)]==expected
            if oracle:
                older=previous=0
                for code,value in zip(native,expected):
                    assert oracle.step(code,a1,a2,previous,older)==value
                    older,previous=previous,value;compared+=1
            pitch=struct.unpack_from('<h',raw)[0]
            increment=fw.phase_increment(pitch*2);rate=48000*increment/8192
            cache[key]=(audio,s['loop'],rate)
            sources.append(dict(library=libid,sample_id=s['id'],native_sha256=s['sha256'],
                                descriptor_hex=s['descriptor_hex'],rate_hz=rate,phase_increment=increment,
                                descriptor_flag='0x11',frames=len(audio),saturations=counts,
                                C_Python_prefix_frames=len(expected),ARM_prefix_frames=len(expected) if oracle else 0))
        return (*cache[key],r['root'])

    def value(audio,loop,position):
        end=len(audio)-1
        if position>=end:position=loop+(position-end)%(end-loop)
        i=int(position);fraction=position-i
        return (audio[i]*(1-fraction)+audio[min(i+1,end)]*fraction)/2**31

    records=[];rate=48000;frames=rate*6
    events=[(0.,1.,60),(.95,1.,64),(1.9,1.,67),(3.,2.5,60),(3.,2.5,64),(3.,2.5,67)]
    for filename,libid,msids,title in CHOICES:
        channels=[array.array('f',[0])*frames,array.array('f',[0])*frames]
        for onset,duration,note in events:
            for ch in range(2):
                audio,loop,baseRate,root=sample(libid,msids[ch if len(msids)==2 else 0],note)
                step=baseRate/rate*2**((note-root)/12)
                count=int(duration*rate);start=int(onset*rate)
                for frame in range(count):
                    gate=min(1.,frame/(rate*.002),(count-1-frame)/(rate*.03))
                    channels[ch][start+frame]+=value(audio,loop,frame*step)*0.2*gate
        peak=max(max(map(abs,ch)) for ch in channels);assert 0<peak<.99
        pcm=array.array('h',[0])*(frames*2)
        for frame in range(frames):
            pcm[frame*2]=round(channels[0][frame]*32767);pcm[frame*2+1]=round(channels[1][frame]*32767)
        if sys.byteorder!='little':pcm.byteswap()
        path=output/(filename+'.wav')
        with wave.open(str(path),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(rate);w.writeframes(pcm.tobytes())
        records.append(dict(file='waveforms/'+path.name,title=title,library_id=libid,multisample_ids=msids,
                            multisample_names=[libraries[libid]['multisamples'][i]['name'] for i in msids],
                            frames=frames,rate_hz=rate,channels=2,pcm_bits=16,shared_gain=.2,peak=peak,sha256=digest(path)))
        print('Rendered source-waveform audition:',filename,flush=True)
    result=dict(firmware_sha256=FW_SHA,files=records,decoded_sources=sources,ARM_feedback_frames=compared,
                library_sha256={n:lib['source_sha256'] for n,lib in libraries.items()},
                scope=['Source-waveform selection aids, not full original Program or plugin renders',
                       'Fixed source layer (v5 for EP), shared 0.2 gain, simple 2ms attack/30ms release, forward-loop interpretation',
                       'No Program velocity switching, Amp/Filter EG, native FX, LFO or articulation; not all descriptor playback flags supported',
                       'User has accepted current Concert baseline; these are additional unselected sound families'],
                source_sha256={name:digest(ROOT/'tools'/name) for name in ('render_library_previews.py','decode_korg_pcm.py','korg_pcm_decode.c','test_korg_pcm.py')})
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    (output.parent/'waveform-manifest.json').write_text(text)
    (ROOT/'research/derived/verification/sound-waveform-preview-check.json').write_text(text)
    print('PASS',len(records),'waveform previews,',len(sources),'decoded samples,',compared,'original ARM feedback frames')


if __name__=='__main__':main()
