#!/usr/bin/env python3
"""Stage the maintained controller kit as ordinary, inspectable app resources."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def verify(destination):
    root = destination.resolve()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1: raise ValueError('Unknown controller resource manifest')
    expected = {'manifest.json'}
    for entry in manifest['files']:
        name = entry['path']
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or name in expected:
            raise ValueError('Invalid controller resource path')
        file = root / path
        if root not in file.resolve().parents or file.is_symlink() or not file.is_file():
            raise ValueError('Controller resource escaped its bundle')
        if hashlib.sha256(file.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Controller resource checksum mismatch: ' + name)
        expected.add(name)
    all_files = list(root.rglob('*'))
    if any(p.is_symlink() for p in all_files): raise ValueError('Controller kit contains a symlink')
    actual = {p.relative_to(root).as_posix() for p in all_files if p.is_file()}
    if expected != actual: raise ValueError('Stale or missing controller resources')
    for path in ('ableton/Remote Scripts/Krose_KeyLab_Essential/programs.json',
                 'templates/standalone/generic-keyboard.json', 'templates/ableton/Krose_Generic_Template/surface.py'):
        if path not in expected: raise ValueError('Incomplete controller support kit')


def build(destination, root=ROOT):
    source = root / 'controllers'
    destination = destination.resolve()
    if destination == source.resolve() or source.resolve() in destination.parents:
        raise ValueError('Controller resources must be generated outside source')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='controller-kit-') as scratch:
        stage = Path(scratch) / 'Controllers'
        stage.mkdir()
        for file in sorted(source.rglob('*')):
            if '__pycache__' in file.parts or file.suffix == '.pyc' or file.name == '.DS_Store': continue
            if file.is_symlink(): raise ValueError('Controller source must not contain symlinks')
            if file.is_file():
                target = stage / file.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, target)
        script = stage / 'ableton/Remote Scripts/Krose_KeyLab_Essential'
        catalog = json.loads((root / 'assets/program-library/FactoryPrograms.json').read_text())
        order = json.loads((root / 'assets/program-library/FactoryBrowser.json').read_text())['order']
        if sorted(order) != list(range(len(catalog))): raise ValueError('Invalid controller catalog order')
        (script / 'program_order.json').write_text(json.dumps(order) + '\n', encoding='utf-8')
        (script / 'programs.json').write_text(json.dumps([row[:3] for row in catalog]) + '\n', encoding='utf-8')
        for source, name in [(root / 'tools/install_ableton_controller.py', 'install_ableton_controller.py'),
                             (root / 'docs/CONTROLLERS.md', 'CONTROLLERS.md'), (root / 'LICENSE', 'LICENSE')]:
            shutil.copyfile(source, stage / name)
        files = [{'path': p.relative_to(stage).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted(stage.rglob('*')) if p.is_file()]
        (stage / 'manifest.json').write_text(json.dumps({'format': 1, 'files': files}, indent=2) + '\n')
        # Preserve timestamps for unchanged resources, so a configure alone
        # does not relink or invalidate a macOS bundle's signature.
        if destination.exists():
            expected = {p.relative_to(stage) for p in stage.rglob('*') if p.is_file()}
            for p in destination.rglob('*'):
                if p.is_symlink(): raise ValueError('Generated controller resources contain a symlink')
                if p.is_file() and p.relative_to(destination) not in expected: p.unlink()
        for p in stage.rglob('*'):
            if p.is_file():
                target = destination / p.relative_to(stage)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.read_bytes() != p.read_bytes(): shutil.copyfile(p, target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, nargs='?')
    parser.add_argument('--verify-output', type=Path, help='Check both built application and VST3 kits')
    args = parser.parse_args()
    if args.verify_output:
        output = args.verify_output
        if (output / 'Release/Krose.app').exists(): output /= 'Release'
        if (output / 'Krose.app').exists():
            paths = [output / 'Krose.app/Contents/Resources/Controllers', output / 'Krose.vst3/Contents/Resources/Controllers']
        else:
            paths = [output / 'Resources/Controllers', output / 'Krose.vst3/Contents/Resources/Controllers']
        for path in paths: verify(path)
        print('PASS app and VST3 built-in controller kits')
    elif args.destination:
        build(args.destination)
    else:
        parser.error('Provide destination or --verify-output')
