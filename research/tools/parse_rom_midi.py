#!/usr/bin/env python3
"""Pure stage-B frame/CRC decoder; never opens MIDI or device nodes."""
import hashlib,io,struct,zlib
from recover_rom_stream import BLOCK_BYTES,parse_records

PREFIX=bytes.fromhex('f042300001497d4b524f534503')

def pack(raw):
    result=bytearray()
    for start in range(0,len(raw),7):
        chunk=raw[start:start+7]
        result.append(sum((x>>7)<<i for i,x in enumerate(chunk)))
        result.extend(x&127 for x in chunk)
    return bytes(result)

def unpack(data):
    if any(b&128 for b in data): raise ValueError('Non-seven-bit packed data')
    out=bytearray();offset=0
    while offset<len(data):
        mask=data[offset];offset+=1;n=min(7,len(data)-offset)
        if not n or mask>>n: raise ValueError('Invalid/truncated MSB group')
        out.extend(data[offset+i]|(((mask>>i)&1)<<7) for i in range(n));offset+=n
    return bytes(out)

def frame(kind,raw,channel=1):
    return PREFIX[:2]+bytes([0x30+channel-1])+PREFIX[3:]+bytes([kind])+pack(raw)+b'\xf7'

def decode(data,expected_channel=1):
    frames=[];current=None
    for byte in data:
        if byte>=0xf8: continue
        if byte==0xf0:
            if current is not None: raise ValueError('Interrupted SysEx frame')
            current=bytearray([byte]);continue
        if current is None: raise ValueError('Unexpected bytes outside SysEx')
        current.append(byte)
        if len(current)>512: raise ValueError('Oversized frame')
        if byte!=0xf7:
            if byte&128: raise ValueError('Invalid status inside SysEx')
            continue
        message=bytes(current);current=None
        expected=PREFIX[:2]+bytes([0x30+expected_channel-1])+PREFIX[3:]
        if len(message)<16 or message[:13]!=expected: raise ValueError('Unexpected model/channel/revision')
        frames.append((message[13],unpack(message[14:-1])))
    if current is not None: raise ValueError('Truncated SysEx capture')
    if not frames: raise ValueError('No stage-B frames')
    return frames

def validate(data,action,block=255,channel=1):
    frames=decode(data,channel)
    for kind,raw in frames:
        if kind==0x13:
            if len(raw)!=8 or raw[:4]!=b'K2X1': raise ValueError('Malformed error frame')
            raise ValueError(f'Instrument error {struct.unpack_from("<I",raw,4)[0]}')
    if action=='tail':
        if len(frames)!=1 or frames[0][0]!=0x14: raise ValueError('Expected one tail frame')
        raw=frames[0][1]
        if len(raw)!=32 or raw[:4]!=b'K2W1': raise ValueError('Invalid tail record')
        address,length,crc=struct.unpack_from('<3I',raw,4)
        if address!=0x3fffff0 or length!=16 or zlib.crc32(raw[16:])!=crc:
            raise ValueError('Invalid tail range/CRC')
        return dict(action=action,bytes=16,tail_hex=raw[16:].hex(),KORG_marker=raw[16:20]==b'KORG',crc32=f'{crc:08x}'),raw[16:]
    if action=='scratch':
        if len(frames)!=1 or frames[0][0]!=0x15: raise ValueError('Expected one RAM test frame')
        raw=frames[0][1]
        if len(raw)!=16 or raw[:4]!=b'K2R1': raise ValueError('Invalid RAM test record')
        address,length,status=struct.unpack_from('<3I',raw,4)
        if (address,length,status)!=(0xc0520000,0x40200,0): raise ValueError('RAM check failed/range mismatch')
        return dict(action=action,RAM_address=hex(address),bytes=length,write_read_restore_passed=True),None
    if action!='block' or not 0<=block<256: raise ValueError('Invalid action/block')
    if frames[0][0]!=0x10 or frames[-1][0]!=0x12: raise ValueError('Missing metadata/end frame')
    header=frames[0][1]
    if len(header)!=64 or struct.unpack_from('<I',header,20)[0]!=block: raise ValueError('Wrong block metadata')
    if any(kind!=0x11 for kind,_ in frames[1:-1]): raise ValueError('Unexpected frame inside block')
    chunks={};duplicates=0
    for kind,raw in frames[1:-1]:
        if len(raw)<16 or raw[:4]!=b'K2D1': raise ValueError('Invalid data header')
        offset,n,reserved,crc=struct.unpack_from('<IHHI',raw,4)
        payload=raw[16:]
        if n!=256 or len(payload)!=n or reserved or offset%256 or offset+n>BLOCK_BYTES:
            raise ValueError('Invalid chunk range/length')
        if zlib.crc32(payload)!=crc: raise ValueError('Chunk CRC mismatch')
        if offset in chunks:
            if chunks[offset]!=payload: raise ValueError('Conflicting duplicate chunk')
            duplicates+=1
        chunks[offset]=payload
    if set(chunks)!=set(range(0,BLOCK_BYTES,256)): raise ValueError('Missing block chunks')
    payload=b''.join(chunks[i] for i in range(0,BLOCK_BYTES,256))
    end=frames[-1][1]
    if len(end)!=16 or end[:4]!=b'K2E1' or struct.unpack_from('<3I',end,4)!=(block,BLOCK_BYTES,zlib.crc32(payload)):
        raise ValueError('End record CRC/range mismatch')
    record=header+payload
    parsed,info=parse_records(io.BytesIO(record),require_complete=False)
    if parsed.get(block)!=payload: raise ValueError('Record mismatch')
    return dict(action=action,block=block,bytes=BLOCK_BYTES,chunks=len(chunks),duplicates=duplicates,
                crc32=f'{zlib.crc32(payload):08x}',payload_sha256=hashlib.sha256(payload).hexdigest(),
                provenance=info['provenance_note']),record
