#!/usr/bin/env python3
"""Verify research provenance and exported catalogs without running firmware."""
import hashlib
import json
import struct
from pathlib import Path

from layout import ROOT
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    inputs=json.loads((ROOT/'research/assets.json').read_text())['assets']
    for item in inputs:
        path=ROOT/item['path']
        assert path.stat().st_size==item['bytes'] and digest(path)==item['sha256'],path
    folder=ROOT/'research/derived/firmware/KROSS2_V124'
    verification=ROOT/'research/derived/verification'
    reports={name:json.loads((verification/name).read_text()) for name in (
        'voice-math-arm-comparison.json','concert-voice-arm-comparison.json',
        'effects-catalog-arm-comparison.json','program-arm-comparison.json',
        'voice-timing-arm-comparison.json','concert-filter-arm-comparison.json')}
    firmware_sha=digest(folder/'KROSSAPP.bin')
    for name,report in reports.items():
        assert report['firmware_sha256']==firmware_sha,name
        for tool,expected in report.get('tool_sha256',{}).items():
            assert digest(ROOT/'tools'/tool)==expected,(name,tool,'stale report')
    timing=reports['voice-timing-arm-comparison.json']
    assert timing['all_voices_visited_once'] and timing['voices_per_slice']*timing['slices_per_round']==120
    assert timing['kernel_sleep_at_clock_100_wait_1_deadline']==102
    assert timing['nominal_voice_control_period_seconds']==0.016
    assert len(timing['TG_command_cases'])==28
    assert timing['TG_reciprocal_table']==[65535]+[65535//(32*n) for n in range(1,25)]
    filters=reports['concert-filter-arm-comparison.json']
    for name in ('map','traces'):assert digest(ROOT/filters[name]['path'])==filters[name]['sha256']
    assert filters['context_count']==32512 and filters['raw_parameter_mutations']==400
    analysis=json.loads((ROOT/'output/kep-analysis/Concert_SE_Grand/program-analysis.json').read_text())
    for osc in analysis['oscillators']:
        for branch,key in (('A','filter_a'),('B','filter_b')):
            values={f['name']:f['value'] for f in osc['groups'][key]}
            for field,value in filters['corrected_factory_fields'][branch].items():assert values[field]==value
            # Consumers show Mixer2 on B output, not its cutoff; lock the
            # corrected semantic grouping as well as the unchanged raw values.
            expected=dict(cutoff_ams1_source=14,cutoff_ams1_intensity=15 if branch=='A' else 61,
                          cutoff_ams2_source=19 if branch=='A' else 14,cutoff_ams2_intensity=21 if branch=='A' else 13,
                          output_ams_source=14 if branch=='A' else 2,output_ams_intensity=0 if branch=='A' else 99)
            for field,value in expected.items():assert values[field]==value,(branch,field)
    catalog=json.loads((folder/'catalog/effects.json').read_text())
    assert catalog['firmware_sha256']==firmware_sha and len(catalog['effects'])==135
    for effect in catalog['effects']:
        for record in effect['assets'].values():
            path=ROOT/record['path']
            assert path.stat().st_size==record['bytes'] and digest(path)==record['sha256'],path
        assert len(effect['parameters'])==len({p['index'] for p in effect['parameters']})
    controls=json.loads((folder/'voice/concert-controls.json').read_text())
    raw=(folder/'voice'/controls['map']['file']).read_bytes()
    assert raw[:8]==b'K2CTR01\x00' and struct.unpack_from('<4I',raw,8)==(2,128,127,20)
    assert len(raw)==24+2*128*127*20==controls['map']['bytes']
    assert hashlib.sha256(raw).hexdigest()==controls['map']['sha256']
    assert controls['map']['sha256']==reports['concert-voice-arm-comparison.json']['map_sha256']
    assert controls['program_sha256']==digest(ROOT/'output/kep-analysis/Concert_SE_Grand/program.bin')
    for tool,expected in controls['tool_sha256'].items():assert digest(ROOT/'tools'/tool)==expected
    index=json.loads((folder/'catalog/index.json').read_text())
    assert index['firmware_sha256']==firmware_sha
    for table in index['tables']:
        if table['bytes'] is not None:assert digest(folder/'catalog'/(table['name']+'.bin'))==table['sha256']
    factory_report=verification/'factory-sound-catalog-check.json'
    if factory_report.exists():
        factory=json.loads(factory_report.read_text())
        assert factory['firmware_sha256']==firmware_sha
        for tool,expected in factory['tool_sha256'].items():assert digest(ROOT/'tools'/tool)==expected
        for path,expected in factory['output_sha256'].items():assert digest(ROOT/path)==expected
        preset_data=json.loads((folder/'sounds/factory/programs.json').read_text())
        source=ROOT/preset_data['recovered_preload']['path'];raw=source.read_bytes()
        assert digest(source)==preset_data['recovered_preload']['sha256']
        assert digest(ROOT/preset_data['source_pdf'])==preset_data['source_pdf_sha256']
        programs=[p for p in preset_data['programs'] if p['kind']=='factory_A_F']
        assert len(programs)==768 and factory['recovered_preload']['ARM_parameter_getter_comparisons']==768*1042
        assert sum(len(e['parameters']) for p in programs for e in p['effects'])==factory['recovered_preload']['ARM_effect_parameter_comparisons']
        for p in programs:
            b=(ROOT/p['program_file']).read_bytes();off=p['program_source_offset']
            assert len(b)==2140 and b==raw[off:off+2140] and digest(ROOT/p['program_file'])==p['program_sha256']
        assert factory['ARM_bank_selector_cases']==12 and factory['ARM_ROM_pointer_and_count_getters']==2
    result={'firmware_sha256':firmware_sha,'unchanged_input_assets':len(inputs),
            'effect_definitions':len(catalog['effects']),'effect_parameters':sum(len(e['parameters']) for e in catalog['effects']),
            'effect_getter_comparisons':reports['effects-catalog-arm-comparison.json']['parameter_getter_comparisons'],
            'voice_sweep_points':controls['sweep_points'],
            'oscillator_group_alignment_checks':reports['program-arm-comparison.json']['oscillator_semantic_group_alignment_checks'],
            'named_or_control_entries':len(index['symbols']),'indexed_source_paths':len(index['source_paths']),
            'indexed_tables':len(index['tables']),
            'voice_math_counts':reports['voice-math-arm-comparison.json']['counts'],
            'nominal_control_period_seconds':timing['nominal_voice_control_period_seconds'],
            'TG_ARM_command_comparisons':len(timing['TG_command_cases']),
            'filter_ARM_contexts':filters['context_count'],
            'filter_ARM_trace_steps':filters['trace_steps_compared'],
            'filter_ARM_command_comparisons':len(filters['TG_filter_commands']),
            'factory_Programs_recovered':768 if factory_report.exists() else 0,
            'factory_ARM_parameter_comparisons':factory['recovered_preload']['ARM_parameter_getter_comparisons'] if factory_report.exists() else 0,
            'report_sha256':{name:digest(verification/name) for name in reports},
            'scope':'Offline provenance/integrity check plus recorded ARM comparison results; no audio/hardware fidelity claim'}
    (verification/'firmware-research-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS',json.dumps(result,indent=2))


if __name__=='__main__':main()
