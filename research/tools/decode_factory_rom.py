#!/usr/bin/env python3
"""Decode the immutable, acquired factory TG ROM. No MIDI or device access.

Unnormalized PCM24 exports preserve source frames, including the candidate end
guard. Native addressing, descriptor bytes and integer playback rates are kept
in a separate manifest; WAV integer rates cannot represent the fractional clock.
"""
from layout import PRODUCT_ROOT
import argparse
import array
import collections
import hashlib
import json
import math
import struct
import wave
from pathlib import Path

import numpy as np

from decode_korg_pcm import Decoder, decode_reference, load_lut, write_wav
from program_firmware import Firmware, ROOT, FW_SHA

ROM = ROOT / 'research/derived/acquisitions/KROSS2_ROM_stage_b_20261031T215150691039Z/complete/TG-ROM-candidate.img'
ROM_SHA = 'c9d4c9b4dd0f915b45a553e6b66d2cab7e51b80f4b2189fb6db4d91b1ccc94a5'
CATALOG = ROOT / 'research/derived/firmware/KROSS2_V124/rom/catalog'
DERIVED = ROOT / 'research/derived/firmware/KROSS2_V124/rom/decoding'
OUTPUT = ROOT / 'output/Factory_ROM_WAV'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def load(name):
    return json.loads((CATALOG / (name + '.json')).read_text())


def source_bytes(rom, descriptor):
    return rom[descriptor['byte_start_candidate']:descriptor['byte_end_exclusive_candidate']]


def decode(rom, descriptor, decoder):
    raw = source_bytes(rom, descriptor)
    if descriptor['flags'] & 1:
        audio, counts = decoder.decode(raw, *descriptor['coefficients_q14'])
        return np.frombuffer(audio, dtype='<i4'), counts
    assert descriptor['coefficients_q14'] == [0, 0]
    return np.frombuffer(raw, dtype='<i2').astype(np.int32) * 65536, [0, 0]


def fine_correction(value):
    """Original 0x1ff764: signed truncation of region fine units *1311/1024."""
    return (abs(value) * 1311 >> 10) * (-1 if value < 0 else 1)


def region_increment(fw, descriptor, region, note):
    raw = bytes.fromhex(region['raw_hex'])
    fine = struct.unpack_from('<h', raw, 6)[0]
    # Original pitch setup stores the signed 16-bit negative base correction.
    state = (region['root_key_candidate'] * 256 - fine_correction(fine)
             - descriptor['pitch_field'] * 2)
    state = ((state + 32768) & 65535) - 32768
    if raw[5] & 1:
        state += (note - region['root_key_candidate']) * 256
    exponent = note * 256 - state
    exponent = ((exponent + 32768) & 65535) - 32768
    increment = fw.phase_increment(exponent)
    # Native 0x1ff6d0 imposes a stricter cap for byte-coded samples.
    limit = 0x8000 if descriptor['flags'] & 1 else 0x1fffff
    if not descriptor['flags'] & 0x21:
        length = descriptor['end_inclusive_candidate'] - descriptor['loop_start']
        if length <= 255:
            limit = 0x10000 if length <= 15 else 0x20000 if length <= 31 else 0x40000 if length <= 63 else 0x80000 if length <= 127 else 0x100000
    return min(increment, limit)


def verify_arm(rom, samples, fw, decoder):
    from program_firmware import Arm
    from test_korg_pcm import FirmwareFeedback
    feedback = FirmwareFeedback()
    cases = []
    for flag in sorted({s['flags'] for s in samples if s['flags'] & 1}):
        d = max((s for s in samples if s['flags'] == flag), key=lambda s: s['end_inclusive_candidate'] - s['start'])
        raw = source_bytes(rom, d)[:1024]
        expected, counts = decode_reference(raw, *d['coefficients_q14'], load_lut())
        actual, c_counts = decoder.decode(raw, *d['coefficients_q14'])
        assert expected == actual and counts == c_counts
        previous = older = 0
        for code, value in zip(raw, expected):
            assert feedback.step(code, *d['coefficients_q14'], previous, older) == value
            older, previous = previous, value
        cases.append(dict(sample_id=d['index'], flags=hex(flag), frames=len(raw), C_Python_original_ARM_equal=True))
    saturation_checks = []
    for sid in (855, 980):
        d = samples[sid]; raw = source_bytes(rom, d)
        expected, counts = decode_reference(raw, *d['coefficients_q14'], load_lut())
        actual, c_counts = decoder.decode(raw, *d['coefficients_q14'])
        assert actual == expected and counts == c_counts and any(counts)
        candidates = [i for i,v in enumerate(expected) if abs(v)==2147483647]
        # Prediction-only saturation need not leave the final output at a rail.
        if not candidates:
            a1,a2=d['coefficients_q14']
            candidates=[i for i in range(1,len(expected)) if abs(a1*expected[i-1]+a2*(expected[i-2] if i>1 else 0))//16384>2147483647]
        assert candidates
        for i in candidates:
            assert feedback.step(raw[i], *d['coefficients_q14'], expected[i-1] if i else 0, expected[i-2] if i>1 else 0)==expected[i]
        saturation_checks.append(dict(sample_id=sid,frames=len(raw),saturations=counts,original_ARM_boundary_frames=candidates))
    arm = Arm(fw)
    rates = []
    for pitch in sorted({s['pitch_field'] for s in samples}):
        actual = arm.pitch_rate(pitch)
        assert actual == fw.phase_increment(pitch * 2)
        rates.append(dict(pitch_field=pitch, phase_increment=actual, effective_rate_hz=48000 * actual / 8192))
    # Exercise the actual region fine/root input and pitch setup, keeping only
    # unrelated external control getters/pitch-EG zeroed as in the prior oracle.
    regions = load('key-regions')[:5568]
    region_checks = []
    for ri in [0, 1, 44, 100, 200, 300, 1000, 2000, 3000, 4000, 5000, 5400]:
        r = regions[ri]; d = samples[r['sample_index_raw']]
        raw = bytes.fromhex(r['raw_hex'])
        for note in sorted({r['root_key_candidate'], r['top_key']}):
            # Recreate pitch_rate's scratch context, then supply real descriptor
            # and key-region bytes to the original setup/update instructions.
            arm.pitch_rate(d['pitch_field'])
            voice, sample, pitchctx, region = 0x11010000, 0x1101c000, 0x1101e000, 0x11021000
            arm.uc.mem_write(sample, bytes.fromhex(d['raw_hex']))
            arm.uc.mem_write(region, raw)
            arm.write(voice + 0x22c, region)
            arm.stubs = {offset: lambda _: 0 for offset in (0x2753DC, 0x2754AC, 0x275688, 0x274DC4, 0x1F8A64, 0x1FFDE8)}
            fine = struct.unpack_from('<h', raw, 6)[0]
            arm.call(0x1ff764, pitchctx, voice, r['root_key_candidate'] * 256, fine,
                     stack=(sample, note * 256, 0, 0))
            actual = struct.unpack('<I', arm.uc.mem_read(pitchctx + 0x18, 4))[0]
            expected = region_increment(fw, d, r, note)
            assert actual == expected, (ri, note, actual, expected)
            region_checks.append(dict(region=ri, note=note, fine_raw=fine, phase_increment=actual))
    save(DERIVED / 'original-arm-verification.json', dict(
        firmware_sha256=FW_SHA, ROM_sha256=ROM_SHA, predictor_cases=cases, saturation_checks=saturation_checks,
        source_rate_checks=rates, region_pitch_checks=region_checks,
        scope='Offline original ARM encoder-feedback and CPU pitch path; external control getters zeroed. Does not emulate TG interpolation or complete Program DSP.'))
    print(f'PASS original ARM: {sum(c["frames"] for c in cases)} real ROM frames, {len(rates)} rates, {len(region_checks)} region pitches', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-arm', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    rom = ROM.read_bytes()
    assert len(rom) == 0x4000000 and hashlib.sha256(rom).hexdigest() == ROM_SHA
    fw = Firmware(); samples = load('sample-descriptors')
    decoder = Decoder(load_lut(), ROOT / 'build/rom-decode-probe')
    if args.verify_arm:
        verify_arm(rom, samples, fw, decoder)
    if args.verify_only:
        return
    records = []; totals = collections.Counter()
    for d in samples:
        audio, counts = decode(rom, d, decoder)
        assert len(audio) == d['end_inclusive_candidate'] - d['start'] + 1
        increment = fw.phase_increment(d['pitch_field'] * 2)
        exact_rate = 48000 * increment / 8192
        folder = 'diagnostics' if d['index'] >= 4068 else 'samples'
        relative = f'{folder}/{d["index"]:04d}.wav'
        path = OUTPUT / relative; path.parent.mkdir(parents=True, exist_ok=True)
        # No global root note: one descriptor may occur in multiple mappings.
        write_wav(path, array.array('i', audio), 1, round(exact_rate))
        with wave.open(str(path), 'rb') as w:
            assert (w.getnframes(), w.getsampwidth(), w.getnchannels(), w.getframerate()) == (len(audio), 3, 1, round(exact_rate))
            payload = w.readframes(w.getnframes())
        # Validate every exported PCM24 frame against high bits of reconstruction.
        b = np.frombuffer(payload, np.uint8).reshape(-1, 3).astype(np.int32)
        back = (b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16)
        back = (back << 8) >> 8
        assert np.array_equal(back, audio >> 8)
        floats = audio.astype(np.float64) / 2**31
        peak = float(np.max(np.abs(floats)))
        loop = d['loop_start'] - d['start']
        record = dict(sample_id=d['index'], role=d['role'], file=relative,
                      encoding='predictive8' if d['flags'] & 1 else 'PCM16LE', flags=d['flags'],
                      frames=len(audio), effective_rate_hz=exact_rate, wav_rate_hz=round(exact_rate),
                      phase_increment=increment, pitch_field=d['pitch_field'], coefficients_q14=d['coefficients_q14'],
                      source_byte_range=[d['byte_start_candidate'], d['byte_end_exclusive_candidate']],
                      source_sha256=hashlib.sha256(source_bytes(rom, d)).hexdigest(),
                      wav_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      loop_start_relative=loop, end_frame_inclusive=len(audio)-1,
                      peak=peak, rms=float(np.sqrt(np.mean(floats * floats))), dc=float(np.mean(floats)),
                      nonzero_frames=int(np.count_nonzero(audio)), saturations=counts,
                      loop_end_minus_start=float(floats[-1]-floats[loop]), descriptor_hex=d['raw_hex'])
        records.append(record)
        totals['frames'] += len(audio); totals['wav_bytes'] += path.stat().st_size
        totals[record['encoding']] += 1
        if d['index'] % 500 == 0:
            print('Decoded', d['index'], flush=True)
    report = dict(ROM=str(ROM.relative_to(PRODUCT_ROOT)), ROM_sha256=ROM_SHA, firmware_sha256=FW_SHA,
                  factory_sample_count=4068, diagnostic_count=2, totals=dict(totals), samples=records,
                  source_rate='48000 * original_integer_phase_increment(2 * signed16_descriptor_pitch) / 8192; WAV header rounded only',
                  format='Unnormalized mono PCM24. PCM16LE keeps original 16-bit precision; predictive8 retains 24 high bits of Q31 reconstruction.',
                  boundary='Full descriptor span through candidate inclusive end; possible interpolation guard retained. Loop/reverse flags and predictor restart state retained as raw metadata, not presented as fully decoded.',
                  audition_scope='Raw ROM waveform data; no factory Program filtering, envelope, modulation, effects or combination reconstruction')
    save(DERIVED / 'sample-decode-manifest.json', report)
    save(OUTPUT / 'manifest.json', report)
    print(f'Exported 4068 factory + 2 diagnostic WAVs: {totals["wav_bytes"]:,} bytes', flush=True)


if __name__ == '__main__':
    main()
