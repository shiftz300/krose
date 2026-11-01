#!/usr/bin/env python3
"""Offline ARM stage-B verification: real FIFO/gates/TG loop, mocked hardware.

Synthetic payloads/wire streams stay in memory, never saved as acquisitions.
"""
import hashlib,json,struct,zlib
from pathlib import Path
from build_rom_stage_b import OUT,SCRATCH,RESERVED,build
from program_firmware import BASE,Firmware,ROOT
from verify_probe_injection import GLOBAL,CONTEXT,setup
from verify_probe_injection_v2 import FIFO,PARSER,CONSUMER,BUFFER
from parse_rom_midi import validate,decode,frame,pack,unpack

RAM=BASE+SCRATCH
TAIL=b'KORG\x01\x02\x04\0SYNTHETC'

def byte_at(offset):
    if offset>=0x3fffff0: return TAIL[offset-0x3fffff0]
    return ((offset*13)^(offset>>8)^(offset>>16)*29)&255

def machine(fw):
    arm=setup(fw)
    from unicorn import UC_HOOK_MEM_READ
    for address in (0x2BCC50,0x2BCCD4,0x276090,0x11C888,0x11C8CC,0x11C90C,0x12E1C0):
        arm.stubs.pop(address,None)
    state=dict(gate=0x1c,paused=False,locked=False,reads=0,writes=0,frames=[],events=[],pause_resume=[])
    arm.stubs.update({0x2E2F9C:lambda a:BUFFER,0x132660:lambda a:0,
                      0x132670:lambda a:0,0x2FC618:lambda a:0})
    arm.call(0x2B79C4,FIFO,8,0x400,2,stack=(1,))
    # No allocator call is permitted AFTER FIFO setup.
    arm.stubs[0x2E2F9C]=lambda a:(_ for _ in ()).throw(AssertionError('Unexpected allocator'))
    arm.uc.mem_write(PARSER,bytes(0x100));arm.write(PARSER+0x18,0xffffffff)
    arm.uc.mem_write(GLOBAL+0x1350,b'\0\0\x01\x3f')
    arm.uc.mem_write(BASE+0x104795C,b'\x01')
    arm.write(BASE+0x104643C,0x60000000)
    arm.stubs[0x272354]=lambda a:0x1101e000
    def pause(a):
        assert a.get('R0')==0x1101e000
        state['paused']=True;state['pause_resume'].append('pause');return 0
    def resume(a):
        assert state['gate']==0x1c and state['paused']
        state['paused']=False;state['pause_resume'].append('resume');return 0
    arm.stubs[0x271DD4]=pause;arm.stubs[0x271DDC]=resume
    def lock(a):
        assert not state['locked'] and state['gate']==0x1c
        assert a.get('R0')==BASE+0x104790C
        state['locked']=True;return 0
    def unlock(a):
        assert state['locked'];state['locked']=False;return 0
    arm.stubs[0x139748]=lock;arm.stubs[0x13978C]=unlock
    def write(a):
        addr,value=a.get('R0'),a.get('R1');state['writes']+=1
        assert not state['locked']
        if addr==0x60000300:
            assert value in (0x2c,0x1c);state['gate']=value
        elif addr==0x60000330:
            assert state['gate']==0x2c;state['halfword']=value
        elif addr==0x60000338: assert value==0xfe and state['gate']==0x2c
        else: raise AssertionError(f'Unexpected peripheral write {addr:#x}')
        return 0
    def read(a):
        addr=a.get('R0');assert state['gate']==0x2c
        if addr==0x60000338: return 0
        assert addr==0x60000334
        offset=state['halfword']*2;assert 0<=offset<0x4000000
        state['reads']+=1
        return byte_at(offset)|(byte_at(offset+1)<<8)
    arm.stubs[0x132690]=write;arm.stubs[0x1326B4]=read
    def send(a):
        assert a.get('R0')==BASE+0x1B5AE1C
        assert state['gate']==0x1c and not state['paused'], 'MIDI before TG resume'
        length=a.get('R2');assert 14<=length<=512
        state['frames'].append(bytes(a.uc.mem_read(a.get('R1'),length)));return 0
    arm.stubs[0x2B7E80]=send
    arm.uc.hook_add(UC_HOOK_MEM_READ,lambda uc,access,addr,size,value,user:
                   (_ for _ in ()).throw(AssertionError('Read past 8-byte event')),
                   begin=CONSUMER+8,end=CONSUMER+15)
    return arm,state

def call(arm,state,mode,block=0,channel=1):
    state['frames'].clear();before=state['reads']
    arm.uc.mem_write(GLOBAL+0x1350,bytes([channel-1]))
    wire=bytes([0xf0,0x42,0x30+channel-1,0,1,0x49,0x72,0x18,mode,block>>7,block&127,0xf7])
    for byte in wire: arm.call(0x2CC9EC,0,byte,count=10000)
    arm.uc.mem_write(CONSUMER,b'\xa5'*16)
    assert arm.call(0x2B7D74,FIFO,CONSUMER)==1
    state['events'].append(bytes(arm.uc.mem_read(CONSUMER,8)).hex())
    arm.call(0x2C1A6C,CONSUMER,CONTEXT,count=150000000)
    assert arm.get('SP')==arm.stack and state['gate']==0x1c and not state['paused'] and not state['locked']
    return b''.join(state['frames']),state['reads']-before

def main():
    manifest=build();fw=Firmware();fw.data=(OUT/'candidate/KROSSAPP.BIN').read_bytes()
    arm,state=machine(fw);cases=[]
    for channel in range(1,17):
        data,reads=call(arm,state,0,channel=channel)
        assert data==bytes([0xf0,0x42,0x30+channel-1,0,1,0x49,0x7d,0x4b,0x52,0x4f,0x53,0x45,3,0xf7]) and reads==0
    for mode,action in [(3,'scratch'),(1,'tail')]:
        data,reads=call(arm,state,mode);report,payload=validate(data,action)
        assert reads==(8 if mode==1 else 0)
        if mode==1: assert payload==TAIL
        assert bytes(arm.uc.mem_read(RAM,RESERVED))==b'\xff'*RESERVED
        cases.append(dict(action=action,report=report,TG_u16_reads=reads))
    for block in (0,255):
        data,reads=call(arm,state,2,block)
        report,record=validate(data,'block',block)
        expected=bytes(byte_at(block*0x40000+i) for i in range(0x40000))
        assert reads==131072 and record[64:]==expected
        assert bytes(arm.uc.mem_read(RAM,RESERVED))==b'\xff'*RESERVED
        assert state['pause_resume'][-2:]==['pause','resume']
        cases.append(dict(action='block',block=block,report=report,TG_u16_reads=reads,
                          frame_count=len(state['frames']),wire_bytes=len(data),all_payload_bytes_match=True))
        print(f'Original TG read + framed transfer block {block}: PASS',flush=True)
        # Corruption and missing chunks must fail before a valid record exists.
        fs=decode(data);bad=bytearray(fs[1][1]);bad[-1]^=1
        altered=frame(fs[0][0],fs[0][1])+frame(0x11,bad)+b''.join(frame(k,r) for k,r in fs[2:])
        for invalid in (altered,b''.join(frame(k,r) for k,r in fs[:1]+fs[2:]),data[:-1]):
            try: validate(invalid,'block',block)
            except ValueError: pass
            else: raise AssertionError('Bad stream accepted')
    arm.uc.mem_write(RAM,b'\x00');data,reads=call(arm,state,3)
    assert reads==0 and decode(data)[0][0]==0x13 and bytes(arm.uc.mem_read(RAM,1))==b'\x00'
    try: validate(data,'scratch')
    except ValueError as error: assert str(error)=='Instrument error 2'
    else: raise AssertionError('Dirty RAM accepted')
    arm.uc.mem_write(RAM,b'\xff')
    # Invalid modes/indices cause no TG or RAM operation.
    for mode,block in ((4,0),(127,0),(1,1),(3,1)):
        data,reads=call(arm,state,mode,block);assert not data and reads==0
    for n in range(280):
        raw=bytes((i*137+n)&255 for i in range(n));assert unpack(pack(raw))==raw
    report=dict(scope='Offline mocked ARM, synthetic TG data; no hardware or synthetic image saved',
                candidate_sha256=manifest['candidate_sha256'],code_bytes=manifest['code_bytes'],
                identity_channels=16,cases=cases,dirty_RAM_rejected=True,invalid_requests=4,
                packing_lengths_verified=280,corrupt_missing_truncated_streams_rejected=True,
                real_gate_and_peripheral_polling_code_executed=True,
                voice_pause_resume=state['pause_resume'],no_MIDI_while_TG_read_mode=True,
                scratch_restored_to_FF=True,no_heap_in_handler=True,hardware_tested=False,
                real_ROM_bytes_recovered=0,
                source_sha256={name:hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in
                               ('kross_rom_stage_b.c','build_rom_stage_b.py','arm_research_link.py','verify_rom_stage_b.py','parse_rom_midi.py')})
    (OUT/'verification-arm.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
