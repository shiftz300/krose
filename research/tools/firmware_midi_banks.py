#!/usr/bin/env python3
"""Decode incoming MIDI bank pairs with original ARM and independent tables."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def signed(b):return b-256 if b&128 else b
def variations(f,base,program):
    offset=f.u32(base+4*program)-BASE;result=[]
    for i in range(16):
        value=signed(f.data[offset+i])
        if value==-1:return result
        result.append(value)
    raise AssertionError(('Unterminated variant list',base,program))
def model(f,encoded,program,alternate,unavailable=-1,special=0):
    if encoded==65535:return encoded,program,0,special
    msb,lsb=divmod(encoded,256)
    if msb==255:msb=0
    elif lsb==255:lsb=0
    raw=msb*256+lsb;bank=raw;valid=1;query=False
    if raw==0x3800:bank=10
    elif raw in [0x3E00,0x7800]:bank=20
    elif msb==0x79:
        if lsb<=9:bank=10+lsb
        else:valid=0
    elif alternate:
        if not raw:bank=10;query=True
        elif raw<=127:
            table=variations(f,0x4ADFC4,program);bank=11+table.index(raw) if raw in table else 10;query=True
        elif msb<=55:
            if program<=119:
                table=variations(f,0x4AE1C4,program);bank=11+table.index(msb) if msb in table else 10
            else:bank=10 if msb>signed(f.data[0x4515B4+program-120]) else msb+10
            query=bank<=20;valid=int(query)
        elif msb==126:bank=20;program=56;query=True
        elif msb==127:bank=20;program=0 if program>55 else program;special=1;query=True
        elif 0x3F00<=raw<=0x3F09:bank=raw-0x3F00;query=True
        elif 0x3F0A<=raw<=0x3F10:bank=raw-0x3F0A;query=True
        elif raw==0x4000:
            bank=signed(f.data[0x4514AC+program]);program=120+(program>>4);query=0<=bank<=20;valid=int(query)
        else:valid=0
    elif raw<=9:query=True
    elif 10<=raw<=16:bank=raw-10;query=True
    else:valid=0
    if query and bank==unavailable:bank=0
    return bank,program,valid,special

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('MIDI-bank-conversion',0x278AF0,0x278CA8),('MIDI-bank-variation-tables',0x278A54,0x278AF0),('MIDI-program-change-input',0x26FDA4,0x26FF84)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    if not args.verify_arm:return
    a=Arm(f);ptr=0x11000000;program_ptr=ptr+4;queries=[];unavailable=-1
    def bank_available(m):queries.append(m.get('R1'));return int(m.get('R1')==unavailable)
    a.stubs={0x278248:bank_available};a.write(0xC1745678,0x11001000)
    def run(encoded,program,alternate,special=0):
        a.write(ptr,encoded,program);a.uc.mem_write(0xC1DCC2D8+0x1352,bytes([16 if alternate else 0]));a.uc.mem_write(0xC1B5719C,bytes([special]));queries.clear()
        returned=a.call(0x278AF0,ptr,program_ptr)
        bank,prog=struct.unpack('<II',a.uc.mem_read(ptr,8));flag=a.uc.mem_read(0xC1B5719C,1)[0]
        expected=model(f,encoded,program,alternate,unavailable,special);assert (bank,prog,returned,flag)==expected,(hex(encoded),program,alternate,unavailable,(bank,prog,returned,flag),expected)
        return dict(encoded_bank=encoded,program_in=program,alternate=alternate,bank=bank,program=prog,accepted=returned,special_low_drums=flag,availability_queries=list(queries))
    counts={};digest=hashlib.sha256();cases=0
    for msb,lsb,alternate,program in itertools.product(range(128),range(128),range(2),[0,24,127]):
        row=run(msb*256+lsb,program,alternate);digest.update(json.dumps(row,sort_keys=True).encode());cases+=1
    counts['legal_bank_pairs']=cases
    cases=0
    for encoded,alternate,program,special in itertools.product([65535]+[0xFF00+n for n in [0,1,9,16,32,127]]+[n*256+255 for n in [0,1,55,56,63,64,120,121,126,127]],range(2),[0,24,56,127],range(2)):
        run(encoded,program,alternate,special);cases+=1
    counts['missing_byte_cases']=cases
    cases=0
    for program,alternate,encoded in itertools.product(range(128),range(2),[0,1,0x3800,0x3E00,0x3F00,0x3F09,0x3F0A,0x4000,0x7800,0x7900,0x7909,0x790A,0x7E00,0x7F00]):
        run(encoded,program,alternate);cases+=1
    counts['all_program_special_banks']=cases
    cases=0
    for unavailable in range(21):
        for encoded,alternate in itertools.product([0,1,9,16,0x3800,0x3F09,0x7800,0x7909,0x7E00,0x7F00],range(2)):run(encoded,56,alternate);cases+=1
    counts['bank_unavailable_cases']=cases;unavailable=-1
    examples=[run(encoded,program,alternate) for encoded,program,alternate in [(0,0,0),(0,0,1),(0x3F00,0,1),(0x7909,0,0),(0x7E00,127,1),(0x7F00,127,1),(65535,24,0)]]
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),counts=counts,matrix_sha256=digest.hexdigest(),examples=examples,
        variation_banks=[variations(f,0x4ADFC4,n) for n in range(128)],variation_msbs=[variations(f,0x4AE1C4,n) for n in range(120)],extended_caps=list(f.data[0x4515B4:0x4515BC]),
        boundaries=['Original bank conversion278AF0, variation search278A54/278A90/278AA0 and special table2787FC execute',
            'Bank availability278248 is the only intercepted branch:0 means populated,1 empty; empty admitted bank maps to0 while retaining successful return',
            'Independent model parses immutable signed variation lists and models prefix priorities, missing-byte sentinels, Program rewriting and special drum flag',
            'Program-change caller26FDA4..26FF84 recorded statically; this result does not execute complete MIDI front-end or actual Program loading',
            'Global config bit1352.bit4 is called alternate mapping here; no undocumented universal GM compatibility claim'])
    (OUT/'midi-banks-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=counts),indent=2))
if __name__=='__main__':main()
