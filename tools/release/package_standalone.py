"""Create a standalone ZIP with all runtime resources; optionally test an extracted copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BANKS = {'Factory.samples': 'program-library', 'SEGrand.samples': 'concert-se-grand'}


def verify_resources(resources, root=ROOT):
    for name, folder in BANKS.items():
        manifest = json.loads((root / 'assets' / folder / 'manifest.json').read_text())
        entry = next(item for item in manifest['files'] if item['file'] == name)
        bank = resources / name
        digest = hashlib.sha256()
        with bank.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(block)
        if bank.stat().st_size != entry['bytes'] or digest.hexdigest() != entry['sha256']:
            raise ValueError('Runtime bank mismatch: ' + name)
    if not (resources / 'native-base@2x.png').is_file():
        raise ValueError('Missing native editor resources')


def package(source, output, platform, version, root=ROOT):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid product version')
    windows = platform == 'windows-x64'
    bundle = source / 'Krose.app'
    resources = source / 'Resources' if windows else bundle / 'Contents/Resources'
    verify_resources(resources, root)
    if windows:
        binary = source / 'Krose.exe'
        with binary.open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise ValueError('Invalid Windows executable')
        suffix = 'portable'
    else:
        binary = bundle / 'Contents/MacOS/Krose'
        info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
        if info['CFBundleShortVersionString'] != version:
            raise ValueError('Application version mismatch')
        archs = set(subprocess.check_output(['lipo', '-archs', str(binary)], text=True).split())
        expected = {'arm64', 'x86_64'} if platform == 'macos-universal' else {platform.removeprefix('macos-')}
        if archs != expected:
            raise ValueError('Application architectures mismatch')
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
        suffix = 'app'
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f'Krose-{version}-{platform}-{suffix}.zip'
    readme = ('Krose standalone\n\n'
              + ('Extract this ZIP completely. Run Krose/Krose.exe. Keep Resources beside the EXE.\n'
                 if windows else 'Extract this ZIP and open Krose.app. Samples are included in the application.\n')
              + '\nNo VST3 host or installer is needed. Select audio/MIDI devices in the application settings.\n'
              + 'For a device-free UI check, run the executable with --no-io --screenshot screenshot.png.\n'
              + 'These builds are unsigned/not notarized.\n')
    with tempfile.TemporaryDirectory(prefix="krose-archive-", dir=output) as scratch:
        incoming = Path(scratch) / destination.name
        if windows:
            with zipfile.ZipFile(incoming, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                files = [binary, *sorted(resources.rglob('*')), *sorted(source.glob('*.dll'))]
                for file in files:
                    if file.is_symlink():
                        raise ValueError('Unexpected Windows payload symlink: ' + str(file))
                    if file.is_file():
                        archive.write(file, 'Krose/' + file.relative_to(source).as_posix())
                archive.writestr('Krose/README.txt', readme)
        else:
            # ditto preserves executable modes, symlinks and the ad-hoc signature.
            subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(bundle), str(incoming)], check=True)
            with zipfile.ZipFile(incoming, 'a', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('README.txt', readme)
        incoming.replace(destination)
    print(destination)
    return destination


def smoke(archive, platform, windows_gl_dir=None):
    with tempfile.TemporaryDirectory(prefix='krose standalone ') as folder:
        root = Path(folder)
        if platform == 'windows-x64':
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(root)
            executable = root / 'Krose/Krose.exe'
        else:
            subprocess.run(['ditto', '-x', '-k', str(archive), str(root)], check=True)
            bundle = root / 'Krose.app'
            subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
            executable = bundle / 'Contents/MacOS/Krose'
        env = dict(os.environ, KROSE_SAMPLE_DIRECTORY=str(root / 'no-shared-samples'),
                   KROSE_MIDI_MAP_FILE=str(root / 'midi.json'), KROSE_FAVORITES_FILE=str(root / 'favorites.json'))
        if windows_gl_dir is not None:
            if platform != 'windows-x64' or not (windows_gl_dir / 'opengl32.dll').is_file():
                raise ValueError('Expected Windows OpenGL test libraries')
            for library in windows_gl_dir.glob('*.dll'):
                shutil.copyfile(library, executable.parent / library.name)
            env['GALLIUM_DRIVER'] = 'llvmpipe'
        # Relative screenshot name also works with the pinned Windows argument parser.
        subprocess.run([str(executable), '--no-io', '--screenshot', 'screenshot.png'],
                       cwd=root, env=env, check=True, timeout=60)
        image = (root / 'screenshot.png').read_bytes()
        if image[:8] != b'\x89PNG\r\n\x1a\n' or len(image) < 24:
            raise ValueError('Missing portable UI screenshot')
        width, height = struct.unpack('>II', image[16:24])
        if width < 1472 or height < 648:
            raise ValueError(f'Incomplete portable UI screenshot: {width}x{height}')
        print(f'PASS extracted standalone: {width}x{height}, device-free launch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path('dist'))
    parser.add_argument('--version', required=True)
    parser.add_argument('--platform', required=True, choices=['windows-x64', 'macos-universal', 'macos-arm64', 'macos-x86_64'])
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--windows-gl-dir', type=Path, help='Software OpenGL DLLs for the extracted smoke-test copy')
    args = parser.parse_args()
    archive = package(args.input, args.output, args.platform, args.version)
    if args.smoke:
        smoke(archive, args.platform, args.windows_gl_dir)


if __name__ == '__main__':
    main()
