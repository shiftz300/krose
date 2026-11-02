#!/usr/bin/env python3
"""Original recorded SysEx blocks, raw playback and parameter-message routing."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import struct
from pathlib import Path
from program_firmware import Arm, Firmware, FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT = ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'


def blocks(payload, flags=0):
    header = bytes([15, flags, 0, 0, 0, 0, 120, 0])
    rows = [bytes([7])+bytes((payload[i:i+7]+[255]*7)[:7][::-1]) for i in range(0,len(payload),7)]
    return header+b''.join(rows)+bytes([8])+bytes(7)


def parameter(channel, group, index, value, flags=1):
    data = [0x42, 0x30+channel, 0, 1, 0x49, 0x41, 4,
            group >> 7, group & 127, index >> 7, index & 127,
            (value >> 28) & 15, (value >> 21) & 127, (value >> 14) & 127, (value >> 7) & 127, value & 127]
    return blocks(data, flags), data


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--verify-arm', action='store_true')
    args = parser.parse_args();f = Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name, lo, hi in [('track-sysex-play',0x2564E0,0x256810),
                         ('track-sysex-classify',0x23DA1C,0x23DD1C),
                         ('track-sysex-value',0x23D83C,0x23DA1C),
                         ('track-sysex-routing',0x241D18,0x2422C4)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm:return
    a=Arm(f);event=0x11000000
    wire, local, decoded, writes, notifications = [], [], [], [], []
    cancel_at = None
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def pb(p,v):a.uc.mem_write(p,bytes([v&255]))
    def call(p,*values,**kw):return a.call(p,*values,**kw)
    def send(m):wire.append([m.get('R0'),bytes(m.uc.mem_read(m.get('R1'),m.get('R2'))).hex()]);return 1
    def receive(m):
        local.append(m.get('R1')&255)
        if cancel_at is not None and len(local)==cancel_at:pb(0xC171696C,1)
        return 0
    def decode(m):
        decoded.append([m.get('R1'),m.get('R2'),m.get('R3'),w(m.get('SP')),w(m.get('SP')+4)])
        return 0
    def capture(out):
        def stub(m):out.append([m.get('R1'),m.get('R2'),m.get('R3')]);return 0
        return stub
    def reset(track=0, local_off=0, wire_off=0, enabled=1):
        for out in [wire,local,decoded,writes,notifications]:out.clear()
        ph(0xC171D4DA,wire_off<<track);ph(0xC171D4DC,local_off<<track)
        pb(0xC1DCD62A,enabled);pb(0xC171696C,0)
        a.stubs={0x2B7E80:send,0x2C2E90:receive,0x241EBC:decode}
    def ports():return [[int(row[1],16) for row in wire if row[0]==p] for p in [0xC10051B8,0xC1B5AE1C]]

    classification_cases=0
    base,data=parameter(0,0,0,0)
    for field,value in itertools.product(range(7),range(256)):
        altered=data.copy();altered[field]=value
        a.uc.mem_write(event,blocks(altered))
        expected = (value & 0xF0 == 0x30) if field==1 else value==data[field]
        assert call(0x23DA1C,event)==int(expected)
        classification_cases+=1
    for chunk_kind in [0,1,6,7,8,9,255]:
        for offset in [8,16,24,32]:
            modified=bytearray(base);modified[offset]=chunk_kind;a.uc.mem_write(event,bytes(modified))
            assert call(0x23DA1C,event)==int(chunk_kind==(8 if offset==32 else 7))
            classification_cases+=1

    raw_cases=0
    for length,track,local_off,wire_off,enabled in itertools.product([0,1,6,7,8,14,15,21,22,64], [0,15], range(2),range(2),range(2)):
        reset(track,local_off,wire_off,enabled)
        payload=[0x7D]+[(i*37)&127 for i in range(max(0,length-1))] if length else []
        a.uc.mem_write(event,blocks(payload));call(0x2564E0,event,track)
        expected=[0xF0]+payload+[0xF7]
        assert ports()==([expected]*2 if not wire_off else [[],[]])
        assert local==(expected if enabled and not local_off else [])
        assert decoded==[];raw_cases+=1

    padding_cases=0
    for padding in range(7):
        reset();payload=[0x7D,1,2,3,4,5,6];payload[padding]=255
        a.uc.mem_write(event,blocks(payload));call(0x2564E0,event,0)
        expected=[0xF0]+[x for x in payload if x!=255]+[0xF7]
        assert ports()==[expected]*2 and local==expected;padding_cases+=1

    abort_cases=[]
    payload=[0x7D]+list(range(20))
    for trigger in [1,2,7,8,9,14,15,16,21,22]:
        reset();cancel_at=trigger
        a.uc.mem_write(event,blocks(payload));call(0x2564E0,event,0)
        consumed=max(7,((trigger-1+6)//7)*7)
        expected=[0xF0]+payload[:consumed]+[0xF7]
        assert local==expected and ports()==[expected]*2
        abort_cases.append(dict(trigger_byte_count=trigger,payload_sent=min(consumed,len(payload))))
    cancel_at=None

    decode_cases=0
    for channel,group,index,value in itertools.product([0,7,15],[0,78,127,128,16383],[0,127,128,16383],[0,1,127,128,0x7FFFFFFF,0x80000000,0xFFFFFFFF]):
        reset();raw,_=parameter(channel,group,index,value)
        a.uc.mem_write(event,raw);call(0x2564E0,event,15)
        assert decoded==[[channel,group,index,15,value]]
        assert local==[] and wire==[];decode_cases+=1

    # Without header flag bit 0, original namespace/parameter-count validation is
    # required before taking the decoded parameter path.
    validation=[]
    for raw_group in [0,8,35,78,79,16383]:
        namespace=raw_group+100
        count=struct.unpack_from('<H',f.data,f.u32(0x407BD0+4*namespace)-0xC0000000)[0] if namespace<=178 else 0
        for index in sorted(set([0,max(0,count-1),count,16383])):
            reset();raw,_=parameter(0,raw_group,index,1,flags=0);a.uc.mem_write(event,raw)
            call(0x2564E0,event,0)
            expected=namespace<=178 and index<count
            assert bool(decoded)==expected and local==[] and wire==[]
            validation.append(dict(group=raw_group,count=count,index=index,accepted=expected))

    playback_cases=0
    cursor,ctx=0x11010000,0x11011000
    for recognized,now,skip,loop in itertools.product(range(2),[119,120,121],range(2),range(2)):
        reset();raw,payload=parameter(3,0,0,123) if recognized else (blocks([0x7D,1,2,3,4,5,6,7]),[0x7D,1,2,3,4,5,6,7])
        stream=struct.pack('<BBBBHH',1,0,0,0,1+len(raw)//8,0)+raw+struct.pack('<BBBBHH',1,0,0,0,1,999)
        a.uc.mem_write(event,stream)
        a.uc.mem_write(ctx,struct.pack('<IIIHHHHHBx',0,0,3,0,0,now,1920,1,0))
        ph(0xC171D4D8,skip);ph(0xC171D514,0);pb(0xC171D4C8,0)
        a.uc.mem_write(0xC171BFA0,struct.pack('<H',20)+b'\x13'*1000);pb(0xC1714D11,0)
        call(0x241364,cursor);call(0x24157C,cursor,event,0,0,stack=(loop,0));call(0x241748,cursor,0,0)
        call(0x256810,ctx,cursor)
        active=now>=120 and not skip
        assert decoded==([[3,0,0,0,123]] if active and recognized else [])
        expected=[0xF0]+payload+[0xF7] if active and not recognized else []
        assert local==expected and ports()==[expected]*2
        playback_cases+=1

    # Original route predicates and serializer, capturing actual parameter writes
    # and application notification as separate boundaries.
    root=0x11020000;a.write(0xC0F55850,root);a.write(root+0x20,0x11021000)
    routes=[]
    parameters=[(0,0),(35,0)]+[(g,34) for g in range(8,24)]+[(8,33),(23,33),(7,34),(24,34)]
    for status,enabled,local_off,wire_off,channel_match,(group,index) in itertools.product(range(8),range(2),range(2),range(2),range(2),parameters):
        track=5;reset(track,local_off,wire_off,enabled)
        del a.stubs[0x241EBC]
        a.stubs[0x23D61C]=capture(writes);a.stubs[0x3A1AC]=capture(notifications)
        pb(0xC17456AC+0x4FE+44*track,status<<5)
        pb(0xC1DCD628,3 if channel_match else 4)
        value=0x87654321
        raw,payload=parameter(3,group,index,value);a.uc.mem_write(event,raw)
        call(0x2564E0,event,track)
        override=8<=group<=23 and index==34
        internal=enabled and group!=35 and status in [1,2] and (not local_off or override) and channel_match
        external=status in [2,3,4] and (not wire_off or override)
        expected=[[group+100,index,value]] if internal else []
        assert writes==notifications==expected,(status,enabled,local_off,wire_off,channel_match,group,index,writes)
        assert ports()==([[0xF0]+payload+[0xF7]]*2 if external else [[],[]])
        routes.append(dict(status=status,enabled=enabled,local_off=local_off,wire_off=wire_off,channel_match=channel_match,
                           group=group,index=index,local=bool(internal),external=external))

    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
        classification_cases=classification_cases,raw_cases=raw_cases,padding_cases=padding_cases,
        abort_cases=abort_cases,parameter_decode_cases=decode_cases,validation=validation,routes=routes,playback_cases=playback_cases,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        boundaries=['Original recorded SysEx classification, block iteration, padding removal, abort check, parameter decode and routing',
                    'Synthetic records; raw local MIDI parser 2C2E90 captured, not executed in these cases',
                    'Parameter write 23D61C and application notification 3A1AC captured; full parameter side effects pending',
                    'Original external serializer and two-port fanout run; port buffer 2B7E80 intercepted',
                    'Malformed chunk type enters assertion loop in disassembly; not executed; file-load reachability unproven'])
    (OUT/'sequence-sysex-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,classification_cases=classification_cases,raw_cases=raw_cases,
                         parameter_decode_cases=decode_cases,validation=len(validation),routes=len(routes),abort_cases=len(abort_cases)),indent=2))


if __name__=='__main__':main()
