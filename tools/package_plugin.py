#!/usr/bin/env python3
"""Package the local macOS builds and record their exact assets/source hashes."""
import argparse
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests',action='store_true',help='Use previously completed CTest logs; do not rerun audio renders')
    args=parser.parse_args()
    build = ROOT / 'build/plugin'
    output = ROOT / 'dist/portable'
    output.mkdir(parents=True, exist_ok=True)
    checks = [
        ('plugin-ctest.log', ['ctest', '--test-dir', str(build), '--output-on-failure']),
        ('engine-sanitizer.log', ['ctest', '--test-dir', str(ROOT / 'build/sanitize'), '--output-on-failure'])]
    for log, command in ([] if args.skip_tests else checks):
        with (build / log).open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
    for log,_ in checks:
        text=(build/log).read_text()
        if '100% tests passed' not in text or re.search(r'[1-9]\d* tests failed',text):
            raise RuntimeError('A successful current test log is required: '+log)
    ui_log = build / 'native-ui-test.log'
    if not ui_log.exists() or 'PASS native UI:' not in ui_log.read_text():
        raise RuntimeError('Run the native Cocoa editor test before packaging')
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
    sources = [ROOT / 'CMakeLists.txt', ROOT / 'CMakePresets.json', *sorted((ROOT / 'src').rglob('*')),
               *sorted((ROOT / 'cmake').rglob('*'))]
    manifest = {'name': 'Krose', 'version': '0.3.2', 'platform': platform.platform(),
                'bundles': bundles, 'assets': json.loads((build / 'generated/assets.json').read_text()),
                'program_library':json.loads((ROOT/'assets/program-library/manifest.json').read_text()),
                'test_logs':{name:digest(build/name) for name in [*(name for name,_ in checks), 'native-ui-test.log']},
                'tests_run_by_packager':not args.skip_tests,
                'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'source_worktree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
                'editor':{'runtime':'iPlug2 IGraphics / NanoVG / Metal',
                          'logical_size':[1472,648],
                          'resource_manifest_sha256':digest(ROOT/'src/plugin/editor/native/assets/files.json')},
                'dependencies': json.loads((ROOT / 'cmake/dependencies.json').read_text()),
                'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sources if p.is_file()},
                'verification': {'vst3_official_validator': result[0],
                                 'native_cocoa_ui':'passed',
                                 'ctest': ['program-engine','piano-engine','native-voice','native-filter','performance','arpeggiator','sample-loading','sample-codec','midi-queue','image-memory','fx-motion','effects','vst3-host'], 'engine_asan_ubsan': 'passed',
                                 'ableton_manual_acceptance': 'pending'}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copy(ROOT / 'docs/PLUGIN.md', output / 'README.md')
    for name in ('LICENSE', 'NOTICE'):
        shutil.copy(ROOT / name, output / name)
    shutil.copy(ROOT / 'docs/LICENSING.md', output / 'LICENSING.md')
    shutil.copytree(ROOT / 'licenses', output / 'licenses', dirs_exist_ok=True)
    for name in ('ARCHITECTURE.md', 'PERFORMANCE.md', 'ARPEGGIATOR.md',
                 'NATIVE_UI.md', 'SAMPLES.md', 'PROJECT_LAYOUT.md', 'RELEASE.md'):
        shutil.copy(ROOT / 'docs' / name, output / name)
    print('Packaged, signed and verified: dist/portable/{Krose.vst3,Krose.app}')


if __name__ == '__main__':
    main()
