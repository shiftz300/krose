#!/usr/bin/env python3
"""Host-only bundle/file-writer checks on temporary ordinary files, never a device."""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from build_probe_injection import OUT
from kross_app_file import bundle, mounted_target, rewrite_existing
from program_firmware import ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    original, candidate = bundle()
    rejected = []
    with tempfile.TemporaryDirectory(prefix='probe-file-test-', dir=ROOT/'build') as temp:
        target = Path(temp)/'KROSSAPP.BIN'
        target.write_bytes(original)
        rewrite_existing(target, original, candidate)
        assert target.read_bytes() == candidate
        for name, before, after in [('concurrent_change', original, original),
                                    ('wrong_replacement_length', candidate, original[:-1])]:
            try: rewrite_existing(target, before, after)
            except ValueError: rejected.append(name)
            else: raise AssertionError(name)
            assert target.read_bytes() == candidate
        rewrite_existing(target, candidate, original)
        assert target.read_bytes() == original
        target.write_bytes(original[:-1])
        try: rewrite_existing(target, original[:-1], candidate)
        except ValueError: rejected.append('wrong_existing_size')
        else: raise AssertionError('wrong_existing_size')
        assert target.read_bytes() == original[:-1]
        link = Path(temp)/'symlink.BIN'
        link.symlink_to(target)
        try: rewrite_existing(link, original[:-1], candidate)
        except OSError: rejected.append('symlink_target')
        else: raise AssertionError('symlink_target')
        for name in (temp, '/dev/disk4', '/Users/shiftz/dev/kross2'):
            try: mounted_target(name)
            except (ValueError, FileNotFoundError): rejected.append('non_volume:'+name.replace(temp, 'temporary-folder'))
            else: raise AssertionError(name)
    client = ROOT/'build/kross-probe-midi'
    subprocess.run(['clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-Wno-deprecated-declarations', str(ROOT/'tools/kross_probe_midi.c'),
                    '-framework', 'CoreMIDI', '-framework', 'CoreFoundation',
                    '-o', str(client)], check=True)
    result = subprocess.check_output([str(client), 'self-test'], text=True).strip()
    assert result.startswith('PASS:')
    raw = ROOT/'research/libraries/KROSS2_local_20261101-022845/internal-storage.img'
    assert raw.stat().st_size == 131072000
    assert sha(raw) == '6cd9b98ca73626535106418bef26c12fa2ae361b92376ab73e958e23ae30c378'
    assert raw.stat().st_mode & 0o777 == 0o400
    baseline = json.loads((ROOT/'build/krose-rename-check.json').read_text())['source_sha256']
    for name, expected in baseline.items(): assert sha(ROOT/name) == expected, name
    assets = json.loads((ROOT/'assets/concert-se-grand/manifest.json').read_text())['files']
    for entry in assets:
        path = ROOT/'assets/concert-se-grand'/entry['file']
        assert path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], entry['file']
    sources = ['tools/kross_probe_injection.S', 'tools/build_probe_injection.py',
               'tools/verify_probe_injection.py', 'tools/kross_probe_midi.c',
               'tools/kross_app_file.py', 'tools/verify_probe_bundle.py',
               'docs/FIRMWARE_INJECTION_STAGE_A.md']
    report = dict(scope='Host temporary files only; no volume installation or MIDI transmission',
                  candidate_sha256=hashlib.sha256(candidate).hexdigest(),
                  temporary_file_install_and_restore_verified=True, rejected_cases=rejected,
                  client_self_test=result, client_binary_sha256=sha(client),
                  original_backup_hash_and_readonly_mode_unchanged=True,
                  product_source_hashes_unchanged=len(baseline), product_assets_unchanged=len(assets),
                  hardware_tested=False, device_writes_executed=0, MIDI_requests_sent=0,
                  source_sha256={name: sha(ROOT/name) for name in sources})
    (OUT/'verification-host.json').write_text(json.dumps(report, indent=2)+'\n')
    (ROOT/'build/firmware-injection-stage-a-check.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
