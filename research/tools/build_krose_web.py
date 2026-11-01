#!/usr/bin/env python3
"""Package a buildless, self-contained Cloudflare Pages audition site.

Lossy Opus audition samples are grouped in <=1MiB resource blocks.
Only public-facing sound metadata/audio is copied. No firmware, acquisition
messages, injection tools, research environments or plugin binary is included.
"""
from layout import PRODUCT_ROOT
import os
import hashlib
import json
import shutil
import struct
import zipfile
from pathlib import Path

from decode_factory_rom import OUTPUT, ROM_SHA, load
from program_firmware import ROOT, Firmware

DEST = ROOT / 'output/Krose_Web'
SOURCE = PRODUCT_ROOT.parent / 'krose-website/public'
LIMIT = 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    catalog=json.loads((ROOT/'output/Factory_Sound_Selection/rom-sound-catalog.json').read_text())
    manifest=json.loads((OUTPUT/'manifest.json').read_text())
    assert catalog['ROM_sha256']==manifest['ROM_sha256']==ROM_SHA
    descriptors=load('sample-descriptors'); regions=load('key-regions'); multi=load('multisamples');fw=Firmware()
    DEST.mkdir(parents=True,exist_ok=True);(DEST/'assets').mkdir(exist_ok=True)
    compressed=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/rom/decoding/web-opus-manifest.json').read_text())
    encoded={r['id']:r for r in compressed['samples']}
    drumkits=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/rom/decoding/factory-drumkits.json').read_text())
    music=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/rom/decoding/web-music.json').read_text())
    releases=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/rom/decoding/web-releases.json').read_text())
    assert releases['firmware_sha256']==digest(fw.data)
    mapping={}; packs=[];pending=[];payload=bytearray();expected_assets=set()
    def flush():
        if not pending:return
        content=bytes(payload); sha=digest(content)
        name=f'assets/samples-{len(packs):03d}-{sha[:12]}.bin';expected_assets.add(name)
        path=DEST/name
        if path.exists():assert path.read_bytes()==content
        else:path.write_bytes(content)
        for sid,offset,length in pending:mapping[str(sid)]=dict(pack=len(packs),offset=offset,length=length)
        packs.append(dict(file=name,bytes=len(content),sha256=sha))
        pending.clear();payload.clear()
    for sample in manifest['samples'][:4068]:
        encoding=encoded[sample['sample_id']];raw=(ROOT/encoding['file']).read_bytes()
        assert encoding['source_wav_sha256']==sample['wav_sha256'] and digest(raw)==encoding['opus_sha256'] and len(raw)<LIMIT
        if len(payload)+len(raw)>LIMIT:flush()
        pending.append((sample['sample_id'],len(payload),len(raw)));payload.extend(raw)
    flush()
    # Only builder-owned, obsolete sample block names may be removed on rebuild.
    for p in (DEST/'assets').glob('samples-*.bin'):
        if str(p.relative_to(DEST)) not in expected_assets:p.unlink()
    samples={}
    for s in manifest['samples'][:4068]:
        sid=s['sample_id']
        samples[str(sid)]={**mapping[str(sid)],'frames':s['frames'],'rate':s['wav_rate_hz'],
                           'pitch':s['pitch_field'],'flags':s['flags'],'loop':s['loop_start_relative'],
                           'loopStart':encoded[sid]['loop_start_seconds'],'loopEnd':encoded[sid]['loop_end_seconds'],
                           'duration':encoded[sid]['decoded_frames_48000']/48000}
    waves=[]
    for w in catalog['waveforms']:
        channels=[]
        for index in w['indices']:
            ms=multi[index];channel=[]
            for r in regions[ms['first_region']:ms['first_region']+ms['region_count']]:
                raw=bytes.fromhex(r['raw_hex'])
                channel.append(dict(sample=r['sample_index_raw'],top=r['top_key'],root=r['root_key_candidate'],
                                    fine=struct.unpack_from('<h',raw,6)[0],fixed=bool(raw[5]&1)))
            channels.append(channel)
        waves.append(dict(id=w['id'],name=w['name'],category=w['category'],categories=w['categories'],
                          channels=channels,used_by=w['used_by']))
    kit_records=[]
    for kit in drumkits['kits']:
        kit_records.append({**{k:kit[k] for k in ('id','name','category')},
                            'keys':{note:{k:value for k,value in key.items() if k!='raw_hex'} for note,key in kit['keys'].items()}})
    data=dict(programs=[{**{k:r[k] for k in ('id','name','category','subcategory','waveform_ids','recommended','effects')},
                         'release_profiles':releases['programs'][r['id']],
                         'release_ams':releases['ams_configs'][r['id']],
                         'drumkit_id':drumkits['program_to_kit'].get(r['id'])} for r in catalog['programs']],
              waveforms=waves,drums=[{k:r[k] for k in ('id','name','category','sample_ids')} for r in catalog['drums']],
              drumkits=kit_records,music=music['pieces'],releaseProfiles=releases['profiles'],releaseAMSTables=releases['ams_tables'],samples=samples,packs=packs,codec='Opus64kVBR',
              phase_base=list(struct.unpack_from('<224I',fw.data,0x405b88)),
              phase_fraction=list(struct.unpack_from('<256H',fw.data,0x405984)))
    (DEST/'catalog.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    site_files=('index.html','styles.css','app.js','custom-select.js','piano-roll.js','midi-recorder.js','release-ams.js','_headers','music-credits.html')
    for name in site_files:
        shutil.copyfile(SOURCE/name,DEST/name)
    # Verify every encoded audition and its frame granules, not lossless identity.
    for sample in manifest['samples'][:4068]:
        m=mapping[str(sample['sample_id'])]; p=packs[m['pack']]
        with (DEST/p['file']).open('rb') as f:f.seek(m['offset']);raw=f.read(m['length'])
        assert digest(raw)==encoded[sample['sample_id']]['opus_sha256']
    files=[p for p in DEST.rglob('*') if p.is_file()]
    assert len(files)<1000 and max(p.stat().st_size for p in files)<25*1024*1024
    report=dict(files=len(files),bytes=sum(p.stat().st_size for p in files),sample_count=4068,resource_blocks=len(packs),
                max_resource_block_bytes=max(p['bytes'] for p in packs),every_packed_Opus_SHA256_equal=True,all_granule_frame_counts_verified=compressed['all_granule_frame_counts_verified'],
                compression='Ogg Opus 64kbps VBR mono; lossy audition',uncompressed_audio_bytes=compressed['raw_wav_bytes'],compressed_audio_bytes=compressed['opus_bytes'],
                limits_basis=['https://developers.cloudflare.com/pages/platform/limits/','https://developers.cloudflare.com/pages/get-started/direct-upload/'],
                package_inputs_sha256={os.path.relpath(p, PRODUCT_ROOT):digest(p.read_bytes()) for p in [*(SOURCE/name for name in site_files),ROOT/'tools/build_krose_web.py',ROOT/'tools/prepare_web_releases.py',ROOT/'research/derived/firmware/KROSS2_V124/rom/decoding/web-releases.json']})
    report_path=ROOT/'research/derived/firmware/KROSS2_V124/rom/decoding/web-package-verification.json'
    report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2)+'\n')
    archive=ROOT/'output/Krose_Web_CF_Pages.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
        for p in sorted(files):z.write(p,str(p.relative_to(DEST)))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print(archive)


if __name__=='__main__':main()
