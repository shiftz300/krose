#!/usr/bin/env python3
"""Bundle the verified local WAVs, unchanged PCM24, and generate EQ constants."""
import argparse
import hashlib
import json
import struct
import wave
from pathlib import Path

from layout import ROOT
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'build/generated')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    folder=ROOT/'output/Concert_SE_Grand_WAV'
    report=json.loads((folder/'decode_report.json').read_text())
    records=sorted(report['samples'],key=lambda x: (('mf','f','ff').index(x['layer']),x['top_key']))
    assert len(records)==84
    table=[]
    offset=32+32*len(records)
    for row in records:
        assert row['pitch_field']==-295
        table.append((('mf','f','ff').index(row['layer']),row['root_key_candidate'],row['top_key'],
                      row['frames'],*row['loop_inclusive'],offset))
        offset+=row['frames']*6
    destination=args.output/'SEGrand.samples'
    temporary=destination.with_suffix('.samples.tmp')
    with temporary.open('wb') as out:
        out.write(struct.pack('<8sIIdII',b'SEGRAND1',1,len(records),42017.578125,32,0))
        for row in table:out.write(struct.pack('<6IQ',*row))
        for row in records:
            path=folder/row['file']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],path
            with wave.open(str(path),'rb') as source:
                assert (source.getnchannels(),source.getsampwidth(),source.getnframes())==(2,3,row['frames'])
                out.write(source.readframes(row['frames']))
        assert out.tell()==offset
    temporary.replace(destination)
    eq_path=ROOT/'research/derived/firmware/KROSS2_V124/effects/007/concert-coefficients.json'
    eq=json.loads(eq_path.read_text())
    values=[v for s in eq['slots'] for b in s['bands'] for v in b['host']['b0_b1_b2_feedback1_feedback2']]
    trim=eq['slots'][0]['trim_linear']*eq['slots'][1]['trim_linear']
    header='#pragma once\nnamespace segrand {\ninline constexpr double kConcertEq[40] = {\n'
    header+=',\n'.join('  '+', '.join(format(v,'.17g') for v in values[i:i+5]) for i in range(0,40,5))
    header+='\n};\ninline constexpr double kConcertTrim = '+format(trim,'.17g')+';\n}\n'
    (args.output/'ConcertEqData.h').write_text(header)
    manifest={'pack':destination.name,'format':'SEGRAND1 v1, LE header32, 84 entries32, unchanged interleaved PCM24',
              'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'bytes':offset,'sample_count':84,
              'root_playback_rate_hz':42017.578125,'eq_source_sha256':hashlib.sha256(eq_path.read_bytes()).hexdigest(),
              'sources':[{'file':r['file'],'sha256':r['sha256']} for r in records]}
    (args.output/'assets.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Packed 84 stereo samples, {offset:,} bytes; generated Concert EQ constants')


if __name__=='__main__':main()
