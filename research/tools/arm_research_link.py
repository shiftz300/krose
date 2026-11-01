#!/usr/bin/env python3
"""Small strict ARM ELF32 research linker: .text/.rodata, ABS32 and branch24.

Rejects unexpected allocated sections, undefined symbols and relocation types.
Does not process vendor images or access hardware.
"""
import struct


def link(path, address):
    d=path.read_bytes()
    if d[:7]!=b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H',d,18)[0]!=40:
        raise ValueError('Expected little-endian ARM ELF32')
    start=struct.unpack_from('<I',d,32)[0]; size,count,names=struct.unpack_from('<3H',d,46)
    sections=[struct.unpack_from('<10I',d,start+i*size) for i in range(count)]
    def body(s): return d[s[4]:s[4]+s[5]]
    strings=body(sections[names])
    def name(s): return strings[s[0]:strings.index(0,s[0])].decode()
    output=bytearray(); locations={}; included=[]
    for i,s in enumerate(sections):
        if not s[2]&2 or not s[5]: continue
        label=name(s)
        if label.startswith('.ARM.exidx'): continue # no unwinder called by freestanding code
        if not (label.startswith('.text') or label.startswith('.rodata')) or s[1]!=1:
            raise ValueError(f'Unsupported allocated section {label}')
        alignment=max(s[8],1)
        output.extend(bytes((-len(output))%alignment)); locations[i]=address+len(output)
        output.extend(body(s)); included.append(dict(name=label,address=hex(locations[i]),bytes=s[5]))
    symbols={}; entries={}
    for i,s in enumerate(sections):
        if s[1]!=2: continue
        labels=body(sections[s[6]]); table=[]
        for off in range(0,s[5],s[9]):
            label,value,length,info,other,section=struct.unpack_from('<IIIBBH',body(s),off)
            label=labels[label:labels.index(0,label)].decode()
            resolved=locations[section]+value if section in locations else value if section==0xfff1 else None
            table.append((label,resolved))
            if label and resolved is not None: entries[label]=resolved
        symbols[i]=table
    relocations=[]
    for s in sections:
        if s[1] not in (4,9) or s[7] not in locations: continue
        if s[1]!=9: raise ValueError('Only REL relocations supported')
        for off in range(0,s[5],s[9]):
            location,info=struct.unpack_from('<II',body(s),off)
            label,target=symbols[s[6]][info>>8]; kind=info&255
            if target is None: raise ValueError(f'Unresolved symbol {label}')
            position=locations[s[7]]+location; index=position-address
            word=struct.unpack_from('<I',output,index)[0]
            if kind==2: result=(word+target)&0xffffffff # R_ARM_ABS32
            elif kind in (28,29):
                addend=(word&0xffffff)<<2
                if addend&0x2000000: addend-=0x4000000
                displacement=target+addend-position
                if displacement&3 or not -0x2000000<=displacement<0x2000000:
                    raise ValueError('ARM branch out of range')
                result=(word&0xff000000)|((displacement>>2)&0xffffff)
            else: raise ValueError(f'Unsupported relocation {kind}: {label}')
            struct.pack_into('<I',output,index,result)
            relocations.append(dict(at=hex(position),kind=kind,symbol=label,target=hex(target)))
    if entries.get('k2_probe_entry')!=address: raise ValueError('Trampoline must be first')
    return bytes(output),dict(sections=included,relocations=relocations,symbols=entries)
