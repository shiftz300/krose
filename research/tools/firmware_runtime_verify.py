#!/usr/bin/env python3
"""Verify current runtime research fingerprints without rewriting older evidence."""
import argparse
import cmath
import hashlib
import json
import math
import re
import wave
from pathlib import Path
from layout import PRODUCT_ROOT as ROOT
from program_firmware import Firmware,FW_SHA

BASE=ROOT/'research/derived/firmware/KROSS2_V124/architecture'
DOC=ROOT/'research/docs/architecture'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence-only',action='store_true',help='Verify research evidence before regenerating the current PDF; default also verifies paper and visual review')
    args=parser.parse_args()
    Firmware()
    protected=load(BASE/'stage01/protected-before.json')
    for row in protected['files']:assert sha(ROOT/row['path'])==row['sha256'],row['path']
    checks=[];exported_paths=[]
    for stage,result,tool in [('stage02','arm-check.json','firmware_runtime_flow.py'),
                              ('stage02','note-layers-check.json','firmware_note_layers.py'),
                              ('stage03','voice-parameters-check.json','firmware_voice_parameters.py'),
                              ('stage03','voice-release-check.json','firmware_voice_release.py'),
                              ('stage03','voice-start-check.json','firmware_voice_start.py'),
                              ('stage03','voice-tg-check.json','firmware_voice_tg.py'),
                              ('stage03','voice-failures-check.json','firmware_voice_failures.py'),
                              ('stage03','factory-regions-check.json','firmware_factory_regions.py'),
                              ('stage03','voice-reuse-check.json','firmware_voice_reuse.py'),
                              ('stage03','mono-keys-check.json','firmware_mono_keys.py'),
                              ('stage03','unison-check.json','firmware_unison.py'),
                              ('stage03','portamento-gate-check.json','firmware_portamento_gate.py'),
                              ('stage04','music-clock-check.json','firmware_music_clock.py'),
                              ('stage04','external-clock-check.json','firmware_external_clock.py'),
                              ('stage04','transport-check.json','firmware_transport.py'),
                              ('stage04','external-tempo-check.json','firmware_external_tempo.py'),
                              ('stage04','sequence-time-check.json','firmware_sequence_time.py'),
                              ('stage04','sequence-notes-check.json','firmware_sequence_notes.py'),
                              ('stage04','sequence-controls-check.json','firmware_sequence_controls.py'),
                              ('stage04','sequence-loops-check.json','firmware_sequence_loops.py'),
                              ('stage04','sequence-sysex-check.json','firmware_sequence_sysex.py'),
                              ('stage04','parameter-cache-check.json','firmware_parameter_cache.py'),
                              ('stage04','parameter-dispatch-check.json','firmware_parameter_dispatch.py'),
                              ('stage04','parameter-notifications-check.json','firmware_parameter_notifications.py'),
                              ('stage04','message-replies-check.json','firmware_message_replies.py'),
                              ('stage04','mmi-parameters-check.json','firmware_mmi_parameters.py'),
                              ('stage04','ui-tree-check.json','firmware_ui_tree.py'),
                              ('stage04','ui-refresh-check.json','firmware_ui_refresh.py'),
                              ('stage04','ui-bitmap-check.json','firmware_ui_bitmap.py'),
                              ('stage04','ui-occlusion-check.json','firmware_ui_occlusion.py'),
                              ('stage04','arpeggiator-check.json','firmware_arpeggiator.py'),
                              ('stage04','arpeggio-sync-check.json','firmware_arpeggio_sync.py'),
                              ('stage04','step-sequencer-check.json','firmware_step_sequencer.py'),
                              ('stage04','drum-patterns-check.json','firmware_drum_patterns.py'),
                              ('stage04','drum-trigger-check.json','firmware_drum_trigger.py'),
                              ('stage04','drum-playback-check.json','firmware_drum_playback.py'),
                              ('stage04','drum-integration-check.json','firmware_drum_integration.py'),
                              ('stage04','music-interlock-check.json','firmware_music_interlock.py'),
                              ('stage04','step-context-check.json','firmware_step_context.py'),
                              ('stage04','step-live-write-check.json','firmware_step_live_write.py'),
                              ('stage04','record-intake-check.json','firmware_record_intake.py'),
                              ('stage04','record-notes-check.json','firmware_record_notes.py'),
                              ('stage04','record-bars-check.json','firmware_record_bars.py'),
                              ('stage04','parametric-eq-check.json','firmware_parametric_eq.py'),
                              ('stage04','effect-routing-check.json','firmware_effect_routing.py'),
                              ('stage04','limiters-check.json','firmware_limiters.py'),
                              ('stage04','chorus-check.json','firmware_chorus.py'),
                              ('stage04','hall-check.json','firmware_hall.py'),
                              ('stage04','voice-lfo-check.json','firmware_voice_lfo.py'),
                              ('stage04','voice-lfo-integration-check.json','firmware_voice_lfo_integration.py'),
                              ('stage04','lfo-targets-check.json','firmware_lfo_targets.py'),
                              ('stage04','ams-mixers-check.json','firmware_ams_mixers.py'),
                              ('stage04','envelopes-check.json','firmware_envelopes.py'),
                              ('stage04','pedal-envelopes-check.json','firmware_pedal_envelopes.py'),
                              ('stage04','pedal-release-flow-check.json','firmware_pedal_release_flow.py'),
                              ('stage04','factory-voice-chain-check.json','firmware_factory_voice_chain.py'),
                              ('stage04','voice-refresh-check.json','firmware_voice_refresh.py'),
                              ('stage04','drum-voice-chain-check.json','firmware_drum_voice_chain.py'),
                              ('stage04','drum-controls-check.json','firmware_drum_controls.py'),
                              ('stage04','gm-programs-check.json','firmware_gm_programs.py'),
                              ('stage04','expansion-pcm-check.json','firmware_expansion_pcm.py'),
                              ('stage04','expansion-voices-check.json','firmware_expansion_voices.py'),
                              ('stage04','program-relocation-check.json','firmware_program_relocation.py'),
                              ('stage04','midi-parameters-check.json','firmware_midi_parameters.py'),
                              ('stage04','midi-banks-check.json','firmware_midi_banks.py'),
                              ('stage04','midi-program-load-check.json','firmware_midi_program_load.py'),
                              ('stage04','midi-voice-handoff-check.json','firmware_midi_voice_handoff.py'),
                              ('stage04','midi-voice-refresh-check.json','firmware_midi_voice_refresh.py'),
                              ('stage04','hall-local-operands-check.json','firmware_hall_operands.py'),
                              ('stage04','midi-reset-check.json','firmware_midi_reset.py'),
                              ('stage04','chorus-program-check.json','firmware_chorus_program.py'),
                              ('stage04','midi-all-off-check.json','firmware_midi_all_off.py'),
                              ('stage04','stop-reuse-check.json','firmware_stop_reuse.py'),
                              ('stage04','stop-reuse-live-check.json','firmware_stop_reuse_live.py'),
                              ('stage04','voice-auxiliary-check.json','firmware_voice_auxiliary.py'),
                              ('stage04','resource-import-check.json','firmware_resource_import.py'),
                              ('stage04','pcm-loop-check.json','firmware_pcm_loop.py'),
                              ('stage04','voice-pressure-check.json','firmware_voice_pressure.py'),
                              ('stage04','mono-live-check.json','firmware_mono_live.py'),
                              ('stage04','master-kernel-check.json','firmware_master_kernel.py'),
                              ('stage04','drum-eg-times-check.json','firmware_drum_envelope_times.py'),
                              ('stage04','drum-eg-live-check.json','firmware_drum_envelope_live.py'),
                              ('stage04','drum-nrpn-live-check.json','firmware_drum_nrpn_live.py'),
                              ('stage04','eq-b2-program-check.json','firmware_eq_b2_program.py'),
                              ('stage04','drum-voice-playback-check.json','firmware_drum_voice_playback.py'),
                              ('stage04','effect-load-state-check.json','firmware_effect_load_state.py')]:
        p=BASE/stage/result;d=load(p)
        assert d['passed'] and d['firmware_sha256']==FW_SHA and not d['device_access']
        assert d['tool_sha256']==sha(ROOT/'research/tools'/tool),tool
        assert d['helper_sha256']==sha(ROOT/'research/tools/program_firmware.py')
        if 'math_sha256' in d:assert d['math_sha256']==sha(ROOT/'research/tools/voice_math.py')
        for name,digest in d.get('additional_helpers',{}).items():assert digest==sha(ROOT/'research/tools'/name)
        for row in d.get('inputs',[]):assert row['sha256']==sha(ROOT/row['path']),row['path']
        if result=='ui-bitmap-check.json':assert d['sample']['sha256']==sha(BASE/stage/'ui-bitmap-pattern-sample.bin')
        if result=='arpeggiator-check.json':assert d['catalog']['sha256']==sha(BASE/stage/'arpeggio-patterns.json')
        if result=='drum-patterns-check.json':assert d['catalog_sha256']==sha(BASE/stage/'drum-patterns.json')
        if result=='factory-voice-chain-check.json':
            assert not d['smoke_only'] and len(d['factory'])==d['counts']['oscillators']==1315
            assert len({x['program'] for x in d['factory']})==d['counts']['programs']==726
            assert sum(len(x['voices']) for x in d['factory'])==d['counts']['voices']==1760
            assert sum(x['tg_start_calls'] for x in d['factory'])==d['counts']['starts']==1615
            assert len(d['extra'])==312 and len(d['reverse_capabilities'])==497
            assert sum(d['reverse_capabilities'])==118
            for row in d['factory']+d['extra']:
                assert row['tg_start_calls']==sum('sample_registers' in voice for voice in row['voices'])
        if result=='voice-refresh-check.json':
            assert not d['smoke_only'] and len(d['traces'])==72
            assert sum(len(t['steps']) for t in d['traces'])==9216
            assert sum(len(p['commits']) for t in d['traces'] for p in t['steps'])==4449
            assert len(d['wave_representatives'])==18 and len(d['filter_route_representatives'])==4
            assert len(d['busy_cases'])==6 and len(d['auxiliary_influence'])==8
            assert all(x['auxiliary_state_changed'] and len(x['steps'])==16 for x in d['auxiliary_influence'])
            assert len({(x['flags'],x['marker'],x['direction']) for x in d['controlled_commits']})==1920
            assert d['coefficient_table'][0]==65535 and d['coefficient_table'][1]==2047 and d['coefficient_table'][24]==85
        if result=='drum-voice-chain-check.json':
            assert not d['smoke_only'] and len(d['kits'])==d['counts']['kits']==42
            assert d['counts']['selection_cases']==42*128*127
            assert len(d['stereo_pairs'])==49 and len(d['reverse_capabilities'])==1014 and sum(d['reverse_capabilities'])==36
            assigned={(kit['program'],key) for kit in d['kits'] for key in kit['assigned_keys']}
            assert len(assigned)==d['counts']['assigned_keys']==3594
            assert {(row['program'],row['note']) for row in d['factory']}==assigned
            assert len(d['factory'])==d['counts']['startup_cases']
            assert sum(len(row['voices']) for row in d['factory'])==d['counts']['voices']
            assert sum(row['tg_start_calls'] for row in d['factory'])==d['counts']['starts']
            assert all(row['tg_start_calls']==sum(bool(v['sample_registers']) for v in row['voices']) for row in d['factory'])
            assert len(d['choke_sequences'])==d['counts']['choke_sequences']
            for trace in d['choke_sequences']:
                old=set(trace['first']['active']);second=trace['second'];stops=old if trace['group'] else set()
                assert set(second['hardstops'])==stops
                assert set(second['active'])==(old-stops)|{v['voice_slot'] for v in second['voices']}
            assert len(d['release_cases'])==d['counts']['release_cases']==43
            assert sum(x['key_obeys_note_off'] for x in d['release_cases'])==1
            coverage=load(BASE/stage/'drum-voice-coverage.json')
            assert coverage['passed'] and coverage['check_sha256']==sha(p)
            assert coverage['tool_sha256']==sha(ROOT/'research/tools/firmware_drum_voice_figures.py')
            assert coverage['preload_sha256']==sha(ROOT/d['inputs'][0]['path'])
            assert (coverage['stored_enabled_slots'],coverage['initialized_slots'])==(5239,5237)
            assert {(x['program'],x['note'],x['slot']) for x in coverage['unreachable_enabled_slots']}=={('F060',74,1),('F061',106,1)}
            assert (coverage['key_note_off_disabled'],coverage['key_note_off_enabled'])==(3583,11)
        if result=='drum-controls-check.json':
            assert not d['smoke_only'] and d['writers']['absolute_cases']==128*13*128
            assert len(d['writers']['increment_cases'])==600
            assert {int(k):v for k,v in d['writers']['fields'].items()}=={20:0,21:1,22:2,23:3,24:4,25:5,26:7,28:8,29:10,30:9}
            assert d['pan']['position_cases']==13824 and len(d['pan']['modulation'])==108 and len(d['pan']['sends'])==15360
            assert len(d['pan']['positions'])==384
            assert len(d['traces'])==216 and len({t['program'] for t in d['traces']})==42
            assert len({(t['program'],t['note']) for t in d['traces']})==72
            assert {t['batch'] for t in d['traces']}=={1,3,8} and all(len(t['steps'])==96 for t in d['traces'])
            assert sum(len(s['commits']) for t in d['traces'] for s in t['steps'])==11946
            assert all(len(s['pan'])==len(s['commits']) for t in d['traces'] for s in t['steps'])
            assert sum(len(s['new_voices']) for t in d['traces'] for s in t['steps'])==318
            latch=d['latched_controls'];assert len(latch['steps'])==32
            assert (latch['retrigger_changed']['voices'][0]['tune'],latch['retrigger_changed']['cutoff'],latch['retrigger_changed']['resonance'])==(2368,8320,16)
            assert (latch['retrigger_baseline']['voices'][0]['tune'],latch['retrigger_baseline']['cutoff'],latch['retrigger_baseline']['resonance'])==(0,0,0)
        if result=='gm-programs-check.json':
            assert not d['smoke_only'] and len(d['records'])==265 and len({r['id'] for r in d['records']})==265
            assert len(d['mapping'])==4096 and sum(d['variant_counts'])==128 and max(d['variant_counts'])==9
            assert d['parameter_fields']==1042 and d['parameter_positions']==276130 and d['unique_parameter_inputs']==3106
            assert all(len(r['parameter_values'])==1042 for r in d['records'])
            assert d['counts']==dict(melodic_startup_contexts=4191,melodic_oscillators=373,melodic_programs=256,drum_selection_cases=292608,drum_startup_contexts=6912,drum_programs=9)
            assert len(d['melodic'])==4191 and len(d['drums'])==6912 and len(d['drum_selection'])==18
            assert len({r['id'] for r in d['melodic'] if r['voices']})==256
            assert sum(len(r['voices']) for r in d['melodic'])==3619 and sum(r['tg_start_calls'] for r in d['melodic'])==3135
            assert sum(len(r['voices']) for r in d['drums'])==sum(r['tg_start_calls'] for r in d['drums'])==3543
            assert all(r['tg_start_calls']==sum(bool(v.get('sample_registers')) for v in r['voices']) for r in d['melodic']+d['drums'])
            assert (len(d['official_conflicts']),len(d['official_name_conflicts']),len(d['official_mode_conflicts']))==(6,1,10)
            assert d['gm_low_key_table'][24]==75 and d['gm_low_key_table'][25:29]==[-1]*4
        if result=='expansion-pcm-check.json':
            assert not d['smoke_only'] and len(d['resources']['maps'])==9728 and len(d['resources']['lookups'])==256
            assert [(b['library'],b['samples'],b['regions'],b['multisamples'],len(b['stereo_pairs']),len(b['drumsamples'])) for b in d['resources']['banks']]==[(1,272,282,10,5,0),(2,602,632,32,0,0),(4,195,216,34,6,45)]
            assert [(e['library'],len(e['samples'])) for e in d['exports']]==[(2,602),(4,195)]
            samples=[s for e in d['exports'] for s in e['samples']]
            assert sum(s['frames'] for s in samples)==17387114 and sum(len(s['arm_points']) for s in samples)==32272
            assert sum(s['bytes'] for s in samples)==52196828 and all(s['saturations']==[0,0] for s in samples)
            for s in samples:
                wavpath=ROOT/s['file'];assert sha(wavpath)==s['sha256'];exported_paths.append(wavpath)
                with wave.open(str(wavpath),'rb') as wav:
                    assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())==(1,3,s['wav_rate_hz'],s['frames'])
            assert len(d['expansion_drumkits'])==4
            assert sum(len(k['keys']) for k in d['expansion_drumkits'])==342
            missing=[s for kit in d['expansion_drumkits'] for key in kit['keys'] for s in key['slots'] if not s['available_bank']]
            assert len(missing)==10 and {s['bank'] for s in missing}=={12} and sum(bool(s['reachable_velocities']) for s in missing)==9
        if result=='expansion-voices-check.json':
            assert not d['smoke_only']
            assert d['counts']==dict(melodic_programs=124,melodic_oscillators=222,drum_programs=4,drum_selection_cases=65024,melodic_contexts=3126,melodic_voices=3198,melodic_starts=3083,melodic_deferred=0,drum_contexts=1739,drum_voices=1883,drum_starts=1883,drum_deferred=11)
            assert len({r['program'] for r in d['melodic']})==124
            assert len({(r['program'],r['oscillator']) for r in d['melodic']})==222
            for label,rows in [('melodic',d['melodic']),('drum',d['drums'])]:
                assert len(rows)==d['counts'][label+'_contexts']
                assert sum(len(r['voices']) for r in rows)==d['counts'][label+'_voices']
                assert sum(r['tg_start_calls'] for r in rows)==d['counts'][label+'_starts']
                assert sum(r['deferred_missing_bank'] for r in rows)==d['counts'][label+'_deferred']
                assert all(r['tg_start_calls']==sum(bool(v.get('sample_registers')) for v in r['voices']) for r in rows)
                assert all(not r['voices'] and not r['tg_start_calls'] for r in rows if r['deferred_missing_bank'])
            assert len(d['drum_selection'])==4 and [r['stored_kit'] for r in d['kit_links']]==[45,45,43,44]
            assert {(r['program'],r['note']) for r in d['drums'] if r['deferred_missing_bank']}=={('EXPCM004:043',45),('EXPCM004:043',83),('EXPCM004:043',96)}
            assert {v['source_wav'] for r in d['melodic']+d['drums'] for v in r['voices']}=={r['path'] for r in d['source_waveforms']}
            assert len(d['source_waveforms'])==572
            for row in d['source_waveforms']:assert sha(ROOT/row['path'])==row['sha256'],row['path']
        if result=='program-relocation-check.json':
            assert d['counts']==dict(kit_cases=33152,arpeggio_pattern_cases=70,program_reference_cases=2910,source_programs=128,source_contexts=384)
            assert len(d['records'])==384 and len({r['program'] for r in d['records']})==128
            assert {r['kit_target'] for r in d['records']}=={42,46,54}
            assert len(d['drum_links'])==12
            assert [r['relocated_kit'] for r in d['drum_links'] if r['kit_target']==46]==[49,49,47,48]
            assert all(set(r['changed_offsets'])<={0x566,0x567,0x4DC,0x4DD,0x4F2,0x4F3,0x502,0x503} for r in d['records'])
        if result=='midi-parameters-check.json':
            assert d['counts']==dict(selector_flags=3072,fine_values=16384,rpn_contexts=12800,rpn_selection_gates=1536,nrpn_contexts=4608,bend_values=16384,poly_pressure=512,channel_pressure=128)
            assert [(r['value'],r['output']) for r in d['bend_examples']]==[(0,-32768),(1,-32764),(127,-32260),(128,-32255),(8191,-1),(8192,0),(8193,4),(16383,32767)]
            assert [(r['value'],r['tune'][0]) for r in d['fine_examples']]==[(0,-100),(1,-100),(4096,-50),(8191,-1),(8192,0),(8193,0),(12288,50),(16383,99)]
            assert [(r['source'],r['live_data'],r['shadow_data'],r['drum_cutoff']) for r in d['source_examples']]==[(0,127,127,99),(1,127,127,99),(5,127,0,99),(8,127,127,99)]
        if result=='midi-banks-check.json':
            assert d['counts']==dict(legal_bank_pairs=98304,missing_byte_cases=272,all_program_special_banks=3584,bank_unavailable_cases=420)
            assert len(d['variation_banks'])==128 and len(d['variation_msbs'])==120 and d['extended_caps']==[2,1,5,3,5,9,5,3]
            assert [(r['bank'],r['program'],r['special_low_drums']) for r in d['examples']]==[(0,0,0),(10,0,0),(0,0,0),(19,0,0),(20,56,0),(20,0,1),(65535,24,0)]
        if result=='midi-program-load-check.json':
            assert not d['smoke_only'] and d['counts']==dict(factory_programs=768,gm_logical_selections=1408,alternate_selections=1024,empty_bank_selections=12,loading_contexts=384)
            for key,amount in [('factory',768),('gm',1408),('alternate',1024),('empty',12),('contexts',384)]:assert len(d[key])==amount
            assert {(row['input_bank'],row['input_program']) for row in d['factory']}=={(b,p) for b in range(6) for p in range(128)}
            assert len({(r['physical_bank'],r['physical_program']) for row in d['gm'] for r in row['loaded']})==265
            assert all(len(row['loaded'])==2 for key in ['factory','gm','alternate','empty'] for row in d[key])
            assert all(r['bank']==0 for row in d['empty'] for r in row['loaded'])
            assert d['example']['bend']==[0,0,32767]
        if result=='midi-voice-handoff-check.json':
            assert not d['smoke_only'] and d['counts']==dict(traces=864,note_ons=1728,note_offs=1728,program_changes=1728,initialized_voices=3600,tg_starts=3024)
            assert len(d['presets'])==12 and len(d['traces'])==864
            assert {(t['mode'],t['velocity'],tuple(t['old']),tuple(t['new'])) for t in d['traces']}=={(m,v,tuple(o),tuple(n)) for m in [0,3] for v in [1,64,127] for o in d['presets'] for n in d['presets']}
            assert all(t['pool_unchanged_on_change'] for t in d['traces'])
            assert sum(len(t[e]['voices']) for t in d['traces'] for e in ['first','second'])==3600
            assert sum(t[e]['tg_start_calls'] for t in d['traces'] for e in ['first','second'])==3024
            figure=load(BASE/stage/'midi-voice-handoff-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p)
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_midi_handoff_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            assert figure['csv_sha256']==sha(BASE/stage/'midi-voice-handoff-example.csv') and len(figure['rows'])==5
        if result=='midi-voice-refresh-check.json':
            assert not d['smoke_only'] and d['counts']==dict(traces=72,updates=6912,commits=3380)
            assert len(d['traces'])==72 and all(len(t['steps'])==96 for t in d['traces'])
            pairs={((0,0),(0,61)),((0,61),(0,0)),((0,11),(5,42)),((5,42),(0,11)),((10,0),(20,0)),((20,0),(10,0))}
            assert {(tuple(t['old']),tuple(t['new']),t['batch'],t['mode'],t['pedal']) for t in d['traces']}=={(o,n,b,m,ped) for o,n in pairs for b in [1,3,8] for m in [0,3] for ped in [False,True]}
            assert sum(len(s['commits']) for t in d['traces'] for s in t['steps'])==3380
            for t in d['traces']:
                assert all(s['state']['volume']==99 for s in t['steps'][8:])
                assert t['steps'][24]['state']['channel_bend']==32767 and t['steps'][24]['state']['timbre_bend']==0
            figure=load(BASE/stage/'midi-voice-refresh-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==96
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_midi_refresh_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            assert figure['csv_sha256']==sha(BASE/stage/'midi-voice-refresh-example.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='hall-local-operands-check.json':
            assert d['counts']==dict(hall_items=121,slots=7,visible_bit_probes=3744,representative_forms=13)
            assert len(d['items'])==121 and len(d['slots'])==7 and len(d['address_references'])==26
            assert d['extra_local_indices']==[62,63]
            assert [s['mfx_modified'] for s in d['slots']]==[[],[],[],[],[],[103,106],[103,106]]
            assert all(len(s['words'])==121 for s in d['slots'])
            fw=Firmware();fx=fw.effect(105)
            assert d['source_code_sha256']==hashlib.sha256(fw.data[fx['code_offset']:fx['code_offset']+8*fx['code_words_64']]).hexdigest()
            figure=load(BASE/stage/'hall-reference-order-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==20
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_hall_operand_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            assert figure['csv_sha256']==sha(BASE/stage/'hall-reference-order.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='midi-reset-check.json':
            assert not d['smoke_only'] and d['counts']==dict(value_matrix=4096,sostenuto_matrix=1536,selector_flags=512,channels_modes=640,blocked_system=64,live_traces=40,live_updates=2560,live_commits=1728)
            assert len(d['defaults'])==120 and len(d['live'])==40 and len(d['matrix_sha256'])==64
            assert {(tuple(t['preset']),t['mode'],t['sostenuto'],t['source']) for t in d['live']}=={(p,m,s,src) for p in [(0,0),(0,61),(5,42),(10,0),(20,0)] for m in [0,3] for s in [0,127] for src in [0,5]}
            assert all(len(t['steps'])==64 for t in d['live'])
            assert sum(len(s['commits']) for t in d['live'] for s in t['steps'])==1728
            for t in d['live']:
                for i in [28,48]:
                    e=t['steps'][i]['event']['reset'];before=bytes.fromhex(e['channel_before']);after=bytes.fromhex(e['channel_after'])
                    assert len(before)==len(after)==436 and after[0x114]==0
                    assert (e['buffer_volume'],e['cached_volume'],e['buffer_pan'],e['cached_pan'],e['fine_tuning'])==(127,99,64,100,10)
                    assert after[0xFA:0xFC]==bytes(2) and after[0x118:0x138]==bytes(32)
                    assert after[0x13C:0x1B4]==after[0x82:0xFA]
                    assert [after[0x82],after[0xA2]]==[before[0x82],before[0xA2]]==e['bank']
                    assert all(after[0x82+cc]==d['defaults'][cc] for cc in range(120) if cc not in [0,32])
                assert t['steps'][28]['event']['reset']['pressed_slots_kept']
            figure=load(BASE/stage/'midi-reset-state-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==10
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_midi_reset_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            assert figure['csv_sha256']==sha(BASE/stage/'midi-reset-state.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='chorus-program-check.json':
            assert not d['smoke_only'] and d['counts']==dict(program_items=106,slots=7,visible_bit_probes=30528,factory_slots=309,wave_labels=2)
            assert len(d['items'])==106 and len(d['slots'])==7 and len(d['references'])==27 and len(d['factory'])==309
            assert d['wave_labels']==['Tri','Sine'] and d['fixed_b_indices']==[768,961,991] and d['b_indices_without_initial_values']==[27,28,29,30]
            assert d['references'][0]['nonlocal_a_items']==[0,64]
            assert [d['references'][i]['a_items'] for i in [1,2,3,6,7,8,9,11,12,26]]==[[21,74],[24,83],[1,101],[4],[22],[25],[96],[86],[87],[103]]
            fw=Firmware();fx=fw.effect(64)
            assert d['source_code_sha256']==hashlib.sha256(fw.data[fx['code_offset']:fx['code_offset']+8*fx['code_words_64']]).hexdigest()
            initial=[fw.u32(fx['constants_offset']+4*i) for i in range(27)]
            for slot,s in enumerate(d['slots']):
                assert s['slot']==slot and len(s['items'])==106
                assert s['base']==fw.u32(0x38CCE8+4*slot) and s['right_base']==s['base']+2881
                assert s['constants']==initial[:1]+[s['base'],s['right_base']]+initial[3:]
                assert [x['pc'] for x in s['mfx_modified']]==([59,60,61,62] if slot in [5,6] else [])
                for x in s['mfx_modified']:assert (int(x['after'],16)-int(x['before'],16))%2**48==((1<<43) if x['pc'] in [59,61] else (-(1<<43))%2**48)
            parent=load(BASE/stage/'chorus-check.json')
            assert [(x['program'],x['source_offset'],x['source_sha256']) for x in d['factory']]==[(x['program'],x['source_offset'],x['source_sha256']) for x in parent['factory']]
            assert all(x['code_sha256']==d['slots'][x['slot']]['code_sha256'] for x in d['factory'])
            figure=load(BASE/stage/'chorus-program-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==33
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_chorus_program_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv_sha256']==sha(BASE/stage/'chorus-program-references.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='midi-all-off-check.json':
            assert not d['smoke_only'] and d['live_continuity_complete'] is False
            assert d['counts']==dict(values_sources=1024,channels_modes=768,key_counters=32,blocked_system=64,live_traces=96,live_updates=3008,live_commits=1340,reuse_faults=80)
            assert len(d['live'])==96 and sum(len(t['steps']) for t in d['live'])==3008
            assert sum(len(s['commits']) for t in d['live'] for s in t['steps'])==1340
            pairs={((0,0),(0,61)),((2,1),(0,61)),((5,36),(0,0)),((5,42),(0,0)),((10,0),(20,0)),((20,0),(10,0))}
            assert {(tuple(t['old']),tuple(t['new']),t['controller'],t['pedals'],t['mode']) for t in d['live']}=={(o,n,c,ped,m) for o,n in pairs for c in [120,123] for ped in range(4) for m in [0,3]}
            faults=[t for t in d['live'] if t['reuse_fault']];complete=[t for t in d['live'] if not t['reuse_fault']]
            assert len(faults)==80 and len(complete)==16
            assert all(t['old']==[2,1] and t['new']==[0,61] and len(t['steps'])==48 for t in complete)
            for t in d['live']:
                assert t['source']==(5 if t['pedals']&1 else 0)
                for s in t['steps']:
                    if 'off' not in s['event']:continue
                    e=s['event']['off'];assert e['channel_preserved'] and e['controllers_preserved']
                    if e['controller']==120:
                        assert not e['after'] and not e['released'] and e['available']==32 and e['tg_active_mask']==0
                        assert sorted(e['killed'])==sorted(v['slot'] for v in e['before'])
                    else:
                        assert not e['killed'] and len(e['after'])==len(e['before'])
                        assert sorted(e['released'])==sorted(v['slot'] for v in e['before'] if v['flags']&128)
                if t['reuse_fault']:
                    f=t['reuse_fault'];assert f['update']==(20 if t['controller']==120 else 36)==len(t['steps'])
                    assert f['memory_fault']==dict(access=20,address='0x4',bytes=4,pc='0xc027242c')
                    assert f['unlinked']['node'][:2]==[0,0] and f['unlinked']['caller']=='0xc01fc760' and f['voice_pairs']
            figure=load(BASE/stage/'midi-all-off-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and (figure['rows'],figure['fault_rows'])==(2,80)
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_midi_all_off_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv_sha256']==sha(BASE/stage/'midi-all-off-example.csv') and figure['fault_csv_sha256']==sha(BASE/stage/'midi-all-off-reuse-faults.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='stop-reuse-check.json':
            assert not d['smoke_only'] and d['live_continuity_complete'] is False and d['portable_unlink_verified']
            c=d['counts']
            for key,value in dict(baseline_cases=336,paired_baselines=168,reuse_faults=120,counterfactual_cases=6,counterfactual_reuses=6,zero_page_cases=2,zero_page_reuses=2,zero_page_writes=6,queued_cases=2,queued_successful_notes=4,queued_faults=2,portable_cases=24).items():assert c[key]==value
            assert len(d['baseline'])==336 and len(d['counterfactual'])==6 and len(d['zero_page'])==len(d['queued'])==2 and len(d['portable'])==24
            presets={(0,0),(0,61),(2,1),(5,42),(10,0),(20,0)};actions={'none','cc123','cc120','timbre','osc','list','slots'}
            assert {(tuple(x['preset']),x['mode'],x['velocity'],x['action']) for x in d['baseline']}=={(p,m,v,a) for p in presets for m in [0,3] for v in [1,64,100,127] for a in actions}
            assert sum(bool(x['paired_slots']) for x in d['baseline'])==168 and sum(bool(x['reuse_fault']) for x in d['baseline'])==120
            for x in d['baseline']:
                assert bool(x['reuse_fault'])==(bool(x['paired_slots']) and x['action'] not in ['none','cc123'])
                if x['reuse_fault']:assert x['reuse_fault']['memory']==dict(access=20,address='0x4',bytes=4,pc='0xc027242c')
                else:assert x['final_lists']['candidate_nodes']==32
            for x in d['counterfactual']:
                assert x['perturbation'] in ['clear_type','clear_partner','clear_both'] and not x['reuse_fault'] and x['edits']
                assert all(e['offset'] in ['0x218','0x230'] and e['after']=='00000000' for e in x['edits'])
            for x in d['zero_page']:
                before=bytes.fromhex(x['vector_before']);after=bytes.fromhex(x['vector_after'])
                assert before==Firmware().data[:64] and after[:8]==bytes(8) and after[8:]==before[8:]
                assert x['final_lists']['candidate_nodes']==32 and x['writes']
                assert all(w['value']==0 and w['size']==4 and (w['address'],w['pc']) in [(4,'0xc027242c'),(0,'0xc0272430')] for w in x['writes'])
            for x in d['queued']:
                assert x['old']==[2,1] and x['new']==[0,61] and [a['note'] for a in x['attempts']]==[67,68,69]
                assert [v['voice_slot'] for a in x['attempts'][:2] for v in a['result']['voices']]==[2,3]
                assert x['attempts'][2]['fault']['memory']['address']=='0x4'
            assert {(tuple(x['preset']),x['mode'],x['velocity']) for x in d['portable']}=={(p,m,v) for p in [(0,0),(2,1),(10,0)] for m in [0,3] for v in [1,64,100,127]}
            for x in d['portable']:
                assert x['software_states_equal'] and x['io_equal'] and x['lists']['candidate_nodes']==32
                assert x['skipped_empty_nodes'] and [w['address'] for w in x['native_zero_page_writes']]==[4,0]*len(x['skipped_empty_nodes'])
                assert all(v['gain']==v['secondary_gain_before'] for v in x['note']['voices'] if v['pair']==2)
            assert any(v['gain'] for x in d['portable'] for v in x['note']['voices'] if v['pair']==2)
            assert c['portable_skipped_empty_nodes']==sum(len(x['skipped_empty_nodes']) for x in d['portable'])
            assert c['portable_native_zero_writes']==2*c['portable_skipped_empty_nodes']==sum(len(x['native_zero_page_writes']) for x in d['portable'])
            figure=load(BASE/stage/'stop-reuse-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==13
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_stop_reuse_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv_sha256']==sha(BASE/stage/'stop-reuse-summary.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='stop-reuse-live-check.json':
            assert not d['smoke_only'] and d['portable_continuity_complete']
            c=d['counts'];traces=d['traces'];prior=load(BASE/stage/'midi-all-off-check.json')
            assert c==dict(traces=96,updates=4608,commits=1652,note_events=192,stop_events=288,previous_prefix_updates=3008,previous_fault_traces_completed=80,skipped_empty_nodes=152,native_zero_page_writes=304,cold_contexts=16)
            def key(t):return tuple(t['old']),tuple(t['new']),t['controller'],t['pedals'],t['mode']
            previous={key(t):t for t in prior['live']}
            assert len(traces)==c['traces']==96 and {key(t) for t in traces}==set(previous)
            assert c['updates']==sum(len(t['steps']) for t in traces)==4608
            assert c['commits']==sum(len(s['commits']) for t in traces for s in t['steps'])
            assert c['note_events']==sum('note' in s['event'] for t in traces for s in t['steps'])==192
            assert c['stop_events']==sum('off' in s['event'] for t in traces for s in t['steps'])==288
            assert c['previous_prefix_updates']==sum(t['previous_prefix_updates'] for t in traces)==3008
            assert c['previous_fault_traces_completed']==sum(bool(t['previous_reuse_fault']) for t in traces)==80
            assert c['cold_contexts']==len(d['cold'])==16
            assert {(tuple(x['preset']),x['mode'],x['note']) for x in d['cold']}=={(p,m,n) for p in [(0,0),(0,61),(10,0),(20,0)] for m in [0,3] for n in [67,72]}
            for t in traces:
                old=previous[key(t)];assert t['initial']==old['initial']
                assert t['software_states_and_io_equal'] and t['model_zero_page_mapped'] is False
                assert t['source']==(5 if t['pedals']&1 else 0)
                assert t['previous_reuse_fault']==old['reuse_fault'] and t['previous_prefix_updates']==len(old['steps'])
                assert [s['update'] for s in t['steps']]==list(range(48))
                for before,after in zip(old['steps'],t['steps']):assert before['state']==after['state'] and before['commits']==after['commits']
                writes=t['native_zero_page_writes'];skipped=t['skipped_empty_nodes']
                assert [w['address'] for w in writes]==[4,0]*len(skipped)
                assert all(w['size']==4 and w['value']==0 and (w['address'],w['pc']) in [(4,'0xc027242c'),(0,'0xc0272430')] for w in writes)
                assert all(x['next']==x['previous']==0 and 0<=x['index']<32 for x in skipped)
                seed=Firmware().data[:64];assert bytes.fromhex(t['native_vector_prefix'])==(bytes(8)+seed[8:] if writes else seed)
                for s in t['steps']:
                    assert s['lists']['candidate_nodes']==32 and s['lists']['available']==s['state']['available']==32-len(s['state']['voices'])
                    if 'off' in s['event']:
                        e=s['event']['off'];assert s['update'] in [0,12,32] and e['controller']==(120 if s['update']==32 else t['controller'])
                        assert e['channel_preserved'] and e['controllers_preserved']
                        if e['controller']==120:assert not e['after'] and e['available']==32 and e['tg_active_mask']==0
                    if 'note' in s['event']:
                        e=s['event']['note'];assert s['update'] in [20,36] and e['note']==(67 if s['update']==20 else 72) and e['velocity']==100
                        assert all(v['gain']==v['secondary_gain_before'] for v in e['voices'] if v['pair']==2)
            assert c['skipped_empty_nodes']==sum(len(t['skipped_empty_nodes']) for t in traces)
            assert c['native_zero_page_writes']==2*c['skipped_empty_nodes']==sum(len(t['native_zero_page_writes']) for t in traces)
            figure=load(BASE/stage/'stop-reuse-live-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==4608
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_stop_reuse_live_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv_sha256']==sha(BASE/stage/'stop-reuse-live.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='voice-auxiliary-check.json':
            assert not d['smoke_only'] and d['omitted_range']==['0xc01fe6f0','0xc01fe75c'] and d['masked_voice_range']==['0x1cc','0x1f0']
            traces=d['traces'];c=d['counts'];prior=load(BASE/stage/'midi-voice-refresh-check.json')
            def key(t):return tuple(t['old']),tuple(t['new']),t['batch'],t['mode'],t['pedal']
            previous={key(t):t for t in prior['traces']}
            assert len(traces)==c['traces']==72 and {key(t) for t in traces}==set(previous)
            assert c['updates']==sum(len(t['steps']) for t in traces)==6912
            assert c['commits']==sum(len(s['commits']) for t in traces for s in t['steps'])==3380
            assert c['skipped_phase_entries']==sum(len(t['skipped']) for t in traces)>0
            assert c['outside_auxiliary_reads']==sum(len(t['outside_auxiliary_reads']) for t in traces)==0
            for t in traces:
                assert t['state_and_io_equal_outside_auxiliary'] and not t['outside_auxiliary_reads']
                assert [s['update'] for s in t['steps']]==list(range(96))
                assert all(x['pc']=='0xc01fe6f0' and 0<=x['poll_cursor']<32 for x in t['skipped'])
                assert any(s['auxiliary_blocks_different'] for s in t['steps'])
                assert t['steps'][-1]['skipped_phases']==len(t['skipped'])
                for s,old in zip(t['steps'],previous[key(t)]['steps']):
                    assert s['state']==old['state'] and s['commits']==old['commits']
                    assert 0<=s['auxiliary_blocks_different']<=32
            # Earlier nonzero-parameter perturbations complement omission of
            # the zero-parameter baseline; keep their original evidence intact.
            influence=load(BASE/stage/'voice-refresh-check.json')['auxiliary_influence']
            assert len(influence)==8 and all(x['auxiliary_state_changed'] and len(x['steps'])==16 for x in influence)
            figure=load(BASE/stage/'voice-auxiliary-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==72
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_voice_auxiliary_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv_sha256']==sha(BASE/stage/'voice-auxiliary-traces.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='resource-import-check.json':
            assert not d['smoke_only'] and d['counts']==dict(section_cases=65,kit_placement_cases=16,partial_successes=10,failed_after_writes=9,program_kit_links=64)
            cases=d['cases'];assert len(cases)==65
            placements=[x for x in cases if x['tag']=='1KBD' and x['variant']=='original'];assert len(placements)==16
            assert {x['index'] for x in placements}==set(range(16))
            kit_names=['NU Pop Kit','Electrik Kit','Bang Kit','Nu DISCO Kit']
            for row in placements:
                assert row['bank']==row['last_bank']==1 and row['returned']==1 and row['copied']==min(4,16-row['index'])
                assert row['stream_position']==row['stream_length']==34944
                assert [x['index'] for x in row['records']]==list(range(row['index'],row['index']+row['copied']))
                assert [x['name'] for x in row['records']]==kit_names[:row['copied']]
            for row in cases:
                assert row['copied']==len(row['records'])
                if row['returned']:assert row['stream_position']==row['stream_length']
                else:assert row['stream_position']==0 and row['io'][-1]['op']=='seek'
                if row['variant'] in ['checksum-header','checksum-payload']:assert row['returned']==0 and row['copied']=={'1KBD':4,'1KBP':64,'1KBA':19}[row['tag']]
                if row['variant']=='short-last-record':assert row['returned']==0 and row['copied']=={'1KBD':3,'1KBP':63,'1KBA':18}[row['tag']]
                if row['variant'] in ['wrong-tag','short-header']:assert row['returned']==row['copied']==0
                if row['variant']=='declared-length-plus8':assert row['returned']==1
                if row['variant']=='zero-records':assert row['returned']==1 and row['copied']==0
            assert sum(x['returned']==0 and x['copied']>0 for x in cases)==9
            links=d['links'];assert len(links)==64
            assert {(x['destination_start'],x['program']) for x in links}=={(k,n) for k in range(42,58) for n in [41,42,43,44]}
            for row in links:
                assert row['stored_kit']=={41:45,42:45,43:43,44:44}[row['program']]
                assert row['relocated_kit']==min(57,row['stored_kit']-42+row['destination_start'])
                installed=next(p for p in placements if p['index']==row['destination_start']-42)['records']
                selected=next(x for x in installed if x['index']+42==row['relocated_kit'])
                assert row['selected_kit_name']==selected['name'] and row['selected_kit_sha256']==selected['sha256']
            assert all(x['selected_kit_name']=='Nu DISCO Kit' for x in links if x['destination_start']<=54 and x['program'] in [41,42])
            assert all(x['selected_kit_name']=='NU Pop Kit' for x in links if x['destination_start']==57)
            figure=load(BASE/stage/'resource-import-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and (figure['rows'],figure['link_rows'])==(65,64)
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_resource_import_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv_sha256']==sha(BASE/stage/'resource-import-cases.csv') and figure['link_csv_sha256']==sha(BASE/stage/'resource-import-kit-links.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='pcm-loop-check.json':
            assert not d['smoke_only'] and d['TG_loop_state_policy_verified'] is False
            assert d['counts']==dict(samples=3406,baseline_frames=104613116,carry_frames=171241524,python_prefix_points=326976,arm_points=336)
            rows=d['rows'];assert len(rows)==3406 and len({(r['library'],r['sample']) for r in rows})==3406
            sizes={'ROM':2416,'EXPCM001':272,'EXPCM002':594,'EXPCM004':124}
            assert sum(r['frames'] for r in rows)==104613116 and len(d['arm_points'])==336
            lookup={(r['library'],r['sample']):r for r in rows}
            loop_firmware=Firmware().data
            lut=[int.from_bytes(loop_firmware[0x3FD180+2*i:0x3FD182+2*i],'little',signed=True) for i in range(256)]
            for point in d['arm_points']:
                row=lookup[point['library'],point['sample']];a1,a2=row['coefficients'];product=a1*point['previous']+a2*point['older']
                prediction=(abs(product)//16384)*(-1 if product<0 else 1);prediction=max(-2147483647,min(2147483647,prediction))
                assert point['value']==max(-2147483647,min(2147483647,prediction+lut[(point['code']+128)&255]*65536))
            assert sum(3*c['loop_frames'] for r in rows for c in r['cuts'])==171241524
            for r in rows:
                assert r['flags']&1 and r['frames']-r['loop']>1
                assert [c['excluded_end_frames'] for c in r['cuts']]==[0,1]
                for cut in r['cuts']:
                    assert cut['end_exclusive']==r['frames']-cut['excluded_end_frames'] and cut['loop_frames']==cut['end_exclusive']-r['loop']
                    assert [c['cycle'] for c in cut['cycles']]==[1,2,3]
                    assert cut['cycles'][0]['initial_state']==cut['first_carry_state']
                    for before,after in zip(cut['cycles'],cut['cycles'][1:]):assert before['final_state']==after['initial_state']
                    for c in cut['cycles']:
                        assert 0<=c['different_pcm24_frames']<=c['different_q31_frames']<=cut['loop_frames']
                        assert 0<=c['rms_difference']<=2 and 0<=c['max_abs_q31_difference']<=4294967294
                assert r['wav_sha256']==sha(ROOT/r['wav_path'])
            assert len(d['groups'])==8
            for group in d['groups']:
                selected=[r for r in rows if r['library']==group['library']];assert len(selected)==group['samples']==sizes[group['library']]
                cycles=[r['cuts'][group['excluded_end_frames']]['cycles'][0] for r in selected]
                assert group['different_pcm24_samples']==sum(c['different_pcm24_frames']>0 for c in cycles)
                assert group['maximum_rms_difference']==max(c['rms_difference'] for c in cycles)
                assert group['different_pcm24_samples']==group['samples']-(group['library']=='ROM' and group['excluded_end_frames']==1)
            witness=d['witness'];assert (witness['library'],witness['sample'],witness['excluded_end_frames'])==('ROM',1857,0)
            assert len(witness['baseline_prefix'])==len(witness['carry_prefix'])==114 and witness['baseline_prefix']!=witness['carry_prefix']
            witness_rms=math.sqrt(sum(((a-b)/2**31)**2 for a,b in zip(witness['baseline_prefix'],witness['carry_prefix']))/114)
            assert abs(witness_rms-witness['rms_difference'])<1e-12
            figure=load(BASE/stage/'pcm-loop-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==20436
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_pcm_loop_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv_sha256']==sha(BASE/stage/'pcm-loop-model-differences.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='voice-pressure-check.json':
            assert not d['smoke_only'] and d['partial_preset'] is None
            counts=d['counts'];traces=d['traces']
            assert (counts['traces'],counts['updates'],counts['note_events'],counts['cold_contexts'])==(32,5632,4672,200)
            assert len(traces)==32 and len(d['cold'])==200
            expected_choices={(preset,batch,pedal,profile) for preset in [(0,0),(0,11),(0,61),(20,0)] for batch in [1,8] for pedal in [False,True] for profile in ['equal','varied']}
            assert {(tuple(t['preset']),t['batch'],t['pedal'],t['score_profile']) for t in traces}==expected_choices
            assert counts['commits']==sum(len(s['commits']) for t in traces for s in t['steps'])
            assert counts['selection_calls']==sum(len(t['selections']) for t in traces)
            assert counts['reclaims']==sum(len(t['reclaims']) for t in traces)
            assert counts['active_reclaims']==sum(r['was_active'] for t in traces for r in t['reclaims'])
            assert counts['paired_active_reclaims']==sum(r['was_active'] and r['pair']!=0 for t in traces for r in t['reclaims'])
            assert counts['stop_acknowledgements']==sum(len(t['stop_acknowledgements']) for t in traces)
            assert counts['start_acknowledgements']==sum(len(t['start_acknowledgements']) for t in traces)
            assert counts['intranote_reuse_events']==sum(bool(s['event'].get('note',{}).get('reused_within_call')) for t in traces for s in t['steps'])
            assert counts['overwritten_constructions']==sum(v['overwritten_by'] is not None for t in traces for s in t['steps'] for v in s['event'].get('note',{}).get('voices',[]))
            assert counts['discarded_constructions']==sum(not v['survived'] for t in traces for s in t['steps'] for v in s['event'].get('note',{}).get('voices',[]))
            assert counts['intranote_reuse_events']==counts['overwritten_constructions']==counts['discarded_constructions']==0
            cold={(tuple(c['preset']),c['note']):c for c in d['cold']}
            assert counts['native_zero_page_writes']==2*counts['skipped_empty_nodes']==sum(len(t['native_zero_page_writes']) for t in traces)
            for t in traces:
                assert t['capacity']==120 and len(t['scores'])==120 and t['software_states_and_io_equal']
                assert [s['update'] for s in t['steps']]==list(range(176))
                if t['preset']!=[20,0]:
                    assert any(s['state']['available']==0 for s in t['steps'][:144])
                    assert any(r['was_active'] and r['available_before']==0 for r in t['reclaims'])
                assert t['steps'][152]['state']['available']==120
                selections=reclaims=0
                for s in t['steps']:
                    state=s['state'];active=state['active_slots'];keyon=state['key_on_slots']
                    assert len(active)==len(set(active)) and set(keyon)<=set(active)<=set(range(120))
                    assert state['available']==120-len(active)
                    assert s['lists']==dict(candidate_nodes=120,active_nodes=len(active),available=state['available'])
                    assert all(re.fullmatch('[0-9a-f]{64}',state[k]) for k in ['control_state_sha256','voice_pool_sha256'])
                    assert s['selection_range'][0]==selections and s['reclaim_range'][0]==reclaims
                    selections=s['selection_range'][1];reclaims=s['reclaim_range'][1]
                    if s['update']<144:assert s['event']['note']['note']==36+s['update']%48
                    if s['update']==144:assert s['event']['off_all_keys']
                    if s['update']==148:assert s['event']['pedal_off']
                    if s['update'] in [156,164]:assert s['event']['note']['note']==(86 if s['update']==156 else 88)
                    if 'note' in s['event']:
                        note=s['event']['note'];original=cold[tuple(t['preset']),note['note']]['event']['voices'];voices=note['voices']
                        assert len(voices)==len(original) and note['surviving_new_voices']==sum(v['survived'] for v in voices)
                        latest={v['voice_slot']:i for i,v in enumerate(voices)}
                        assert note['reused_within_call']==sorted(slot for slot in latest if sum(v['voice_slot']==slot for v in voices)>1)
                        for i,(v,expected) in enumerate(zip(voices,original)):
                            assert v['construction']==i and (v['sample'],v['osc'],v['weight'],v['pair'])==(expected['sample'],expected['osc'],expected['weight'],expected['pair'])
                            assert (v['program_pointer'],v['osc_pointer'],v['started'],v['sample_registers'])==(expected['program_pointer'],expected['osc_pointer'],expected['started'],expected['sample_registers'])
                            assert v['gain']==(v['gain_before'] if v['pair']==2 else expected['gain'])
                            assert v['overwritten_by']==(latest[v['voice_slot']] if latest[v['voice_slot']]!=i else None)
                            if v['overwritten_by'] is not None:assert not v['survived']
                    for c in s['commits']:assert c['score_readback']==t['scores'][c['voice']]
                assert selections==len(t['selections']) and reclaims==len(t['reclaims'])
                for row in t['selections']:
                    slots,scores,status=row['slots'],row['scores'],row['active']
                    assert len(slots)==len(scores)==len(status) and len(set(slots))==len(slots)
                    expected=slots[0] if slots else None;best=65535
                    for slot,score,ok in zip(slots,scores,status):
                        assert 0<=slot<120 and 0<=score<=65535
                        if ok and score<best:
                            expected=slot;best=score
                            if best<=4:break
                    assert row['selected_slot']==expected
                for row in t['reclaims']:
                    assert row['resets']==row['expected_resets'] and all(0<=i<120 for i in row['resets'])
                    assert len(row['resets'])==(2 if row['pair'] and row['partner'] is not None else 1)
                for row in t['stop_acknowledgements']:
                    assert 0<=row['mask']<2**120 and 0<=row['before']<2**120
                    assert row['after']==row['before']&~row['mask']
                for row in t['start_acknowledgements']:
                    assert 0<=row['mask']<2**120 and 0<=row['before']<2**120
                    assert row['after']==row['before']|row['mask']
                assert [w['address'] for w in t['native_zero_page_writes']]==[4,0]*len(t['skipped_empty_nodes'])
                assert all(w['size']==4 and w['value']==0 and w['pc'] in ['0xc027242c','0xc0272430'] for w in t['native_zero_page_writes'])
            figure=load(BASE/stage/'voice-pressure-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==5632
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_voice_pressure_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv_sha256']==sha(BASE/stage/'voice-pressure-updates.csv')
            for summary in figure['summaries']:
                group=[t for t in traces if t['preset']==summary['preset']];assert len(group)==8
                representative=next(t for t in group if t['batch']==8 and t['pedal'] and t['score_profile']=='equal')
                assert summary['first_full_update']==next((s['update'] for s in representative['steps'][:144] if s['state']['available']==0),None)
                assert summary['active_reclaims']==sum(r['was_active'] for t in group for r in t['reclaims'])
                assert summary['paired_active_reclaims']==sum(r['was_active'] and r['pair']!=0 for t in group for r in t['reclaims'])
            sequences=[]
            for profile in ['equal','varied']:
                trace=next(t for t in traces if t['preset']==[0,0] and t['batch']==8 and not t['pedal'] and t['score_profile']==profile)
                sequences.append([r['selected_slot'] for r in trace['selections'] if r['selected_slot'] is not None])
            assert figure['A000_score_comparison']==dict(batch=8,pedal=False,nonempty_selections=230,different_selections=229)
            assert len(sequences[0])==len(sequences[1])==230 and sum(a!=b for a,b in zip(*sequences))==229
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='mono-live-check.json':
            assert not d['smoke_only']
            c=d['counts'];traces=d['traces'];assert c['traces']==len(traces)==26 and c['updates']==4160
            assert (c['created'],c['retunes'],c['glides'],c['commits'],c['glide_affected_constructions'],c['glide_changed_regions'])==(2514,778,3292,42,48,20)
            expected={((b,n),priority,pedal) for b,n in [(3,24),(3,9),(3,46)] for priority in range(3) for pedal in [False,True]}
            expected|={((b,n),2,pedal) for b,n in [(3,17),(3,15),(5,6),(5,110)] for pedal in [False,True]}
            assert {(tuple(t['preset']),t['priority'],t['pedal']) for t in traces}==expected
            assert c['created']==sum(len(s['event']['created']) for t in traces for s in t['steps'])
            assert c['retunes']==sum(len(s['event']['retunes']) for t in traces for s in t['steps'])
            assert c['glides']==sum(len(s['event']['glides']) for t in traces for s in t['steps'])
            assert c['glide_affected_constructions']==sum(v['initial_pitch']!=v['pitch_target'] for t in traces for s in t['steps'] for v in s['event']['created'])
            assert c['glide_changed_regions']==sum(v['region']!=v['target_region'] for t in traces for s in t['steps'] for v in s['event']['created'])
            assert c['commits']==sum(len(s['commits']) for t in traces for s in t['steps'])
            assert c['native_zero_page_writes']==2*c['skipped_empty_nodes']==sum(len(t['native_zero_page_writes']) for t in traces)
            from firmware_mono_keys import Model as KeyModel
            raw_programs=(ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all').read_bytes();rom=Firmware().data
            def mono_region(multisample,pitch):
                at=0x48F5CC+28*multisample;first=int.from_bytes(rom[at:at+2],'little');count=rom[at+2];previous=-1;query=pitch>>8
                for i in range(count):
                    top=int.from_bytes(rom[0x492C2B+20*(first+i):0x492C2C+20*(first+i)],'little',signed=True)
                    if (previous<query<=top and top>0) or (query==0 and top==0):return first+i
                    previous=top
                return None
            overflows=0
            for t in traces:
                index=128*t['preset'][0]+t['preset'][1];source=raw_programs[0x1EF220+2140*index:0x1EF220+2140*(index+1)]
                setup=t['setup'];assert setup['source_sha256']==hashlib.sha256(source).hexdigest()
                assert setup['source_control_bytes']==list(source[0x508:0x50D]) and source[0x508]&128
                edited=bytearray(source);edited[0x509]=(source[0x509]&~12)|(t['priority']<<2)
                assert setup['runtime_sha256']==hashlib.sha256(edited).hexdigest()
                assert setup['edits']==([] if edited[0x509]==source[0x509] else [dict(offset='0x509',before=source[0x509],after=edited[0x509])])
                assert setup['raw_legato']==bool(source[0x509]&16)
                assert setup['reuse']==(bool(source[0x509]&16) and not bool(source[0x509]&32))
                assert setup['offset']==bool(source[0x509]&32)
                assert setup['unison']==(source[0x50A]&7 if source[0x50A]&128 else 0)
                key_model=KeyModel(10,t['priority'],setup['raw_legato']);count=0
                assert [s['update'] for s in t['steps']]==list(range(160))
                for s in t['steps']:
                    event=s['event'];action=event['input'];dispatch=[]
                    if action:
                        kind,note,velocity=action
                        if kind=='on':
                            overflows+=len(key_model.keys)==10
                            selected,first=key_model.on(note,velocity);count+=1
                            if (selected and not setup['reuse']) or first:dispatch.append(['reset'])
                            if selected:dispatch.append(['on',0x90,note,velocity])
                        elif kind=='off':
                            if not setup['reuse']:dispatch.append(['off',0x80,note,velocity])
                            fallback=key_model.off(note);count=max(0,count-1)
                            if fallback is not None:
                                if not setup['reuse']:dispatch.append(['reset'])
                                dispatch.append(['on',0x80,fallback,key_model.velocity])
                            elif setup['reuse'] and not key_model.keys:dispatch.append(['off',0x80,note,velocity])
                        elif note==123:key_model.keys.clear();count=0
                        elif note==120:count=0
                    assert event['dispatch']==dispatch and event['keys']==key_model.keys and event['cached_velocity']==key_model.velocity and event['count']==count
                    for glide in event['glides']:
                        speed=glide['speed'];assert 0<=speed<128
                        coefficient=int.from_bytes(rom[0x3FD380+4*speed:0x3FD384+4*speed],'little',signed=True)
                        assert coefficient==glide['coefficient'];previous=glide['previous'];target=glide['target']
                        if not coefficient or previous==-1:position=step=limit=0;initial=target
                        else:
                            step=max(1,coefficient*abs(target-previous)//3072) if glide['scaled'] else coefficient
                            if target>=previous:position=(previous-target)*256;limit=0;initial=target
                            else:position=0;limit=(target-previous)*256;step=-step;initial=previous
                        assert [glide[k] for k in ['position','step','limit','initial_pitch']]==[position,step,limit,initial]
                        assert (glide['slot'] is None)==glide['temporary']
                    for row in event['created']:
                        assert row['source_pointer']==0x12000000+2144*index
                        assert row['osc_pointer']==row['source_pointer']+0x564+380*row['osc']
                        assert 0<=row['slot']<120 and 0<=row['sample']<4070
                        assert row['sample']==int.from_bytes(rom[0x492C28+20*row['region']:0x492C2A+20*row['region']],'little')
                        assert row['gain']==(row['gain_before'] if row['side']==1 else row['expected_gain'])
                        glide=event['glides'][row['glide_index']]
                        assert (row['pitch_target'],row['initial_pitch'])==(glide['target'],glide['initial_pitch'])
                        assert row['region']==mono_region(row['multisample'],row['initial_pitch'])
                        assert row['target_region']==mono_region(row['multisample'],row['pitch_target'])
                        assert row['unison_count']==setup['unison']
                        assert (0<=row['unison_index']<setup['unison']) if setup['unison'] else row['unison_index']==255
                    for row in event['retunes']:
                        assert row['velocity_before']==row['velocity_after'] and row['preserved_sha256']==row['after_preserved_sha256']
                        assert row['tracking']==row['tracking_expected'] and row['tg_starts']==0
                        assert re.fullmatch('[0-9a-f]{64}',row['preserved_sha256'])
                    state=s['state'];assert state['available']==120-len(state['voices'])
                assert not t['steps'][-1]['state']['voices'] and t['steps'][-1]['state']['available']==120
                if setup['unison']:
                    assert {r['unison_index'] for s in t['steps'] for r in s['event']['created']}==set(range(setup['unison']))
                assert [w['address'] for w in t['native_zero_page_writes']]==[4,0]*len(t['skipped_empty_nodes'])
                assert all(w['size']==4 and w['value']==0 and w['pc'] in ['0xc027242c','0xc0272430'] for w in t['native_zero_page_writes'])
            assert c['overflow_insertions']==overflows==52
            figure=load(BASE/stage/'mono-live-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==4160
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_mono_live_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv_sha256']==sha(BASE/stage/'mono-live-updates.csv')
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
            for summary in figure['summaries']:
                trace=next(t for t in traces if t['preset']==summary['preset'] and t['priority']==2 and t['pedal'])
                assert summary['created']==sum(len(s['event']['created']) for s in trace['steps'])
                assert summary['retunes']==sum(len(s['event']['retunes']) for s in trace['steps'])
        if result=='master-kernel-check.json':
            assert not d['smoke_only'] and d['actual_audio_algorithm_verified'] is False
            assert d['counts']==dict(slots=7,program_items=123,window_words=25,factory_slots=94,factory_callbacks=564,host_frames=512,frequency_points=129)
            from firmware_hall_operands import visible,decode,relocated,storage
            firmware=Firmware();effect=firmware.effect(5);rom=firmware.data
            raw=rom[effect['code_offset']:effect['code_offset']+123*8];words=visible(raw)
            initial=[firmware.u32(effect['constants_offset']+4*i) for i in range(37)]
            assert d['source_program_sha256']==hashlib.sha256(raw).hexdigest() and d['initial_constants']==initial
            assert d['items']==[dict(pc=i,visible48=f'{v:012x}',**decode(v)) for i,v in enumerate(words)]
            window=initial[1:26];analytic=[8388607*(1-math.cos(2*math.pi*(i+1)/26))/26 for i in range(25)]
            assert d['window']==window==window[::-1]==[math.floor(x) for x in analytic]
            assert d['window_sum']==sum(window)==8388599
            assert d['analytic_window']==analytic and d['maximum_quantization_error']==max(x-v for x,v in zip(analytic,window))<1
            assert [s['slot'] for s in d['slots']]==list(range(7))
            for slot in d['slots']:
                index=slot['slot'];base=firmware.u32(0x38CCE8+4*index);values=initial.copy();values[30:34]=[base,base+25,base+24,base+49]
                assert slot['base']==base and slot['constants']==values
                assert slot['address_intervals']==[[base,base+24],[base+25,base+49]]
                generic=[relocated(v,index) for v in words];expected=generic.copy()
                if index in [5,6]:
                    for pc in [108,110,112,113]:expected[pc]=(expected[pc]&~511)|14
                assert slot['items']==[dict(pc=i,**decode(v)) for i,v in enumerate(expected)]
                assert slot['program_sha256']==hashlib.sha256(storage(expected)).hexdigest()
                changes=[dict(pc=i,before=f'{x:012x}',after=f'{y:012x}',c_before=decode(x)['c'],c_after=decode(y)['c']) for i,(x,y) in enumerate(zip(generic,expected)) if x!=y]
                assert slot['mfx_modified']==changes and [c['pc'] for c in changes]==([108,110,112,113] if index in [5,6] else [])
            parent=[r for r in load(BASE/stage/'limiters-check.json')['factory'] if r['effect']==5]
            assert len(parent)==len(d['factory'])==94
            for row,old in zip(d['factory'],parent):
                slot=int(old['slot'][-1])+(4 if old['slot'].startswith('MFX') else -1)
                assert (row['program'],row['slot'],row['source_offset'],row['source_sha256'],row['parameters'])==(old['program'],slot,old['source_offset'],old['source_sha256'],old['parameters'])
                expected=old['words'].copy();expected[30:34]=d['slots'][slot]['constants'][30:34]
                assert row['constants']==expected and row['constants'][1:26]==window and row['window_unchanged']
                assert row['program_sha256']==d['slots'][slot]['program_sha256']
            assert [r['index'] for r in d['references']]==list(range(37))
            for reference in d['references']:
                index=reference['index'];assert reference['value']==initial[index]
                assert reference['a_items']==[r['pc'] for r in d['items'] if r['a']==index and (r['format']<0x5000 or r['flag2'])]
                assert reference['b_items']==[r['pc'] for r in d['items'] if r['b']==index and (r['format']!=0x5000 or r['flag2'])]
            host=d['host_reference'];assert host['kind']=='host25_tap_FIR_candidate_only'
            assert host['original_DSP_audio_executed'] is False and host['original_limiter_algorithm_verified'] is False
            assert (host['frames'],host['channels'],host['weights_divisor'],host['group_delay_frames'])==(512,2,8388607,12)
            assert host['block_sizes_equal'] and host['channels_isolated'] and host['max_direct_convolution_error']<1e-14
            weights=[v/8388607 for v in window];assert host['weights']==weights and host['dc_gain']==sum(weights)
            assert abs(host['centroid']-12)<1e-12 and host['alternative_binary_Q23_dc_gain']==sum(window)/2**23
            assert host['impulse']==weights+[0.]*103 and host['step']==[sum(weights[:min(i+1,25)]) for i in range(64)]
            assert len(host['curves'])==129
            for i,row in enumerate(host['curves']):
                angle=math.pi*i/128;response=sum(w*cmath.exp(-1j*angle*k) for k,w in enumerate(weights))
                assert row['fraction_of_nyquist']==i/128 and abs(row['real']-response.real)<1e-13 and abs(row['imag']-response.imag)<1e-13
                assert abs(row['magnitude']-abs(response))<1e-13 and abs((response*cmath.exp(1j*angle*12)).imag)<1e-13
            figure=load(BASE/stage/'master-kernel-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==[25,129,94]
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_master_kernel_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            for row,count in zip(figure['csv'],[25,129,94]):
                assert row['sha256']==sha(ROOT/row['path']) and len((ROOT/row['path']).read_text().splitlines())==count+1
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='drum-eg-times-check.json':
            assert not d['smoke_only'] and d['actual_DSP_audio_executed'] is False
            assert d['counts']==dict(helper_cases=268950,kits=42,phase_traces=378,offset_calls=2052,segment_calls=4104)
            assert d['helper_matrix']['cases']==268950 and len(d['helper_matrix']['examples'])==15
            assert len(d['traces'])==378 and len({t['program'] for t in d['traces']})==42
            from firmware_envelopes import Core
            from firmware_drum_voice_chain import KIT_OFFSET,KIT_STRIDE
            from firmware_factory_voice_chain import sb
            firmware=Firmware();core=Core(firmware)
            preload=(ROOT/d['inputs'][0]['path']).read_bytes()
            parent=load(BASE/stage/'drum-voice-chain-check.json')
            by_program={}
            for trace in d['traces']:
                by_program.setdefault(trace['program'],[]).append(trace)
                assert trace['immediate_eg_bytes_unchanged']
                source=next(t for t in parent['factory'] if (t['program'],t['note'],t['velocity'])==(trace['program'],trace['note'],100))
                assert set(trace['voices'])==set(source['active'])
                assert len(trace['offsets'])==4*len(trace['voices']) and len(trace['segments'])==8*len(trace['voices'])
                expected={(i,k,phase) for i in trace['voices'] for k in ['filter','amp'] for phase in ['attack','decay','slope','release']}
                assert {(s['voice'],s['kind'],s['phase']) for s in trace['segments']}==expected
                for row in trace['offsets']:
                    assert row['phase'] in ['attack','decay']
                    assert row['helper']==('decay' if row['phase']=='decay' else row['kind']+'_attack')
                    voice=next(v for v in source['voices'] if v['voice_slot']==row['voice'])
                    offset=KIT_OFFSET+source['kit']*KIT_STRIDE+24+voice['key']*68+12*voice['slot']
                    layer=sb(preload,offset+(9 if row['phase']=='decay' else 8))
                    assert row['layer']==layer and row['key']==trace['key_'+row['phase']]
                    assert row['result']==max(0,min(99,row['shared_base']+layer+row['key']-64))
                    segment=next(s for s in trace['segments'] if (s['voice'],s['kind'],s['phase'])==(row['voice'],row['kind'],row['phase']))
                    assert segment['time_index']==row['result']
                for segment in trace['segments']:
                    assert 0<=segment['time_index']<=99 and 0<=segment['curve']<=10
                    duration=core.math.eg_duration(firmware.u32(0x3FD5A4+4*segment['time_index']),segment['amount'])
                    assert segment['duration']==duration
            for traces in by_program.values():
                assert {(t['key_attack'],t['key_decay']) for t in traces}=={(a,b) for a in [0,64,127] for b in [0,64,127]}
                for voice in traces[0]['voices']:
                    for kind in ['filter','amp']:
                        for phase in ['slope','release']:
                            assert len({s['time_index'] for t in traces for s in t['segments'] if (s['voice'],s['kind'],s['phase'])==(voice,kind,phase)})==1
            figure=load(BASE/stage/'drum-eg-times-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==4104
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_drum_envelope_time_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv']['sha256']==sha(ROOT/figure['csv']['path'])
            import csv
            with (ROOT/figure['csv']['path']).open(newline='') as stream:rows=list(csv.DictReader(stream))
            expected=[dict(program=t['program'],note=t['note'],key_attack=t['key_attack'],key_decay=t['key_decay'],**s) for t in d['traces'] for s in t['segments']]
            assert rows==[{k:str(v) for k,v in row.items()} for row in expected]
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='drum-eg-live-check.json':
            assert not d['smoke_only'] and d['actual_DSP_audio_executed'] is False
            assert len(d['traces'])==d['counts']['traces']==24
            assert {(t['program'],t['note'],t['batch'],t['variant']) for t in d['traces']}=={(n,k,b,v) for n,k in [('F033',48),('F036',48),('F042',48),('F068',34)] for b in [1,3,8] for v in ['early','late']}
            parent=load(BASE/stage/'drum-voice-chain-check.json');preload=(ROOT/d['inputs'][0]['path']).read_bytes()
            from firmware_drum_voice_chain import KIT_OFFSET,KIT_STRIDE
            from firmware_factory_voice_chain import sb
            from voice_math import VoiceMath
            math_model=VoiceMath(Firmware())
            counts=dict(traces=len(d['traces']),updates=0,commits=0,offsets=0,segments=0,core_steps=0,immediate_edits=0,retriggers=0)
            for trace in d['traces']:
                src=preload[trace['source_offset']:trace['source_offset']+2140]
                assert hashlib.sha256(src).hexdigest()==trace['source_sha256']
                source=next(t for t in parent['factory'] if (t['program'],t['note'],t['velocity'])==(trace['program'],trace['note'],100))
                assert set(trace['first_voices'])==set(source['active'])
                assert len(trace['steps'])==1536 and [s['update'] for s in trace['steps']]==list(range(1536))
                assert all(s['elapsed']==[0,1,3,20][i%4] for i,s in enumerate(trace['steps']))
                assert len(trace['key_edits'])==2 and all(e['immediate_eg_bytes_unchanged'] for e in trace['key_edits'])
                assert (trace['key_edits'][0]['selector'],trace['key_edits'][0]['value'],trace['key_edits'][0]['update'])==(22,0,0)
                edit=trace['key_edits'][1];assert edit['selector']==23 and edit['value']==(48 if trace['variant']=='early' else 32)
                if trace['variant']=='early':assert edit['update']==0
                else:assert trace['retrigger_at'] is not None and trace['off_at']==trace['retrigger_at']+16
                for row in trace['offsets']:
                    key=72 if row['phase']=='attack' else 80;selector=22 if row['phase']=='attack' else 23
                    for edit in trace['key_edits']:
                        if edit['selector']==selector and edit['update']<=row['update']:key=edit['value']
                    assert row['key']==key and row['result']==max(0,min(99,row['shared_base']+row['layer']+key-64))
                    valid_layers={sb(preload,KIT_OFFSET+source['kit']*KIT_STRIDE+24+v['key']*68+12*v['slot']+(8 if row['phase']=='attack' else 9)) for v in source['voices']}
                    assert row['layer'] in valid_layers
                    assert any((s['voice'],s['kind'],s['phase'],s['update'],s['time_index'])==(row['voice'],row['kind'],row['phase'],row['update'],row['result']) for s in trace['segments'])
                for segment in trace['segments']:
                    assert 0<=segment['time_index']<=99 and 0<=segment['curve']<=10
                    assert segment['duration']==math_model.eg_duration(math_model.firmware.u32(0x3FD5A4+4*segment['time_index']),segment['amount'])
                assert sum(s['core_steps'] for s in trace['steps'])==sum(c['update']>=0 for c in trace['core_checks'])
                for c in trace['core_checks']:
                    assert c['remaining_after']==c['remaining_before']-24 and c['done']==(c['remaining_after']<=0)
                    assert -32768<=c['level']<=32767 and len(c['before_sha256'])==len(c['after_sha256'])==64
                for ack in trace['acknowledgements']:
                    assert ack['command'] in [1,2]
                    assert ack['after']==(ack['before']&~ack['mask'] if ack['command']==1 else ack['before']|ack['mask'])
                for step in trace['steps']:
                    assert all(len(v['stages'])==len(v['levels'])==len(v['remaining'])==len(v['durations'])==2 for v in step['state'])
                if trace['program']=='F042':
                    primary=trace['first_voices'][0]
                    amp=next(o for o in trace['offsets'] if o['kind']=='amp' and o['phase']=='decay' and o['voice']==primary)
                    assert amp['key']==(48 if trace['variant']=='early' else 80)
                    if trace['variant']=='early':
                        assert not any(o['kind']=='filter' and o['phase']=='decay' and o['voice']==primary for o in trace['offsets'])
                        assert any(not s['state'] for s in trace['steps'])
                    else:
                        filt=next(o for o in trace['offsets'] if o['kind']=='filter' and o['phase']=='decay' and o['voice']==primary)
                        assert filt['key']==32 and filt['update']>trace['key_edits'][1]['update']
                        assert any(o['phase']=='attack' and o['key']==0 and o['voice'] not in trace['first_voices'] for o in trace['offsets'])
                counts['updates']+=len(trace['steps']);counts['commits']+=sum(s['commits'] for s in trace['steps'])
                counts['offsets']+=len(trace['offsets']);counts['segments']+=len(trace['segments']);counts['core_steps']+=len(trace['core_checks'])
                counts['immediate_edits']+=len(trace['key_edits']);counts['retriggers']+=trace['retrigger_at'] is not None
            assert d['counts']==counts and counts['updates']==36864
            figure=load(BASE/stage/'drum-eg-live-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p)
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_drum_envelope_live_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            assert figure['csv']['sha256']==sha(ROOT/figure['csv']['path'])
            import csv
            with (ROOT/figure['csv']['path']).open(newline='') as stream:rows=list(csv.DictReader(stream))
            expected=[]
            for number,t in enumerate(d['traces']):
                for step in t['steps']:
                    for v in step['state']:
                        expected.append(dict(trace=number,program=t['program'],note=t['note'],batch=t['batch'],variant=t['variant'],update=step['update'],voice=v['voice'],pair=v['pair'],
                            filter_stage=v['stages'][0],amp_stage=v['stages'][1],filter_level=v['levels'][0],amp_level=v['levels'][1],filter_remaining=v['remaining'][0],amp_remaining=v['remaining'][1],filter_duration=v['durations'][0],amp_duration=v['durations'][1]))
            assert figure['rows']==len(rows)==len(expected) and rows==[{k:str(v) for k,v in row.items()} for row in expected]
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='drum-nrpn-live-check.json':
            assert not d['smoke_only'] and d['actual_DSP_audio_executed'] is False
            fields={20:0,21:1,22:2,23:3,24:4,25:5,26:7,28:8,29:10,30:9}
            def replay_cc(rows,configured=False):
                keys=bytearray(bytes([64]*7+[127,255,255,255,0])*128);flags=140 if configured else 0
                values={99:23,98:48,6:80} if configured else {};shadow={}
                if configured:keys[12*48+2:12*48+4]=bytes([72,80])
                for row in rows:
                    cc,value,source=row['cc'],row['value'],row['source'];before=bytes(keys);values[cc]=value
                    if source!=5:shadow[cc]=value
                    if cc in [98,99]:
                        flags=(flags&~64)|(0x88 if cc==98 else 0x84)
                        if flags&(4 if cc==98 else 8):flags&=~48
                    elif cc in [100,101]:
                        flags=(flags&127)|(0x42 if cc==100 else 0x41)
                        if flags&(1 if cc==100 else 2):flags&=~48
                    elif cc in [6,96,97] and flags&0x8C==0x8C:
                        high,key=values.get(99,0),values.get(98,0)
                        if high in fields:
                            at=12*key+fields[high];old=keys[at] if keys[at]<128 else keys[at]-256
                            keys[at]=value if cc==6 else max(0,min(127,old+(1 if cc==96 else -1)))
                    elif cc in [6,38] and flags&0x43==0x43:flags|=16 if cc==6 else 32
                    assert row['flags']==flags and row['selected_high']==values.get(99,0) and row['selected_key']==values.get(98,0)
                    assert row['live']==value and row['shadow']==shadow.get(cc,0)
                    assert row['keys_sha256']==hashlib.sha256(keys).hexdigest()
                    changes=[dict(key=i//12,field=i%12,before=a,after=b) for i,(a,b) in enumerate(zip(before,keys)) if a!=b]
                    assert row['changes']==changes
            assert [len(d['matrix'][k]) for k in ['messages','default_overrides','selector_retention']]==[1520,12,12]
            replay_cc(d['matrix']['messages']);replay_cc(d['matrix']['default_overrides']+d['matrix']['selector_retention'],True)
            assert all(not r['changes'] for r in d['matrix']['messages'][:7])
            retention=[r['changes'] for r in d['matrix']['selector_retention'] if r['changes']]
            assert [(v[0]['key'],v[0]['field'],v[0]['after']) for v in retention]==[(48,2,70),(48,3,41),(49,3,42),(49,2,43)]
            assert all(r['changes'][0]['before']==255 and r['changes'][0]['after']==0 for r in d['matrix']['default_overrides'] if r['changes'])
            assert len(d['traces'])==12 and {(t['program'],t['note'],t['batch'],t['source']) for t in d['traces']}=={(n,k,b,s) for n,k in [('F033',48),('F042',48),('F068',34)] for b in [1,8] for s in [0,5]}
            from voice_math import VoiceMath
            math_model=VoiceMath(Firmware());preload=(ROOT/d['inputs'][0]['path']).read_bytes()
            for trace in d['traces']:
                off=0x1EF220+2140*((ord(trace['program'][0])-65)*128+int(trace['program'][1:]))
                assert hashlib.sha256(preload[off:off+2140]).hexdigest()==trace['source_sha256']
                assert len(trace['steps'])==1024 and [s['update'] for s in trace['steps']]==list(range(1024))
                assert len(trace['messages'])==12 and all(r['source']==trace['source'] for r in trace['messages'])
                replay_cc(trace['messages'])
                assert len(trace['key_edits'])==2 and all(e['immediate_eg_bytes_unchanged'] for e in trace['key_edits'])
                assert trace['retrigger_at'] is not None and trace['off_at']==trace['retrigger_at']+16
                assert sum(s['core_steps'] for s in trace['steps'])==sum(c['update']>=0 for c in trace['core_checks'])
                for row in trace['core_checks']:
                    assert row['remaining_after']==row['remaining_before']-24 and row['done']==(row['remaining_after']<=0)
                for segment in trace['segments']:
                    assert segment['duration']==math_model.eg_duration(math_model.firmware.u32(0x3FD5A4+4*segment['time_index']),segment['amount'])
                for row in trace['offsets']:
                    assert row['result']==max(0,min(99,row['shared_base']+row['layer']+row['key']-64))
                    assert any((s['voice'],s['kind'],s['phase'],s['update'],s['time_index'])==(row['voice'],row['kind'],row['phase'],row['update'],row['result']) for s in trace['segments'])
            for program in ['F033','F042','F068']:
                for batch in [1,8]:
                    pair=[t for t in d['traces'] if (t['program'],t['batch'])==(program,batch)];assert [t['source'] for t in pair]==[0,5]
                    for field in ['key_edits','offsets','segments','core_checks','steps']:assert pair[0][field]==pair[1][field]
            counts=dict(matrix_messages=sum(len(v) for v in d['matrix'].values()),traces=len(d['traces']),updates=sum(len(t['steps']) for t in d['traces']),
                live_messages=sum(len(t['messages']) for t in d['traces']),commits=sum(s['commits'] for t in d['traces'] for s in t['steps']),
                core_steps=sum(len(t['core_checks']) for t in d['traces']),segments=sum(len(t['segments']) for t in d['traces']),offsets=sum(len(t['offsets']) for t in d['traces']))
            assert d['counts']==counts and counts['updates']==12288 and counts['live_messages']==144
            figure=load(BASE/stage/'drum-nrpn-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==[1544,144]
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_drum_nrpn_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            def flatten_nrpn(row,group,trace):
                return dict(group=group,trace=trace,update=row['update'],cc=row['cc'],value=row['value'],source=row['source'],flags=row['flags'],selected_high=row['selected_high'],selected_key=row['selected_key'],
                    live=row['live'],shadow=row['shadow'],keys_sha256=row['keys_sha256'],changes=json.dumps(row['changes'],sort_keys=True,separators=(',',':')))
            expected=[[flatten_nrpn(row,g,-1) for g,rows in d['matrix'].items() for row in rows],[flatten_nrpn(row,'live',i) for i,t in enumerate(d['traces']) for row in t['messages']]]
            import csv
            for path,rows in zip(figure['csv'],expected):
                assert path['sha256']==sha(ROOT/path['path'])
                with (ROOT/path['path']).open(newline='') as stream:actual=list(csv.DictReader(stream))
                assert actual==[{k:str(v) for k,v in row.items()} for row in rows]
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='eq-b2-program-check.json':
            assert not d['smoke_only'] and d['actual_DSP_audio_executed'] is False
            assert d['counts']==dict(slots=7,empty_slots=7,program_items=118,mirror_pairs=46,factory_slots=331,callbacks=6620,nonidentical_endpoint_slots=61)
            from firmware_hall_operands import visible,decode,relocated,storage
            firmware=Firmware();effect=firmware.effect(7);rom=firmware.data
            words=visible(rom[effect['code_offset']:effect['code_offset']+118*8]);initial=[firmware.u32(effect['constants_offset']+4*i) for i in range(50)]
            assert d['initial_constants']==initial and d['items']==[dict(pc=i,visible48=f'{v:012x}',**decode(v)) for i,v in enumerate(words)]
            assert d['extra_local_a_indices']==[50,51]
            assert [s['slot'] for s in d['slots']]==[s['slot'] for s in d['empty_slots']]==list(range(7))
            empty_effect=firmware.effect(0);empty_words=visible(rom[empty_effect['code_offset']:empty_effect['code_offset']+64])
            for slot,empty in zip(d['slots'],d['empty_slots']):
                index=slot['slot'];expected=[relocated(v,index) for v in words]
                if index in [5,6]:
                    for pc in [55,106]:expected[pc]=(expected[pc]-(1<<41))&((1<<48)-1)
                assert slot['program_sha256']==hashlib.sha256(storage(expected)).hexdigest()
                assert slot['mfx_modified']==([55,106] if index in [5,6] else [])
                assert empty['word0']==(0 if index in [5,6] else 8388607)
                assert empty['program_sha256']==hashlib.sha256(storage([relocated(v,index) for v in empty_words])).hexdigest()
            parent=load(BASE/stage/'parametric-eq-check.json')
            assert len(d['factory'])==len(parent['factory'])==331
            for row,old in zip(d['factory'],parent['factory']):
                slot=int(old['slot'][-1])+(4 if old['slot'].startswith('MFX') else -1)
                assert (row['program'],row['slot'],row['slot_number'],row['parameters'],row['source_sha256'])==(old['program'],old['slot'],slot,old['parameters'],old['source_sha256'])
                expected=initial+[0]*30;expected[0]=old['parameters'][0]*8388607//100;expected[1]=old['parameters'][17]*8388607//100
                for band,starts in zip(old['bands'],[[2],[12,22],[32],[37]]):
                    for start,native in zip(starts,band['native']):expected[start:start+len(native)]=native
                expected[44]=old['bands'][2]['scale'];expected[45]=old['bands'][3]['scale']
                assert row['constants']==expected and row['program_sha256']==d['slots'][slot]['program_sha256']
            assert len(d['mirrors'])==46
            for row,pc in zip(d['mirrors'],range(7,53)):
                lhs=decode(words[pc]);rhs=decode(words[pc+51]);expected=lhs.copy()
                if expected['b']!=768:expected['b']+=30
                if expected['c']==32:expected['c']=33
                assert rhs==expected and row==dict(left=pc,right=pc+51,b_left=lhs['b'],b_right=rhs['b'])
            for ref,start,end in zip(d['endpoint_references'],[12,22],[22,32]):
                uses=[x for x in d['items'] if start<=x['a']<end and (x['format']<0x5000 or x['flag2'])]
                assert ref==dict(constants=list(range(start,end)),left_items=[x['pc'] for x in uses if x['pc']<53],right_items=[x['pc'] for x in uses if x['pc']>=53],
                    left_b_fields=sorted({x['b'] for x in uses if x['pc']<53}),right_b_fields=sorted({x['b'] for x in uses if x['pc']>=53}))
            host=d['host_candidates'];assert host['kind']=='two_unverified_host_candidates' and host['actual_DSP_executed'] is False
            assert (host['frames'],host['channels'],host['frequency_points'])==(512,2,129)
            assert host['weights']==[0. if i<128 else (i-128)/128 if i<256 else 1. for i in range(512)]
            assert len(host['input'])==512 and all(len(row)==2 for row in host['input'])
            candidates=[r for r in parent['factory'] if r['bands'][1]['coefficients'][0]!=r['bands'][1]['coefficients'][1]]
            assert len(candidates)==len(host['rows'])==61
            categories={}
            def eq_transfer(c,hz):
                z=cmath.exp(-2j*math.pi*hz/48000)
                return (c[0]+c[1]*z+c[2]*z*z)/(1-c[3]*z-c[4]*z*z)
            def eq_tdf2(c,frames):
                state=[[0.,0.] for _ in range(2)];result=[]
                for frame in frames:
                    row=[]
                    for channel,x in enumerate(frame):
                        z1,z2=state[channel];y=c[0]*x+z1;state[channel]=[c[1]*x+c[3]*y+z2,c[2]*x+c[4]*y];row.append(y)
                    result.append(row)
                return result
            for row,old in zip(host['rows'],candidates):
                band=old['bands'][1];a,b=band['coefficients'];g=band['gain'];other=max(-36,min(36,g+band['delta']))
                category='both_nonnegative' if min(g,other)>=0 else 'both_negative' if max(g,other)<0 else 'cross_zero'
                assert (row['program'],row['slot'],row['source_sha256'],row['coefficients'],row['gain'],row['other_gain'],row['category'])==(old['program'],old['slot'],old['source_sha256'],[a,b],g,other,category)
                categories[category]=categories.get(category,0)+1
                assert row['feedback_words_equal']==(a[3:]==b[3:]) and row['block_sizes_equal'] and row['constant_endpoints_equal']
                assert row['parallel_transposed_reference_error']<1e-9 and row['midpoint_transposed_reference_error']<1e-9
                assert len(row['static'])==3
                for curve,w in zip(row['static'],[.25,.5,.75]):
                    assert curve['weight']==w and len(curve['curves'])==129
                    coefs=[(1-w)*x+w*y for x,y in zip(a,b)]
                    for i,v in enumerate(curve['curves']):
                        hz=20*1000**(i/128);parallel=(1-w)*eq_transfer(a,hz)+w*eq_transfer(b,hz);coefficient=eq_transfer(coefs,hz)
                        assert v['hz']==hz and abs(v['complex_difference']-abs(parallel-coefficient))<1e-12
                        assert abs(v['parallel_db']-20*math.log10(max(abs(parallel),1e-15)))<1e-11
                        assert abs(v['coefficient_db']-20*math.log10(max(abs(coefficient),1e-15)))<1e-11
                    assert curve['maximum_complex_difference']==max(v['complex_difference'] for v in curve['curves'])
                    assert curve['maximum_db_difference']==max(abs(v['parallel_db']-v['coefficient_db']) for v in curve['curves'])
                pa,pb=eq_tdf2(a,host['input']),eq_tdf2(b,host['input']);interpolated=row['dynamic_coefficient'];parallel=row['dynamic_parallel']
                assert len(parallel)==len(interpolated)==512
                for i,(x,w) in enumerate(zip(host['input'],host['weights'])):
                    c=[(1-w)*u+w*v for u,v in zip(a,b)]
                    for channel in range(2):
                        assert abs(parallel[i][channel]-((1-w)*pa[i][channel]+w*pb[i][channel]))<1e-9
                        x1=host['input'][i-1][channel] if i else 0.;x2=host['input'][i-2][channel] if i>1 else 0.
                        y1=interpolated[i-1][channel] if i else 0.;y2=interpolated[i-2][channel] if i>1 else 0.
                        expected=c[0]*x[channel]+c[1]*x1+c[2]*x2+c[3]*y1+c[4]*y2
                        assert abs(interpolated[i][channel]-expected)<1e-12
                delta=[x-y for p,q in zip(parallel,interpolated) for x,y in zip(p,q)]
                assert row['dynamic_maximum_difference']==max(map(abs,delta)) and row['dynamic_rms_difference']==math.sqrt(sum(v*v for v in delta)/1024)
            assert categories==dict(both_nonnegative=50,cross_zero=8,both_negative=3)
            figure=load(BASE/stage/'eq-b2-program-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==[118,23607,512]
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_eq_b2_program_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            program=[dict(pc=r['pc'],visible48=r['visible48'],a=r['a'],b=r['b'],c=r['c'],low=r['low'],upper=r['upper'],format=r['format'],flag2=int(r['flag2'])) for r in d['items']]
            curves=[dict(program=r['program'],slot=r['slot'],gain=r['gain'],other_gain=r['other_gain'],category=r['category'],weight=s['weight'],**v) for r in host['rows'] for s in r['static'] for v in s['curves']]
            dynamic=max(host['rows'],key=lambda r:r['dynamic_maximum_difference'])
            frames=[dict(program=dynamic['program'],slot=dynamic['slot'],frame=i,weight=w,input_left=host['input'][i][0],input_right=host['input'][i][1],parallel_left=dynamic['dynamic_parallel'][i][0],parallel_right=dynamic['dynamic_parallel'][i][1],
                coefficient_left=dynamic['dynamic_coefficient'][i][0],coefficient_right=dynamic['dynamic_coefficient'][i][1]) for i,w in enumerate(host['weights'])]
            import csv
            for file,rows in zip(figure['csv'],[program,curves,frames]):
                assert file['sha256']==sha(ROOT/file['path'])
                with (ROOT/file['path']).open(newline='') as stream:actual=list(csv.DictReader(stream))
                assert actual==[{k:str(v) for k,v in row.items()} for row in rows]
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='drum-voice-playback-check.json':
            from collections import Counter
            assert not d['smoke_only'] and not d['actual_DSP_audio_executed']
            traces=d['traces'];assert len(traces)==12
            assert {(t['program'],t['batch'],t['pattern'],t['synthetic']) for t in traces}=={
                (program,batch,index,synthetic) for program in ['F033','F042'] for batch in [4,16]
                for index,synthetic in [(799,True),(799,False),(31,False)]}
            catalog=load(BASE/stage/'drum-patterns.json')
            for t in traces:
                events=t['music_events'];assert t['dispatched']==[dict(**e,source=1) for e in events]
                assert all(e['status']&15==7 for e in events)
                ons=[(e['tick'],e['note'],e['velocity']) for e in events if e['status']&240==144]
                if t['synthetic']:
                    assert t['ticks']==3840
                    assert ons==[(0,36,90),(120,38,100),(1800,42,110),(1921,36,90),(2040,38,100),(3720,42,110)]
                    assert [(e['tick'],e['note']) for e in events if e['status']&240==128]==[(60,36),(240,38),(1920,42),(1980,36),(2160,38),(3839,42)]
                else:
                    expected=[];pattern=catalog['patterns'][t['pattern']]
                    for bar in pattern['bars']:
                        for raw in bar['events']:
                            r=bytes.fromhex(raw);tick=int.from_bytes(r[6:8],'little')
                            if tick<1920:expected.append((1920*bar['number']+tick,r[2],r[3]))
                    assert ons==expected and t['ticks']==len(pattern['bars'])*1920
                balance=Counter()
                for e in events:
                    balance[e['note']]+=1 if e['status']&240==144 else -1
                    assert balance[e['note']]>=0
                assert not any(balance.values()) and t['cleanup_available']==32
                assert t['native_zero_page_writes']==2*t['empty_unlinks']
                assert all(r['word']&65535==0 and 0<=r['slot']<32 for r in t['zero_amplitude_responses'])
                assert [s['tick'] for s in t['steps']]==list(range(0,t['ticks'],8))
                assert [s['elapsed'] for s in t['steps']]==[0]+[8]*(len(t['steps'])-1)
                for s in t['steps']:
                    assert 0<=s['active']<=32 and 0<=s['available']<=32 and s['commits']>=0
                    assert len(s['state_sha256'])==len(s['commit_sha256'])==64
                multiplicity=2 if t['program']=='F033' else 1
                assert len(t['constructed'])==multiplicity*len(ons)
                for v in t['constructed']:
                    assert (v['tick'],v['note'],v['velocity']) in ons
                    assert v['gain']==(v['gain_before'] if v['pair']==2 else v['expected_gain'])
                    assert set(v['sample_registers'])=={'0x200','0x208','0x20c','0x210'}
            counts=dict(traces=len(traces),ticks=sum(t['ticks'] for t in traces),updates=sum(len(t['steps']) for t in traces),
                music_events=sum(len(t['music_events']) for t in traces),voices=sum(len(t['constructed']) for t in traces),
                starts=sum('sample_registers' in v for t in traces for v in t['constructed']),
                commits=sum(s['commits'] for t in traces for s in t['steps']),empty_unlinks=sum(t['empty_unlinks'] for t in traces))
            assert d['counts']==counts and counts['ticks']==53760 and counts['updates']==6720
            failure=load(BASE/stage/'drum-voice-playback-feedback-failure.json')
            assert not failure['passed'] and failure['failed_tick']==6480 and not failure['actual_DSP_audio_executed']
            assert failure['tool_sha256']==sha(ROOT/failure['archived_tool'])
            figure=load(BASE/stage/'drum-voice-playback-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p)
            assert figure['rows']==[counts['music_events'],counts['voices'],counts['updates']]
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_drum_voice_playback_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            from firmware_drum_voice_playback_figures import exports
            import csv
            for file,rows in zip(figure['csv'],exports(d)):
                assert file['sha256']==sha(ROOT/file['path'])
                with (ROOT/file['path']).open(newline='') as stream:actual=list(csv.DictReader(stream))
                assert actual==[{k:str(v) for k,v in row.items()} for row in rows]
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        if result=='effect-load-state-check.json':
            import struct,csv
            from firmware_hall_operands import visible,storage
            assert not d['smoke_only'] and not d['actual_DSP_audio_executed']
            assert d['counts']==dict(effects=122,single_effects=112,double_effects=10,loads=1668,sequences=7,sequence_loads=21,excluded_zero_code=13)
            f=Firmware();effects=[f.effect(i) for i in range(135)]
            assert [r['effect'] for r in d['excluded']]==[e['id'] for e in effects if not e['code_words_64']]
            expected={(e['id'],s,b) for e in effects if e['code_words_64'] for s in (range(7) if e['code_words_64']<=124 else [0,1,2,3,5]) for b in [False,True]}
            assert {(r['effect'],r['slot'],r['buffered']) for r in d['rows']}==expected and len(d['rows'])==len(expected)
            def seed_state(seed):
                constants=[(0x91000000+0x10203*i+seed*0x10101)&0xFFFFFFFF for i in range(640)]
                program=bytearray(b''.join(struct.pack('<II',((i*17+seed)&65535)|0xA55A0000,(0x12345678+i*0x10203+seed)&0xFFFFFFFF) for i in range(1024)))
                return constants,program
            def check_load(row,constants,program):
                e=effects[row['effect']];slot=row['slot'];n=e['code_words_64'];k=e['constant_words_32'];units=1+(n>124)
                assert (row['units'],row['code_count'],row['initial_count'],row['zero_tail'])==(units,n,k,80*units-k)
                constants[80*slot:80*(slot+units)]=list(struct.unpack_from('<'+'I'*k,f.data,e['constants_offset']))+[0]*(80*units-k)
                start=32+124*slot;program[start*8:(start+n)*8]=f.data[e['code_offset']:e['code_offset']+8*n]
                cb=struct.pack('<640I',*constants)
                assert row['cpu_constants_sha256']==row['uploaded_constants_sha256']==hashlib.sha256(cb).hexdigest()
                assert row['cpu_program_container_sha256']==hashlib.sha256(program).hexdigest()
                assert row['uploaded_visible_program_sha256']==hashlib.sha256(storage(visible(program))).hexdigest()
                packets={kind:[dict(kind=kind,start=base+i,count=min(size,count-i)) for i in range(0,count,size)] for kind,base,count,size in [('program',start,n,16),('constant',80*slot,80*units,32)]}
                order=['constant','program'] if row['buffered'] else ['program','constant']
                assert row['packets']==sum([packets[kind] for kind in order],[])
                if row['buffered']:
                    state=struct.pack('<BB5h',1,1,slot,0,n-1,0,80*units-1)
                    assert row['context_before_flush']==state.hex()
                    assert row['phases']==[dict(name='constant_flush',packets=len(packets['constant']),context=state.hex()),dict(name='program_commit',packets=len(row['packets']),context=(b'\0\0'+state[2:]).hex())]
                else:assert row['context_before_flush']==bytes(12).hex() and not row['phases']
                return constants,program
            for row in d['rows']:check_load(row,*seed_state(19+row['slot']+row['effect']))
            assert [t['slot'] for t in d['sequences']]==list(range(7))
            for t in d['sequences']:
                assert [r['effect'] for r in t['steps']]==[105,7,0] and t['eq_a50_a51']==[0,0] and t['empty_tail_zero']
                state=seed_state(201+t['slot'])
                for row in t['steps']:
                    assert row['slot']==t['slot'] and row['buffered']
                    state=check_load(row,*state)
            figure=load(BASE/stage/'effect-load-state-figure-check.json')
            assert figure['passed'] and figure['source_sha256']==sha(p) and figure['rows']==[1668,21]
            assert figure['tool_sha256']==sha(ROOT/'research/tools/firmware_effect_load_state_figures.py')
            assert figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
            for name,digest in figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
            from firmware_effect_load_state_figures import exports
            for file,rows in zip(figure['csv'],exports(d)):
                assert file['sha256']==sha(ROOT/file['path'])
                with (ROOT/file['path']).open(newline='') as stream:actual=list(csv.DictReader(stream))
                assert actual==[{k:str(v) for k,v in row.items()} for row in rows]
            for row in figure['images']:assert row['sha256']==sha(ROOT/row['path'])
        checks.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p)))
    layers=load(BASE/'stage02/note-layers-check.json')['results']
    mapping=load(BASE/'stage02/factory-note-layer-map.json')
    assert mapping['firmware_sha256']==FW_SHA
    assert mapping['preload_sha256']==sha(ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all')
    both=one=neither=0;programs=set();cases=0
    for osc in mapping['oscillators']:
        assert len(osc['velocities'])==127
        index=(ord(osc['program'][0])-65)*128+int(osc['program'][1:])
        raw=(ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all').read_bytes() if cases==0 else raw
        assert hashlib.sha256(raw[0x1EF220+2140*index:0x1EF220+2140*(index+1)]).hexdigest()==osc['program_sha256']
        for r in osc['velocities']:
            if len(r['slots'])==2:
                valid=sum(bool(v) for v in r['descriptor_low_flags'])
                if valid==2:both+=1;programs.add(osc['program'])
                elif valid==1:one+=1
                else:neither+=1
            cases+=1
    assert cases==layers['factory_layer_selection']['cases']==167005
    assert (both,one,neither,len(programs))==(44446,8972,0,272)
    # Host audio references are tracked separately from original ARM modules.
    audio_path=BASE/'stage04/eq-audio-reference-check.json';audio=load(audio_path)
    assert audio['passed'] and audio['firmware_sha256']==FW_SHA and not audio['device_access']
    assert audio['tool_sha256']==sha(ROOT/'research/tools/firmware_eq_audio_reference.py')
    for row in audio['inputs']:assert row['sha256']==sha(ROOT/row['path'])
    rom=Firmware().data
    for directory,region,sample,side in [(200,2400,2445,'L'),(201,2412,2446,'R')]:
        name=rom[0x48F5CC+28*directory+4:0x48F5CC+28*directory+28].decode('ascii').rstrip(' \0')
        assert name=='Str.Ensemble 2 -'+side
        assert int.from_bytes(rom[0x492C28+20*region:0x492C28+20*region+2],'little')==sample
    assert audio['counts']==dict(factory_coefficient_sets=331,stream_frames=2048,impulse_models=5,impulse_frames=262144,frequency_points=121,audio_clips=5,audio_frames_per_clip=103340)
    native_eq=load(BASE/'stage04/parametric-eq-check.json')['factory'];assert len(audio['models'])==331
    for i,(model,native) in enumerate(zip(audio['models'],native_eq)):
        assert model['index']==i and (model['program'],model['slot'],model['source_sha256'],model['parameters'])==(native['program'],native['slot'],native['source_sha256'],native['parameters'])
        assert model['sections']==[band['coefficients'][0] for band in native['bands']]
        assert model['trim']==(native['parameters'][0]*8388607//100)/8388607
        assert model['block_sizes_equal'] and model['channels_isolated'] and model['direct_form_relative_error']<1e-7
        assert len(model['pole_radii'])==4 and max(model['pole_radii'])<1
    assert audio['max_direct_form_relative_error']==max(x['direct_form_relative_error'] for x in audio['models'])
    assert len(audio['impulses'])==5 and len({x['index'] for x in audio['impulses']})==5
    assert all(x['frames']==262144 and x['frequency_points']==121 and x['maximum_relative_complex_error']<1e-5 and math.isfinite(x['tail_peak']) for x in audio['impulses'])
    assert len(audio['curves'])==4 and {(x['low_shelf'],x['high_shelf']) for x in audio['curves']}=={(a,b) for a in [0,1] for b in [0,1]}
    for curve in audio['curves']:
        model=audio['models'][curve['index']];assert model['parameters'][4]==0 and model['parameters'][17]==100
        assert len(curve['frequencies'])==len(curve['analytic_db'])==len(curve['impulse_db'])==121
        for hz,db,impulse_db in zip(curve['frequencies'],curve['analytic_db'],curve['impulse_db']):
            z=cmath.exp(-2j*math.pi*hz/48000);response=model['trim']
            for b0,b1,b2,f1,f2 in model['sections']:response*=((b0+b1*z+b2*z*z)/(1-f1*z-f2*z*z))
            assert abs(db-20*math.log10(max(abs(response),1e-12)))<1e-8 and abs(impulse_db-db)<1e-5
    assert len(audio['clips'])==5 and {x['model_index'] for x in audio['clips'] if x['kind']=='host_eq_reference'}=={x['index'] for x in audio['curves']}
    assert len([x for x in audio['clips'] if x['kind']=='source' and x['model_index'] is None])==1
    for row in audio['clips']:
        path=ROOT/row['path'];assert row['sha256']==sha(path) and row['clipped_samples']==0
        assert (row['frames'],row['channels'],row['sample_rate'],row['sample_width'])==(103340,2,48000,3)
        assert abs(row['peak']-row['pre_export_peak']*audio['common_export_gain'])<1e-12 and row['peak']<=.9000000001
        with wave.open(str(path)) as stream:
            assert stream.getparams()[:4]==(2,3,48000,103340);raw_audio=stream.readframes(103340)
        assert len(raw_audio)==103340*6
        peak=max(abs(int.from_bytes(raw_audio[i:i+3],'little',signed=True))/2**23 for i in range(0,len(raw_audio),3))
        assert abs(peak-row['peak'])<=2**-24
    audio_figure=load(BASE/'stage04/eq-audio-reference-figure-check.json')
    assert audio_figure['passed'] and audio_figure['source_sha256']==sha(audio_path) and audio_figure['rows']==484
    assert audio_figure['tool_sha256']==sha(ROOT/'research/tools/firmware_eq_audio_figures.py')
    assert audio_figure['helper_sha256']==sha(ROOT/'research/tools/firmware_runtime_figures.py')
    for name,digest in audio_figure['additional_helpers'].items():assert digest==sha(ROOT/'research/tools'/name)
    assert audio_figure['csv_sha256']==sha(BASE/'stage04/eq-audio-reference-curves.csv')
    for row in audio_figure['images']:assert row['sha256']==sha(ROOT/row['path'])
    audio_checks=[dict(path=str(audio_path.relative_to(ROOT)),sha256=sha(audio_path))]
    link_count=0
    extra_docs=['RECORDING.md','EFFECT_EQ.md','EFFECT_EQ_AUDIO.md','EFFECT_ROUTING.md','EFFECT_LIMITERS.md','EFFECT_CHORUS.md','EFFECT_HALL.md','VOICE_LFO.md','VOICE_LFO_INPUTS.md','LFO_TARGETS.md','AMS_MIXERS.md','ENVELOPES.md','PEDAL_ENVELOPES.md','PEDAL_RELEASE_FLOW.md','FACTORY_VOICE_CHAIN.md','VOICE_REFRESH.md','DRUM_VOICE_CHAIN.md','DRUM_CONTROLS.md','GM_PROGRAMS.md','EXPANSION_PCM.md','PCM_LOOP_BOUNDARY.md','EXPANSION_VOICES.md','PROGRAM_RELOCATION.md','RESOURCE_IMPORT.md','MIDI_PARAMETERS.md','MIDI_BANKS.md','MIDI_PROGRAM_LOAD.md','MIDI_VOICE_HANDOFF.md','MIDI_VOICE_REFRESH.md','HALL_LOCAL_OPERANDS.md','MIDI_RESET.md','CHORUS_PROGRAM.md','MIDI_ALL_OFF.md','MIDI_STOP_REUSE.md','MIDI_STOP_REUSE_LIVE.md','VOICE_AUXILIARY.md','PLUGIN_REPORT.md']
    for name in ['RUNTIME_FLOW.md','VOICE_PARAMETERS.md','VOICE_RELEASE.md','VOICE_TG.md','VOICE_FAILURES.md','FACTORY_REGIONS.md','VOICE_REUSE.md','MONO_KEYS.md','UNISON.md','MUSIC_CLOCK.md','EXTERNAL_CLOCK.md','MIDI_TRANSPORT.md','EXTERNAL_TEMPO.md','SEQUENCE_TIME.md','SEQUENCE_NOTES.md','SEQUENCE_CONTROLS.md','SEQUENCE_LOOPS.md','SEQUENCE_SYSEX.md','PARAMETER_CACHE.md','PARAMETER_DISPATCH.md','PARAMETER_NOTIFICATIONS.md','MESSAGE_REPLIES.md','MMI_PARAMETERS.md','UI_TREE.md','UI_REFRESH.md','UI_BITMAP.md','UI_OCCLUSION.md','ARPEGGIATOR.md','STEP_SEQUENCER.md','DRUM_PATTERNS.md','REVERSE_STATUS.md']:
        p=DOC/name;text=p.read_text()
        assert not re.search(r'不是.{0,100}而是',text)
        for target in re.findall(r'\[[^]]*\]\(([^)]+)\)',text):
            if '://' in target:continue
            assert (p.parent/target.split('#')[0]).is_file(),target
            link_count+=1
    extra_docs.extend(['VOICE_PRESSURE.md','MONO_LIVE.md','MASTER_LIMITER_KERNEL.md'])
    for name in extra_docs:
        p=DOC/name;text=p.read_text()
        assert not re.search(r'不是.{0,100}而是',text)
        for target in re.findall(r'\[[^]]*\]\(([^)]+)\)',text):
            if '://' in target:continue
            assert (p.parent/target.split('#')[0]).is_file(),target
            link_count+=1
    # The published stage01 PDF remains matched to its own source and renderer.
    paper=load(BASE/'stage01/report-check.json')
    assert paper['markdown_sha256']==sha(DOC/'REPORT.md')
    assert paper['pdf_sha256']==sha(DOC/'KROSS2-v1.2.4-architecture-report.pdf')
    assert paper['generator_sha256']==sha(ROOT/'research/tools/firmware_architecture_report.py')
    plugin_paper=None
    if not args.evidence_only:
        plugin_paper=load(BASE/'stage05/plugin-report-check.json')
        assert plugin_paper['passed'] and plugin_paper['pages']==10
        assert plugin_paper['visual_review']['passed'] and len(plugin_paper['visual_review']['pages'])==10
        assert plugin_paper['visual_review']['pdf_sha256']==plugin_paper['pdf']['sha256']
        assert plugin_paper['arm_checks']==checks
        assert plugin_paper['host_audio_checks']==audio_checks
        assert plugin_paper['tool_sha256']==sha(ROOT/'research/tools/firmware_plugin_report.py')
        assert plugin_paper['font_helper_sha256']==sha(ROOT/'research/tools/firmware_architecture_report.py')
        for row in [plugin_paper['pdf'],plugin_paper['markdown']]+plugin_paper['images']+plugin_paper['references']+plugin_paper['visual_review']['pages']:
            assert row['sha256']==sha(ROOT/row['path']),row['path']
    result=dict(passed=True,firmware_sha256=FW_SHA,protected_files=len(protected['files']),
        protected_product_unchanged=True,current_checks=checks,host_audio_checks=audio_checks,document_links_checked=link_count,
        factory_map_cases=cases,factory_two_candidate_flags=dict(both_valid=both,one_valid=one,neither_valid=neither,programs_both_valid=len(programs)),
        stage01_paper_unchanged=True,current_paper_verified=not args.evidence_only,device_access=False,tool_sha256=sha(Path(__file__)))
    (BASE/'stage02/verification.json').write_text(json.dumps(result,indent=2)+'\n')
    paths=list((BASE/'stage02').glob('*'))+list((BASE/'stage03').glob('*'))+list((BASE/'stage04').glob('*'))
    paths += [ROOT/'research/tools/firmware_effect_load_state.py',ROOT/'research/tools/firmware_effect_load_state_figures.py',DOC/'EFFECT_LOAD_STATE.md']+list((DOC/'figures').glob('effect-load-state.*'))
    paths += [ROOT/'research/tools/firmware_drum_voice_playback.py',ROOT/'research/tools/firmware_drum_voice_playback_figures.py',DOC/'DRUM_VOICE_PLAYBACK.md']+list((DOC/'figures').glob('drum-voice-playback.*'))
    paths += [ROOT/'research/tools/firmware_eq_b2_program.py',ROOT/'research/tools/firmware_eq_b2_program_figures.py',DOC/'EQ_B2_PROGRAM.md']+list((DOC/'figures').glob('eq-b2-program.*'))
    paths += [ROOT/'research/tools/firmware_drum_nrpn_live.py',ROOT/'research/tools/firmware_drum_nrpn_figures.py',DOC/'DRUM_NRPN_LIVE.md']+list((DOC/'figures').glob('drum-nrpn-state.*'))
    paths += [ROOT/'research/tools/firmware_drum_envelope_live.py',ROOT/'research/tools/firmware_drum_envelope_live_figures.py',DOC/'DRUM_ENVELOPE_LIVE.md']+list((DOC/'figures').glob('drum-eg-live.*'))
    paths += [ROOT/'research/tools/firmware_drum_envelope_times.py',ROOT/'research/tools/firmware_drum_envelope_time_figures.py',DOC/'DRUM_ENVELOPE_TIMES.md']+list((DOC/'figures').glob('drum-eg-time-offsets.*'))
    paths += [ROOT/'research/tools/firmware_master_kernel.py',ROOT/'research/tools/firmware_master_kernel_figures.py',DOC/'MASTER_LIMITER_KERNEL.md']+list((DOC/'figures').glob('master-limiter-window.*'))
    paths += [ROOT/'research/tools/firmware_mono_live.py',ROOT/'research/tools/firmware_mono_live_figures.py',DOC/'MONO_LIVE.md']+list((DOC/'figures').glob('mono-live.*'))
    paths += [ROOT/'research/tools/firmware_voice_pressure.py',ROOT/'research/tools/firmware_voice_pressure_figures.py',DOC/'VOICE_PRESSURE.md']+list((DOC/'figures').glob('voice-pressure.*'))
    paths += [ROOT/'research/tools/firmware_pcm_loop.py',ROOT/'research/tools/firmware_pcm_loop.c',ROOT/'research/tools/firmware_pcm_loop_figures.py',DOC/'PCM_LOOP_BOUNDARY.md']+list((DOC/'figures').glob('pcm-loop-hypotheses.*'))
    paths += [ROOT/'research/tools/firmware_resource_import.py',ROOT/'research/tools/firmware_resource_import_figures.py',DOC/'RESOURCE_IMPORT.md']+list((DOC/'figures').glob('resource-import-placement.*'))
    paths += [ROOT/'research/tools/firmware_eq_audio_reference.py',ROOT/'research/tools/firmware_eq_audio_figures.py',DOC/'EFFECT_EQ_AUDIO.md']
    paths += list((DOC/'figures').glob('eq-audio-reference.*'))+[ROOT/row['path'] for row in audio['clips']]
    if plugin_paper:paths+=list((BASE/'stage05').rglob('*'))+[ROOT/plugin_paper['pdf']['path'],DOC/'PLUGIN_REPORT.md',ROOT/'research/tools/firmware_plugin_report.py']
    paths+=list((DOC/'figures').glob('plugin-*.*'))
    paths += [DOC/n for n in ['RUNTIME_FLOW.md','VOICE_PARAMETERS.md','VOICE_RELEASE.md','VOICE_TG.md','VOICE_FAILURES.md','FACTORY_REGIONS.md','VOICE_REUSE.md','MONO_KEYS.md','UNISON.md','MUSIC_CLOCK.md','EXTERNAL_CLOCK.md','MIDI_TRANSPORT.md','EXTERNAL_TEMPO.md','SEQUENCE_TIME.md','SEQUENCE_NOTES.md','SEQUENCE_CONTROLS.md','SEQUENCE_LOOPS.md','SEQUENCE_SYSEX.md','PARAMETER_CACHE.md','PARAMETER_DISPATCH.md','PARAMETER_NOTIFICATIONS.md','MESSAGE_REPLIES.md','MMI_PARAMETERS.md','UI_TREE.md','UI_REFRESH.md','UI_BITMAP.md','UI_OCCLUSION.md','ARPEGGIATOR.md','STEP_SEQUENCER.md','DRUM_PATTERNS.md','REVERSE_STATUS.md']]
    paths += list((DOC/'figures').glob('note-runtime-flow.*'))+list((DOC/'figures').glob('velocity-crossfade.*'))
    paths += list((DOC/'figures').glob('voice-lifecycle.*'))
    paths += list((DOC/'figures').glob('portamento-modes.*'))
    paths += list((DOC/'figures').glob('mono-key-priority.*'))+list((DOC/'figures').glob('unison-spread.*'))
    paths += list((DOC/'figures').glob('music-clock-counts.*'))+list((DOC/'figures').glob('music-clock-delay.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_runtime_flow.py','firmware_note_layers.py','firmware_voice_parameters.py','firmware_runtime_figures.py','firmware_runtime_verify.py']]
    paths += [ROOT/'research/tools'/n for n in ['firmware_voice_release.py','firmware_voice_start.py','firmware_voice_tg.py','firmware_voice_failures.py','firmware_voice_figures.py']]
    paths += [ROOT/'research/tools'/n for n in ['firmware_factory_regions.py','firmware_voice_reuse.py']]
    paths += [ROOT/'research/tools'/n for n in ['firmware_mono_keys.py','firmware_unison.py','firmware_mono_figures.py','firmware_portamento_gate.py']]
    paths += [ROOT/'research/tools'/n for n in ['firmware_music_clock.py','firmware_music_clock_figures.py','firmware_external_clock.py','firmware_external_clock_figures.py']]
    paths += list((DOC/'figures').glob('external-clock-path.*'))+list((DOC/'figures').glob('external-clock-auto.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_transport.py','firmware_external_tempo.py','firmware_transport_figures.py']]
    paths += list((DOC/'figures').glob('transport-deferred.*'))+list((DOC/'figures').glob('external-tempo-readback.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_sequence_time.py','firmware_sequence_time_figures.py']]
    paths += list((DOC/'figures').glob('song-position-meter.*'))+list((DOC/'figures').glob('tempo-track-events.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_sequence_notes.py','firmware_sequence_notes_figures.py']]
    paths += list((DOC/'figures').glob('sequence-note-path.*'))+list((DOC/'figures').glob('sequence-note-ties.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_sequence_controls.py','firmware_sequence_controls_figures.py']]
    paths += list((DOC/'figures').glob('sequence-control-cache.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_sequence_loops.py','firmware_sequence_loops_figures.py']]
    paths += list((DOC/'figures').glob('sequence-loop-bars.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_sequence_sysex.py','firmware_sequence_sysex_figures.py']]
    paths += list((DOC/'figures').glob('sequence-sysex-blocks.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_parameter_cache.py','firmware_parameter_cache_figures.py','firmware_parameter_dispatch.py','firmware_parameter_dispatch_figures.py']]
    paths += list((DOC/'figures').glob('parameter-cache-queue.*'))+list((DOC/'figures').glob('parameter-dispatch.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_parameter_notifications.py','firmware_parameter_notifications_figures.py']]
    paths += list((DOC/'figures').glob('parameter-song-sync.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_message_replies.py','firmware_message_replies_figures.py']]
    paths += list((DOC/'figures').glob('parameter-message-handoff.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_mmi_parameters.py','firmware_mmi_parameters_figures.py']]
    paths += list((DOC/'figures').glob('mmi-parameter-update.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_ui_tree.py','firmware_ui_refresh.py','firmware_ui_figures.py']]
    paths += list((DOC/'figures').glob('ui-tree-order.*'))+list((DOC/'figures').glob('ui-refresh-path.*'))
    paths += [ROOT/'research/tools/firmware_ui_bitmap.py']+list((DOC/'figures').glob('ui-bitmap-operations.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_ui_occlusion.py','firmware_ui_occlusion_figures.py']]
    paths += list((DOC/'figures').glob('ui-occlusion-regions.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_arpeggiator.py','firmware_arpeggiator_figures.py']]
    paths += list((DOC/'figures').glob('arpeggio-logic.*'))+list((DOC/'figures').glob('arpeggio-timing.*'))
    paths += [ROOT/'research/tools/firmware_arpeggio_sync.py']
    paths += list((DOC/'figures').glob('arpeggio-presets.*'))+list((DOC/'figures').glob('arpeggio-dual-sync.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_step_sequencer.py','firmware_step_figures.py']]
    paths += list((DOC/'figures').glob('step-start-stop.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_drum_patterns.py','firmware_drum_pattern_figures.py']]
    paths += [ROOT/'research/tools/firmware_drum_trigger.py']
    paths += [ROOT/'research/tools/firmware_drum_playback.py']
    paths += [ROOT/'research/tools/firmware_drum_integration.py']
    paths += [ROOT/'research/tools/firmware_music_interlock.py']+list((DOC/'figures').glob('music-interlock.*'))
    paths += [ROOT/'research/tools/firmware_step_context.py']
    paths += [ROOT/'research/tools/firmware_step_live_write.py']+list((DOC/'figures').glob('step-edit-commit.*'))
    paths += [DOC/n for n in extra_docs]
    paths += [ROOT/'research/tools'/n for n in ['firmware_record_intake.py','firmware_record_figures.py']]+list((DOC/'figures').glob('record-intake.*'))
    paths += [ROOT/'research/tools/firmware_record_notes.py']+list((DOC/'figures').glob('record-note-pair.*'))
    paths += [ROOT/'research/tools/firmware_record_bars.py']+list((DOC/'figures').glob('record-held-bars.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_parametric_eq.py','firmware_parametric_eq_figures.py']]
    paths += list((DOC/'figures').glob('p4eq-coefficient-scale.*'))+list((DOC/'figures').glob('p4eq-shelves.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_effect_routing.py','firmware_effect_routing_figures.py']]
    paths += list((DOC/'figures').glob('effects-program-routing.*'))+list((DOC/'figures').glob('effects-route-transitions.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_limiters.py','firmware_limiter_figures.py']]
    paths += list((DOC/'figures').glob('limiter-control-maps.*'))+list((DOC/'figures').glob('mastering-release-map.*'))+list((DOC/'figures').glob('limiter-sidechain-eq.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_chorus.py','firmware_chorus_figures.py']]
    paths += list((DOC/'figures').glob('chorus-delay-rate.*'))+list((DOC/'figures').glob('chorus-signed-mix.*'))+list((DOC/'figures').glob('chorus-pre-eq-cap.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_hall.py','firmware_hall_figures.py']]
    paths += list((DOC/'figures').glob('hall-delay-intervals.*'))+list((DOC/'figures').glob('hall-decay-damping.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_voice_lfo.py','firmware_voice_lfo_figures.py']]
    paths += list((DOC/'figures').glob('voice-lfo-periodic.*'))+list((DOC/'figures').glob('voice-lfo-random.*'))+list((DOC/'figures').glob('voice-lfo-fade-ams.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_voice_lfo_integration.py','firmware_voice_lfo_input_figures.py']]
    paths += list((DOC/'figures').glob('voice-lfo-rate-factors.*'))+list((DOC/'figures').glob('voice-lfo-rate-path.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_lfo_targets.py','firmware_lfo_target_figures.py']]
    paths += list((DOC/'figures').glob('lfo-target-pitch-depth.*'))+list((DOC/'figures').glob('lfo-target-fade-paths.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_ams_mixers.py','firmware_ams_mixer_figures.py']]
    paths += list((DOC/'figures').glob('ams-mixer-smoothing.*'))+list((DOC/'figures').glob('ams-mixer-shape-quantize.*'))+list((DOC/'figures').glob('ams-mixer-gate.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_envelopes.py','firmware_envelope_figures.py']]
    paths += list((DOC/'figures').glob('envelope-lifecycle.*'))+list((DOC/'figures').glob('envelope-time-modulation.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_pedal_envelopes.py','firmware_pedal_envelope_figures.py']]
    paths += list((DOC/'figures').glob('pedal-release-scales.*'))+list((DOC/'figures').glob('pedal-auxiliary-cycles.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_pedal_release_flow.py','firmware_pedal_release_figures.py']]
    paths += list((DOC/'figures').glob('pedal-release-handoff.*'))+list((DOC/'figures').glob('pedal-release-holds.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_factory_voice_chain.py','firmware_factory_voice_figures.py']]
    paths += list((DOC/'figures').glob('factory-voice-stereo-chain.*'))+list((DOC/'figures').glob('factory-voice-overlaps.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_voice_refresh.py','firmware_voice_refresh_figures.py']]
    paths += list((DOC/'figures').glob('voice-refresh-cadence.*'))+list((DOC/'figures').glob('voice-refresh-smoothing.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_drum_voice_chain.py','firmware_drum_voice_figures.py']]
    paths += list((DOC/'figures').glob('drum-voice-resource-path.*'))+list((DOC/'figures').glob('drum-voice-choke-release.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_drum_controls.py','firmware_drum_control_figures.py']]
    paths += list((DOC/'figures').glob('drum-control-pan.*'))+list((DOC/'figures').glob('drum-control-timing.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_gm_programs.py','firmware_gm_figures.py']]
    paths += list((DOC/'figures').glob('gm-bank-fallback.*'))+list((DOC/'figures').glob('gm-drum-low-keys.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_expansion_pcm.py','firmware_expansion_figures.py']]+exported_paths
    paths += [ROOT/'research/tools'/n for n in ['firmware_program_relocation.py','firmware_program_relocation_figures.py']]
    paths += [ROOT/'research/tools'/n for n in ['firmware_midi_parameters.py','firmware_midi_banks.py','firmware_midi_parameter_figures.py','firmware_midi_program_load.py','firmware_midi_voice_handoff.py','firmware_midi_handoff_figures.py','firmware_midi_voice_refresh.py','firmware_midi_refresh_figures.py','firmware_hall_operands.py','firmware_hall_operand_figures.py','firmware_midi_reset.py','firmware_midi_reset_figures.py','firmware_chorus_program.py','firmware_chorus_program_figures.py','firmware_midi_all_off.py','firmware_midi_all_off_figures.py','firmware_stop_reuse.py','firmware_stop_reuse_port.py','firmware_stop_reuse_figures.py','firmware_stop_reuse_live.py','firmware_stop_reuse_live_figures.py','firmware_voice_auxiliary.py','firmware_voice_auxiliary_figures.py']]
    paths += list((DOC/'figures').glob('stop-reuse-boundaries.*'))+list((DOC/'figures').glob('stop-reuse-live.*'))
    paths += list((DOC/'figures').glob('voice-auxiliary-omission.*'))
    paths += list((DOC/'figures').glob('midi-all-off-behavior.*'))
    paths += list((DOC/'figures').glob('chorus-program-references.*'))
    paths += list((DOC/'figures').glob('midi-reset-state.*'))
    paths += list((DOC/'figures').glob('hall-reference-order.*'))
    paths += list((DOC/'figures').glob('midi-voice-refresh.*'))
    paths += list((DOC/'figures').glob('midi-voice-handoff.*'))
    paths += list((DOC/'figures').glob('midi-tuning-bend.*'))+list((DOC/'figures').glob('midi-bank-mapping.*'))
    paths += list((DOC/'figures').glob('program-reference-relocation.*'))
    paths += [ROOT/'research/tools'/n for n in ['firmware_expansion_voices.py','firmware_expansion_voice_figures.py']]
    paths += list((DOC/'figures').glob('expansion-voice-startup.*'))+list((DOC/'figures').glob('expansion-voice-kit-links.*'))
    paths += list((DOC/'figures').glob('expansion-resource-banks.*'))+list((DOC/'figures').glob('expansion-drum-dependencies.*'))
    paths += list((DOC/'figures').glob('drum-playback-loop.*'))
    paths += list((DOC/'figures').glob('drum-pattern-pool.*'))
    rows=[dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(paths) if p.is_file() and p.name!='manifest.json']
    (BASE/'stage02/manifest.json').write_text(json.dumps(dict(firmware_sha256=FW_SHA,files=rows),indent=2)+'\n')
    print(json.dumps(dict(passed=True,protected_files=len(protected['files']),artifacts=len(rows),current_ARM_checks=len(checks),factory_cases=cases),indent=2))
if __name__=='__main__':main()
