#!/usr/bin/env python3
"""Generate compile-time native control tables; no firmware needed at runtime."""
import argparse
import hashlib
import json
import struct
from program_firmware import Firmware, FW_SHA, ROOT


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=__import__('pathlib').Path,required=True)
    output=parser.parse_args().output;output.mkdir(parents=True,exist_ok=True)
    firmware=Firmware()
    program=(ROOT/'output/kep-analysis/Concert_SE_Grand/program.bin').read_bytes()
    assert hashlib.sha256(program).hexdigest()=='a52ae2deebe0a0997bb50d50b3b26c1e40bd278567068e6afc85ae20e09222e4'
    tables=[('kEgTime',0x3FD5A4,100,'I','uint32_t'),('kEgShort',0x3FD734,640*11,'I','uint32_t'),
            ('kEgMedium',0x404534,91*11,'I','uint32_t'),('kEgLong',0x4054D8,22,'I','uint32_t'),
            ('kEgAsymptote',0x405830,11,'I','uint32_t'),('kExpFraction',0x4076E4,256,'H','uint16_t'),
            ('kVelocityGain',0x4064EA,256,'H','uint16_t'),('kExpVelocity',0x405F08,128,'h','int16_t'),
            ('kTgReciprocal',0x3A8D40,25,'H','uint16_t')]
    text='#pragma once\n#include <cstdint>\nnamespace segrand::native_data {\n'
    entries=[]
    for name,offset,count,fmt,ctype in tables:
        raw=firmware.data[offset:offset+struct.calcsize(fmt)*count]
        values=struct.unpack('<'+str(count)+fmt,raw)
        text+=f'inline constexpr {ctype} {name}[{count}]={{\n'
        text+='\n'.join('  '+','.join(str(v) for v in values[i:i+12])+',' for i in range(0,count,12))+'\n};\n'
        entries.append({'name':name,'firmware_offset':offset,'elements':count,'sha256':hashlib.sha256(raw).hexdigest()})
    text+='inline constexpr uint8_t kProgram[2144]={\n'
    text+='\n'.join('  '+','.join(str(v) for v in program[i:i+24])+',' for i in range(0,len(program),24))+'\n};\n}\n'
    (output/'NativeVoiceData.h').write_text(text)
    controls=json.loads((ROOT/'research/derived/firmware/KROSS2_V124/voice/concert-controls.json').read_text())
    traces=bytearray(b'K2TRACE1')
    records=[]
    for trace in controls['trajectories']:
        for state in trace['trace']:
            records.append((trace['note'],trace['velocity'],state['control_tick'],trace['note_off_control_tick'],
                            state['eg_stage'],state['eg_control_level'],state['amp_control_gain'],state['eg_duration_units']))
    traces.extend(struct.pack('<I',len(records)))
    for record in records:traces.extend(struct.pack('<8I',*record))
    (output/'native-voice-traces.bin').write_bytes(traces)
    timing=json.loads((ROOT/'research/derived/verification/voice-timing-arm-comparison.json').read_text())
    commands=bytearray(b'K2TGSLW1'+struct.pack('<I',len(timing['TG_command_cases'])))
    for row in timing['TG_command_cases']:
        commands.extend(struct.pack('<4iI',row['duration_units'],row['previous_target'],row['target'],row['step'],row['register_word']))
    (output/'native-tg-commands.bin').write_bytes(commands)
    (output/'voice-assets.json').write_text(json.dumps({'firmware_sha256':FW_SHA,'tables':entries,
        'program_sha256':hashlib.sha256(program).hexdigest(),'header_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'trace_fixture_records':len(records),'trace_fixture_sha256':hashlib.sha256(traces).hexdigest(),
        'scope':'Factory Concert control constants extracted at build time; generated code has no runtime firmware/Unicorn dependency'},indent=2)+'\n')
    print('Generated native control tables and',len(records),'ARM trace fixtures')


if __name__=='__main__':main()
