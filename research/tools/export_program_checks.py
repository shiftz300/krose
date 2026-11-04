#!/usr/bin/env python3
"""Freeze prior isolated-ARM voice-selection observations for product CTest."""
import hashlib,json
from pathlib import Path
from layout import ROOT,PRODUCT_ROOT

def main():
    manifest=json.loads((PRODUCT_ROOT/'assets/program-library/manifest.json').read_text())
    indices={p['id']:i for i,p in enumerate(manifest['programs'])}
    directory=ROOT/'derived/firmware/KROSS2_V124/architecture'
    rows=[];cases=[];inputs=[]
    for stage,name,groups in [('stage04','factory-voice-chain-check.json',['factory','extra']),('stage04','gm-programs-check.json',['melodic']),('stage04','expansion-voices-check.json',['melodic'])]:
        path=directory/stage/name;data=json.loads(path.read_text());assert data['passed'] and not data['smoke_only']
        inputs.append(dict(path=str(path.relative_to(PRODUCT_ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for group in groups:
            for case in data[group]:
                identity=case.get('program',case.get('id'))
                if identity not in indices:continue
                program=indices[identity];osc=case['oscillator']-1;mask=0
                for voice in case['voices']:
                    if voice['weight']>0:mask|=1<<voice['slot']
                    bank=voice.get('sample_bank',0)
                    sample=voice['sample']+(bank-1)*10000 if bank else voice['sample']
                    rows.append([program,osc,case['note'],case['velocity'],voice['slot'],voice['side'],sample,voice['weight'],voice['pitch']])
                cases.append([program,osc,case['note'],case['velocity'],mask])
    target=PRODUCT_ROOT/'tests/fixtures/full-programs';target.mkdir(exist_ok=True)
    for name,content in [('voices.tsv',rows),('selection.tsv',cases)]:
        (target/name).write_text(''.join('\t'.join(map(str,row))+'\n' for row in content))
    files=[dict(file=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(target.glob('*.tsv'))]
    (target/'manifest.json').write_text(json.dumps(dict(format_version=1,files=files,inputs=inputs,voices=len(rows),selections=len(cases)),indent=2)+'\n')
    print(len(rows),'voices,',len(cases),'selection cases')
if __name__=='__main__':main()
