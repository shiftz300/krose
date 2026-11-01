#!/usr/bin/env python3
"""Sweep native Concert amplitude/EG controls, retaining explicit context limits."""
import hashlib
import json
import struct

from program_firmware import ROOT, FW_SHA
from voice_firmware import VoiceOracle
from voice_math import VoiceMath


def main():
    oracle=VoiceOracle()
    math=VoiceMath(oracle.firmware)
    folder=ROOT/'research/derived/firmware/KROSS2_V124/voice'
    folder.mkdir(parents=True,exist_ok=True)
    selected=[]
    grid=bytearray(b'K2CTR01\x00'+struct.pack('<4I',2,128,127,20))
    for oscillator in range(2):
        for note in range(128):
            for velocity in range(1,128):
                level=119 if velocity<107 else 127
                initial=oracle.initialize(note,velocity,oscillator,level)
                expected=(math.velocity_gain(velocity,70)*math.multisample_gain(level)) >> 16
                assert initial['amp_velocity_factor']==expected,(note,velocity,oscillator,initial['amp_velocity_factor'],expected)
                sources={14:(129*velocity+1)>>2,
                         15:(struct.unpack_from('<h',oracle.firmware.data,0x405F08+velocity*2)[0]+1)>>3}
                osc_bytes=oracle.program[0x564+380*oscillator:0x564+380*(oscillator+1)]
                sources[1]=math.basic_mixer(osc_bytes[0x14C:],sources)
                sources[2]=math.basic_mixer(osc_bytes[0x164:],sources)
                assert initial['ams_mixers']==[sources[1],sources[2]]
                release=oracle.release()
                grid.extend(struct.pack('<4H2h2I',initial['amp_control_gain'],initial['eg_control_level'],
                                        initial['amp_velocity_factor'],initial['multisample_factor'],
                                        *initial['ams_mixers'],initial['eg_duration_units'],release['eg_duration_units']))
                if note in (24,60,84,108) and velocity in (40,85,86,100,106,107,127):
                    selected.append({'oscillator':oscillator+1,'note':note,'velocity':velocity,
                                     'slot_level':level,'initial':initial,
                                     'release_duration_units':release['eg_duration_units']})
            print(f'Completed OSC{oscillator+1} note {note}',flush=True) if note%32==0 else None
    grid_path=folder/'concert-control-map.bin'
    grid_path.write_bytes(grid)
    trajectories=[]
    for note,velocity in [(36,64),(60,100),(96,127)]:
        oracle.initialize(note,velocity,0,119 if velocity<107 else 127)
        trace=[];last_stage=None
        # This is indexed by original control calls, not physical seconds.
        for tick in range(4000):
            if tick==1200:oracle.release()
            state=oracle.advance()
            if tick%16==0 or state['eg_stage']!=last_stage:
                trace.append({'control_tick':tick,**state})
            last_stage=state['eg_stage']
            if tick>=1200 and state['eg_stage']==7:break
        assert state['eg_stage']==7,('Release did not terminate',note,velocity,state)
        trajectories.append({'note':note,'velocity':velocity,'note_off_control_tick':1200,'trace':trace})
    result={'firmware_sha256':FW_SHA,'program_sha256':hashlib.sha256(oracle.program).hexdigest(),
            'tool_sha256':{name:hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in
                           ('program_firmware.py','voice_math.py','voice_firmware.py','probe_concert_voice.py')},
            'sweep_points':2*128*127,'fields':selected,'trajectories':trajectories,
            'map':{'file':grid_path.name,'sha256':hashlib.sha256(grid).hexdigest(),'bytes':len(grid),
                   'header':'magic8 K2CTR01 NUL; LE u32 oscillator_count=2,note_count=128,velocity_count=127,stride=20',
                   'order':'oscillator 0..1, note 0..127, velocity 1..127',
                   'record':'LE 4H2h2I: amp_control_gain,eg_control_level,amp_velocity_factor,multisample_factor,mixer1,mixer2,attack_duration_internal,release_duration_internal'},
            'scope':['Original key tracking, stateless AMS mixers, amp gain and amp EG control routines',
                     'Synthetic mode=4, part volume127, CC7/CC11 full, original Program mixer value103, zero extra sample/amp offsets, no LFO audio contribution',
                     'External Tone Adjust getter returns zero; MIDI override-enable getter returns false; mute lookup returns enabled',
                     'No keyboard global velocity-curve translation, Filter EG, hardware clock/cadence, TG gain/interpolation or audio output validation',
                     'Control-call trajectories must not be labelled physical seconds until scheduler cadence is verified'],
            'checks':{'velocity_gain_table_and_slot_scaling':'all 32512 original initializers matched independent integer formula',
                      'AMS_mixers_1_2':'all 32512 original contexts matched independent stateless mixer formula'}}
    (folder/'concert-controls.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'research/derived/verification/concert-voice-arm-comparison.json').write_text(json.dumps({
        'firmware_sha256':FW_SHA,'sweep_points':result['sweep_points'],'checks':result['checks'],
        'tool_sha256':result['tool_sha256'],
        'map_sha256':result['map']['sha256'],'scope':result['scope']},indent=2)+'\n')
    print('PASS 32512 original Concert control contexts; three release trajectories terminated; wrote',folder)


if __name__=='__main__':main()
