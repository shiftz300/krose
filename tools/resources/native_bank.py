"""Offline conversion from verified original waveforms to frozen native banks.

Ordinary builds never run this tool or read the research archive. The existing
C++ codec regression executable verifies all decoded samples before publication.
"""
import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
FACTORY='assets/program-library/Factory.samples'
CONCERT='assets/concert-se-grand/SEGrand.samples'


def digest(data):return hashlib.sha256(data).hexdigest()


def sha(file):
    h=hashlib.sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8388608),b''):h.update(chunk)
    return h.hexdigest()


def read_json(file):return json.loads(file.read_text())


def require(value,message):
    if not value:raise ValueError(message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='Restored research root')
    parser.add_argument('--verifier',type=Path,required=True,help='Built test-sample-codec executable')
    parser.add_argument('--root',type=Path,default=ROOT,help='Accepted v2 PCM checkout')
    parser.add_argument('--output',type=Path,required=True,help='Staging directory, never the product root')
    args=parser.parse_args();source=args.source
    require(args.output.resolve()!=args.root.resolve(),'Use a staging directory')
    for name in [FACTORY,CONCERT]:
        for item in read_json((args.root/name).parent/'manifest.json')['files']:
            file=(args.root/name).parent/item['file']
            require(file.stat().st_size==item['bytes'] and sha(file)==item['sha256'],f'Frozen asset mismatch: {file}')
    firmware=source/'derived/firmware/KROSS2_V124/KROSSAPP.bin'
    require(sha(firmware)=='3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54','Unexpected firmware LUT')
    lut=firmware.read_bytes()[0x3fd180:0x3fd380]
    descriptors=read_json(source/'derived/firmware/KROSS2_V124/rom/catalog/sample-descriptors.json')
    rom_file=source/'derived/acquisitions/KROSS2_ROM_stage_b_20261031T215150691039Z/complete/TG-ROM-candidate.img'
    require(sha(rom_file)=='c9d4c9b4dd0f915b45a553e6b66d2cab7e51b80f4b2189fb6db4d91b1ccc94a5','Unexpected TG ROM')
    rom=rom_file.read_bytes();libraries={}
    for id in [1,2,4]:
        metadata=read_json(source/f'derived/kep/EXPCM00{id}/library.json')
        decoded=metadata['decoded'].removeprefix('research/')
        require(sha(source/decoded)==metadata['decoded_sha256'],f'Unexpected expansion {id}')
        libraries[id]=(metadata,(source/decoded).read_bytes())
    args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='native-',dir=args.output) as temporary:
        stage=Path(temporary)
        with (args.root/FACTORY).open('rb') as f, (args.root/CONCERT).open('rb') as c:
            with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as factory,mmap.mmap(c.fileno(),0,access=mmap.ACCESS_READ) as concert:
                require(factory[:12]==b'KRPRG002\x02\0\0\0','Expected accepted Factory v2 PCM')
                require(concert[:12]==b'SEGRAND1\x01\0\0\0','Expected accepted Concert v1 PCM')
                count,regions,programs=struct.unpack_from('<III',factory,12)
                table=24+224*4+256*2+129*2
                payload_start=table+count*32+regions*96+programs*2232
                next_offset=payload_start+512+count*8
                header=bytearray(next_offset);header[:table]=factory[:table]
                header[:12]=b'KRPRG003\x03\0\0\0';header[table:table+512]=lut
                header[table+512+count*40:]=factory[table+count*32:payload_start]
                offsets={};codecs=dict(predictive=0,pcm16=0)
                with (stage/'Factory.samples').open('wb') as output:
                    output.write(header)
                    for i in range(count):
                        old=table+i*32;destination=table+512+i*40
                        id,frames=struct.unpack_from('<II',factory,old)
                        old_offset=struct.unpack_from('<Q',factory,old+24)[0]
                        if id<10000:
                            descriptor=descriptors[id];require(descriptor['index']==id,'Missing ROM descriptor')
                            codec=1 if descriptor['flags']&1 else 2;a1,a2=descriptor['coefficients_q14']
                            start=descriptor['byte_start_candidate'];encoded=rom[start:start+frames*(1 if codec==1 else 2)]
                        else:
                            library,data=libraries[id//10000]
                            sample=next(sample for sample in library['samples'] if sample['id']==id%10000)
                            a1,a2=struct.unpack_from('<hh',bytes.fromhex(sample['descriptor_hex']),8)
                            codec=1;encoded=data[sample['offset']:sample['offset']+frames]
                        require(len(encoded)==frames*(1 if codec==1 else 2),f'Truncated sample {id}')
                        offsets[digest(factory[old_offset:old_offset+frames*3])]=i
                        header[destination:destination+24]=factory[old:old+24]
                        struct.pack_into('<QhhI',header,destination+24,next_offset,a1,a2,codec)
                        output.write(encoded);next_offset+=len(encoded);codecs['predictive' if codec==1 else 'pcm16']+=1
                    output.seek(0);output.write(header)
                view=bytearray(concert[:32+84*32]);struct.pack_into('<I',view,8,2)
                for i in range(84):
                    descriptor=32+i*32;frames=struct.unpack_from('<I',concert,descriptor+12)[0]
                    offset=struct.unpack_from('<Q',concert,descriptor+24)[0];stereo=concert[offset:offset+frames*6]
                    for channel in range(2):
                        mono=bytearray(frames*3)
                        for byte in range(3):mono[byte::3]=stereo[channel*3+byte::6]
                        struct.pack_into('<I',view,descriptor+24+channel*4,offsets[digest(mono)])
                (stage/'SEGrand.samples').write_bytes(view)
        baseline=stage/'accepted';baseline.mkdir()
        for name in [FACTORY,CONCERT]:
            try:os.link(args.root/name,baseline/Path(name).name)
            except OSError:shutil.copyfile(args.root/name,baseline/Path(name).name)
        subprocess.run([str(args.verifier.resolve()),str(baseline),str(stage)],check=True)
        report=dict(samples=count,concertChannels=168,programs=programs,codecs=codecs,bitExact=True,
                    previousBytes=(args.root/FACTORY).stat().st_size+(args.root/CONCERT).stat().st_size,nativeBytes=next_offset+len(view),
                    inputs=dict(factory=sha(args.root/FACTORY),concert=sha(args.root/CONCERT),firmware=sha(firmware),rom=sha(rom_file)),
                    files=[dict(file=name,bytes=(stage/name).stat().st_size,sha256=sha(stage/name)) for name in ['Factory.samples','SEGrand.samples']])
        for name in ['Factory.samples','SEGrand.samples']:(stage/name).replace(args.output/name)
        (args.output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':main()
