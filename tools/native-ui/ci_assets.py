"""Stage compile-only asset bundles. These placeholders cannot render audio.

The private PCM banks never enter CI or published artifacts. Product manifests
remain untouched; CI builds use explicit paths under build/compile-assets.
"""
import hashlib,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[2]
for name in ['concert-se-grand','program-library']:
    source=root/'assets'/name
    target=root/'build/compile-assets'/name
    if target.exists():shutil.rmtree(target)
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('*.samples'))
    manifest=json.loads((target/'manifest.json').read_text())
    for entry in manifest['files']:
        path=target/entry['file']
        if not path.exists() and path.suffix=='.samples':
            path.write_bytes(b'KROSE COMPILE ONLY - NO AUDIO DATA\n')
            entry['bytes']=path.stat().st_size
            entry['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest['kind']='COMPILE ONLY - INVALID AUDIO BANKS - DO NOT DISTRIBUTE'
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
