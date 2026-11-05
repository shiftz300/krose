"""Precompile the layered Mac icon once; ordinary builds only copy the result.

Requires Apple's actool from Xcode 26+. The output is architecture-independent
and can be checked in, so developer builds need only Command Line Tools.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'src/plugin/resources/Krose.icon'
OUTPUT = ROOT / 'src/plugin/resources/macos-icon'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_digest(source):
    files = sorted(p for p in source.rglob('*') if p.is_file())
    inventory = ''.join(p.relative_to(source).as_posix() + ':' + digest(p) + '\n' for p in files)
    return hashlib.sha256(inventory.encode()).hexdigest()


def verify(source, output):
    manifest = json.loads((output / 'manifest.json').read_text())
    if manifest.get('format') != 1 or manifest.get('icon_name') != 'Krose':
        raise ValueError('Unsupported compiled icon manifest')
    if manifest['source_sha256'] != source_digest(source):
        raise ValueError('Layered icon changed: regenerate the precompiled asset')
    if manifest['assets_sha256'] != digest(output / 'Assets.car'):
        raise ValueError('Compiled icon asset checksum mismatch')


def compile_icon(source, output, actool):
    source = source.resolve()
    fingerprint = source_digest(source)
    with tempfile.TemporaryDirectory(prefix='krose-icon-') as temporary:
        stage = Path(temporary)
        partial = stage / 'Info.plist'
        subprocess.run([actool, str(source), '--compile', str(stage),
                        '--platform', 'macosx', '--target-device', 'mac',
                        '--minimum-deployment-target', '13.0', '--app-icon', 'Krose',
                        '--include-all-app-icons', '--standalone-icon-behavior', 'all',
                        '--output-partial-info-plist', str(partial)], check=True)
        info = plistlib.loads(partial.read_bytes())
        if info.get('CFBundleIconName') != 'Krose' or not (stage / 'Assets.car').is_file():
            raise ValueError('actool did not produce a named layered icon catalog')
        # Save the compiler's catalog inventory for review, outside product resources.
        inventory = subprocess.check_output(['assetutil', '--info', str(stage / 'Assets.car')])
        if 'Krose' not in inventory.decode():
            raise ValueError('Compiled catalog is missing the Krose icon')
        if source_digest(source) != fingerprint:
            raise ValueError('Icon source changed during compilation')
        version = subprocess.check_output([actool, '--version'], text=True).strip()
        manifest = {'format': 1, 'icon_name': 'Krose', 'source_sha256': fingerprint,
                    'assets_sha256': digest(stage / 'Assets.car'), 'compiler': version}
        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stage / 'Assets.car', output / 'Assets.car')
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        verify(source, output)
        print(f'Precompiled icon: {output} ({(output / "Assets.car").stat().st_size} bytes)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--actool', help='Explicit path to Apple actool')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify(args.source, args.output)
    else:
        actool = args.actool or subprocess.check_output(['xcrun', '--find', 'actool'], text=True).strip()
        compile_icon(args.source, args.output, actool)


if __name__ == '__main__':
    main()
