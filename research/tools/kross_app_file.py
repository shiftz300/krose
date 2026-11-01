#!/usr/bin/env python3
"""Explicit file-only installation/reversion of pinned research applications.

check and invocations without --write are read-only. Never opens a raw disk,
mounts, formats, installs a bootloader or changes any file other than the existing
6MiB KROSSAPP.BIN. Hardware operation remains experimental and unverified.
"""
import argparse
import datetime
import hashlib
import json
import os
import plistlib
import stat
import subprocess
from pathlib import Path

from build_probe_injection import IMAGE_BYTES, OUT, SLOT, TABLE, sum16
from program_firmware import BASE, FW_SHA, ROOT
import struct


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bundle(revision=1):
    if revision not in (1, 2, 3): raise ValueError('Unsupported research revision')
    directory = OUT if revision == 1 else OUT.with_name('stage-a-v2' if revision == 2 else 'stage-b')
    original = (directory/'restore/KROSSAPP.BIN').read_bytes()
    candidate = (directory/'candidate/KROSSAPP.BIN').read_bytes()
    code = (directory/'probe-arm.text.bin').read_bytes()
    manifest = json.loads((directory/'manifest.json').read_text())
    verified = json.loads((directory/'verification-arm.json').read_text())
    if len(original) != IMAGE_BYTES or sha(original) != FW_SHA:
        raise ValueError('Restore copy does not match the pinned official v1.2.4 application')
    expected = bytearray(original)
    if not 0 < len(code) <= 4096 or original[SLOT:SLOT+len(code)] != b'\xff'*len(code):
        raise ValueError('Bad injection slot/code size')
    struct.pack_into('<I', expected, TABLE, BASE+SLOT)
    expected[SLOT:SLOT+len(code)] = code
    struct.pack_into('<H', expected, len(expected)-2, sum16(expected))
    digest = sha(candidate)
    if candidate != expected or manifest['candidate_sha256'] != digest or verified['candidate_sha256'] != digest:
        raise ValueError('Candidate differs from the offline-verified research bundle')
    if manifest['code_sha256'] != sha(code) or manifest['TG_reading'] is not (revision == 3):
        raise ValueError('Unexpected bundle capability/profile')
    return original, candidate


def mounted_target(name):
    volume = Path(name).expanduser().resolve(strict=True)
    if volume.parent != Path('/Volumes') or not os.path.ismount(volume):
        raise ValueError('Use the exact mounted USB volume root under /Volumes, not a device node/directory')
    info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(volume)]))
    if info.get('MountPoint') != str(volume) or info.get('Internal') is not False or info.get('BusProtocol') != 'USB':
        raise ValueError('diskutil did not identify this exact mount as an external USB volume')
    if info.get('FilesystemType') != 'msdos':
        raise ValueError('Expected the backed-up MS-DOS/FAT system volume')
    for filename in ('SYSINFO.BIN', 'HWINFO.BIN', 'GLOBAL.BIN', 'KROSSAPP.BIN'):
        item = volume/filename
        if item.is_symlink() or not item.is_file():
            raise ValueError(f'Missing expected regular file {filename}; no filesystem repair attempted')
    return volume/'KROSSAPP.BIN', {k: info.get(k) for k in
            ('MountPoint', 'DeviceNode', 'VolumeName', 'FilesystemType', 'BusProtocol', 'Internal')}


def rewrite_existing(target, expected_before, replacement):
    """No creation/truncation/rename; recheck the open file before touching it."""
    flags = os.O_RDWR | os.O_NOFOLLOW
    descriptor = os.open(target, flags)
    with os.fdopen(descriptor, 'r+b', buffering=0) as file:
        status = os.fstat(file.fileno())
        if not stat.S_ISREG(status.st_mode) or status.st_size != IMAGE_BYTES:
            raise ValueError('Existing application is not a regular 6MiB file')
        before = file.read()
        if before != expected_before:
            raise ValueError('Application changed since the preflight check; nothing written')
        if len(replacement) != IMAGE_BYTES:
            raise ValueError('Replacement length mismatch')
        file.seek(0)
        pending = memoryview(replacement)
        while pending:
            count = file.write(pending[:65536])
            if not count: raise IOError('Short application write')
            pending = pending[count:]
        file.flush()
        os.fsync(file.fileno())
        file.seek(0)
        if file.read() != replacement:
            raise IOError('Read-back mismatch; remain in USB mode and restore the original application')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'install', 'restore'))
    parser.add_argument('--volume', required=True, help='Exact mounted KROSS system volume root')
    parser.add_argument('--revision', type=int, choices=(1,2,3), default=1, help='1/2: identity-only; 3: bounded TG reader. Explicit selection required')
    parser.add_argument('--write', action='store_true', help='Perform the explicitly selected file replacement')
    parser.add_argument('--allow-damaged-app', action='store_true', help='Restore only: allow unknown checksum in a same-size existing application')
    args = parser.parse_args()
    try:
        if args.action == 'check' and args.write: raise ValueError('check never writes; omit --write')
        if args.allow_damaged_app and args.action != 'restore': raise ValueError('--allow-damaged-app is restore-only')
        original, candidate = bundle(args.revision)
        previous = [bundle(i)[1] for i in range(1,args.revision)]
        target, info = mounted_target(args.volume)
        if target.stat().st_size != IMAGE_BYTES: raise ValueError('Existing application size differs from 6MiB; stop for inspection')
        current = target.read_bytes()
        kind = ('official-1.2.4' if current == original else
                ('stage-a-candidate' if args.revision == 1 else 'stage-a-v2-candidate' if args.revision == 2 else 'stage-b-candidate') if current == candidate else
                'previous-verified-candidate' if current in previous else 'unknown-or-damaged')
        plan = dict(action=args.action, target=str(target), device=info, current_kind=kind,
                    current_sha256=sha(current), original_sha256=FW_SHA,
                    candidate_sha256=sha(candidate), write_requested=args.write,
                    candidate_revision=args.revision, TG_reading_enabled=args.revision==3,
                    hardware_tested=False, recovery_guaranteed=False)
        print(json.dumps(plan, indent=2), flush=True)
        if args.action == 'check': return
        replacement = candidate if args.action == 'install' else original
        if current == replacement:
            print('Already matches requested application; no write performed.'); return
        if args.action == 'install' and current != original and current not in previous:
            raise ValueError('Installation requires exact official 1.2.4 or a verified earlier candidate')
        if args.action == 'restore' and current != candidate and current not in previous and not args.allow_damaged_app:
            raise ValueError('Unknown application: inspect first, or explicitly restore with --allow-damaged-app')
        if not args.write:
            print('PLAN ONLY; omit nothing except add --write when intentionally performing this experiment.'); return
        # Local pre-write copy/log. Never creates a second file on the keyboard.
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        log_dir = OUT.parent/'operations'/stamp
        log_dir.mkdir(parents=True, exist_ok=False)
        (log_dir/'before.KROSSAPP.BIN').write_bytes(current)
        plan['status'] = 'started'
        log = log_dir/'operation.json'
        log.write_text(json.dumps(plan, indent=2)+'\n')
        try:
            if not os.path.ismount(target.parent): raise ValueError('USB volume was unmounted')
            rewrite_existing(target, current, replacement)
        except Exception as error:
            plan.update(status='failed', error=str(error))
            log.write_text(json.dumps(plan, indent=2)+'\n')
            raise
        plan.update(status='readback-verified', written_sha256=sha(replacement))
        log.write_text(json.dumps(plan, indent=2)+'\n')
        print(f'Application file read-back verified. Log: {log}')
        print('Eject the USB volume successfully before switching power off. Startup/recovery is not proven by this file check.')
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'STOP: {error}\n')


if __name__ == '__main__':
    main()
