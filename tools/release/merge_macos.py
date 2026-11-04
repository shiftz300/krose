"""Merge separately trained native macOS bundles into a Universal release."""
import argparse
import hashlib
import plistlib
from pathlib import Path
import shutil
import subprocess
import tempfile


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def resources(bundle):
    """Both native builds must carry exactly the same product resources."""
    result = {}
    for file in bundle.rglob('*'):
        relative = file.relative_to(bundle)
        if '_CodeSignature' in relative.parts or relative in (
                Path('Contents/MacOS/Krose'), Path('Contents/Info.plist')):
            continue
        if file.is_file():
            result[str(relative)] = hashlib.sha256(file.read_bytes()).hexdigest()
    return result


def validate_pair(arm, intel):
    if resources(arm) != resources(intel):
        raise ValueError('Native bundle resources differ: ' + arm.name)
    infos = [plistlib.loads((bundle/'Contents/Info.plist').read_bytes()) for bundle in (arm, intel)]
    for key in ('CFBundleIdentifier', 'CFBundleExecutable', 'CFBundleVersion', 'CFBundleShortVersionString'):
        if infos[0].get(key) != infos[1].get(key):
            raise ValueError('Native bundle metadata differs: ' + key)
    for bundle, arch in [(arm, 'arm64'), (intel, 'x86_64')]:
        if output('lipo', '-archs', str(bundle/'Contents/MacOS/Krose')).split() != [arch]:
            raise ValueError('Expected native ' + arch + ' bundle: ' + str(bundle))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm64', required=True, type=Path)
    parser.add_argument('--x86-64', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    pairs = [(args.arm64/name, args.x86_64/name) for name in ('Krose.app', 'Krose.vst3')]
    for arm, intel in pairs:
        validate_pair(arm, intel)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='krose-universal-', dir=args.output.parent) as temporary:
        for arm, intel in pairs:
            destination = Path(temporary)/arm.name
            shutil.copytree(arm, destination, symlinks=True)
            shutil.rmtree(destination/'Contents/_CodeSignature', ignore_errors=True)
            binary = destination/'Contents/MacOS/Krose'
            subprocess.run(['lipo', '-create', str(arm/'Contents/MacOS/Krose'),
                            str(intel/'Contents/MacOS/Krose'), '-output', str(binary)], check=True)
            for arch in ('arm64', 'x86_64'):
                subprocess.run(['lipo', str(binary), '-verify_arch', arch], check=True)
            subprocess.run(['codesign', '--force', '--sign', '-', str(destination)], check=True)
            subprocess.run(['codesign', '--verify', '--deep', '--strict', str(destination)], check=True)
        args.output.mkdir(parents=True, exist_ok=True)
        for arm, _ in pairs:
            destination = args.output/arm.name
            if destination.exists():
                shutil.rmtree(destination)
            shutil.move(str(Path(temporary)/arm.name), destination)
    print('Merged trained arm64/x86_64 bundles: ' + str(args.output))


if __name__ == '__main__':
    main()
