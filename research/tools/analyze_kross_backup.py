#!/usr/bin/env python3
"""Offline FAT16/hidden-area audit of the verified KROSS2 USB image.

Never opens a device, mounts a volume, or alters the acquired image. Files are
exported under derived/ with a manifest; unknown local edits are not replaced.
"""
from layout import PRODUCT_ROOT
import bisect
import collections
import hashlib
import json
import math
import struct
from pathlib import Path

from layout import ROOT
SOURCE=ROOT/'research/libraries/KROSS2_local_20261101-022845/internal-storage.img'
EXPECTED='6cd9b98ca73626535106418bef26c12fa2ae361b92376ab73e958e23ae30c378'
OUT=ROOT/'research/derived/acquisitions/KROSS2_local_20261101-022845'


def sha(data):return hashlib.sha256(data).hexdigest()


def store(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=data:raise ValueError(f'Refusing to overwrite changed result: {path}')
    else:path.write_bytes(data)


def stats(data):
    zeros=data.count(0);ones=data.count(255)
    counts=collections.Counter(data) if zeros!=len(data) and ones!=len(data) else {}
    entropy=-sum(n/len(data)*math.log2(n/len(data)) for n in counts.values()) if counts else 0
    return dict(bytes=len(data),zero_bytes=zeros,ff_bytes=ones,other_bytes=len(data)-zeros-ones,
                entropy_bits_per_byte=entropy,sha256=sha(data))


def main():
    data=SOURCE.read_bytes();assert sha(data)==EXPECTED and len(data)==131072000
    assert data[510:512]==b'\x55\xaa'
    start_sector=struct.unpack_from('<I',data,454)[0]
    # The acquisition records a 2048-byte logical sector, not the common512.
    bps=2048;base=start_sector*bps
    boot=data[base:base+bps];assert struct.unpack_from('<H',boot,11)[0]==bps
    spc=boot[13];reserved=struct.unpack_from('<H',boot,14)[0];fat_count=boot[16]
    root_count=struct.unpack_from('<H',boot,17)[0];spf=struct.unpack_from('<H',boot,22)[0]
    total=struct.unpack_from('<H',boot,19)[0] or struct.unpack_from('<I',boot,32)[0]
    fat_base=base+reserved*bps;fat_bytes=spf*bps;root_base=fat_base+fat_count*fat_bytes
    root_bytes=((root_count*32+bps-1)//bps)*bps;data_base=root_base+root_bytes;cluster_bytes=spc*bps
    fat=list(struct.unpack('<'+'H'*(fat_bytes//2),data[fat_base:fat_base+fat_bytes]))
    copies=[data[fat_base+i*fat_bytes:fat_base+(i+1)*fat_bytes] for i in range(fat_count)]
    assert all(c==copies[0] for c in copies)
    declared_clusters=(total-(data_base-base)//bps)//spc
    physical_clusters=(len(data)-data_base)//cluster_bytes
    usable=min(declared_clusters,physical_clusters,len(fat)-2)
    files=[];directories=[];deleted=[];owners={};extents=[]
    def chain(first):
        result=[];seen=set();index=first
        while index>=2:
            assert index not in seen and index<len(fat),('bad cluster',index)
            seen.add(index);result.append(index)
            nxt=fat[index]
            if nxt>=0xfff8:return result
            assert nxt not in (0,1,0xfff7),('broken chain',index,nxt)
            index=nxt
        return result
    def cluster(index):
        off=data_base+(index-2)*cluster_bytes
        assert 0<=off and off+cluster_bytes<=len(data),('out of image',index,off)
        return data[off:off+cluster_bytes]
    def lfn_part(raw):
        return (raw[1:11]+raw[14:26]+raw[28:32]).decode('utf-16le',errors='replace').split('\0')[0].rstrip('\uffff')
    def visit(payload,parent,depth=0):
        assert depth<12
        long_parts={}
        for offset in range(0,len(payload),32):
            raw=payload[offset:offset+32]
            if len(raw)<32 or raw[0]==0:break
            if raw[0]==0xe5:
                if raw[11]!=15:deleted.append(dict(parent=parent,short_raw=raw[:11].hex(),first_cluster=struct.unpack_from('<H',raw,26)[0],bytes=struct.unpack_from('<I',raw,28)[0]))
                long_parts={};continue
            if raw[11]==15:
                long_parts[raw[0]&31]=lfn_part(raw);continue
            short=raw[:8].decode('ascii',errors='replace').rstrip();ext=raw[8:11].decode('ascii',errors='replace').rstrip()
            short+=('.'+ext if ext else '')
            name=''.join(long_parts[k] for k in sorted(long_parts)) if long_parts else short;long_parts={}
            if raw[11]&8 or short in ('.','..'):continue
            assert name and name not in ('.','..') and '/' not in name and '\\' not in name
            rel=parent+'/'+name if parent else name;first=struct.unpack_from('<H',raw,26)[0];size=struct.unpack_from('<I',raw,28)[0]
            clusters=chain(first)
            for c in clusters:
                assert c not in owners,('crosslink',rel,owners.get(c));owners[c]=rel
            blocks=b''.join(cluster(c) for c in clusters)
            isdir=bool(raw[11]&16)
            entry=dict(path=rel,short_name=short,directory=isdir,bytes=size,clusters=clusters)
            consumed=0
            for c in clusters:
                lo=data_base+(c-2)*cluster_bytes;hi=lo+cluster_bytes
                extents.append((lo,hi,rel))
                consumed+=cluster_bytes
            if isdir:
                directories.append(entry);visit(blocks,rel,depth+1)
            else:
                assert size<=len(blocks)
                content=blocks[:size];entry.update(sha256=sha(content),header_hex=content[:32].hex(),slack=stats(blocks[size:]))
                files.append(entry);store(OUT/'files'/rel,content)
    visit(data[root_base:root_base+root_bytes],'')
    extents.sort();starts=[e[0] for e in extents]
    def owner(offset):
        index=bisect.bisect_right(starts,offset)-1
        return extents[index][2] if index>=0 and offset<extents[index][1] else 'unallocated_or_filesystem_metadata'
    free=[c for c in range(2,usable+2) if fat[c]==0]
    orphan=[c for c in range(2,usable+2) if fat[c]!=0 and c not in owners]
    def audit_clusters(indices):
        counts=collections.Counter();changed=[];digest=hashlib.sha256()
        for c in indices:
            b=cluster(c);digest.update(b)
            z=b.count(0);f=b.count(255)
            counts.update(bytes=len(b),zero_bytes=z,ff_bytes=f,other_bytes=len(b)-z-f)
            if z!=len(b) and f!=len(b):changed.append(dict(cluster=c,offset=data_base+(c-2)*cluster_bytes,statistics=stats(b)))
        return dict(cluster_count=len(indices),totals=dict(counts),concatenated_sha256=digest.hexdigest(),nonuniform_clusters=changed)
    patterns={b'RIFF':'RIFF container candidate',b'fLaC':'FLAC marker',b'OggS':'Ogg marker',b'KROSSPCM.BIN':'PCM image filename',b'BOOTSYS.BIN':'boot filename',b'KORG':'KORG marker',b'\x7fELF':'ELF marker'}
    signature_hits=[]
    for pattern,label in patterns.items():
        at=0
        while True:
            off=data.find(pattern,at)
            if off<0:break
            signature_hits.append(dict(label=label,offset=off,owner=owner(off)))
            at=off+1
    # Native input fingerprints from independent known samples: no decoder or
    # compression experiment is run by this image audit.
    native_matches=[]
    for name in ('000.kpcm','056.kpcm','057.kpcm','112.kpcm','113.kpcm','224.kpcm'):
        p=ROOT/'output/kep-analysis/native_samples'/name
        if p.exists():
            needle=p.read_bytes()[:128];off=data.find(needle)
            if len(needle)==128 and off>=0:native_matches.append(dict(file=name,offset=off,owner=owner(off)))
    footer_hits=[];at=0
    while True:
        off=data.find(b'KORG',at)
        if off<0:break
        candidate_base=off-0x3fffff0
        if 0<=candidate_base and candidate_base+0x4000000<=len(data):
            footer_hits.append(dict(offset=off,candidate_PCM_base=candidate_base,owner=owner(off)))
        at=off+1
    regions=dict(prepartition=stats(data[:base]),filesystem_metadata=stats(data[base:data_base]),
                 free_clusters=audit_clusters(free),allocated_unreferenced_clusters=audit_clusters(orphan),
                 physical_tail=stats(data[data_base+usable*cluster_bytes:]))
    result=dict(source=str(SOURCE.relative_to(PRODUCT_ROOT)),source_sha256=EXPECTED,image_bytes=len(data),tool_sha256=sha(Path(__file__).read_bytes()),
                filesystem=dict(type='FAT16',sector_bytes=bps,partition_offset=base,cluster_bytes=cluster_bytes,fat_copies=fat_count,
                                FAT_copies_identical=True,root_offset=root_base,data_offset=data_base,declared_volume_bytes=total*bps,
                                declared_volume_end=base+total*bps,physical_available_volume_bytes=len(data)-base,
                                declared_clusters=declared_clusters,fully_available_clusters=usable,
                                geometry_note='BPB volume extends beyond exposed device by partition offset; analyzed without repair'),
                files=files,directories=directories,deleted_entries=deleted,region_audit=regions,
                signatures=signature_hits,known_native_code_prefix_matches=native_matches,candidate64MiB_KORG_footers=footer_hits,
                limitations=['Signature absence alone does not rule out every possible headerless codec',
                             'PADSMPLA and other containers need separate semantic analysis',
                             'No filesystem repair, device access, new compression or product resource changes'])
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'image-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(files=len(files),directories=len(directories),deleted=len(deleted),filesystem=result['filesystem'],
                         free=regions['free_clusters'],orphans=regions['allocated_unreferenced_clusters'],
                         native_matches=native_matches,footer_hits=footer_hits),indent=2))


if __name__=='__main__':main()
