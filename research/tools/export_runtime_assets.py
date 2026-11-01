#!/usr/bin/env python3
"""Explicit research -> product handoff. Never called by the normal build.

Rebuild validated inputs in build/, then freeze runtime assets and independent
ARM regression fixtures. The player, CMake build and CTest do not run research.
"""
from layout import PRODUCT_ROOT
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from layout import ROOT
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def export(folder,files,provenance,kind):
    folder.mkdir(parents=True,exist_ok=True)
    previous=folder/'manifest.json'
    known={r['file']:r['sha256'] for r in json.loads(previous.read_text())['files']} if previous.exists() else {}
    # Refuse unknown edits before changing anything in this bundle.
    for name,source in files.items():
        target=folder/name
        if target.exists() and sha(target)!=sha(source):
            if name not in known or sha(target)!=known[name]:raise ValueError(f'Unknown local asset edit: {target}')
    for name,source in files.items():
        target=folder/name
        if not target.exists() or sha(target)!=sha(source):shutil.copyfile(source,target)
    result=dict(format_version=1,kind=kind,
                files=[dict(file=name,bytes=(folder/name).stat().st_size,sha256=sha(folder/name)) for name in files],
                provenance_sha256={str(p.relative_to(PRODUCT_ROOT)):sha(p) for p in provenance},
                exporter_sha256=sha(Path(__file__)),
                scope='Frozen build/test input; provenance paths are references, not normal build dependencies')
    previous.write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    stage=ROOT/'build/research-export/concert-se-grand';stage.mkdir(parents=True,exist_ok=True)
    for command in ([sys.executable,'tools/verify_firmware_research.py'],
                    [sys.executable,'tools/verify_wav_exports.py'],
                    [sys.executable,'tools/prepare_plugin_assets.py','--output',str(stage)],
                    [sys.executable,'tools/prepare_voice_assets.py','--output',str(stage)]):
        subprocess.run(command,cwd=ROOT,check=True)
    # Current accepted product resources are a strict byte-identity baseline.
    reference=ROOT/'output/Concert_SE_Grand_Filter/manifest.json'
    accepted=json.loads(reference.read_text())
    assert sha(stage/'SEGrand.samples')==accepted['sample_pack_sha256']
    assert sha(stage/'NativeVoiceData.h')==accepted['source_sha256']['build/plugin/generated/NativeVoiceData.h']
    old_eq=ROOT/'build/plugin/generated/ConcertEqData.h'
    if old_eq.exists():assert sha(stage/'ConcertEqData.h')==sha(old_eq)
    product=export(ROOT/'assets/concert-se-grand',
                   {name:stage/name for name in ('SEGrand.samples','ConcertEqData.h','NativeVoiceData.h','assets.json','voice-assets.json')},
                   [reference,ROOT/'output/Concert_SE_Grand_WAV/decode_report.json',
                    ROOT/'research/derived/verification/voice-timing-arm-comparison.json',
                    ROOT/'research/derived/firmware/KROSS2_V124/effects/007/concert-coefficients.json'],
                   'Concert product runtime assets; unchanged accepted audio data')
    voice=ROOT/'research/derived/firmware/KROSS2_V124/voice'
    fixtures=export(ROOT/'tests/fixtures/concert-se-grand',
                    {'concert-control-map.bin':voice/'concert-control-map.bin',
                     'native-voice-traces.bin':stage/'native-voice-traces.bin',
                     'native-tg-commands.bin':stage/'native-tg-commands.bin',
                     'concert-filter-map.bin':voice/'concert-filter-map.bin',
                     'concert-filter-traces.bin':voice/'concert-filter-traces.bin'},
                    [ROOT/'research/derived/verification/concert-voice-arm-comparison.json',
                     ROOT/'research/derived/verification/concert-filter-arm-comparison.json',
                     ROOT/'research/derived/verification/voice-timing-arm-comparison.json'],
                    'Independent original-ARM test fixtures; never linked into the plugin')
    print('Exported',len(product['files']),'runtime assets and',len(fixtures['files']),'test fixtures; no plugin deployment')


if __name__=='__main__':main()
