#!/usr/bin/env python3
"""Compare published Electribe RAM/Flash requests against KROSS2 offline.

Author scripts are inspected, never imported or run. No MIDI/USB is opened.
"""
import argparse
import ast
import hashlib
import json
import struct
import zipfile
from pathlib import Path

from program_firmware import Arm, Firmware, BASE, ROOT, FW_SHA

OUT=ROOT/'research/derived/firmware/KROSS2_V124/rom/recovery'
EXTERNAL=ROOT/'research/external/rom-recovery-20261101'


def sha(data): return hashlib.sha256(data).hexdigest()


def encode(data):
    result=bytearray()
    for start in range(0,len(data),7):
        part=data[start:start+7]
        result.append(sum((v>>7)<<i for i,v in enumerate(part)))
        result.extend(v&127 for v in part)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args()
    source=json.loads((EXTERNAL/'source-files.json').read_text())
    for item in source['files']: assert sha((ROOT/item['path']).read_bytes())==item['sha256']
    author=ast.parse((EXTERNAL/'hacktribe/scripts/e2sysex.py').read_text())
    commands={}
    for method in ast.walk(author):
        if isinstance(method,ast.FunctionDef) and method.name in ('read_cpu_ram','read_flash','execute_cpu_ram'):
            constants=[n.elts[0].value for n in ast.walk(method) if isinstance(n,ast.List) and len(n.elts)==1
                       and isinstance(n.elts[0],ast.Constant) and isinstance(n.elts[0].value,int)]
            assert len(constants)==1;commands[method.name]=constants[0]
    assert commands==dict(read_cpu_ram=0x52,execute_cpu_ram=0x57,read_flash=0x55)
    archive=ROOT/'research/downloads/KROSS2_V122.zip'
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        members=[dict(file=p.filename,bytes=p.file_size) for p in z.infolist() if not p.is_dir()]
    assert not any(p['file'].split('/')[-1] in ('BOOTSYS.BIN','KROSSPCM.BIN') for p in members)
    firmware=Firmware();images={124:firmware.data,122:(ROOT/'research/derived/firmware/KROSS2_V122/KROSSAPP.bin').read_bytes()}
    assert sha(images[122])=='959e585abd71f7986ff73c6861e4b518d26c253269b2b33fd9d1b962ecf905e8'
    getters=[]
    pattern=struct.pack('<III',0xE59F0000,0xE1A0F00E,0x8001B000)
    for version,data in images.items():
        assert len(data)==6291456 and sum(data[:-2])&65535==int.from_bytes(data[-2:],'little')
        offset=data.find(pattern);assert offset>=0 and data.find(pattern,offset+1)<0
        getters.append(dict(version=version,firmware_sha256=sha(data),boot_version_pointer_getter=hex(offset),
                            boot_version_pointer=hex(0x8001B000),application_tail_sum16_valid=True))
    cases=[]
    if args.verify_arm:
        for kind,command in commands.items():
            raw=struct.pack('<II',0x80000000 if kind!='read_flash' else 0,0x1C000 if kind=='read_cpu_ram' else 16)
            for model in (0x24,0x49):
                arm=Arm(firmware);packet,context=0x11010000,0x11011000
                arm.write(packet+0x18,0xFFFFFFFF)
                arm.uc.mem_write(BASE+0x1DCC2D8+0x1353,b'\x20')
                arm.stubs={0x243DB0:lambda a:0,0x276090:lambda a:1}
                wire=bytes([0xF0,0x42,0x30,0,1,model,command])+encode(raw)+b'\xf7'
                events=[]
                for b in wire:
                    if arm.call(0x2C2E90,packet,b,7,count=10000):
                        events.append(bytes(arm.uc.mem_read(packet,16)))
                captures=[]
                def capture(a): captures.append(dict(target='0x2be8bc',packet=bytes(a.uc.mem_read(a.get('R0'),16)).hex()));return 0
                arm.stubs.update({0x40C10:lambda a:0,0x2BCC50:lambda a:0x11015000,
                                  0x2BCCD4:lambda a:1,0x2BE8BC:capture})
                for event in events:
                    if event[0]!=0x55: continue  # malformed-message event is not a read handler
                    arm.uc.mem_write(packet,event[:3]+b'\x07'+event[4:])
                    arm.call(0x2C11A0,packet,context,event[0],count=10000)
                if model==0x24 or command in (0x52,0x57): assert not events and not captures
                else: assert len(events)==1 and not captures and events[0][0]==5
                cases.append(dict(author_function=kind,command=command,model=model,input_hex=wire.hex(),
                                  decoded_events=[e.hex() for e in events],captures=captures,
                                  hardware_access=False))
        arm=Arm(firmware);packet,context=0x11010000,0x11011000
        arm.uc.mem_write(packet,b'\x55\0\0\x07'+bytes(28));captures=[]
        def opcode55(a):captures.append('0x2be8bc');return 0
        arm.stubs={0x40C10:lambda a:0,0x2BCC50:lambda a:0x11015000,
                   0x2BCCD4:lambda a:1,0x2BE8BC:opcode55}
        arm.call(0x2C11A0,packet,context,0x55,count=10000)
        assert captures==['0x2be8bc']
        from types import SimpleNamespace
        for item in getters:
            arm=Arm(SimpleNamespace(data=images[item['version']]))
            assert arm.call(int(item['boot_version_pointer_getter'],16))&0xFFFFFFFF==0x8001B000
            item['original_ARM_return_verified']=True
    report=dict(firmware_sha256=FW_SHA,tool_sha256=sha(Path(__file__).read_bytes()),
                author_sources=source,author_commands=commands,
                official_122=dict(zip_sha256=sha(archive.read_bytes()),members=members),
                boot_version_getters=getters,compatibility_cases=cases,
                opcode55_internal_event_target='0x2be8bc' if args.verify_arm else None,
                conclusion='Electribe source has useful RAM/boot extraction precedent; its commands are not a KROSS2 dumper',
                collision='On KROSS2, 0x55 reaches Exclusive configuration handling, not Flash reading',
                boot_code_available=False,real_ROM_bytes_recovered=0,
                limitations=['Shared boot-version RAM pointer is not proof of identical bootloader or USB protocol',
                             'No KROSS2 hardware command was sent; no external author script was executed'])
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/('protocol-comparison-arm.json' if args.verify_arm else 'protocol-comparison.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('Compared author commands, checked official1.2.2 ZIP; offline ARM cases:',len(cases),'boot getters:',len(getters))


if __name__=='__main__': main()
