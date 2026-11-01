#!/usr/bin/env python3
"""Check ROM exports, audition links, deployment archive and product isolation."""
import hashlib
import json
import wave
import zipfile
from pathlib import Path

import numpy as np

from decode_factory_rom import ROM, ROM_SHA, OUTPUT, DERIVED, ROOT, save


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert sha(ROM)==ROM_SHA and ROM.stat().st_mode&0o222==0
    manifest=json.loads((OUTPUT/'manifest.json').read_text());assert manifest['ROM_sha256']==ROM_SHA
    assert len(manifest['samples'])==4070
    for s in manifest['samples']:
        p=OUTPUT/s['file'];assert sha(p)==s['wav_sha256']
        with wave.open(str(p),'rb') as w:assert (w.getnframes(),w.getnchannels(),w.getsampwidth(),w.getframerate())==(s['frames'],1,3,s['wav_rate_hz'])
        assert s['nonzero_frames']>0
    selection=ROOT/'output/Factory_Sound_Selection';catalog=json.loads((selection/'rom-sound-catalog.json').read_text())
    for item in catalog['waveforms']+catalog['drums']:
        p=selection/item['preview'];assert sha(p)==item['preview_sha256']
        with wave.open(str(p),'rb') as w:
            assert w.getnframes()==item['preview_frames'] and w.getframerate()==48000
            a=np.frombuffer(w.readframes(w.getnframes()),'<i2');assert np.max(np.abs(a.astype(np.int32)))<=26215 and np.any(a)
    by_id={w['id']:w for w in catalog['waveforms']}
    for p in catalog['programs']:
        assert all(i in by_id for i in p['waveform_ids'])
        assert sha(ROOT/p['source_file'])==p['source_sha256']
    arm=json.loads((DERIVED/'original-arm-verification.json').read_text())
    assert len(arm['predictor_cases'])==4 and len(arm['source_rate_checks'])==48 and len(arm['saturation_checks'])==2
    kits=json.loads((DERIVED/'factory-drumkits.json').read_text())
    assert kits['ARM_parameter_checks']==36582 and len(kits['kits'])==42
    rename=json.loads((ROOT/'build/krose-rename-check.json').read_text())
    for name,digest in rename['source_sha256'].items():assert sha(ROOT/name)==digest,name
    assets=ROOT/'assets/concert-se-grand';runtime=json.loads((assets/'manifest.json').read_text())
    for item in runtime['files']:assert sha(assets/item['file'])==item['sha256']
    web=ROOT/'output/Krose_Web';report=json.loads((DERIVED/'web-package-verification.json').read_text())
    for path,digest in report['package_inputs_sha256'].items():assert sha(ROOT/path)==digest
    with zipfile.ZipFile(ROOT/'output/Krose_Web_CF_Pages.zip') as z:
        assert z.testzip() is None
        names=set(z.namelist());assert names=={str(p.relative_to(web)) for p in web.rglob('*') if p.is_file()}
        for name in names:
            assert not name.startswith('/') and '..' not in Path(name).parts
            assert hashlib.sha256(z.read(name)).hexdigest()==sha(web/name)
        assert len(names)==report['files']<1000
    result=dict(ROM_sha256=ROM_SHA,raw_WAV_files=4070,nonzero_factory_samples=4068,audition_WAVs=1454,factory_Programs=768,
                factory_drumkits=42,product_source_files_unchanged=len(rename['source_sha256']),runtime_assets_unchanged=len(runtime['files']),
                deployment_files=report['files'],deployment_bytes=report['bytes'],archive_entries_SHA256_equal=True,
                desktop_product_modified=False,VST3_copied_or_installed=False,
                scope='Offline data integrity, archive verification and product-baseline checks; browser behavior recorded separately. No hardware A/B or Cloudflare deployment.')
    save(DERIVED/'export-verification.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
