#!/usr/bin/env python3
"""Verify current filter-player evidence and WAVs, preserving older snapshots.

Aggregates completed executable test logs; does not rerun a DAW or firmware.
"""
import array
import hashlib
import json
import math
import re
import sys
import wave
from pathlib import Path

from layout import ROOT
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return (ROOT/path).read_text()


def main():
    report_path='research/derived/verification/concert-filter-arm-comparison.json'
    report=json.loads(read(report_path))
    assert sha(ROOT/'research/derived/firmware/KROSS2_V124/KROSSAPP.bin')==report['firmware_sha256']
    assert sha(ROOT/'output/kep-analysis/Concert_SE_Grand/program.bin')==report['program_sha256']
    for tool,expected in report['tool_sha256'].items():assert sha(ROOT/'tools'/tool)==expected
    for key in ('map','traces'):assert sha(ROOT/report[key]['path'])==report[key]['sha256']
    assert report['context_count']==32512 and report['trace_fixture_records']==552
    assert report['trace_steps_compared']==4152 and report['raw_parameter_mutations']==400
    generated=json.loads(read('build/plugin/generated/voice-assets.json'))
    assert generated['firmware_sha256']==report['firmware_sha256']
    assert sha(ROOT/'build/plugin/generated/NativeVoiceData.h')==generated['header_sha256']
    assert 'IPLUG_DEPLOY_PLUGINS:BOOL=OFF' in read('build/plugin/CMakeCache.txt')
    assert not (Path.home()/'Library/Audio/Plug-Ins/VST3/SEGrand.vst3').exists()
    previous=json.loads(read('output/SEGrand/manifest.json'))
    for bundle in previous['bundles']:
        assert sha(ROOT/'output/SEGrand'/bundle['file']/'Contents/MacOS/SEGrand')==bundle['binary_sha256']
    control=json.loads(read('output/Concert_SE_Grand_Control/manifest.json'))
    for recording in control['recordings']:
        assert sha(ROOT/'output/Concert_SE_Grand_Control'/recording['file'])==recording['sha256']

    core_sources=['src/instrument/NativeVoice.h','src/instrument/NativeVoice.cpp',
                  'src/instrument/NativeFilter.h','src/instrument/NativeFilter.cpp',
                  'src/instrument/PianoEngine.h','src/instrument/PianoEngine.cpp',
                  'src/dsp/concert_effects.c','src/dsp/concert_effects.h',
                  'build/plugin/generated/NativeVoiceData.h']
    executables=['build/plugin/test-native-filter','build/plugin/test-piano-engine',
                 'build/sanitize/test-native-filter','build/sanitize/test-piano-engine',
                 'build/plugin/render-piano','build/plugin/benchmark-piano',
                 'build/plugin/out/SEGrand.vst3/Contents/MacOS/SEGrand']
    for binary in executables:
        assert all((ROOT/name).stat().st_mtime <= (ROOT/binary).stat().st_mtime for name in core_sources),('Stale build',binary)
    logs={'ctest':'build/filter-player-ctest.log','sanitizers':'build/filter-player-sanitizer.log',
          'validator':'build/filter-vst3-validator.log','render':'build/filter-render.log',
          'test_details':'build/plugin/Testing/Temporary/LastTest.log'}
    assert '100% tests passed out of 4' in read(logs['ctest'])
    assert '100% tests passed out of 3' in read(logs['sanitizers'])
    assert '47 tests passed, 0 tests failed' in read(logs['validator'])
    details=read(logs['test_details'])
    assert '32512 ARM filter contexts, 552 ARM trace states' in details
    assert 'filter connected/bypass difference' in details and 'zero audio-thread new' in details
    assert 'PASS compiled VST3' in details
    release=re.search(r'native release timing ([0-9.]+)\.\.([0-9.]+) s',details);assert release
    for log,binary in [('ctest',executables[0]),('sanitizers',executables[2]),('validator',executables[-1])]:
        assert (ROOT/logs[log]).stat().st_mtime >= (ROOT/binary).stat().st_mtime
    assert read(logs['render']).count('listening gain 1\n')==3
    benchmark=json.loads(read('build/filter-piano-benchmark.json'))
    assert all(m['active_voices_at_start_and_end']==64 for m in benchmark['measurements'])

    output=ROOT/'output/Concert_SE_Grand_Filter';recordings=[]
    for name,space,enabled in [('instrument-filter.wav',1,True),('instrument-filter-dry.wav',0,True),('instrument-bypass-dry.wav',0,False)]:
        path=output/name
        assert path.stat().st_mtime >= (ROOT/'build/plugin/render-piano').stat().st_mtime
        with wave.open(str(path),'rb') as wav:
            assert (wav.getframerate(),wav.getnchannels(),wav.getsampwidth(),wav.getnframes())==(48000,2,2,672000)
            samples=array.array('h',wav.readframes(wav.getnframes()))
        if sys.byteorder!='little':samples.byteswap()
        peak=max(abs(x) for x in samples);assert 0<peak<32767
        recordings.append(dict(file=name,sha256=sha(path),bytes=path.stat().st_size,
                               rate_hz=48000,channels=2,pcm_bits=16,frames=672000,duration_seconds=14,
                               space=space,filter_enabled=enabled,EQ_enabled=True,export_gain=1,
                               peak=peak/32768,rms=math.sqrt(sum(x*x for x in samples)/len(samples))/32768))
    assert recordings[2]['sha256']==sha(ROOT/'output/Concert_SE_Grand_Control/instrument-native-dry.wav')
    assert recordings[1]['sha256']!=recordings[2]['sha256']
    sources=core_sources+['CMakeLists.txt','src/plugin/SEGrand.cpp','tools/analyze_concert_program.py',
                         'tools/test_native_filter.cpp','tools/test_piano_engine.cpp','tools/render_piano.cpp',
                         'tools/benchmark_piano.cpp','tools/verify_filter_player.py']
    result=dict(
        name='Concert SE Grand verified filter controls and approximate host filter',
        firmware_sha256=report['firmware_sha256'],program_sha256=report['program_sha256'],
        ARM_report_path=report_path,ARM_report_sha256=sha(ROOT/report_path),
        tests=dict(ARM_contexts=32512,ARM_continuous_trace_steps=4152,CPP_selected_ARM_states=552,
                   raw_parameter_mutations=400,Mixer2_boundary_injections=7,TG_filter_commands=10,
                   CTest=[4,4],ASan_UBSan=[3,3],VST3_validator=[47,47],
                   amplitude_release_seconds_min_max=[float(release[1]),float(release[2])],
                   scope='Recorded executable tests; no physical KROSS2/DAW or listening acceptance'),
        corrected_factory_fields=report['corrected_factory_fields'],
        model_assumptions=dict(cutoff_hz='20000*2^((cutoffWord/317-99)/10), capped at 0.45*hostRate',
                               resonance_q='(1/sqrt(2))*2^(6*resonanceWord/31744)',
                               branch_gain='trimWord*outputWord/32768^2',
                               audio_filter='RBJ two-pole LP + constant-0dB-peak BP, Parallel sum, per-OSC states',
                               smoothing='16ms host-frame coefficient interpolation; not TG control-word stepping',
                               external_AMS='KnobMod1/modwheel/ribbon/LFO and sample offsets zero; only factory velocity/tracking/mixers/Filter EG connected',
                               limits='TG internal Hz/Q, nonlinearity, fixed-point/pan/mix and absolute audio gain unresolved'),
        controls=dict(preset='Concert',output_db=-6,velocity_extra_exponent=1,amp_release_base_seconds=.288),
        benchmark=benchmark,recordings=recordings,
        previous_control_dry_bit_identical_to_bypass=True,
        source_sha256={name:sha(ROOT/name) for name in sources},
        log_sha256={name:sha(ROOT/path) for name,path in logs.items()},
        executable_sha256={path:sha(ROOT/path) for path in executables},
        sample_pack_sha256=sha(ROOT/'build/plugin/generated/SEGrand.samples'),
        deployment=dict(IPLUG_DEPLOY_PLUGINS=False,user_plugin_absent=True,
                        historical_output_binaries_and_control_WAVs_unchanged=True,
                        packaging_or_installation_performed=False))
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    (output/'manifest.json').write_text(text)
    (ROOT/'research/derived/verification/filter-player-check.json').write_text(text)
    print('PASS filter-player recorded tests/provenance, three WAVs, unchanged historical outputs and no deployment')


if __name__=='__main__':main()
