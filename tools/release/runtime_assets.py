"""Losslessly package Factory PCM once; reconstruct the duplicate Concert bank in CI."""
import argparse, base64, hashlib, io, json, lzma, mmap, struct, tarfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
FACTORY = 'assets/program-library/Factory.samples'
CONCERT = 'assets/concert-se-grand/SEGrand.samples'
REFS = 'concert-refs.json'
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''): h.update(chunk)
    return h.hexdigest()
def verify(root, name):
    path = root / name
    manifest = json.loads((path.parent / 'manifest.json').read_text())
    entry = next(v for v in manifest['files'] if v['file'] == path.name)
    if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
        raise ValueError('Runtime bank mismatch: ' + name)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('action', choices=['pack', 'extract'])
p.add_argument('archive', type=Path)
p.add_argument('--root', type=Path, default=ROOT)
a = p.parse_args(); root = a.root
if a.action == 'pack':
    for name in [FACTORY, CONCERT]: verify(root, name)
    with (root / FACTORY).open('rb') as f, (root / CONCERT).open('rb') as c:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as fm, mmap.mmap(c.fileno(), 0, access=mmap.ACCESS_READ) as cm:
            count = struct.unpack_from('<I', fm, 12)[0]; table = 24 + 224*4 + 256*2 + 129*2
            offsets = {}
            for i in range(count):
                frames = struct.unpack_from('<I', fm, table+i*32+4)[0]
                offset = struct.unpack_from('<Q', fm, table+i*32+24)[0]
                offsets[hashlib.sha256(fm[offset:offset+frames*3]).digest()] = offset
            pairs = []
            for i in range(84):
                frames = struct.unpack_from('<I', cm, 32+i*32+12)[0]
                offset = struct.unpack_from('<Q', cm, 32+i*32+24)[0]
                stereo = cm[offset:offset+frames*6]; pair = []
                for channel in range(2):
                    mono = bytearray(frames*3)
                    for byte in range(3): mono[byte::3] = stereo[channel*3+byte::6]
                    pair.append(offsets[hashlib.sha256(mono).digest()])
                pairs.append([frames, *pair])
            refs = json.dumps(dict(header=base64.b64encode(cm[:32+84*32]).decode(), pairs=pairs)).encode()
    a.archive.parent.mkdir(parents=True, exist_ok=True)
    filters = [dict(id=lzma.FILTER_DELTA, dist=3), dict(id=lzma.FILTER_LZMA2, preset=6)]
    with lzma.LZMAFile(a.archive, 'wb', filters=filters) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as tar:
            info = tarfile.TarInfo(FACTORY); info.size = (root/FACTORY).stat().st_size
            with (root/FACTORY).open('rb') as stream: tar.addfile(info, stream)
            info = tarfile.TarInfo(REFS); info.size = len(refs); tar.addfile(info, io.BytesIO(refs))
    lock = dict(tag='runtime-assets-v1', file=a.archive.name, sha256=digest(a.archive))
    (ROOT/'packaging/runtime-assets.json').write_text(json.dumps(lock, indent=2)+'\n')
else:
    lock = json.loads((ROOT/'packaging/runtime-assets.json').read_text())
    if digest(a.archive) != lock['sha256']: raise ValueError('Archive checksum mismatch')
    with tarfile.open(a.archive) as tar:
        members = tar.getmembers()
        if sorted(m.name for m in members) != sorted([FACTORY, REFS]) or not all(m.isfile() for m in members):
            raise ValueError('Unexpected archive members')
        destination = root/FACTORY; destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix('.incoming')
        with tar.extractfile(FACTORY) as src, temporary.open('wb') as dst:
            import shutil
            shutil.copyfileobj(src, dst)
        temporary.replace(destination); verify(root, FACTORY)
        refs = json.load(tar.extractfile(REFS))
    destination = root/CONCERT; destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.incoming')
    header = base64.b64decode(refs['header'], validate=True)
    if len(header) != 32+84*32 or len(refs['pairs']) != 84: raise ValueError('Invalid Concert references')
    with (root/FACTORY).open('rb') as src, temporary.open('wb') as dst:
        dst.write(header)
        for frames, left, right in refs['pairs']:
            if not 4 <= frames <= 48000*60: raise ValueError('Invalid frame count')
            stereo = bytearray(frames*6)
            for channel, offset in enumerate([left, right]):
                if offset < 0 or offset+frames*3 > (root/FACTORY).stat().st_size: raise ValueError('Invalid PCM reference')
                src.seek(offset); mono = src.read(frames*3)
                for byte in range(3): stereo[channel*3+byte::6] = mono[byte::3]
            dst.write(stereo)
    temporary.replace(destination); verify(root, CONCERT)
print('Verified lossless runtime archive:', a.archive)
