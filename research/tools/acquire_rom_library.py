#!/usr/bin/env python3
"""Serial full-library capture using the already-verified one-block endpoint.

No firmware install, SD access or TG writes. Resumes completed CRC-verified
blocks and only imports a complete 256-block record set at the end.
"""
import argparse,datetime,hashlib,io,json,subprocess,sys,time
from pathlib import Path
from program_firmware import ROOT
from recover_rom_stream import parse_records

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--experimental-stage-b',action='store_true')
    args=parser.parse_args()
    if not args.experimental_stage_b: parser.error('--experimental-stage-b is required')
    session=args.session.resolve(strict=True)
    if (ROOT/'research/derived/acquisitions').resolve() not in session.parents: raise ValueError('Invalid session location')
    def state(): return json.loads((session/'session.json').read_text())
    initial=state()
    if (initial.get('blocks',{}).get('255',{}).get('successful_reads',0)<2 or
        not initial.get('post_pilot_sound_normal') or not initial.get('tail',{}).get('KORG_marker')):
        raise ValueError('Repeated pilot, KORG tail and post-pilot sound confirmation required')
    start=time.monotonic();completed_this_run=0
    log=session/'library-progress.json'
    for block in range(256):
        current=state()
        if current.get('blocked_reason'): raise ValueError(current['blocked_reason'])
        if str(block) in current.get('blocks',{}):
            entry=current['blocks'][str(block)];record=Path(entry['record']).read_bytes()
            parsed,_=parse_records(io.BytesIO(record),require_complete=False)
            if list(parsed)!=[block] or hashlib.sha256(parsed[block]).hexdigest()!=entry['payload_sha256']:
                raise ValueError(f'Existing record for block {block} changed')
            continue
        print(f'READING block {block}/255',flush=True)
        proc=subprocess.run([sys.executable,str(ROOT/'tools/acquire_rom_block.py'),'block','--block',str(block),
                             '--session',str(session),'--experimental-stage-b'],
                            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (session/f'library-block-{block:03}.log').write_text(proc.stdout)
        if proc.returncode:
            print(proc.stdout,flush=True)
            raise RuntimeError(f'Block {block} failed; raw capture retained; stopped without importing a complete image')
        completed_this_run+=1;current=state();count=len(current['blocks']);elapsed=time.monotonic()-start
        progress=dict(status='capturing',verified_blocks=count,total_blocks=256,
                      verified_payload_bytes=count*0x40000,elapsed_seconds=round(elapsed,2),
                      recorded_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),last_verified_block=block)
        log.write_text(json.dumps(progress,indent=2)+'\n')
        print(f'VERIFIED {count}/256 blocks; {count*256} KiB; elapsed {elapsed:.1f}s',flush=True)
    current=state();records=[]
    for block in range(256): records.append(Path(current['blocks'][str(block)]['record']).read_bytes())
    stream=b''.join(records)
    blocks,validation=parse_records(io.BytesIO(stream))
    assert len(blocks)==256 and validation['complete']
    stream_path=session/'complete-records.bin'
    if stream_path.exists():
        if stream_path.read_bytes()!=stream: raise ValueError('Existing complete records changed')
    else:
        with stream_path.open('xb') as file: file.write(stream)
    stream_path.chmod(0o400)
    subprocess.run([sys.executable,str(ROOT/'tools/recover_rom_stream.py'),str(stream_path),
                    '--out-dir',str(session/'complete')],check=True)
    progress=dict(status='complete-candidate-imported',verified_blocks=256,
                  verified_payload_bytes=0x4000000,elapsed_seconds=round(time.monotonic()-start,2),
                  input_records_sha256=hashlib.sha256(stream).hexdigest(),validation=validation,
                  candidate=str(session/'complete/TG-ROM-candidate.img'))
    log.write_text(json.dumps(progress,indent=2)+'\n');print(json.dumps(progress,indent=2),flush=True)

if __name__=='__main__': main()
