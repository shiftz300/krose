#!/usr/bin/env python3
"""Original resource-section reader/converter with private stream and storage."""
import argparse,contextlib,hashlib,io,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_expansion_pcm import read_library
from firmware_program_relocation import Rig as RelocationRig
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def word(data,at):return struct.unpack_from('<I',data,at)[0]

class Rig:
    def __init__(self,f):
        self.a=a=Arm(f);a.uc.mem_map(0x12000000,0x400000)
        self.obj,self.stream,self.vtable,self.count=0x11001000,0x11001100,0x11001200,0x11001300
        self.work=0x11060000;self.heap=0x11020000;self.next_heap=self.heap;self.allocations=[];self.frees=[]
        def allocate(m):
            size=m.get('R0');assert 0<size<=0x20000
            p=self.next_heap;self.next_heap+=(size+15)&~15;assert self.next_heap<self.work
            m.uc.mem_write(p,bytes(size));self.allocations.append((p,size));return p
        def free(m):self.frees.append(m.get('R0'));return 0
        def assertion(m):raise AssertionError(dict(native_assert_lr=hex(m.get('LR')),arguments=[m.get('R'+str(i)) for i in range(3)]))
        def read(m):
            assert m.get('R0')==self.stream;dest,size=m.get('R1'),m.get('R2');before=self.position
            if self.position+size>len(self.data):self.io.append(dict(op='read-failed',position=before,size=size));return 0
            m.uc.mem_write(dest,self.data[self.position:self.position+size]);self.position+=size;self.io.append(dict(op='read',position=before,size=size));return 1
        def seek(m):
            assert m.get('R0')==self.stream;offset=m.get('R1');offset=offset-2**32 if offset&2**31 else offset;origin=m.get('R2')
            p=offset+(0 if origin==0 else self.position if origin==1 else len(self.data));assert 0<=p<=len(self.data)
            self.position=p;self.io.append(dict(op='seek',position=p,origin=origin));return 1
        def tell(m):assert m.get('R0')==self.stream;return self.position
        def lookup(m):
            kind,bank,index=[m.get('R'+str(i)) for i in range(3)];assert kind==self.kind
            capacity=self.capacity;assert 0<=index<capacity and self.first_bank<=bank<=self.last_bank,(kind,bank,index)
            slot=(bank-self.first_bank)*capacity+index;address=0x12000000+32+slot*(self.record_size+64)
            self.lookups.append(dict(kind=kind,bank=bank,index=index,address=address));return address
        a.stubs={0x14E730:allocate,0x14E760:free,0x14E968:lambda m:self.work,0x2DC184:lambda m:0,0x2DC1BC:lambda m:0,
            0x2C4474:lambda m:0,0x2C5220:assertion,0x2A6CBC:lookup,0x2F0000:read,0x2F0004:seek,0x2F0008:tell}
        a.write(self.stream,self.vtable);a.write(self.vtable+0x10,BASE+0x2F0000);a.write(self.vtable+0x18,BASE+0x2F0004);a.write(self.vtable+0x1C,BASE+0x2F0008)
        a.call(0x1F2E34,self.obj,self.stream,0)
    def run(self,data,tag,bank,index,last_bank):
        a=self.a;self.data=data;self.position=0;self.io=[];self.lookups=[];self.allocations.clear();self.frees.clear()
        self.kind,self.capacity,self.record_size={'1KBD':(3,16,8728),'1KBP':(0,128,2140),'1KBA':(4,256,552)}[tag]
        self.first_bank=bank;self.last_bank=last_bank
        extent=(last_bank-bank+1)*self.capacity*(self.record_size+64);assert extent<=0x400000
        a.uc.mem_write(0x12000000,b'\xa5'*extent);a.write(self.count,0)
        result=a.call(0x1F32C0,self.obj,int.from_bytes(tag.encode(),'little'),bank,index,stack=(last_bank,0,self.count),count=30000000)
        copied=word(bytes(a.uc.mem_read(self.count,4)),0);records=[];self.actual_records=[]
        for request in self.lookups:
            p=request['address'];raw=bytes(a.uc.mem_read(p,self.record_size));assert bytes(a.uc.mem_read(p-32,32))==bytes(a.uc.mem_read(p+self.record_size,32))==b'\xa5'*32
            self.actual_records.append(raw)
            records.append(dict(bank=request['bank'],index=request['index'],sha256=hashlib.sha256(raw).hexdigest(),name=raw[:24].decode('ascii',errors='replace').rstrip(' \0')))
        # Independent section model: all complete file records are consumed
        # and checksummed, but destination writes stop after its last bank.
        expected=bytearray(b'\xa5'*extent);wanted=[];ok=0
        if len(data)>=32 and data[:4]==tag.encode():
            count,stride,version=word(data,12),word(data,16),word(data,20);assert stride%8==0 and version==37
            available=min(count,(len(data)-32)//stride);space=(last_bank-bank+1)*self.capacity-index
            writes=min(available,space)
            for i in range(writes):
                source=data[32+i*stride:32+i*stride+self.record_size];assert len(source)==self.record_size
                linear=index+i;dest_bank=bank+linear//self.capacity;dest_index=linear%self.capacity;offset=32+linear*(self.record_size+64)
                expected[offset:offset+self.record_size]=source;wanted.append(dict(bank=dest_bank,index=dest_index,sha256=hashlib.sha256(source).hexdigest(),name=source[:24].decode('ascii',errors='replace').rstrip(' \0')))
            checksum=sum(x[0] for x in struct.iter_unpack('<I',data[32:32+available*stride]))&0xFFFFFFFF
            ok=int(available==count and checksum==word(data,8))
        assert records==wanted and copied==len(wanted) and result==ok,(records,wanted,copied,result,ok)
        assert self.position==(32+word(data,12)*word(data,16) if ok else 0)
        assert bytes(a.uc.mem_read(0x12000000,extent))==expected
        return dict(returned=result,copied=copied,stream_position=self.position,stream_length=len(data),records=records,io=self.io.copy(),allocations=self.allocations.copy(),frees=self.frees.copy())
def section_bytes(lib,tag):
    s=lib['sections'][tag];return lib['decoded_bytes'][s['offset']:s['payload_offset']+s['bytes']]
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();r=Rig(f);libraries=[read_library(i) for i in [1,2,4]];cases=[];placements=[];sources=[]
    def run(lib,tag,bank,index,last_bank,variant='original',data=None):
        raw=section_bytes(lib,tag) if data is None else data;result=r.run(raw,tag,bank,index,last_bank)
        row=dict(library=lib['id'],tag=tag,bank=bank,index=index,last_bank=last_bank,variant=variant,source_section_sha256=hashlib.sha256(raw).hexdigest(),**result)
        cases.append(row);return row
    future=libraries[-1]
    for index in ([0] if args.smoke else range(16)):
        row=run(future,'1KBD',1,index,1);placements.append(row)
    if not args.smoke:
        for lib in libraries:
            for bank in [6,9]:
                for index in [0,96,127]:run(lib,'1KBP',bank,index,9)
            for index in [0,237,255]:run(lib,'1KBA',1,index,1)
        # A valid checksum with a full destination still returns success;
        # checksum/read errors retain already written records and rewind only
        # the private stream. Test each supported resource tag separately.
        for tag in ['1KBD','1KBP','1KBA']:
            data=section_bytes(future,tag);bank=6 if tag=='1KBP' else 1;last=9 if tag=='1KBP' else 1
            corrupt=bytearray(data);struct.pack_into('<I',corrupt,8,word(corrupt,8)^1)
            run(future,tag,bank,0,last,'checksum-header',bytes(corrupt))
            corrupt=bytearray(data);corrupt[32+24]^=1;run(future,tag,bank,0,last,'checksum-payload',bytes(corrupt))
            run(future,tag,bank,0,last,'short-last-record',data[:-1])
            run(future,tag,bank,0,last,'short-header',data[:31])
            corrupt=bytearray(data);corrupt[:4]=b'BAD!';run(future,tag,bank,0,last,'wrong-tag',bytes(corrupt))
            # The section kernel does not consult the declared byte length.
            # The outer parser must validate it before selecting a section.
            corrupt=bytearray(data);struct.pack_into('<I',corrupt,4,word(corrupt,4)+8)
            run(future,tag,bank,0,last,'declared-length-plus8',bytes(corrupt))
            empty=bytearray(data[:32]);struct.pack_into('<III',empty,4,0,0,0)
            run(future,tag,bank,0,last,'zero-records',bytes(empty))
    # Import real Program records, then pass the imported native2140-byte
    # payload to the earlier original reference-relocation function.
    imported=run(future,'1KBP',6,0,9);actual_programs=r.actual_records.copy();assert imported['copied']==64
    relocation=RelocationRig(f);links=[]
    for placement in placements:
        target=42+placement['index'];installed={42+x['index']:x for x in placement['records']}
        for number in [41,42,43,44]:
            raw=actual_programs[number];assert len(raw)==2140 and raw[0x508]&7==2
            moved=relocation.run(raw,kit_target=target,program_count=64);kit=int.from_bytes(moved[0x566:0x568],'little')
            assert kit in installed
            links.append(dict(destination_start=target,program=number,name=raw[:24].decode('ascii').rstrip(' \0'),stored_kit=int.from_bytes(raw[0x566:0x568],'little'),
                relocated_kit=kit,selected_kit_name=installed[kit]['name'],selected_kit_sha256=installed[kit]['sha256'],imported_program_sha256=hashlib.sha256(raw).hexdigest(),relocated_program_sha256=hashlib.sha256(moved).hexdigest()))
    for name,lo,hi in [('resource-section-import',0x1F32C0,0x1F363C),('resource-current-converter',0x1F2BE4,0x1F2E04),('resource-storage-capacity',0x2A6A6C,0x2A6CA8),('resource-import-call-site',0x1EE9FC,0x1EEB48)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    for lib in libraries:sources.extend(lib['inputs'])
    counts=dict(section_cases=len(cases),kit_placement_cases=len(placements),partial_successes=sum(x['returned']==1 and x['copied']<word(section_bytes(libraries[[1,2,4].index(x['library'])],x['tag']),12) for x in cases if x['variant']=='original'),
        failed_after_writes=sum(x['returned']==0 and x['copied']>0 for x in cases),program_kit_links=len(links))
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_expansion_pcm.py','firmware_program_relocation.py','firmware_inspect.py']},
        inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in dict.fromkeys(sources)],counts=counts,cases=cases,links=links,
        boundaries=['Original1F32C0 section loop,1F282C adapter,2A7204 type layout,2A6A6C capacity,1F2DF4 current-version conversion and lazy converter factory execute; no replacement of record conversion or relocation arithmetic',
            'Only stream read/seek/tell, storage lookup2A6CBC, private allocation/workspace/free, base destructor and exception registration supplied; private file reads fail without advancing when a complete request cannot be satisfied',
            'Current37-format1KBD/1KBP/1KBA records compare whole private destination including every untouched slot and32-byte per-record guards; Program disk stride2144 imports2140 native bytes, with alignment padding excluded',
            'All16 user-kit destinations execute actual Future Synth order; its64 actual imported Programs feed original1F373C for four kit Programs and map to actual installed kit records; duplicate references remain intact',
            'Capacity exhaustion can return1 after consuming/checksumming all records while copying only a prefix; checksum/short-read failures rewind the stream but do not undo prior destination writes',
            'Section byte-length metadata is not validated by this kernel. Synthetic length mutation isolates that fact; outer section selection, installer settings, older versions, device state and full filesystem/PCM upload remain outside this run',
            'The file-order destination and reference results are bounded to the original section-plus-reference kernels and explicit caller settings, not a complete real-device installation or audio result; product/input files unchanged'])
    if not args.smoke:(OUT/'resource-import-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,smoke_only=args.smoke,counts=counts),indent=2))
if __name__=='__main__':main()
