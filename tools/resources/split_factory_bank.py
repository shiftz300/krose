"""Prepare the shipped onboard library and the default OASYS sample payload."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import mmap
from pathlib import Path
import struct


def split(source: Path, destination: Path, test_expansions: Path | None = None, compile_only=False):
    with source.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as bank:
        if compile_only:
            placeholder = b'KROSE COMPILE ONLY - NO AUDIO DATA\n'
            if len(bank) != len(placeholder) or bank[:] != placeholder:
                raise ValueError('Expected the compile-only placeholder bank')
            destination.mkdir(parents=True, exist_ok=True)
            for name in ('Factory.samples', 'EXPCM001.pcm'):
                (destination / name).write_bytes(placeholder)
            return
        if bank[:12] != b'KRPRG003\x03\0\0\0':
            raise ValueError('Expected a verified KRPRG003 bank')
        samples, regions, programs = struct.unpack_from('<III', bank, 12)
        descriptors = 24 + 224 * 4 + 256 * 2 + 129 * 2 + 512
        payload = descriptors + samples * 40 + regions * 96 + programs * 2232
        header = bytearray(bank[:payload])
        header[:12] = b'KRPRG004\x04\0\0\0'
        offsets = {0: payload, 1: 0, 2: 0, 4: 0}
        destination.mkdir(parents=True, exist_ok=True)
        with ExitStack() as files:
            base = files.enter_context((destination / 'Factory.samples').open('wb'))
            packs = {1: files.enter_context((destination / 'EXPCM001.pcm').open('wb'))}
            if test_expansions is not None:
                test_expansions.mkdir(parents=True, exist_ok=True)
                for group in (2, 4):
                    packs[group] = files.enter_context((test_expansions / f'EXPCM{group:03}.pcm').open('wb'))
            base.write(header)
            previous_end = payload
            for index in range(samples):
                position = descriptors + index * 40
                sample_id, frames = struct.unpack_from('<II', bank, position)
                offset, _, _, codec = struct.unpack_from('<QhhI', bank, position + 24)
                group = sample_id // 10000
                size = frames * (3, 1, 2)[codec]
                end = offset + size
                if offset != previous_end or end > len(bank) or group not in offsets:
                    raise ValueError('Invalid waveform descriptor')
                struct.pack_into('<Q', header, position + 24, offsets[group])
                offsets[group] += size
                if group == 0:
                    base.write(bank[offset:end])
                elif group in packs:
                    packs[group].write(bank[offset:end])
                previous_end = end
            if previous_end != len(bank) or not offsets[1]:
                raise ValueError('Incomplete waveform payload')
            base.seek(0)
            base.write(header)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--test-expansions', type=Path)
    parser.add_argument('--compile-only', action='store_true')
    args = parser.parse_args()
    split(args.source, args.destination, args.test_expansions, args.compile_only)
