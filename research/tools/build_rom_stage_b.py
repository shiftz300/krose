#!/usr/bin/env python3
"""Build stage-B ROM reader candidate offline. Never installs firmware."""
import hashlib,json,struct,subprocess
from pathlib import Path
from arm_research_link import link
from build_probe_injection import SLOT,TABLE,sum16
from program_firmware import ROOT,BASE,FW_SHA,Firmware

OUT=ROOT/'research/derived/firmware/KROSS2_V124/rom/injection/stage-b'
SCRATCH=0x520000
RESERVED=0x40200
SOURCE=ROOT/'tools/kross_rom_stage_b.c'
def sha(data): return hashlib.sha256(data).hexdigest()

def build():
    original=Firmware().data
    obj=ROOT/'build/kross-rom-stage-b.o'
    subprocess.run(['clang','-target','armv5te-none-eabi','-march=armv5te','-marm',
                    '-std=c99','-O2','-ffreestanding','-fno-builtin','-fno-stack-protector',
                    '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror',
                    '-c',str(SOURCE),'-o',str(obj)],check=True)
    code,linked=link(obj,BASE+SLOT)
    assert len(code)<0x2000 and original[SLOT:SLOT+len(code)]==b'\xff'*len(code)
    assert original[SCRATCH:SCRATCH+RESERVED]==b'\xff'*RESERVED
    refs=[i for i in range(0,len(original)-3,4) if BASE+SCRATCH<=struct.unpack_from('<I',original,i)[0]<BASE+SCRATCH+RESERVED]
    if refs: raise ValueError(f'Original image contains possible references to reserved RAM: {refs}')
    image=bytearray(original);struct.pack_into('<I',image,TABLE,BASE+SLOT)
    image[SLOT:SLOT+len(code)]=code;struct.pack_into('<H',image,len(image)-2,sum16(image))
    OUT.mkdir(parents=True,exist_ok=True)
    for label,data in [('candidate',image),('restore',original)]:
        (OUT/label).mkdir(exist_ok=True);(OUT/label/'KROSSAPP.BIN').write_bytes(data)
    (OUT/'probe-arm.text.bin').write_bytes(code)
    (OUT/'link-map.json').write_text(json.dumps(linked,indent=2)+'\n')
    report=dict(stage='B: bounded TG window / one block per request',revision=3,
                original_sha256=FW_SHA,candidate_sha256=sha(image),code_sha256=sha(code),
                code_bytes=len(code),source_sha256=sha(SOURCE.read_bytes()),TG_reading=True,
                flash_programming=False,hardware_tested=False,recovery_guaranteed=False,
                reserved_RAM=dict(start=hex(BASE+SCRATCH),bytes=RESERVED,original_bytes='all FF',
                                  original_possible_pointer_references=refs,
                                  runtime_ownership_and_permissions='not yet hardware verified'),
                modes={'0':'identity 03','1':'original last16 ROM metadata read',
                       '2':'one block, event byte5 selects 0..255','3':'reserved RAM pattern/write/read/restore check'},
                no_heap=True,no_boot_hook=True,no_automatic_export=True,
                transport='256 raw bytes/frame; per-frame and per-block CRC32; MSB-mask MIDI packing')
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    (OUT/'SHA256SUMS').write_text(''.join(f'{sha(data)}  {label}/KROSSAPP.BIN\n' for label,data in [('candidate',image),('restore',original)]))
    return report

if __name__=='__main__': print(json.dumps(build(),indent=2))
