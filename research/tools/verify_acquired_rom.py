#!/usr/bin/env python3
"""Validate a complete acquired candidate against session records and ROM checks.

No keyboard APIs. Optional ARM execution feeds captured bytes to the original
diagnostic reader, with all TG/voice gates mocked on the computer.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from program_firmware import ROOT,FW_SHA,Firmware,Arm

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--verify-arm',action='store_true')
    args=parser.parse_args();session=args.session.resolve(strict=True)
    if (ROOT/'research/derived/acquisitions').resolve() not in session.parents: raise ValueError('Invalid session location')
    state=json.loads((session/'session.json').read_text())
    image_path=session/'complete/TG-ROM-candidate.img';data=image_path.read_bytes()
    if len(data)!=0x4000000 or len(state['blocks'])!=256: raise ValueError('Incomplete acquisition')
    imported=json.loads((session/'complete/import-report.json').read_text())
    if sha(data)!=imported['candidate_sha256']: raise ValueError('Imported image changed')
    hashes=[]
    for block in range(256):
        payload=data[block*0x40000:(block+1)*0x40000];digest=sha(payload)
        if digest!=state['blocks'][str(block)]['payload_sha256']: raise ValueError(f'Block {block} differs from acquisition record')
        hashes.append(digest)
    if data[-16:].hex()!=state['tail']['tail_hex'] or data[-16:-12]!=b'KORG': raise ValueError('Independent tail mismatch')
    # Exact indices used by 0x11cbc4, including the first-block full sweep and
    # the final u32 of blocks 1..254. This is not a checksum over every ROM word.
    indices=list(range(65536))+[(block<<16)+65535 for block in range(1,255)]
    sums=[sum(struct.unpack_from('<H',data,index*4+half*2)[0] for index in indices)&65535 for half in (0,1)]
    stored=list(struct.unpack_from('<HH',data,len(data)-4))
    diagnostics=dict(original_function='0x11cbc4 / 0x11cc88',words_per_half=len(indices),
                     computed_u16=sums,stored_u16=stored,passed=sums==stored,
                     scope='Original sparse diagnostic algorithm, not a full-content checksum')
    if args.verify_arm:
        arm=Arm(Firmware());manager=0x11010000;arm.write(manager,0x60000000)
        reads=[0]
        def read(a):
            offset=a.get('R1')*4+a.get('R2')*2
            assert 0<=offset<len(data)-1;reads[0]+=1
            return struct.unpack_from('<H',data,offset)[0]
        arm.stubs={0x11C888:lambda a:0,0x11C8CC:lambda a:0,0x12E1C0:read}
        result=arm.call(0x11CC88,manager,count=12000000)
        expected=0 if sums==stored else 1 if sums[0]!=stored[0] else 2
        if result!=expected: raise ValueError('Python diagnostic differs from original ARM')
        diagnostics.update(ARM_result=result,ARM_TG_reads=reads[0],ARM_agrees_with_computation=True)
    catalog=ROOT/'research/derived/firmware/KROSS2_V124/rom/catalog'
    descriptors=json.loads((catalog/'sample-descriptors.json').read_text())
    for descriptor in descriptors:
        start,end=descriptor['byte_start_candidate'],descriptor['byte_end_exclusive_candidate']
        if not 0<=start<end<=len(data): raise ValueError(f'Descriptor {descriptor["index"]} outside acquired image')
    coverage=dict(descriptors=len(descriptors),maximum_end=max(d['byte_end_exclusive_candidate'] for d in descriptors),
                  musical_multisamples=496,drumsamples=1014,
                  interpretation='Ranges covered under previously recovered address scaling; waveform decoding not yet validated')
    report=dict(status='complete-acquired-candidate-verified' if diagnostics['passed'] else 'complete-transport-candidate-diagnostic-mismatch',image=str(image_path),bytes=len(data),
                image_sha256=sha(data),transport_verified_blocks=256,
                independent_footer=data[-16:].hex(),unique_block_payload_hashes=len(set(hashes)),
                repeated_pilot_reads=state['blocks']['255'].get('successful_reads',0),
                original_diagnostic=diagnostics,catalog_coverage=coverage,
                raw_capture_directory=state['raw_dir'],application_candidate_sha256=state['profile_sha256'],
                original_firmware_sha256=FW_SHA,
                SD_export_used=False,waveform_decoding_complete=False,
                source_sha256=sha(Path(__file__).read_bytes()))
    image_path.chmod(0o400)
    (session/'complete/acquisition-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    (session/'complete/SHA256SUMS').write_text(f'{sha(data)}  TG-ROM-candidate.img\n')
    print(json.dumps(report,indent=2))
    if not diagnostics['passed']: raise SystemExit('Original ROM diagnostic checksum mismatch; image retained for investigation')

if __name__=='__main__': main()
