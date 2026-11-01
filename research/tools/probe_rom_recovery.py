#!/usr/bin/env python3
"""Verify a complete synthetic recovery stream plus an isolated ARM reader.

No test ROM image is saved. The only ARM peripheral reads are synthetic. This
tool does not install a handler, patch firmware, connect devices or send MIDI.
"""
import argparse
import ctypes
import hashlib
import io
import json
import struct
import subprocess
from pathlib import Path

from program_firmware import Arm, BASE, Firmware, FW_SHA, ROOT
from recover_rom_stream import BLOCK_BYTES, parse_records

OUT=ROOT/'research/derived/firmware/KROSS2_V124/rom/recovery'
SOURCE=ROOT/'tools/rom_recovery_core.c'


def sha(data): return hashlib.sha256(data).hexdigest()


def payload(block):
    data=bytearray(bytes((block*29+i*13)&255 for i in range(256))*1024)
    if block==255: data[-16:]=b'KORG\x01\x02\x04\0SYNTHETC'
    assert len(data)==BLOCK_BYTES
    return bytes(data)


def build():
    native=ROOT/'build/rom-recovery-native.dylib'
    arm=ROOT/'build/rom-recovery-arm.o'
    flags=['-std=c99','-O2','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror']
    subprocess.run(['clang',*flags,'-dynamiclib',str(SOURCE),'-o',str(native)],check=True)
    subprocess.run(['clang','-target','armv5te-none-eabi','-march=armv5te','-marm',*flags,
                    '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector',
                    '-c',str(SOURCE),'-o',str(arm)],check=True)
    return native,arm


def arm_text(path):
    data=path.read_bytes()
    assert data[:7]==b'\x7fELF\x01\x01\x01' and struct.unpack_from('<H',data,18)[0]==40
    start=struct.unpack_from('<I',data,32)[0]
    size,count,names=struct.unpack_from('<3H',data,46)
    sections=[struct.unpack_from('<10I',data,start+i*size) for i in range(count)]
    def body(s): return data[s[4]:s[4]+s[5]]
    strings=body(sections[names])
    def name(offset): return strings[offset:strings.index(0,offset)].decode()
    index=next(i for i,s in enumerate(sections) if name(s[0])=='.text')
    assert not any(s[1] in (4,9) and s[7]==index and s[5] for s in sections), 'Unresolved text relocation'
    entry=None
    for s in sections:
        if s[1]!=2: continue
        symbols=body(s); labels=body(sections[s[6]])
        for offset in range(0,len(symbols),s[9]):
            label,value,length,info,other,section=struct.unpack_from('<IIIBBH',symbols,offset)
            if labels[label:labels.index(0,label)]==b'k2_export_block':
                assert section==index; entry=value
    assert entry is not None
    return body(sections[index]),entry


def native_stream(path):
    READ=ctypes.CFUNCTYPE(None,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p)
    EMIT=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32)
    class API(ctypes.Structure):
        _fields_=[('abi',ctypes.c_uint32),('kind',ctypes.c_uint32),('manager',ctypes.c_void_p),
                  ('read',READ),('emit',EMIT),('sink',ctypes.c_void_p),('fingerprint',ctypes.c_void_p)]
    stream=io.BytesIO(); reads=[]; emits=[]; failure=[0]
    def read(manager,block,target):
        assert manager==1; reads.append(block); ctypes.memmove(target,payload(block),BLOCK_BYTES)
    def emit(sink,data,length):
        emits.append(length)
        if failure[0]==len(emits): return 1
        stream.write(ctypes.string_at(data,length)); return 0
    reader,writer=READ(read),EMIT(emit)
    fingerprint=ctypes.create_string_buffer(bytes.fromhex(FW_SHA))
    api=API(1,1,1,reader,writer,None,ctypes.addressof(fingerprint))
    scratch=ctypes.create_string_buffer(b'\xcc'*(BLOCK_BYTES+32)); target=ctypes.addressof(scratch)+16
    library=ctypes.CDLL(str(path)); export=library.k2_export_block
    export.argtypes=[ctypes.POINTER(API),ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32]; export.restype=ctypes.c_int
    for block in range(256): assert export(ctypes.byref(api),block,target,BLOCK_BYTES)==0
    assert reads==list(range(256)) and emits==[64,BLOCK_BYTES]*256
    assert scratch.raw[:16]==b'\xcc'*16 and scratch.raw[BLOCK_BYTES+16:BLOCK_BYTES+32]==b'\xcc'*16
    data=stream.getvalue(); blocks,parsed=parse_records(io.BytesIO(data),allow_synthetic=True)
    digest=hashlib.sha256()
    for block in range(256):
        assert blocks[block]==payload(block); digest.update(blocks[block])
    rejected=[]
    for name,case in [('synthetic_origin',data),('truncated_header',data[:63]),
                      ('truncated_payload',data[:100]),('missing_blocks',data[:64+BLOCK_BYTES])]:
        try: parse_records(io.BytesIO(case),allow_synthetic=name!='synthetic_origin')
        except ValueError as error: rejected.append(dict(case=name,reason=str(error)))
        else: raise AssertionError(name)
    corrupt=bytearray(data[:64+BLOCK_BYTES]); corrupt[100]^=1
    try: parse_records(io.BytesIO(corrupt),allow_synthetic=True)
    except ValueError as error: rejected.append(dict(case='corrupted_payload',reason=str(error)))
    else: raise AssertionError('CRC corruption accepted')
    # Identical retransmission is accepted; mismatching data at the same block
    # index is rejected even if its own CRC is valid.
    _,duplicates=parse_records(io.BytesIO(data+data[:64+BLOCK_BYTES]),allow_synthetic=True)
    assert duplicates['duplicates']==1
    conflict=bytearray(data[:64+BLOCK_BYTES]); conflict[100]^=1
    import zlib
    struct.pack_into('<I',conflict,24,zlib.crc32(conflict[64:]))
    try: parse_records(io.BytesIO(data+conflict),allow_synthetic=True)
    except ValueError as error: rejected.append(dict(case='conflicting_duplicate',reason=str(error)))
    else: raise AssertionError('Conflicting duplicate accepted')
    bad_calls=[]
    for block,capacity,shift in [(256,BLOCK_BYTES,0),(0xFFFFFFFF,BLOCK_BYTES,0),
                                  (0,BLOCK_BYTES-1,0),(0,BLOCK_BYTES,1)]:
        previous=len(reads); result=export(ctypes.byref(api),block,target+shift,capacity)
        assert result==-2 and len(reads)==previous
        bad_calls.append(dict(block=block,capacity=capacity,misalignment=shift,result=result))
    output_failures=[]
    for stage,result in [(1,-3),(2,-4)]:
        emits.clear(); failure[0]=stage
        assert export(ctypes.byref(api),0,target,BLOCK_BYTES)==result
        output_failures.append(dict(failed_emit_call=stage,result=result))
    return dict(blocks_verified=256,payload_bytes=256*BLOCK_BYTES,encoded_stream_bytes=len(data),
                synthetic_image_sha256=digest.hexdigest(),image_saved=False,
                source_kind=parsed['source_kind'],rejected_inputs=rejected,
                identical_retransmissions=duplicates['duplicates'],invalid_calls=bad_calls,
                output_failures=output_failures)


def verify_arm(fw,code,entry):
    machine=Arm(fw)
    location=0x10010000
    machine.uc.mem_map(location,0x10000); machine.uc.mem_write(location,code)
    api,fingerprint,scratch=0x11001000,0x11002000,0x11010000
    machine.uc.mem_write(fingerprint,bytes.fromhex(FW_SHA))
    # The new core calls the existing original block reader directly.
    # Only TG u16 data and peripheral gating are mocked; no writer is reachable.
    manager=0x11003000; machine.write(manager,0x60000000)
    machine.write(api,1,1,manager,BASE+0x11C90C,BASE+0x132690,0,fingerprint)
    cases=[]
    for block in (0,255):
        expected=payload(block); reads=[0]; emitted=[]
        def read(a):
            index,half=a.get('R1'),a.get('R2')
            assert index==(block<<16)+reads[0]//2 and half==reads[0]%2
            position=(index-(block<<16))*4+half*2; reads[0]+=1
            return struct.unpack_from('<H',expected,position)[0]
        def emit(a):
            emitted.append(bytes(a.uc.mem_read(a.get('R1'),a.get('R2')))); return 0
        machine.stubs={0x11C888:lambda a:0,0x11C8CC:lambda a:0,0x12E1C0:read,0x132690:emit}
        machine.uc.mem_write(scratch+BLOCK_BYTES,b'\xcc'*16)
        assert machine.call(location+entry-BASE,api,block,scratch,BLOCK_BYTES,count=20000000)==0
        assert reads[0]==131072 and list(map(len,emitted))==[64,BLOCK_BYTES]
        record=b''.join(emitted); blocks,info=parse_records(io.BytesIO(record),allow_synthetic=True,require_complete=False)
        assert blocks[block]==expected
        assert bytes(machine.uc.mem_read(scratch+BLOCK_BYTES,16))==b'\xcc'*16
        cases.append(dict(block=block,original_TG_u16_reads=reads[0],all_payload_bytes_match=True,
                          record_sha256=sha(record),source_kind=info['source_kind']))
        print(f'Original ARM + new exporter block {block}: PASS',flush=True)
    return cases


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--verify-arm',action='store_true'); args=parser.parse_args()
    native,obj=build(); code,entry=arm_text(obj)
    OUT.mkdir(parents=True,exist_ok=True)
    # This is a relocatable research module, deliberately not named KROSSAPP.
    (OUT/'exporter-arm.text.bin').write_bytes(code)
    report=dict(scope='Offline recovery prototype; no deployment mechanism or installed firmware',
                firmware_sha256=FW_SHA,source_sha256=sha(SOURCE.read_bytes()),
                tools_sha256={p:sha((ROOT/'tools'/p).read_bytes()) for p in
                              ('probe_rom_recovery.py','recover_rom_stream.py','program_firmware.py')},
                code_bytes=len(code),code_entry_offset=entry,code_sha256=sha(code),
                original_firmware_modified=False,real_ROM_bytes_recovered=0,
                native=native_stream(native),ARM=verify_arm(Firmware(),code,entry) if args.verify_arm else [],
                missing=['A validated way to run the module on the owned instrument',
                         'A real transport for the emitted records',
                         'Actual lower64MiB TG ROM bytes and format validation on them'])
    (OUT/('recovery-check-arm.json' if args.verify_arm else 'recovery-check.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('tools_sha256',)},indent=2))


if __name__=='__main__': main()
