#!/usr/bin/env python3
"""Fetch pinned build dependencies into build/, preserving unknown local trees."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    pins = json.loads((ROOT / 'cmake/dependencies.json').read_text())
    deps = ROOT / 'build/deps'
    downloads = ROOT / 'build/downloads'
    deps.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    pin = pins['iplug2']
    archive = downloads / ('iplug2-' + pin['commit'][:8] + '.tar.gz')
    if not archive.exists():
        temporary = archive.with_suffix('.download')
        subprocess.run(['curl', '-fL', '--retry', '2', pin['url'], '-o', str(temporary)], check=True)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != pin['sha256']:
            raise RuntimeError('iPlug2 archive checksum mismatch')
        temporary.replace(archive)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == pin['sha256']
    iplug = deps / 'iPlug2'
    # Compare a present tree with the pinned archive rather than overwriting it.
    with tarfile.open(archive) as package:
        members = package.getmembers()
        prefix = 'iPlug2-' + pin['commit'] + '/'
        for item in members:
            if item.name.rstrip('/') == prefix.rstrip('/'):
                continue
            if not item.name.startswith(prefix) or '..' in Path(item.name).parts or item.issym() or item.islnk():
                raise RuntimeError('Unexpected archive member: ' + item.name)
        if not iplug.exists():
            with tempfile.TemporaryDirectory(dir=deps) as scratch:
                package.extractall(scratch)
                (Path(scratch) / prefix.rstrip('/')).rename(iplug)
        for item in members:
            if not item.isfile():
                continue
            relative = item.name[len(prefix):]
            # This placeholder is deliberately replaced with the SDK symlink.
            if relative.startswith('Dependencies/IPlug/VST3_SDK/'):
                continue
            path = iplug / relative
            if not path.is_file() or hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(package.extractfile(item).read()).digest():
                raise RuntimeError('Modified/missing pinned iPlug2 file: ' + relative)
    pin = pins['vst3sdk']
    sdk = deps / 'vst3sdk'
    if not sdk.exists():
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', pin['tag'], pin['url'], str(sdk)], check=True)
    if run('git', '-C', str(sdk), 'rev-parse', 'HEAD') != pin['commit']:
        raise RuntimeError('Existing VST3 SDK has a different revision; left untouched')
    subprocess.run(['git', '-C', str(sdk), 'submodule', 'update', '--init', '--depth', '1', *pin['submodules']], check=True)
    for name in pin['submodules']:
        if run('git', '-C', str(sdk / name), 'status', '--porcelain'):
            raise RuntimeError('Modified VST3 SDK submodule: ' + name)
    link = iplug / 'Dependencies/IPlug/VST3_SDK'
    if link.is_symlink():
        assert link.resolve() == sdk.resolve()
    else:
        if link.exists():
            files = list(link.iterdir())
            if any(p.name != 'README.md' or not p.is_file() for p in files):
                raise RuntimeError('Existing SDK folder is not the iPlug2 placeholder')
            for path in files:
                path.unlink()
            link.rmdir()
        link.symlink_to(os.path.relpath(sdk, link.parent), target_is_directory=True)
    print('Pinned iPlug2 and VST3 SDK ready in build/deps/')


if __name__ == '__main__':
    main()
