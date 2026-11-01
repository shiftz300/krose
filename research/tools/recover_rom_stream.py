#!/usr/bin/env python3
"""Validate and assemble explicitly supplied KROSS2 recovery records offline.

This is an importer, not an acquisition interface. It never opens MIDI, USB or
raw devices. Synthetic records are categorically rejected by the CLI. No image
is written until all 256 blocks and the KORG footer are present and validated.
"""
import argparse
import hashlib
import io
import json
import struct
import zlib
from pathlib import Path

from program_firmware import ROOT, FW_SHA

MAGIC=b'KR2BLK01'
BLOCK_BYTES=0x40000
IMAGE_BYTES=0x4000000


def parse_records(stream, *, allow_synthetic=False, require_complete=True):
    blocks={}; duplicates=0; source_kind=None
    while True:
        header=stream.read(64)
        if not header: break
        if len(header)!=64: raise ValueError('Truncated block header')
        magic,header_bytes,image_bytes,block_bytes,index,crc,kind,firmware=struct.unpack('<8s6I32s',header)
        if (magic,header_bytes,image_bytes,block_bytes)!=(MAGIC,64,IMAGE_BYTES,BLOCK_BYTES):
            raise ValueError('Unsupported recovery record format')
        if index>=256 or kind not in (0,1): raise ValueError('Invalid block index/source kind')
        if firmware.hex()!=FW_SHA: raise ValueError('Firmware profile mismatch')
        if kind==1 and not allow_synthetic: raise ValueError('Synthetic test data is not an acquired ROM')
        if source_kind is not None and source_kind!=kind: raise ValueError('Mixed source provenance tags')
        source_kind=kind
        payload=stream.read(BLOCK_BYTES)
        if len(payload)!=BLOCK_BYTES: raise ValueError('Truncated block payload')
        if zlib.crc32(payload)!=crc: raise ValueError(f'CRC mismatch for block {index}')
        if index in blocks:
            if payload!=blocks[index]: raise ValueError(f'Conflicting duplicate block {index}')
            duplicates+=1
        blocks[index]=payload
    missing=sorted(set(range(256))-blocks.keys())
    if require_complete and missing: raise ValueError(f'Incomplete acquisition: {len(missing)} blocks missing')
    if not missing and blocks[255][-16:-12]!=b'KORG': raise ValueError('Expected ROM footer missing')
    return blocks,dict(blocks=len(blocks),duplicates=duplicates,missing_blocks=missing,
                       complete=not missing,source_kind='synthetic' if source_kind==1 else 'unestablished',
                       provenance_note='CRC/profile tags establish consistency, not physical origin or authenticity')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args()
    source=args.input.resolve()
    if not source.is_file() or source.is_symlink(): raise ValueError('Input must be a regular acquired file')
    output=args.out_dir.resolve()
    research=(ROOT/'research/derived').resolve()
    if research not in output.parents: raise ValueError('Output must stay under research/derived/')
    data=source.read_bytes()
    blocks,report=parse_records(io.BytesIO(data))
    image=b''.join(blocks[i] for i in range(256))
    assert len(image)==IMAGE_BYTES
    output.mkdir(parents=True,exist_ok=True)
    target=output/'TG-ROM-candidate.img'
    if target.exists() and target.read_bytes()!=image: raise ValueError('Refusing to overwrite changed candidate')
    target.write_bytes(image)
    report.update(input=str(source),input_sha256=hashlib.sha256(data).hexdigest(),
                  candidate=str(target),candidate_sha256=hashlib.sha256(image).hexdigest(),
                  bytes=len(image),firmware_sha256=FW_SHA,
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  status='Structurally complete candidate; real sample decoding and provenance still require validation')
    (output/'import-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
