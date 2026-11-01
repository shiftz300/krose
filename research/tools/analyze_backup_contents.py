#!/usr/bin/env python3
"""Recover Pad audio and raw GM Programs from the verified local USB backup.

Offline only. Never opens devices, changes acquired files or exports to assets/.
Stereo pairing is an explicitly recorded interpretation of adjacent equal slots.
"""
import array
import csv
import io
import json
import re
import struct
import sys
import wave
from pathlib import Path

from analyze_kross_backup import EXPECTED, OUT, ROOT, SOURCE, sha, stats, store


def main():
    image = SOURCE.read_bytes()
    assert sha(image) == EXPECTED
    audit = json.loads((OUT / 'image-audit.json').read_text())
    assert audit['source_sha256'] == EXPECTED
    assert audit['tool_sha256'] == sha((ROOT / 'tools/analyze_kross_backup.py').read_bytes())
    files = {}
    containers = []
    slack = []
    for entry in audit['files']:
        data = (OUT / 'files' / entry['path']).read_bytes()
        assert sha(data) == entry['sha256']
        files[entry['path']] = data
        if data[:4] == b'KSB0':
            header = struct.unpack('>16I', data[:64])
            assert header[1] == 64 and header[7] == len(data) - 64
            checksum = sum(data[64:]) & 0xffffffff
            # Save observed equivalence, rather than guessing a header flag.
            mode = 'byte_sum32' if checksum == header[8] else 'byte_sum16'
            assert checksum == header[8] or checksum & 65535 == header[8]
            containers.append(dict(file=entry['path'], header_u32_be=list(header),
                                   payload_bytes=len(data)-64, checksum_mode_observed=mode,
                                   checksum_expected=header[8], byte_sum32=checksum,
                                   nested_KORG=data[64:68] == b'KORG'))
        if entry['slack']['other_bytes']:
            fs = audit['filesystem']
            blocks = b''.join(image[fs['data_offset']+(c-2)*fs['cluster_bytes']:
                                   fs['data_offset']+(c-1)*fs['cluster_bytes']]
                              for c in entry['clusters'])
            tail = blocks[entry['bytes']:]
            name = entry['path'].replace('/', '_') + '.slack.bin'
            store(OUT / 'slack' / name, tail)
            slack.append(dict(owner=entry['path'], file='slack/'+name,
                              statistics=stats(tail),
                              interpretation='Uninterpreted file tail; not a recovered ROM sample'))

    data = files['PADSMPLA.BIN']
    slots = []
    position = 64
    for index in range(32):
        descriptor = data[position:position+100]
        assert len(descriptor) == 100
        length = struct.unpack_from('<I', descriptor, 0x44)[0]
        pitch = struct.unpack_from('<h', descriptor)[0]
        end = struct.unpack_from('<I', descriptor, 0x18)[0]
        pcm = data[position+100:position+100+length]
        assert len(pcm) == length and length % 2 == 0 and end+1 == length//2
        assert pitch == 0 and descriptor[7] == 0x12
        name = descriptor[0x48:0x58].decode('ascii').rstrip(' \0')
        values = array.array('h', pcm)
        if sys.byteorder != 'little': values.byteswap()
        slots.append(dict(index=index, name=name, descriptor_offset=position,
                          descriptor_hex=descriptor.hex(), pcm_offset=position+100,
                          pcm_bytes=length, frames=length//2, pitch=pitch,
                          flags=descriptor[7], end_inclusive=end,
                          pcm_sha256=sha(pcm), peak=max(abs(v) for v in values),
                          rms=(sum(v*v for v in values)/len(values))**0.5))
        position += 100+length
    assert position == len(data)
    pairs = []
    for first in range(0, 32, 2):
        left, right = slots[first:first+2]
        assert (left['name'], left['frames']) == (right['name'], right['frames'])
        a = data[left['pcm_offset']:left['pcm_offset']+left['pcm_bytes']]
        b = data[right['pcm_offset']:right['pcm_offset']+right['pcm_bytes']]
        stereo = bytearray(len(a)*2)
        stereo[0::4], stereo[1::4] = a[0::2], a[1::2]
        stereo[2::4], stereo[3::4] = b[0::2], b[1::2]
        name = re.sub(r'[^a-zA-Z0-9_-]', '_', left['name'])
        filename = f'pad-wav/{first//2+1:02d}_{name}.wav'
        out = io.BytesIO()
        with wave.open(out, 'wb') as wav:
            wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(48000)
            wav.writeframes(stereo)
        store(OUT / filename, out.getvalue())
        # Independently read the container and deinterleave every sample byte.
        with wave.open(io.BytesIO(out.getvalue()), 'rb') as wav:
            assert wav.getparams()[:4] == (2, 2, 48000, left['frames'])
            recovered = wav.readframes(wav.getnframes())
        assert recovered[0::4] == a[0::2] and recovered[1::4] == a[1::2]
        assert recovered[2::4] == b[0::2] and recovered[3::4] == b[1::2]
        pairs.append(dict(name=left['name'], slots=[first, first+1], wav=filename,
                          wav_sha256=sha(out.getvalue()), frames=left['frames'],
                          duration_seconds=left['frames']/48000))

    programs = []
    for bank, count in [('PROGGC.BIN', 128), ('PROGGV.BIN', 128), ('PROGGD.BIN', 9)]:
        payload = files[bank][64:]
        assert len(payload) == count*2140
        store(OUT / 'gm-programs' / (bank+'.payload.bin'), payload)
        for index in range(count):
            raw = payload[index*2140:(index+1)*2140]
            name = raw[:24].decode('ascii').rstrip(' \0')
            assert name.startswith('GM ')
            programs.append(dict(bank=bank, index=index, name=name, bytes=2140,
                                 source_offset=64+index*2140, raw_sha256=sha(raw)))
    csv_output = io.StringIO(newline='')
    writer = csv.DictWriter(csv_output, fieldnames=list(programs[0]))
    writer.writeheader(); writer.writerows(programs)
    store(OUT / 'gm-programs/programs.csv', csv_output.getvalue().encode())
    result = dict(source_sha256=EXPECTED, tool_sha256=sha(Path(__file__).read_bytes()),
                  extracted_files_verified=len(files), KSB0_containers=containers,
                  pad=dict(source='files/PADSMPLA.BIN', source_sha256=sha(data),
                           descriptor_bytes=100, slot_count=32, pcm_bytes=sum(x['pcm_bytes'] for x in slots),
                           parser_consumed_bytes=position, source_bytes=len(data),
                           encoding='signed little-endian PCM16', wav_rate_hz=48000,
                           rate_basis='All pitch fields zero; existing recovered 48000 * 2**(pitch/1536) relation',
                           pairing_status='Adjacent equal-name/equal-length slots paired in file order; physical L/R not verified',
                           provenance_status='Pad sampler contents of this machine; factory versus user origin not established',
                           firmware_loader_offset='0x287adc', descriptor_read_offset='0x287c5c',
                           slots=slots, stereo_pairs=pairs),
                  gm=dict(count=len(programs), record_bytes=2140,
                          status='Recovered raw Program records; not all fields newly interpreted or ROM audio recovered',
                          programs=programs), file_slack=slack,
                  limitations=['No TG factory ROM audio recovered',
                               'KORG-wrapped PPROG/PCOMBI payloads not decoded by this tool',
                               'No device commands, new compression, product changes or VST installation'])
    (OUT / 'contents-analysis.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(dict(KSB0=len(containers), pad_slots=len(slots), stereo_WAVs=len(pairs),
                          pad_PCM_bytes=result['pad']['pcm_bytes'], GM_Programs=len(programs),
                          nontrivial_slack=slack), indent=2))


if __name__ == '__main__': main()
