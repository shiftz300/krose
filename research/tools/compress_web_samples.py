#!/usr/bin/env python3
"""Encode web-only auditions; preserve raw PCM24 research exports."""
from layout import PRODUCT_ROOT
import argparse
import concurrent.futures
import hashlib
import json
import math
import struct
import subprocess
import wave

from decode_factory_rom import OUTPUT, DERIVED, ROOT, save


def flac_main():
    manifest=json.loads((OUTPUT/'manifest.json').read_text())
    folder=ROOT/'build/web-flac';folder.mkdir(parents=True,exist_ok=True)
    previous=DERIVED/'web-flac-manifest.json'
    old=json.loads(previous.read_text())['samples'] if previous.exists() else []
    old={r['id']:r for r in old};todo=[]
    for sample in manifest['samples'][:4068]:
        sid=sample['sample_id'];path=folder/f'{sid:04d}.flac';record=old.get(sid)
        if not record or record['source_wav_sha256']!=sample['wav_sha256'] or not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['flac_sha256']:
            todo.append(OUTPUT/sample['file'])
    if todo:
        # A single encoder process, with its own encode-vs-decode verification.
        result=subprocess.run(['flac','--silent','--force','--lax','--no-padding','--no-seektable','-8','--verify',f'--output-prefix={folder}/',*map(str,todo)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stderr[-5000:])
    rows=[]
    for sample in manifest['samples'][:4068]:
        sid=sample['sample_id'];path=folder/f'{sid:04d}.flac';raw=path.read_bytes()
        assert raw[:4]==b'fLaC' and int.from_bytes(raw[5:8],'big')==34
        packed=int.from_bytes(raw[18:26],'big');rate=packed>>44;channels=((packed>>41)&7)+1;bits=((packed>>36)&31)+1;frames=packed&((1<<36)-1)
        assert (rate,channels,bits,frames)==(sample['wav_rate_hz'],1,24,sample['frames'])
        with wave.open(str(OUTPUT/sample['file']),'rb') as w:pcm=w.readframes(w.getnframes())
        assert hashlib.md5(pcm).digest()==raw[26:42]
        rows.append(dict(id=sid,file=str(path.relative_to(PRODUCT_ROOT)),source_wav_sha256=sample['wav_sha256'],flac_sha256=hashlib.sha256(raw).hexdigest(),
                         bytes=len(raw),frames=frames,rate=rate,channels=channels,bits=bits,PCM_MD5_verified=True))
    total=sum(r['bytes'] for r in rows);original=sum((OUTPUT/s['file']).stat().st_size for s in manifest['samples'][:4068])
    save(previous,dict(codec='FLAC24 lossless',encoder=subprocess.check_output(['flac','--version'],text=True).strip(),
                       raw_wav_bytes=original,flac_bytes=total,reduction_fraction=1-total/original,all_4068_PCM_MD5_equal=True,samples=rows))
    print(f'FLAC: {original:,} -> {total:,} bytes ({(1-total/original)*100:.1f}% smaller); every PCM MD5 matches',flush=True)


def opus_info(raw):
    pos=0;last=0;head=None
    while pos<len(raw):
        assert raw[pos:pos+4]==b'OggS'
        segments=raw[pos+26];size=sum(raw[pos+27:pos+27+segments]);body=raw[pos+27+segments:pos+27+segments+size]
        if body.startswith(b'OpusHead'):head=body
        granule=struct.unpack_from('<Q',raw,pos+6)[0]
        if granule!=0xffffffffffffffff:last=granule
        pos+=27+segments+size
    assert pos==len(raw) and head and head[9]==1
    return last-struct.unpack_from('<H',head,10)[0]


def opus_main():
    manifest=json.loads((OUTPUT/'manifest.json').read_text())
    folder=ROOT/'build/web-opus';folder.mkdir(parents=True,exist_ok=True)
    previous=DERIVED/'web-opus-manifest.json'
    old=json.loads(previous.read_text())['samples'] if previous.exists() else [];old={r['id']:r for r in old}
    def encode(s):
        sid=s['sample_id'];target=folder/f'{sid:04d}.opus';source=OUTPUT/s['file'];prepared=folder/f'{sid:04d}-loop.wav'
        rate=s['wav_rate_hz'];frames=s['frames'];lo=s['loop_start_relative'];period=frames-1-lo
        expanded=bool(s['flags']&16 and period>=8 and (frames/rate<.2 or period/rate<.04))
        padded=not expanded and frames/rate<.04
        sidecar=folder/f'{sid:04d}.json';prior=json.loads(sidecar.read_text()) if sidecar.exists() else old.get(sid)
        if prior and prior.get('encoding_version')==2 and bool(prior.get('padded_one_shot'))==padded and prior['source_wav_sha256']==s['wav_sha256'] and target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==prior['opus_sha256']:return prior
        loop_start=lo/rate;loop_end=(frames-1)/rate
        if expanded:
            with wave.open(str(source),'rb') as w:pcm=w.readframes(w.getnframes())
            cycle=pcm[lo*3:(frames-1)*3];cycles=max(1,math.ceil((.6*rate-lo)/period))
            pcm=pcm[:lo*3]+cycle*cycles+cycle[:3]
            with wave.open(str(prepared),'wb') as w:w.setnchannels(1);w.setsampwidth(3);w.setframerate(rate);w.writeframes(pcm)
            frames=len(pcm)//3;source=prepared
            stable=min(cycles-1,max(0,math.ceil(.12*rate/period)))
            loop_start=(lo+stable*period)/rate;loop_end=(frames-1)/rate
        elif padded:
            with wave.open(str(source),'rb') as w:pcm=w.readframes(w.getnframes())
            frames=math.ceil(.06*rate);pcm+=bytes(frames*3-len(pcm))
            with wave.open(str(prepared),'wb') as w:w.setnchannels(1);w.setsampwidth(3);w.setframerate(rate);w.writeframes(pcm)
            source=prepared
        result=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-f','wav','-i',str(source),
                        '-af','aresample=48000:filter_size=64:phase_shift=10:cutoff=0.97','-c:a','libopus','-b:a','64k','-vbr','on',
                        '-application','audio','-compression_level','10','-map_metadata','-1',str(target)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(f'Sample {sid}: {result.stderr}')
        raw=target.read_bytes();decoded_frames=opus_info(raw)
        expected=round(frames*48000/rate)
        assert abs(decoded_frames-expected)<=2,(sid,decoded_frames,expected)
        record=dict(id=sid,encoding_version=2,file=str(target.relative_to(PRODUCT_ROOT)),source_wav_sha256=s['wav_sha256'],opus_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                    original_frames=s['frames'],encoded_source_frames=frames,decoded_frames_48000=decoded_frames,
                    loop_extended=expanded,padded_one_shot=padded,loop_start_seconds=loop_start,loop_end_seconds=loop_end)
        sidecar.write_text(json.dumps(record)+'\n');return record
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for index,row in enumerate(pool.map(encode,manifest['samples'][:4068])):
            rows.append(row)
            if index%500==0:print('Opus encoded',index,flush=True)
    total=sum(r['bytes'] for r in rows);original=sum((OUTPUT/s['file']).stat().st_size for s in manifest['samples'][:4068])
    save(previous,dict(codec='Ogg Opus, 64kbps VBR mono, 48kHz; lossy audition only',raw_wav_bytes=original,opus_bytes=total,
                       reduction_fraction=1-total/original,all_granule_frame_counts_verified=True,short_loop_extended_count=sum(r['loop_extended'] for r in rows),samples=rows))
    print(f'Opus: {original:,} -> {total:,} bytes ({(1-total/original)*100:.1f}% smaller)',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--codec',choices=('opus','flac'),default='opus');args=parser.parse_args()
    opus_main() if args.codec=='opus' else flac_main()
