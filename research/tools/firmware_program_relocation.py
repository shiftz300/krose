#!/usr/bin/env python3
"""Check native post-import Program reference relocation in private memory."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_expansion_pcm import read_library
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def u16(raw,at):return struct.unpack_from('<H',raw,at)[0]
def put16(raw,at,value):struct.pack_into('<H',raw,at,value&65535)
def program_ref(raw,at):return raw[at]+128*raw[at+1]
def set_program_ref(raw,at,value):raw[at:at+2]=bytes([value&127,value>>7])

def model(raw,kit_target,pattern_target,program_target,program_count):
    out=bytearray(raw)
    if out[0x508]&7==2 and u16(out,0x566)>=42:put16(out,0x566,min(57,u16(out,0x566)-42+kit_target))
    if u16(out,0x4DC)>1028:put16(out,0x4DC,min(1284,u16(out,0x4DC)+pattern_target-1024))
    for at in [0x4F2,0x502]:
        value=program_ref(out,at)
        if 768<=value<768+program_count:set_program_ref(out,at,min(1279,value-768+program_target))
    return bytes(out)

class Rig:
    def __init__(self,f):
        self.a=a=Arm(f);self.record=0x11010000;self.object=0x11001000;self.storage=[];self.freed=[]
        def allocate(m):assert m.get('R0')==16;return self.object
        def lookup(m):
            assert m.get('R0')==0 and m.get('R1')==9 and m.get('R2')==17
            self.storage.append([m.get('R0'),m.get('R1'),m.get('R2')]);return self.record
        a.stubs={0x14E730:allocate,0x14E760:lambda m:self.freed.append(m.get('R0')) or 0,
            0x2DC184:lambda m:0,0x2DC1BC:lambda m:0,0x2C4474:lambda m:0,
            0x2A6A6C:lambda m:128,0x2A6CBC:lookup}
    def run(self,raw,kit_target=42,pattern_target=1024,program_target=768,program_count=128):
        a=self.a;sentinel=b'\xA5'*32;a.uc.mem_write(self.record-32,sentinel+raw+sentinel);self.storage.clear();self.freed.clear()
        a.call(0x1F373C,0,9,17,kit_target,stack=(4,pattern_target,0,program_target,program_count))
        actual=bytes(a.uc.mem_read(self.record,len(raw)));expected=model(raw,kit_target,pattern_target,program_target,program_count)
        assert actual==expected,(kit_target,pattern_target,program_target,program_count,[hex(i) for i,(x,y) in enumerate(zip(actual,expected)) if x!=y][:12])
        assert bytes(a.uc.mem_read(self.record-32,32))==bytes(a.uc.mem_read(self.record+len(raw),32))==sentinel
        assert self.storage==[[0,9,17]] and self.freed==[self.object]
        return actual

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('program-reference-relocation',0x1F373C,0x1F3970),('program-relocation-caller',0x1EEA8C,0x1EEB48)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    r=Rig(f);template=bytearray(2144);template[0x508]=2;kit_cases=pattern_cases=program_ref_cases=0
    digest=hashlib.sha256()
    # Full low-byte kit domain, all oscillator modes and legal user-kit destinations.
    for mode,kit,target in itertools.product(range(8),list(range(256))+[32767,32768,65535],range(42,58)):
        raw=bytearray(template);raw[0x508]=mode;put16(raw,0x566,kit);out=r.run(raw,kit_target=target);digest.update(out);kit_cases+=1
    for value,target in itertools.product([0,1023,1024,1027,1028,1029,1030,1279,1280,1284,1285,32767,32768,65535],[1024,1025,1152,1283,1284]):
        raw=bytearray(template);put16(raw,0x4DC,value);r.run(raw,pattern_target=target);pattern_cases+=1
    for count,target in itertools.product([0,1,32,64,128],[0,127,128,768,1216,1279]):
        values=sorted({0,767,768,769,895,896,1279,1280,16383,max(0,767+count),768+count})
        for first,second in itertools.product(values,values):
            raw=bytearray(template);set_program_ref(raw,0x4F2,first);set_program_ref(raw,0x502,second);r.run(raw,program_target=target,program_count=count);program_ref_cases+=1
    libs=[read_library(n) for n in [1,2,4]];inputs=[];records=[];links=[]
    for lib in libs:
        inputs.extend(lib['inputs'])
        for program in lib['programs']:
            path=ROOT/program['path'];raw=path.read_bytes();inputs.append(path)
            section=lib['sections']['1KBP'];start=section['payload_offset']+2144*program['index']
            assert sha(path)==program['sha256'] and raw==lib['decoded_bytes'][start:start+2144]
            for kit_target,pattern_target,program_target in [(42,1024,768),(46,1152,896),(54,1284,1216)]:
                out=r.run(raw,kit_target,pattern_target,program_target,len(lib['programs']))
                changed=[i for i,(x,y) in enumerate(zip(raw,out)) if x!=y]
                row=dict(program=f"EXPCM{lib['id']:03d}:{program['index']:03d}",name=program['name'],kit_target=kit_target,pattern_target=pattern_target,program_target=program_target,changed_offsets=changed,sha256=hashlib.sha256(out).hexdigest())
                if raw[0x508]&7==2:row.update(stored_kit=u16(raw,0x566),relocated_kit=u16(out,0x566));links.append(row)
                records.append(row)
    # Confirm no implicit rename, sample bank rewrite, or reference edits outside the rules.
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={'firmware_expansion_pcm.py':sha(ROOT/'research/tools/firmware_expansion_pcm.py')},
        inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in dict.fromkeys(inputs)],
        counts=dict(kit_cases=kit_cases,arpeggio_pattern_cases=pattern_cases,program_reference_cases=program_ref_cases,source_programs=128,source_contexts=len(records)),kit_matrix_sha256=digest.hexdigest(),records=records,drum_links=links,
        rules=dict(kit='if mode&7==2 and kit>=42: min(57,kit-42+kit_target)',arpeggio_pattern='if value>1028: min(1284,value+pattern_target-1024)',program_reference='for both references: if 768<=value<768+program_count: min(1279,value-768+program_target)'),
        boundaries=['Original function1F373C, typed Program adapter1F282C/1F2934, tag layout2A7204 and normal destructor execute',
            'Storage lookup2A6CBC supplies one private Program at logical bank9/index17; count getter2A6A6C returns128; allocation/free, base destructor and exception registration intercepted',
            'Every case compares the full2144-byte record and32-byte guards; only parameter relocation is executed, not full file import, disk or hardware',
            'Caller1EEA8C..1EEB48 passes kit destination as loader+2EC+42, arpeggio destination as loader+304+1024, referenced Program base as destination Program bank*128+index, and imported Program count',
            'Duplicate saved kit45 remains duplicate after translation; file kit order and actual full importer placement still require separate evidence'])
    (OUT/'program-relocation-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=result['counts']),indent=2))
if __name__=='__main__':main()
