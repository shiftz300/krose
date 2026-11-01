#!/usr/bin/env python3
"""Recover every v1.2.4 effect, including startup-populated definitions.

Runs only pure constructors/getters and the original buffered DSP loader.
No OS startup, hardware register access or replacement DSP code is used.
"""
from layout import PRODUCT_ROOT
import hashlib
import json
import struct

from program_firmware import Arm, Firmware, ROOT, BASE, FW_SHA, EFFECT_COUNT


def initializer_candidates(firmware, definition):
    data=firmware.data
    pattern=struct.pack('<I',BASE+definition)
    literals=[i*4 for i in range(len(data)//4) if data[i*4:i*4+4]==pattern]
    found=[]
    # Static candidate only: nearest APCS prologue before the definition literal.
    # Original constructor execution below must produce an in-image code bundle.
    for literal in literals:
        if literal>=0x330000:continue
        for offset in range(literal-4,max(0,literal-80),-4):
            if data[offset:offset+4]==b'\x0d\xc0\xa0\xe1':
                found.append(offset)
                break
    return sorted(set(found))


def main():
    firmware=Firmware()
    arm=Arm(firmware)
    effects=[]
    generated=[]
    parameter_comparisons=0
    for effect_id in range(EFFECT_COUNT):
        entry=firmware.effect(effect_id)
        definition=entry['definition_offset']
        entry['initial_code_offset']=entry['code_offset']
        entry['initial_code_words_64']=entry['code_words_64']
        if entry['code_offset'] is None:
            candidates=initializer_candidates(firmware,definition)
            assert len(candidates)==1,(effect_id,candidates)
            constructor=candidates[0]
            arm.call(constructor)
            resolved,count=struct.unpack('<IH',arm.uc.mem_read(BASE+definition+8,4)+arm.uc.mem_read(BASE+definition+30,2))
            assert BASE<=resolved<BASE+len(firmware.data) and 0<count<=1024,(effect_id,resolved,count)
            entry['code_offset']=resolved-BASE
            entry['code_words_64']=count
            entry['initialization']={'constructor_offset':constructor,'method':'original ARM constructor, no stubs',
                                     'result':'code pointer and length populated in mapped RAM'}
            generated.append({'id':effect_id,'name':entry['name'],'constructor_offset':constructor,'code_words_64':count})
        else:
            entry['initialization']={'method':'definition already populated in firmware file'}
        code=firmware.data[entry['code_offset']:entry['code_offset']+entry['code_words_64']*8]
        constants=firmware.data[entry['constants_offset']:entry['constants_offset']+entry['constant_words_32']*4]
        assert len(code)==entry['code_words_64']*8 and len(constants)==entry['constant_words_32']*4
        context=0x11008000
        arm.uc.mem_write(context,b'\x01'+bytes(31))
        arm.call(0x5A51C,context,0,2,BASE+definition)
        assert bytes(arm.uc.mem_read(0xC0FEB1C8+0x100,len(code)))==code,effect_id
        assert bytes(arm.uc.mem_read(0xC0FE9DC8,len(constants)))==constants,effect_id
        upload=b''.join(struct.pack('<3H',word[0],word[3],word[2]) for word in struct.iter_unpack('<4H',code))
        folder=ROOT/'research/derived/firmware/KROSS2_V124/effects'/f'{effect_id:03d}'
        folder.mkdir(parents=True,exist_ok=True)
        entry['assets']={}
        for name,data in [('dsp-code.u64le.bin',code),('initial-constants.u32le.bin',constants),('dsp-upload.u16le.bin',upload)]:
            path=folder/name
            if path.exists():
                assert path.read_bytes()==data,('Existing research asset differs',path)
            else:path.write_bytes(data)
            entry['assets'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                                  'path':str(path.relative_to(PRODUCT_ROOT))}
        entry['validation']='Original buffered loader reproduced code and constants exactly'
        for parameter in entry['parameters']:
            descriptor=parameter['descriptor']
            for raw in (bytes(8),b'\xff'*8,b'\x55'*8,b'\xaa'*8):
                expected=firmware.read_value(raw,0,descriptor)
                actual=arm.parameter(raw,descriptor)
                assert (actual&0xFFFFFFFF)==(expected&0xFFFFFFFF),(effect_id,parameter['index'],actual,expected)
                parameter_comparisons+=1
        effects.append(entry)
    output=ROOT/'research/derived/firmware/KROSS2_V124/catalog'
    output.mkdir(parents=True,exist_ok=True)
    report={'firmware_sha256':FW_SHA,'effect_table_offset':0x336D6C,'effect_count':EFFECT_COUNT,
            'tool_sha256':{name:hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in
                           ('program_firmware.py','probe_effect_catalog.py')},
            'effects':effects,'runtime_populated_definitions':generated,
            'unique_code_payloads':len({e['assets']['dsp-code.u64le.bin']['sha256'] for e in effects}),
            'scope':'Code/constants/parameter metadata and original loader validation; DSP ISA/audio execution still unresolved'}
    (output/'effects.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'research/derived/verification/effects-catalog-arm-comparison.json').write_text(json.dumps({
        'firmware_sha256':FW_SHA,'effect_bundles_compared':EFFECT_COUNT,'startup_constructors':generated,
        'tool_sha256':report['tool_sha256'],
        'parameter_count':sum(len(e['parameters']) for e in effects),
        'parameter_getter_comparisons':parameter_comparisons,'parameter_patterns':['00','ff','55','aa'],'stubs':[],
        'execution_scope':'Pure constructors and buffered loader only; no OS/MMIO/TG'},indent=2)+'\n')
    print(f'PASS {EFFECT_COUNT} effect bundles, {len(generated)} original startup constructors, {report["unique_code_payloads"]} unique code payloads; {parameter_comparisons} getter comparisons')
    for row in generated:print(row)


if __name__=='__main__':main()
