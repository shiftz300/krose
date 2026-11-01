#!/usr/bin/env python3
"""Export factory Program Amp EG release times/curves for the static preview.

Release-time AMS is exported with original lookup tables. Earlier EG stages
and the hardware TG gain transfer are not reproduced. Existing verified integer curve math is reused.
"""
import hashlib
import json
import math
import struct

from program_firmware import Firmware, ROOT
from voice_math import VoiceMath, EnvelopeSegment
from decode_factory_rom import DERIVED, save


def build_releases():
    source=ROOT/'research/derived/firmware/KROSS2_V124/sounds/factory/programs.json'
    factory=json.loads(source.read_text())
    catalog=json.loads((ROOT/'output/Factory_Sound_Selection/rom-sound-catalog.json').read_text())
    fw=Firmware();vm=VoiceMath(fw)
    assert hashlib.sha256(fw.data).hexdigest()==factory['firmware_sha256']
    programs={p['bank_program']:p for p in factory['programs'] if p['kind']=='factory_A_F'}
    waves={w['id']:set(w['indices']) for w in catalog['waveforms']}
    profiles={};mappings={};provenance={};configs={};unresolved=[]
    for p in catalog['programs']:
        source_program=programs[p['id']]
        raw=(ROOT/source_program['program_file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==source_program['program_sha256']
        mapping={};origins={};program_configs={}
        for wave_id in p['waveform_ids']:
            candidates=[o for o in source_program['oscillators'] if o['active'] and any(waves[wave_id].intersection(s['ROM_multisample_indices']) for s in o['slots'])]
            if not candidates:continue
            # Preview plays one selected waveform, not the full layered Program.
            osc=candidates[0];eg=osc['groups']['amp_eg'];index=eg['release_time'];curve=eg['curve_release'];key=f'{index}:{curve}'
            eg_offset=0x564+380*(osc['oscillator']-1)+0x118
            assert raw[eg_offset+7]==index and raw[eg_offset+11]==curve
            if key not in profiles:
                segment=EnvelopeSegment(vm,32767,0,index,0,curve,stage=8)
                units=segment.total;steps=max(1,math.ceil(units/24));values=[1.0]
                for _ in range(steps):
                    level,done=segment.step();values.append(round(max(0,min(1,level/32767)),7))
                assert done
                values[-1]=0.0
                profiles[key]=dict(time_index=index,curve_index=curve,base_seconds=units/1500,
                                   seconds=steps*.016,values=values)
            mapping[wave_id]=key
            origins[wave_id]=dict(oscillator=osc['oscillator'],matching_oscillators=[o['oscillator'] for o in candidates],
                                  release_time=index,curve_release=curve,
                                  time_ams=[{'source':eg[f'time_ams_source_{i}'],'intensity':eg[f'time_ams_{i}_release']} for i in (1,2,3)])
            base=0x564+380*(osc['oscillator']-1)
            ams=origins[wave_id]['time_ams']
            tracking=[list(vm.keyboard_tracking(raw[offset:offset+7],note,amp) for note in range(128)) for offset,amp in [(base+0xFC,False),(base+0x13C,True),(0x554,False),(0x55C,False)]]
            mixers=[list(raw[base+offset:base+offset+24]) for offset in (0x14C,0x164)]
            program_configs[wave_id]=dict(base_units=fw.u32(0x3FD5A4+index*4),curve=curve,time_ams=ams,tracking=tracking,mixers=mixers)
            if any(entry['intensity'] and entry['source']==8 for entry in ams):
                lfo=raw[0x53c:0x554]
                # Only E043 currently uses Common LFO directly for release time.
                # Its unshaped triangle is tempo synchronized, with no speed AMS.
                assert lfo[16]==0 and lfo[4]&128 and lfo[8:16]==bytes([19,0,0,0,0,0,0,0]) and lfo[19:23]==bytes(4)
                period=struct.unpack_from('<H',fw.data,fw.pointer(0x2c4df4)+(lfo[4]&15)*2)[0]*lfo[5]
                program_configs[wave_id]['common_lfo']={'period_ticks':period,'ticks_per_quarter':480,'waveform':0}

            def check_source(source,seen=()):
                assert source not in seen, ('Circular release mixer',p['id'],source)
                if source in (1,2):
                    m=mixers[source-1];kind=m[0]&7
                    assert kind in (0,1,2)
                    if kind==2:check_source(m[1],seen+(source,))
                    else:
                        if m[2] or kind==1 and m[4]:check_source(m[1],seen+(source,))
                        if m[4]:check_source(m[3],seen+(source,))
                else:
                    assert source==0 or 9<=source<=45 or source==8 and 'common_lfo' in program_configs[wave_id], ('Unported release AMS',p['id'],source)
            for entry in ams:
                if entry['intensity']:check_source(entry['source'])
        configs[p['id']]=program_configs
        mappings[p['id']]=mapping
        provenance[p['id']]=dict(program_sha256=source_program['program_sha256'],waveforms=origins)
    tables={name:list(struct.unpack_from('<'+str(count)+kind,fw.data,offset)) for name,offset,count,kind in [
        ('short',0x3FD734,640*11,'I'),('medium',0x404534,91*11,'I'),('long',0x4054D8,22,'I'),
        ('asymptote',0x405830,11,'I'),('expFraction',0x4076E4,256,'H'),('expVelocity',0x405F08,128,'h')]}
    return dict(ams_configs=configs,ams_tables=tables,unresolved=unresolved,profiles=profiles,programs=mappings,provenance=provenance,
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),firmware_sha256=factory['firmware_sha256'],
                scope='Factory base Amp EG release time and integer curve; 16ms control cadence with browser linear interpolation. First matching active OSC for selected waveform; release-time AMS from original source IDs/intensities, static tracking and mixer types 0/1/2; unsupported internal generators listed in unresolved. No full Program layering, earlier EG stages or TG audio gain model. Drum kits retain one-shot behavior.')


def main():
    result=build_releases();save(DERIVED/'web-releases.json',result)
    print(f"Exported {len(result['programs'])} Programs, {len(result['profiles'])} release profiles")


if __name__=='__main__':main()
