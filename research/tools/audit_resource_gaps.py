#!/usr/bin/env python3
"""Bounded, read-only audit of missing local banks and verified kit imports."""
import hashlib
import json
from pathlib import Path
from layout import PRODUCT_ROOT, ROOT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    evidence = ROOT / 'derived/firmware/KROSS2_V124/architecture/stage04/resource-import-check.json'
    check = json.loads(evidence.read_text())
    assert check['passed'] and not check['smoke_only'] and not check['device_access']
    assert check['tool_sha256'] == digest(ROOT / 'tools/firmware_resource_import.py')
    assert check['helper_sha256'] == digest(ROOT / 'tools/program_firmware.py')
    for name, expected in check['additional_helpers'].items():
        assert digest(ROOT / 'tools' / name) == expected
    for source in check['inputs']:
        assert digest(PRODUCT_ROOT / source['path']) == source['sha256']

    banks = []
    for path in sorted((ROOT / 'derived/kep').glob('EXPCM*/library.json')):
        library = json.loads(path.read_text())
        assert digest(ROOT / library['source']) == library['source_sha256']
        assert digest(ROOT / library['decoded']) == library['decoded_sha256']
        banks.append(dict(library=library['id'], logical_bank=library['id'] + 1,
                          source=library['source'], sha256=library['source_sha256']))
    assert [bank['logical_bank'] for bank in banks] == [2, 3, 5]
    links = [row for row in check['links'] if row['destination_start'] == 42]
    assert [row['selected_kit_name'] for row in links] == [
        'Nu DISCO Kit', 'Nu DISCO Kit', 'Electrik Kit', 'Bang Kit']
    bundle = json.loads((PRODUCT_ROOT / 'assets/program-library/manifest.json').read_text())
    assert len(bundle['missing_layers']) == 4
    assert {row['bank'] for row in bundle['missing_layers']} == {6}
    packed = sorted(str(p.relative_to(PRODUCT_ROOT)) for folder in ['libraries', 'EXPCM001']
                    for p in (ROOT / folder).rglob('*.KEP'))
    result = dict(passed=True, device_access=False, importer_counts=check['counts'],
                  importer_evidence_sha256=digest(evidence), available_banks=banks,
                  local_KEP_files=packed, confirmed_kit_links=links,
                  remaining_layers=bundle['missing_layers'],
                  scope='Existing local sources and original section-import observations only; '
                        'bank 6 PCM not available, no replacement samples inferred.')
    output = ROOT / 'derived/catalog/resource-gap-audit.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=True, importer_cases=check['counts']['section_cases'],
                          confirmed_kit_links=len(links), missing_layers=4), indent=2))


if __name__ == '__main__':
    main()
