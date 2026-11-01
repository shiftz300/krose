#!/usr/bin/env python3
"""Read-only source audit: waveform sharing and lossless storage candidates.

No product assets, plugin, or accepted WAV is changed. FLAC candidates live in
build/; report records PCM round trips and native decoder identity separately.
"""
from layout import PRODUCT_ROOT
import collections
import concurrent.futures
import csv
import hashlib
import json
import shutil
import subprocess
import wave
from pathlib import Path

from decode_korg_pcm import Decoder, load_lut

from layout import ROOT
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder = ROOT / 'research/derived/verification/resource-layout'
    folder.mkdir(parents=True, exist_ok=True)
    cache = ROOT / 'build/resource-layout/flac'
    cache.mkdir(parents=True, exist_ok=True)
    flac = shutil.which('flac')
    if not flac:
        raise RuntimeError('This optional research measurement requires the flac CLI')
    version = subprocess.check_output([flac, '--version'], text=True).strip()
    source = ROOT / 'research/derived/firmware/KROSS2_V124/sounds/factory/programs.json'
    programs = [p for p in json.loads(source.read_text())['programs'] if p['kind'] == 'factory_A_F']
    assert len(programs) == 768
    uses = collections.defaultdict(set)
    references = 0
    for p in programs:
        if p['oscillator_mode'] == 'd':
            continue
        for osc in p['oscillators']:
            if not osc['active']:
                continue
            for slot in osc['slots']:
                for index, name in zip(slot['ROM_multisample_indices'], slot['ROM_multisample_names']):
                    uses[index, name].add(p['bank_program'])
                    references += 1
    with (folder / 'factory-wave-sharing.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['ROM_index', 'name', 'referencing_program_count', 'programs'])
        writer.writerows((i, name, len(ids), ' '.join(sorted(ids))) for (i, name), ids in sorted(uses.items()))

    report_path = ROOT / 'output/Concert_SE_Grand_WAV/decode_report.json'
    records = json.loads(report_path.read_text())['samples']
    native_path = ROOT / 'output/kep-analysis/samples.json'
    native = {r['id']: r for r in json.loads(native_path.read_text())}
    decoder = Decoder(load_lut(), ROOT / 'build/resource-layout/decoder')
    rows = []
    for r in records:
        wav = ROOT / 'output/Concert_SE_Grand_WAV' / r['file']
        assert sha(wav) == r['sha256'], wav
        with wave.open(str(wav), 'rb') as stream:
            assert stream.getsampwidth() == 3 and stream.getnchannels() == 2
            raw = stream.readframes(stream.getnframes())
        reconstructed = bytearray(len(raw))
        native_bytes = 0
        checkpoints = 0
        for channel, (native_id, coefficients) in enumerate(zip(r['native_ids'], r['coefficients_q14'])):
            desc = native[native_id]
            path = ROOT / 'output/kep-analysis' / desc['native_file']
            assert sha(path) == desc['sha256']
            encoded = path.read_bytes()
            assert len(encoded) == r['frames']
            audio, _ = decoder.decode(encoded, *coefficients)
            # Retain precisely the accepted PCM24 output, not a new quantizer.
            decoded = audio.tobytes()
            for byte in range(3):
                reconstructed[channel * 3 + byte::6] = decoded[byte + 1::4]
            native_bytes += len(encoded)
            checkpoints += (len(encoded) + 4095) // 4096
        assert reconstructed == raw, wav
        rows.append(dict(file=r['file'], wav_bytes=wav.stat().st_size, pcm24_bytes=len(raw),
                         native_bytes=native_bytes, checkpoint_bytes_estimate=checkpoints * 8,
                         pcm24_sha256=hashlib.sha256(raw).hexdigest(), native_decode_matches=True))

    def measure(row):
        wav = ROOT / 'output/Concert_SE_Grand_WAV' / row['file']
        compressed = cache / (row['file'].replace('/', '_') + '.flac')
        encoded = subprocess.run([flac, '-5', '--silent', '--force', '--no-padding', '--no-seektable',
                                  '--output-name=' + str(compressed), str(wav)], capture_output=True, check=True)
        decoded = subprocess.check_output([flac, '--decode', '--stdout', '--silent', '--force-raw-format',
                                           '--endian=little', '--sign=signed', str(compressed)])
        assert hashlib.sha256(decoded).hexdigest() == row['pcm24_sha256']
        return dict(row, flac_bytes=compressed.stat().st_size, flac_roundtrip_matches=True,
                    encoder_notice=encoded.stderr.decode().strip())

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        rows = list(executor.map(measure, rows))
    totals = {key: sum(r[key] for r in rows) for key in
              ('wav_bytes', 'pcm24_bytes', 'native_bytes', 'checkpoint_bytes_estimate', 'flac_bytes')}
    result = dict(scope='Storage experiment only; no plugin reader or compressed runtime asset implemented',
                  source_sha256={str(p.relative_to(PRODUCT_ROOT)): sha(p) for p in (source, report_path, native_path, Path(__file__))},
                  factory=dict(programs=len(programs), raw_program_bytes=768 * 2140,
                               non_drum_programs=sum(p['oscillator_mode'] != 'd' for p in programs),
                               active_slot_mono_ROM_references=references, unique_referenced_ROM_metadata=len(uses),
                               counts_scope='Enabled slots in active oscillators; stereo expanded to L/R; no drum mapping, no byte-size inference',
                               top_shared=[dict(index=i, name=n, program_count=len(ids)) for (i,n),ids in
                                           sorted(uses.items(), key=lambda pair: (-len(pair[1]),pair[0]))[:15]]),
                  concert=dict(stereo_samples=len(rows), totals=totals,
                               current_runtime_pack_bytes=(ROOT / 'assets/concert-se-grand/SEGrand.samples').stat().st_size,
                               flac_version=version, flac_options=['-5','--no-padding','--no-seektable'],
                               native_status='Existing predictive codes plus coefficients/LUT regenerate accepted PCM24 exactly for all 84 WAVs; no additional loss, not a claim about pre-encoding original PCM',
                               checkpoint_status='Size estimate only: two int32 predictor histories per 4096 mono codes; seek-state behavior not implemented/tested',
                               rows=rows))
    output = folder / 'resource-budget.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(factory=result['factory'], concert_totals=totals, samples_verified=len(rows)), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
