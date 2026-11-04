"""Create or verify/extract the two frozen sample banks used in release CI."""
import argparse, hashlib, json, tarfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

FILES = ['assets/concert-se-grand/SEGrand.samples', 'assets/program-library/Factory.samples']
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('action', choices=['pack', 'extract'])
p.add_argument('archive', type=Path)
a = p.parse_args()
if a.action == 'pack':
    a.archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(a.archive, 'w:gz', compresslevel=1) as tar:
        for name in FILES:
            tar.add(ROOT / name, arcname=name)
    lock = dict(tag='runtime-assets-v1', file=a.archive.name,
                sha256=digest(a.archive))
    (ROOT / 'packaging/runtime-assets.json').write_text(json.dumps(lock, indent=2) + '\n')
else:
    lock = json.loads((ROOT / 'packaging/runtime-assets.json').read_text())
    assert digest(a.archive) == lock['sha256'], 'Archive checksum mismatch'
    with tarfile.open(a.archive) as tar:
        members = tar.getmembers()
        assert sorted(m.name for m in members) == sorted(FILES)
        for member in members:
            assert member.isfile() and not member.issym() and not member.islnk()
            destination = ROOT / member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, destination.open('wb') as dst:
                import shutil
                shutil.copyfileobj(src, dst)
    for name in FILES:
        path = ROOT / name
        manifest = json.loads((path.parent / 'manifest.json').read_text())
        entry = next(v for v in manifest['files'] if v['file'] == path.name)
        assert digest(path) == entry['sha256']
print('Verified runtime assets:', a.archive)
