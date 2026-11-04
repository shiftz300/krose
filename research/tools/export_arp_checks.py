#!/usr/bin/env python3
"""Freeze original built-in generator observations for the native arpeggiator."""
import hashlib
import json
from layout import ROOT, PRODUCT_ROOT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = ROOT / 'derived/firmware/KROSS2_V124/architecture/stage04/arpeggio-sync-check.json'
    data = json.loads(source.read_text())
    assert data['passed'] and not data['device_access']
    destination = PRODUCT_ROOT / 'tests/fixtures/arpeggiator'
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in data['presets']:
        fields = [row['kind'], row['octaves'], row['sort'], len(row['keys']), len(row['notes']), *row['keys']]
        for note, velocity in zip(row['notes'], row['velocities']):
            fields.extend([note, velocity])
        rows.append(' '.join(map(str, fields)))
    (destination / 'presets.tsv').write_text('\n'.join(rows) + '\n')
    rows = [f'{trace["kind"]} {event["tick"]} {int(event["on"])} {event["note"]} {event["velocity"]}'
            for trace in data['continuous'] for event in trace['events']]
    (destination / 'events.tsv').write_text('\n'.join(rows) + '\n')
    files = [destination / name for name in ['presets.tsv', 'events.tsv']]
    manifest = dict(format_version=1, source=str(source.relative_to(PRODUCT_ROOT)), source_sha256=digest(source),
                    files=[dict(file=p.name, bytes=p.stat().st_size, sha256=digest(p)) for p in files],
                    scope='Original five built-in generators; 200 cases, 9600 notes and five continuous clock traces')
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(manifest['scope'])


if __name__ == '__main__':
    main()
