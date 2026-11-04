#!/usr/bin/env python3
"""Check recorded native-player tests and rendered WAVs; retain their fingerprints.

Does not run a host or claim hardware fidelity. Run the documented builds/tests
and render commands first. Original research/exports are never rewritten.
"""
import array
import hashlib
import json
import re
import sys
import wave
from pathlib import Path

from layout import ROOT
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(relative):
    return (ROOT / relative).read_text()


def main():
    generated = json.loads(read('build/plugin/generated/voice-assets.json'))
    timing = json.loads(read('research/derived/verification/voice-timing-arm-comparison.json'))
    assert digest(ROOT/'research/derived/firmware/KROSS2_V124/KROSSAPP.bin') == generated['firmware_sha256'] == timing['firmware_sha256']
    assert digest(ROOT/'output/kep-analysis/Concert_SE_Grand/program.bin') == generated['program_sha256']
    assert digest(ROOT/'build/plugin/generated/NativeVoiceData.h') == generated['header_sha256']
    assert digest(ROOT/'build/plugin/generated/native-voice-traces.bin') == generated['trace_fixture_sha256']
    assert 'IPLUG_DEPLOY_PLUGINS:BOOL=OFF' in read('build/plugin/CMakeCache.txt')
    # This project previously withdrew its installation. Do not touch the directory.
    user_plugin = Path.home()/'Library/Audio/Plug-Ins/VST3/SEGrand.vst3'
    assert not user_plugin.exists(), 'Unexpected installed SEGrand; inspect without deleting it'
    previous = json.loads(read('output/SEGrand/manifest.json'))
    for bundle in previous['bundles']:
        path = ROOT/'output/SEGrand'/bundle['file']/'Contents/MacOS/SEGrand'
        assert digest(path) == bundle['binary_sha256'], 'Historical bundle binary changed'

    sources = [
        'CMakeLists.txt', 'src/instrument/NativeVoice.h', 'src/instrument/NativeVoice.cpp',
        'src/instrument/PianoEngine.h', 'src/instrument/PianoEngine.cpp',
        'src/plugin/KrosePlugin.cpp', 'src/dsp/concert_effects.c', 'src/dsp/concert_effects.h',
        'tools/prepare_voice_assets.py', 'tools/test_native_voice.cpp',
        'tools/test_piano_engine.cpp', 'tools/render_piano.cpp', 'tools/benchmark_piano.cpp',
        'tools/verify_native_player.py',
    ]
    native_binary = ROOT/'build/plugin/test-native-voice'
    for name in sources[:7] + ['tools/prepare_voice_assets.py', 'tools/test_native_voice.cpp']:
        assert (ROOT/name).stat().st_mtime <= native_binary.stat().st_mtime, ('Rebuild tests after edit', name)
    logs = {
        'ctest': 'build/native-player-ctest.log',
        'sanitizers': 'build/native-player-sanitizer.log',
        'validator': 'build/native-vst3-validator.log',
        'test_details': 'build/plugin/Testing/Temporary/LastTest.log',
    }
    assert '100% tests passed out of 3' in read(logs['ctest'])
    assert '100% tests passed out of 2' in read(logs['sanitizers'])
    assert '47 tests passed, 0 tests failed' in read(logs['validator'])
    details = read(logs['test_details'])
    assert '32512 ARM initial/release contexts, 243 multi-stage ARM trace states, 28 TG commands' in details
    assert 'zero audio-thread new' in details and 'PASS compiled VST3' in details
    release = re.search(r'native release timing ([0-9.]+)\.\.([0-9.]+) s', details)
    assert release
    assert (ROOT/logs['ctest']).stat().st_mtime >= native_binary.stat().st_mtime
    benchmark = json.loads(read('build/native-piano-benchmark.json'))
    assert all(m['active_voices_at_start_and_end'] == 64 for m in benchmark['measurements'])

    output = ROOT/'output/Concert_SE_Grand_Control'
    recordings = []
    for name, space in [('instrument-native.wav', 1), ('instrument-native-dry.wav', 0)]:
        path = output/name
        assert path.stat().st_mtime >= (ROOT/'build/plugin/render-piano').stat().st_mtime, 'Re-render after rebuilding'
        with wave.open(str(path), 'rb') as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) == (48000, 2, 2, 672000)
            samples = array.array('h', wav.readframes(wav.getnframes()))
        if sys.byteorder != 'little':
            samples.byteswap()
        peak = max(abs(x) for x in samples)
        assert 0 < peak < 32767
        recordings.append({'file': name, 'sha256': digest(path), 'bytes': path.stat().st_size,
                           'rate_hz': 48000, 'channels': 2, 'pcm_bits': 16, 'frames': 672000,
                           'duration_seconds': 14, 'export_gain': 1,
                           'integer_peak': peak, 'space': space, 'EQ_enabled': True})
    result = {
        'name': 'Concert SE Grand native control model integration',
        'firmware_sha256': generated['firmware_sha256'],
        'program_sha256': generated['program_sha256'],
        'voice_asset_manifest': generated,
        'nominal_control_hz': 62.5, 'nominal_TG_audio_hz': 48000,
        'controls': {'release_base_seconds': .288, 'velocity_trim_exponent': 1, 'preset': 'Concert', 'output_db': -6},
        'tests': {'ARM_contexts': 32512, 'ARM_selected_trace_states': 243, 'ARM_TG_commands': 28,
                  'CTest': [3, 3], 'ASan_UBSan': [2, 2], 'VST3_validator': [47, 47],
                  'release_test_seconds_min_max': [float(release[1]), float(release[2])],
                  'release_test_context': 'MIDI60 velocity100, hold0.5s, rates44100/48000/96000/192000'},
        'benchmark': benchmark,
        'recordings': recordings,
        'source_sha256': {name: digest(ROOT/name) for name in sources},
        'log_sha256': {name: digest(ROOT/path) for name, path in logs.items()},
        'timing_report_sha256': digest(ROOT/'research/derived/verification/voice-timing-arm-comparison.json'),
        'benchmark_report_sha256': digest(ROOT/'build/native-piano-benchmark.json'),
        'sample_pack_sha256': digest(ROOT/'build/plugin/generated/SEGrand.samples'),
        'build_vst3_binary_sha256': digest(ROOT/'build/plugin/out/SEGrand.vst3/Contents/MacOS/SEGrand'),
        'deployment': {'IPLUG_DEPLOY_PLUGINS': False, 'user_plugin_absent': True,
                       'historical_output_bundle_binaries_unchanged': True,
                       'packaging_or_installation_performed': False},
        'scope': [
            'Aggregates recorded executable tests and verifies their source/artifact fingerprints; does not rerun tests',
            'Firmware ARM control arithmetic verified; TG per-audio-frame step/clamp remains an interpretation',
            'Per-note control phase, shared sample read, mean OSC control gain and 0.4 headroom are host choices',
            'Physical oscillator, TG mix/pan/interpolation, filter, half-pedal and original effects DSP remain unverified',
            'No hardware A/B, listening acceptance, GUI or Ableton acceptance asserted',
        ],
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    (output/'manifest.json').write_text(text)
    (ROOT/'research/derived/verification/native-player-check.json').write_text(text)
    print('PASS native-player provenance, recorded tests, two WAV exports and no deployment')


if __name__ == '__main__':
    main()
