#!/usr/bin/env python3
"""Freeze original mono-key and Time-mode glide observations for native tests."""
import hashlib
import json
from pathlib import Path
from layout import ROOT, PRODUCT_ROOT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = ROOT / 'derived/firmware/KROSS2_V124/architecture/stage03'
    keys_path = source / 'mono-keys-check.json'
    glide_path = source / 'voice-reuse-check.json'
    keys, glide = [json.loads(p.read_text()) for p in (keys_path, glide_path)]
    assert keys['passed'] and glide['passed']
    assert not keys['device_access'] and not glide['device_access']
    # Product runtime table and independent observed trajectories are frozen
    # together; ordinary CMake never invokes this exporter.
    table = glide['portamento_coefficients']
    header = '#pragma once\n#include <array>\nnamespace segrand {\n// Original v1.2.4 table at 0x3FD380; evidence fingerprint in PERFORMANCE.md.\ninline constexpr std::array<int,128> kPortamentoCoefficients = {\n'
    header += ''.join('  ' + ', '.join(map(str, table[i:i + 8])) + ',\n' for i in range(0, 128, 8))
    header += '};\n}\n'
    (PRODUCT_ROOT / 'src/instrument/PerformanceData.h').write_text(header)
    output = PRODUCT_ROOT / 'tests/fixtures/performance'
    output.mkdir(parents=True, exist_ok=True)
    lines = []
    for trace in keys['timbre_timelines']:
        if trace['legato']:
            continue  # The list itself is identical; audio reuse is tested separately.
        priority = ['Low', 'High', 'Last'].index(trace['priority'])
        lines.append(f'{priority} reset 0 0 -1 0 0')
        for row in trace['rows']:
            operation, note, velocity = row['input']
            head = row['keys'][0] if row['keys'] else -1
            lines.append(f'{priority} {operation} {note} {velocity} {head} {len(row["keys"])} {row["cached_velocity"]}')
    (output / 'keys.tsv').write_text('\n'.join(lines) + '\n')
    lines = []
    for trace in glide['glide_series']:
        if not trace['scaled']:
            continue
        for row in trace['series']:
            lines.append(f'{trace["speed"]} {trace["interval"]} {row["visit"]} {row["pitch_q16"]} {row["step"]}')
    (output / 'glide.tsv').write_text('\n'.join(lines) + '\n')
    (output / 'coefficients.tsv').write_text('\n'.join(map(str, glide['portamento_coefficients'])) + '\n')
    files = [output / name for name in ['keys.tsv', 'glide.tsv', 'coefficients.tsv']]
    manifest = dict(format_version=1, sources={str(p.relative_to(PRODUCT_ROOT)): digest(p) for p in (keys_path, glide_path)},
                    files=[dict(file=p.name, bytes=p.stat().st_size, sha256=digest(p)) for p in files],
                    scope='Frozen original ARM list/accumulator observations; audio timing and rendering tested separately')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Frozen {len(keys["timbre_timelines"])} source timelines and Time-mode glide visits')


if __name__ == '__main__':
    main()
