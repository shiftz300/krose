#!/usr/bin/env python3
"""Offline original-ARM release AMS fixtures. No device/MIDI access."""
import json,struct
from program_firmware import ROOT
from voice_firmware import VoiceOracle
DERIVED=ROOT/'research/derived/firmware/KROSS2_V124/rom/decoding'
def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')


def main():
    oracle=VoiceOracle();a=oracle.arm
    releases=json.loads((DERIVED/'web-releases.json').read_text())
    programs={p['bank_program']:p for p in json.loads((ROOT/'research/derived/firmware/KROSS2_V124/sounds/factory/programs.json').read_text())['programs']}
    cases=[];seen=set()
    variants=[(36,32,{},0),(60,100,{1:80,17:96,19:32,80:127,81:127},3),(96,127,{1:127,17:0,19:127,21:96,80:0,81:0},9)]
    for pid,configs in releases['ams_configs'].items():
        for wid,config in configs.items():
            osc=releases['provenance'][pid]['waveforms'][wid]['oscillator']-1
            if (pid,osc) in seen:continue
            seen.add((pid,osc));oracle.program=(ROOT/programs[pid]['program_file']).read_bytes()
            for note,velocity,cc,seconds in variants:
                a.stubs[0x2737C8]=lambda _:0
                oracle.initialize(note,velocity,osc)
                a.uc.mem_write(oracle.controls,bytes([255])*128)
                for key,value in cc.items():a.uc.mem_write(oracle.controls+key,bytes([value]))
                a.stubs[0x2737C8]=lambda machine:int(machine.get('R1') in cc)
                # Recompute the original stateless mixers with live CC values.
                for offset in (0x1F0,0x1F8):a.call(0x20119C,oracle.voice+offset,oracle.voice,1)
                if config.get('common_lfo'):
                    lfo=config['common_lfo'];phase=int((seconds*2*lfo['ticks_per_quarter']%lfo['period_ticks'])*65535/lfo['period_ticks'])
                    a.uc.mem_write(oracle.context+0x58,bytes(48));a.uc.mem_write(oracle.context+0x62,struct.pack('<H',phase))
                    a.call(0x200A3C,oracle.context+0x58,0,0,oracle.patch+0x53c,stack=(0,))
                sources={str(e['source']):a.call(0x1F8608,oracle.voice,e['source']) for e in config['time_ams'] if e['intensity']}
                result=oracle.release()
                cases.append(dict(program=pid,waveform=wid,note=note,velocity=velocity,cc=cc,seconds=seconds,sources=sources,units=result['eg_duration_units']))
    save(ROOT/'research/derived/verification/web-release-ams-arm.json',dict(cases=cases,coefficients=[dict(curve=curve,steps=steps,value=a.call(0x1FAB3C,curve,steps)&0xffffffff) for curve in range(11) for steps in (0,1,639,640,641,703,704,6399,6400,6401,230399,230400,300000)],firmware_sha256=releases['firmware_sha256'],
        scope='Original voice AMS dispatch, stateless mixers and release setup. Synthetic CC enable gate, Tone Adjust zero. Common LFO original waveform sampled at explicit phase; browser supplies tempo/clock. No hardware or audio audition.'))
    print('Captured',len(cases),'original ARM release cases across',len(seen),'Program oscillators')


if __name__=='__main__':main()
