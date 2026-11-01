#!/usr/bin/env python3
"""Generate a conservative, searchable v1.2.4 ARM research index.

Direct branch/literal scans are candidates, not automatic function recovery.
Only explicitly named entries have curated semantics; indirect edges remain
unresolved and linear excerpts never imply exact function boundaries.
"""
import argparse
import collections
import csv
import hashlib
import json
import re
import struct

from program_firmware import Firmware, ROOT, BASE, FW_SHA
from firmware_inspect import inspect

SYMBOLS={
    0x57C1C:('shared_math_constructor','verified helper'),
    0x60F70:('filter_math_constructor','verified helper'),
    0x5A51C:('effect_buffered_loader','verified helper'),
    0x12DAAC:('TG_program_upload_48bit','verified transport'),
    0x12DBC4:('TG_constant_upload_32bit','verified transport'),
    0x1F6958:('pcm_voice_initialize','static interpretation'),
    0x1F8140:('pcm_voice_control_advance','static interpretation'),
    0x1F8608:('voice_AMS_dispatch','partly executed'),
    0x1F9DD4:('amp_gain_update','original synthetic voice sweeps; TG output unverified'),
    0x1FA1A0:('amp_gain_initialize','original synthetic voice sweeps; velocity factor independently checked'),
    0x1FA300:('amp_EG_initialize','partly executed'),
    0x1FA664:('amp_EG_release','static interpretation'),
    0x1FA6C0:('amp_EG_next_stage','static interpretation'),
    0x1FA828:('amp_EG_advance','static interpretation'),
    0x1FA928:('amp_EG_attack_setup','static interpretation'),
    0x1FAB3C:('EG_curve_coefficient','ARM comparison passed'),
    0x1FAC24:('EG_segment_advance','ARM comparison passed without pedal scaling'),
    0x1FAED0:('EG_level_AMS_clamped','ARM comparison passed with source injection'),
    0x1FAF3C:('EG_set_segment_target','ARM comparison passed'),
    0x1FB02C:('EG_time_modulation','ARM comparison passed'),
    0x1FB0AC:('EG_prepare_segment','ARM comparison passed'),
    0x1FB8C4:('filter_EG_initialize','static interpretation'),
    0x1FBAF8:('filter_EG_next_stage','static interpretation'),
    0x1FB250:('filter_keyboard_tracking_scale','ARM filter sweep and raw parameter mutations'),
    0x1FB284:('filter_cutoff_control_quantize','ARM filter sweep; not Hz'),
    0x1FB2B0:('filter_cutoff_EG_AMS_update','32512 original contexts and trace comparison'),
    0x1FB3A4:('filter_resonance_trim_output_update','ARM controls and raw-field mutations'),
    0x1FB4B0:('filter_pair_control_update','original factory Filter A/B sweep'),
    0x1FB79C:('filter_pair_initialize','original factory Filter A/B sweep'),
    0x1FB928:('filter_EG_segment_setup','4152 original control/EG steps'),
    0x1FBAA0:('filter_EG_release','original traces with note-off'),
    0x1FBBE0:('filter_EG_advance','4152 original control/EG steps'),
    0x1FBD70:('filter_EG_attack_and_first_advance','original factory initialization'),
    0x12CEE4:('TG_filter_route_type_write','static interpretation; audio behavior unresolved'),
    0x12CFA8:('TG_filter_initial_control_write','static register packing'),
    0x12D088:('TG_filter_smoothed_control_write','10 ARM command captures; not silicon audio'),
    0x1FD3CC:('voice_manager_control_slice','static interpretation'),
    0x1FF348:('oscillator_phase_increment','ARM comparison passed'),
    0x1FF38C:('oscillator_pitch_update','ARM comparison passed with external modulation disabled'),
    0x1FF764:('oscillator_pitch_initialize','ARM comparison passed with external modulation disabled'),
    0x200FB4:('signed_modulation_product','ARM comparison passed'),
    0x20102C:('exp2_Q16','ARM comparison passed'),
    0x20119C:('AMS_mixer_update','static interpretation'),
    0x201674:('multisample_gain_initialize','ARM comparison passed'),
    0x201434:('AMS_mixer_initialize','original synthetic voice sweeps'),
    0x2913EC:('general_keyboard_tracking','ARM comparison passed for Concert parameters'),
    0x2915A8:('amp_keyboard_tracking','ARM comparison passed for Concert parameters'),
    0x20AF84:('parameter_integer_getter','ARM comparison passed'),
    0x20CF34:('ROM_multisample_table_getter','original ARM pointer verified'),
    0x20CF40:('ROM_multisample_count_getter','original ARM count497 verified'),
    0x2C5720:('factory_bank_filename_selector_fragment','six original ARM excerpts; not a full function'),
    0x17F610:('preload_bank_filename_selector_fragment','six original ARM excerpts; not a full function'),
    0x2753DC:('tone_adjust_value_getter','static interpretation'),
}
TABLES={0x336D6C:('effect_definitions',135*4),0x3D9B10:('voice_AMS_source_labels',47*4),
        0x336CD0:('effect_Dmod_source_labels',38*4),0x3FD5A4:('EG_base_duration',100*4),
        0x3FD734:('EG_curve_short',640*11*4),0x404534:('EG_curve_medium',91*11*4),
        0x4054D8:('EG_curve_long',22*4),0x405830:('EG_curve_asymptote',11*4),
        0x405F08:('exponential_velocity_source',128*2),
        0x4064EA:('amp_velocity_gain',256*2),0x4076E4:('exp2_fraction',256*2),
        0x407BD0:('parameter_namespace_pointers',None),
        0x48F5CC:('ROM_multisample_metadata',497*28),
        0x457BB8:('internal_bank_filename_pointers',49*4)}


def scan(data):
    calls=[];literals=collections.defaultdict(list)
    for offset in range(0,0x330000,4):
        word=struct.unpack_from('<I',data,offset)[0]
        if (word & 0x0F000000)==0x0B000000 and word>>28!=15:
            relative=word&0xFFFFFF
            if relative&0x800000:relative-=0x1000000
            target=offset+8+relative*4
            if 0<=target<0x330000:calls.append([offset,target])
        if word&0x0F7F0000==0x051F0000:
            address=offset+8+(1 if word&(1<<23) else -1)*(word&4095)
            if 0<=address<=len(data)-4:
                value=struct.unpack_from('<I',data,address)[0]
                if BASE<=value<BASE+len(data):literals[value-BASE].append([offset,address])
    return calls,literals


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--entry',type=lambda s:int(s,0),help='Show indexed callers and a bounded ARM excerpt')
    parser.add_argument('--bytes',type=lambda s:int(s,0),default=0x100)
    args=parser.parse_args()
    firmware=Firmware();calls,literals=scan(firmware.data)
    incoming=collections.defaultdict(list)
    for source,target in calls:incoming[target].append(source)
    if args.entry is not None:
        entry=args.entry
        print(SYMBOLS.get(entry,('unnamed entry','candidate')),hex(entry))
        print('Candidate direct callers:',[hex(n) for n in incoming[entry]])
        inspect(firmware.data,entry,min(len(firmware.data),entry+args.bytes))
        return
    folder=ROOT/'research/derived/firmware/KROSS2_V124/catalog'
    folder.mkdir(parents=True,exist_ok=True)
    effects_path=folder/'effects.json'
    effects=json.loads(effects_path.read_text())['effects'] if effects_path.exists() else []
    names={offset:tuple(value) for offset,value in SYMBOLS.items()}
    effect_users=collections.defaultdict(list)
    for effect in effects:
        for stage,entry in enumerate(effect['arm_functions']):
            names.setdefault(entry,(f'effect_{effect["id"]:03d}_control_{stage}','effect definition callback; role unresolved'))
            effect_users[entry].append({'effect_id':effect['id'],'callback_index':stage})
        init=effect['initialization'].get('constructor_offset')
        if init is not None:names[init]=(f'effect_{effect["id"]:03d}_constructor','original constructor execution verified')
    symbols=[{'offset':o,'virtual_address':BASE+o,'name':name,'status':status,
              'candidate_direct_callers':incoming[o],
              'effect_users':effect_users[o],
              'pointer_literal_references':literals[o]} for o,(name,status) in sorted(names.items())]
    tables=[]
    for offset,(name,size) in TABLES.items():
        item={'offset':offset,'name':name,'bytes':size,'pointer_literal_references':literals[offset]}
        if size is not None:
            raw=firmware.data[offset:offset+size]
            item['sha256']=hashlib.sha256(raw).hexdigest()
            (folder/(name+'.bin')).write_bytes(raw)
        tables.append(item)
    source_paths=[]
    for match in re.finditer(rb'[ -~]{6,}\x00',firmware.data):
        value=match.group()[:-1].decode('ascii')
        if '../source/' in value or '/source/' in value:
            source_paths.append({'offset':match.start(),'path':value,'pointer_literal_references':literals[match.start()]})
    metadata={'firmware_sha256':FW_SHA,'image_base':BASE,'scan_interval':[0,0x330000],
              'coordinate_system':'all offsets relative to decompressed KROSSAPP.bin, not CMP/KEP',
              'limitations':['ARM word scan may include embedded data; edges are candidates',
                            'No inferred complete function boundaries or indirect-call recovery',
                            'Named entries retain separate evidence status; source paths are debug strings'],
              'symbols':symbols,'tables':tables,'source_paths':source_paths,
              'effect_catalog':'effects.json'}
    (folder/'index.json').write_text(json.dumps(metadata,indent=2)+'\n')
    with (folder/'symbols.csv').open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['image_offset','virtual_address','name','evidence_status'])
        writer.writerows((hex(s['offset']),hex(s['virtual_address']),s['name'],s['status']) for s in symbols)
    (folder/'arm-candidates.json').write_text(json.dumps({'firmware_sha256':FW_SHA,
        'scope':'Unvalidated direct BL and PC-relative pointer candidates over 0..0x330000; not a complete call graph',
        'direct_bl_pairs':calls,'pointer_literals':{hex(k):v for k,v in literals.items()}},separators=(',',':'))+'\n')
    print(f'Indexed {len(symbols)} named/control entries, {len(tables)} tables, {len(source_paths)} source-path strings; {len(calls)} candidate BL edges')


if __name__=='__main__':main()
