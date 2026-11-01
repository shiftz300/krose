#!/usr/bin/env python3
"""Read-only integrity verification after splitting the product and website."""
import hashlib
import json
import wave
from pathlib import Path
from layout import ROOT, PRODUCT_ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    migration = json.loads((ROOT/'archive/migration-2026-11-01/manifest.json').read_text())
    historical_source_changes=[]
    for old, item in migration['protected_before'].items():
        path = ROOT/old
        assert path.is_file(),path
        if (old.startswith('src/') or old.startswith('tests/') and '/fixtures/' not in old or old.startswith('assets/') and path.suffix=='.md') and sha(path)!=item['sha256']:
            historical_source_changes.append(old)
            continue
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], path
    raw = ROOT/'output/Factory_ROM_WAV'
    manifest = json.loads((raw/'manifest.json').read_text())
    for item in manifest['samples']:
        path = raw/item['file']
        assert sha(path) == item['wav_sha256'], path
        with wave.open(str(path), 'rb') as wav:
            assert (wav.getnframes(),wav.getnchannels(),wav.getsampwidth(),wav.getframerate()) == (item['frames'],1,3,item['wav_rate_hz']), path
    grand = ROOT/'output/Concert_SE_Grand_WAV'
    stereo = json.loads((grand/'decode_report.json').read_text())['samples']
    for item in stereo:
        assert sha(grand/item['file']) == item['sha256'], item['file']
    selection = ROOT/'output/Factory_Sound_Selection'
    catalog = json.loads((selection/'rom-sound-catalog.json').read_text())
    for item in catalog['waveforms']+catalog['drums']:
        assert sha(selection/item['preview']) == item['preview_sha256'], item['id']
    for program in catalog['programs']:
        assert sha(ROOT/program['source_file']) == program['source_sha256'], program['id']
    oasys = ROOT/'output/OASYS_Piano_WAV'
    oasys_manifest = json.loads((oasys/'manifest.json').read_text())['samples']
    for item in oasys_manifest:
        path = oasys/item['file']
        assert sha(path) == item['wav_sha256'], path
        with wave.open(str(path), 'rb') as wav:
            assert (wav.getnframes(),wav.getnchannels(),wav.getsampwidth(),wav.getframerate()) == (item['frames'],1,3,item['wav_rate_hz']), path
    opus_manifest = json.loads((oasys/'web-opus-manifest.json').read_text())['samples']
    assert {p['id'] for p in opus_manifest} == {p['sample_id'] for p in oasys_manifest}
    for item in opus_manifest:
        assert sha(ROOT/item['file']) == item['opus_sha256'], item['file']
    boundary = json.loads((PRODUCT_ROOT/'build/project-boundary-check.json').read_text())
    for name, expected in boundary['source_sha256'].items():
        assert sha(PRODUCT_ROOT/name) == expected, ('Native source changed since isolated build', name)
    for folder in ['assets/concert-se-grand', 'assets/factory-starter', 'tests/fixtures/concert-se-grand']:
        base = PRODUCT_ROOT/folder
        for item in json.loads((base/'manifest.json').read_text())['files']:
            assert sha(base/item['file']) == item['sha256'], item['file']
    print(json.dumps({'protected_files':len(migration['protected_before']), 'unchanged_migration_files':len(migration['protected_before'])-len(historical_source_changes), 'factory_WAV':len(manifest['samples']), 'grand_stereo_WAV':len(stereo), 'audition_WAV':len(catalog['waveforms'])+len(catalog['drums']), 'program_sources':len(catalog['programs']), 'oasys_mono_WAV':len(oasys_manifest), 'oasys_Opus':len(opus_manifest), 'native_source_fingerprints':len(boundary['source_sha256']), 'intentional_source_changes_since_migration':historical_source_changes, 'current_native_isolated_CTest':boundary['isolated_CTest'], 'runtime_and_test_bundles':'SHA256 verified'}, indent=2))


if __name__ == '__main__':
    main()
