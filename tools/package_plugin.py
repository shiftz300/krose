#!/usr/bin/env python3
"""Package the local macOS builds and record their exact assets/source hashes."""
import hashlib
import json
import platform
import plistlib
import re
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    build = ROOT / 'build/plugin'
    output = ROOT / 'output/Krose'
    output.mkdir(parents=True, exist_ok=True)
    checks = [
        ('plugin-ctest.log', ['ctest', '--test-dir', str(build), '--output-on-failure']),
        ('engine-sanitizer.log', ['ctest', '--test-dir', str(ROOT / 'build/sanitize'), '--output-on-failure'])]
    for log, command in checks:
        with (build / log).open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
    bundles = []
    for name in ('Krose.vst3', 'Krose.app'):
        source = build / 'out' / name
        subprocess.run(['codesign', '--force', '--sign', '-', str(source)], check=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(source)], check=True)
        destination = output / name
        if destination.exists():
            info = plistlib.loads((destination / 'Contents/Info.plist').read_bytes())
            if not info['CFBundleIdentifier'].startswith('dev.LocalInstruments.'):
                raise RuntimeError('Refusing to replace an unknown bundle')
            shutil.rmtree(destination)
        shutil.copytree(source, destination, symlinks=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(destination)], check=True)
        binary = destination / 'Contents/MacOS/Krose'
        bundles.append({'file': name, 'binary_sha256': digest(binary),
                        'architecture': subprocess.check_output(['lipo', '-archs', str(binary)], text=True).strip()})
    with (build / 'official-validator.log').open('w') as stream:
        subprocess.run([str(build / 'sdk-validator/validator'), str(output / 'Krose.vst3')],
                       stdout=stream, stderr=subprocess.STDOUT, check=True)
    result = re.search(r'Result: (\d+) tests passed, (\d+) tests failed', (build / 'official-validator.log').read_text())
    assert result and int(result[1]) > 0 and int(result[2]) == 0
    sources = [ROOT / 'CMakeLists.txt', *sorted((ROOT / 'src').rglob('*')),
               *sorted((ROOT / 'cmake').rglob('*'))]
    manifest = {'name': 'Krose', 'version': '0.1.0', 'platform': platform.platform(),
                'bundles': bundles, 'assets': json.loads((build / 'generated/assets.json').read_text()),
                'dependencies': json.loads((ROOT / 'cmake/dependencies.json').read_text()),
                'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sources if p.is_file()},
                'verification': {'vst3_official_validator': result[0],
                                 'ctest': ['piano-engine', 'vst3-host'], 'engine_asan_ubsan': 'passed',
                                 'ableton_manual_acceptance': 'pending'},
                'benchmark': json.loads((ROOT / 'build/piano-benchmark.json').read_text())}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copy(ROOT / 'docs/PLUGIN.md', output / 'README.md')
    print('Packaged, signed and verified: output/Krose/{Krose.vst3,Krose.app}')


if __name__ == '__main__':
    main()
