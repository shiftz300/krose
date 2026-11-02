#!/usr/bin/env python3
"""Read-only input/product checks; write only the current architecture results.

Does not rerun old probes, modify old reports or access any device. The previous
ARM result must match the exact current scripts and generated startup input.
"""
import hashlib
import json
import re
from pathlib import Path

from program_firmware import Firmware, FW_SHA
from layout import PRODUCT_ROOT as ROOT
from firmware_architecture_index import OUT


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    f=Firmware()
    protected=json.loads((OUT/'protected-before.json').read_text())
    for row in protected['files']:
        assert sha(ROOT/row['path'])==row['sha256'],row['path']
    static=json.loads((OUT/'static-check.json').read_text())
    arm=json.loads((OUT/'arm-check.json').read_text())
    assert static['passed'] and arm['passed']
    assert static['tool_sha256']==sha(ROOT/'research/tools/firmware_architecture_index.py')
    assert arm['tool_sha256']==sha(ROOT/'research/tools/firmware_architecture_verify_arm.py')
    assert arm['helper_sha256']==sha(ROOT/'research/tools/program_firmware.py')
    assert arm['startup_input_sha256']==sha(OUT/'startup.json')
    inputs=[dict(path='research/derived/firmware/KROSS2_V124/KROSSAPP.bin',sha256=FW_SHA)]
    for path,expected in [
        ('research/derived/acquisitions/KROSS2_ROM_stage_b_20261031T215150691039Z/complete/TG-ROM-candidate.img','c9d4c9b4dd0f915b45a553e6b66d2cab7e51b80f4b2189fb6db4d91b1ccc94a5'),
        ('research/libraries/KROSS2_local_20261101-022845/internal-storage.img','6cd9b98ca73626535106418bef26c12fa2ae361b92376ab73e958e23ae30c378')]:
        p=ROOT/path;assert sha(p)==expected,path
        inputs.append(dict(path=path,sha256=expected))
    historical=[
        'research/derived/firmware/KROSS2_V124/catalog/index.json',
        'research/derived/verification/pcm-arm-comparison.json',
        'research/derived/verification/voice-timing-arm-comparison.json',
        'research/derived/verification/effects-catalog-arm-comparison.json',
        'research/derived/verification/dsp-transport.json',
        'research/derived/verification/concert-filter-arm-comparison.json',
        'research/derived/firmware/KROSS2_V124/rom/dispatch/dispatch-check-arm.json']
    snapshots=[]
    for name in historical:
        p=ROOT/name;d=json.loads(p.read_text())
        assert d['firmware_sha256']==FW_SHA,name
        snapshots.append(dict(path=name,sha256=sha(p),scope='historical execution/index; version and bytes checked, probe NOT rerun'))
    sources=json.loads((OUT/'references/sources.json').read_text())
    for source in sources['sources']:
        if source.get('local_path'):
            assert sha(OUT/source['local_path'])==source['sha256']
        for selected in source.get('selected_files',[]):
            assert sha(OUT/selected['local_path'])==selected['sha256']
    document=ROOT/'research/docs/architecture/REPORT.md'
    # Figure links are checked locally; external reference links are provenance.
    for target in re.findall(r'!\[[^]]*\]\(([^)]+)\)',document.read_text()):
        assert (document.parent/target).is_file(),target
    report=json.loads((OUT/'report-check.json').read_text())
    assert report['markdown_sha256']==sha(document)
    assert report['pdf_sha256']==sha(document.parent/'KROSS2-v1.2.4-architecture-report.pdf')
    assert report['generator_sha256']==sha(ROOT/'research/tools/firmware_architecture_report.py')
    result=dict(passed=True,firmware_sha256=FW_SHA,inputs=inputs,
        protected_product_files=len(protected['files']),protected_product_unchanged=True,
        historical_snapshots=snapshots,static_checks=static['checks'],
        original_ARM_checks=list(arm['results']),
        sources_and_selected_reference_files_verified=True,
        report_pages=report['pages'],report_text_check=report['text_extraction_passed'],
        visual_review=report['visual_review'],device_access=False,
        tool_sha256=sha(Path(__file__)))
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    paths=list(OUT.rglob('*'))+list(document.parent.rglob('*'))+list((ROOT/'research/tools').glob('firmware_architecture_*.py'))
    manifest=[]
    for p in sorted(paths):
        if p.is_file() and p.name!='manifest.json':
            manifest.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)))
    (OUT/'manifest.json').write_text(json.dumps(dict(firmware_sha256=FW_SHA,files=manifest),indent=2)+'\n')
    print(json.dumps(dict(passed=True,protected_files=len(protected['files']),historical_snapshots=len(snapshots),
        artifacts=len(manifest),pdf_pages=report['pages'],visual_review=report['visual_review']),indent=2))


if __name__=='__main__':main()
