#!/usr/bin/env python3
"""Explicit stage-B acquisition: identity -> RAM test -> tail -> single block.

Never installs firmware. Raw device replies go to research/libraries; decoded
records/reports go to research/derived/acquisitions. No complete ROM is invented.
"""
import argparse,datetime,hashlib,json,subprocess,time
from pathlib import Path
from build_rom_stage_b import OUT
from program_firmware import ROOT
from parse_rom_midi import validate

def sha(data): return hashlib.sha256(data).hexdigest()
def stamp(): return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
def save(path,data):
    with path.open('xb') as file: file.write(data)
def metadata(path,data): path.write_text(json.dumps(data,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('init','scratch','tail','block'))
    parser.add_argument('--session',type=Path)
    parser.add_argument('--source',type=int)
    parser.add_argument('--destination',type=int)
    parser.add_argument('--channel',type=int,default=1,choices=range(1,17))
    parser.add_argument('--block',type=int,default=255,choices=range(256),metavar='N',help='One block number, 0..255; default 255')
    parser.add_argument('--experimental-stage-b',action='store_true')
    args=parser.parse_args()
    profile=json.loads((OUT/'manifest.json').read_text())
    verified=json.loads((OUT/'verification-arm.json').read_text())
    if verified['candidate_sha256']!=profile['candidate_sha256']: raise ValueError('Unverified stage-B candidate')
    if args.action=='init':
        if not args.source or not args.destination: parser.error('init requires --source and --destination')
        if args.session: parser.error('init creates a new session; omit --session')
        name='KROSS2_ROM_stage_b_'+stamp()
        raw=ROOT/'research/libraries'/name;raw.mkdir()
        session=ROOT/'research/derived/acquisitions'/name;session.mkdir()
        state=dict(stage='B',profile_sha256=profile['candidate_sha256'],source_uid=args.source,
                   destination_uid=args.destination,channel=args.channel,raw_dir=str(raw),
                   created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),blocks={})
        metadata(session/'session.json',state)
        print(json.dumps(dict(session=str(session),raw_dir=str(raw),device_access=False),indent=2));return
    if not args.experimental_stage_b: parser.error('Acquisition requires --experimental-stage-b')
    if not args.session: parser.error('--session is required')
    session=args.session.resolve(strict=True)
    if (ROOT/'research/derived/acquisitions').resolve() not in session.parents: raise ValueError('Invalid session location')
    state=json.loads((session/'session.json').read_text())
    if state['profile_sha256']!=profile['candidate_sha256']: raise ValueError('Session firmware profile changed')
    raw=Path(state['raw_dir']).resolve(strict=True)
    if raw.parent!=(ROOT/'research/libraries').resolve() or raw.name!=session.name: raise ValueError('Invalid raw source directory')
    if args.action in ('tail','block') and not state.get('scratch',{}).get('write_read_restore_passed'):
        raise ValueError('Successful RAM scratch check required first')
    if args.action=='block' and not state.get('tail',{}).get('KORG_marker'):
        raise ValueError('CRC-valid KORG ROM tail required before reading a block')
    if args.action=='block' and state.get('blocked_reason'):
        raise ValueError('Session blocked after an integrity failure: '+state['blocked_reason'])
    endpoints=['--source',str(state['source_uid']),'--destination',str(state['destination_uid']),
               '--channel',str(state['channel'])]
    identity=subprocess.run([str(ROOT/'build/kross-probe-midi'),'probe',*endpoints,'--revision','3',
                             '--experimental-stage-b'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15)
    print(identity.stdout,flush=True)
    if identity.returncode or 'PASS: KROSE stage-B revision 03' not in identity.stdout:
        raise ValueError('Stage-B identity preflight failed; no ROM command sent')
    label=f'{stamp()}-{args.action}'+(f'-{args.block:03}' if args.action=='block' else '')
    capture=raw/(label+'.syx');step=session/label;step.mkdir()
    mode={'scratch':3,'tail':1,'block':2}[args.action]
    command=[str(ROOT/'build/kross-rom-midi'),*endpoints,'--mode',str(mode),'--block',str(args.block if mode==2 else 0),
             '--capture',str(capture),'--experimental-stage-b']
    started=time.monotonic()
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    lines=[]
    for line in process.stdout: lines.append(line);print(line,end='',flush=True)
    code=process.wait()
    wire=capture.read_bytes() if capture.exists() else b''
    if capture.exists(): capture.chmod(0o400)
    report=dict(action=args.action,block=args.block if mode==2 else None,
                profile_sha256=state['profile_sha256'],raw_capture=str(capture),
                raw_sha256=sha(wire),raw_bytes=len(wire),client_exit_code=code,
                capture_seconds=round(time.monotonic()-started,3),
                identity_preflight=identity.stdout,client_log=''.join(lines),
                source='Real CoreMIDI capture from explicitly selected owned KROSS2 endpoints',
                physical_authenticity_note='Source log is evidence of this session, not cryptographic device attestation')
    try:
        if code: raise ValueError('MIDI capture incomplete/failed; raw bytes retained')
        parsed,payload=validate(wire,args.action,args.block,state['channel'])
        report.update(status='validated',validation=parsed)
        if args.action=='scratch': state['scratch']=parsed
        elif args.action=='tail':
            save(step/'ROM-tail.bin',payload);state['tail']=parsed
            if not parsed['KORG_marker']: raise ValueError('Unexpected ROM tail; block acquisition remains disabled')
        else:
            if args.block==255 and payload[-16:].hex()!=state['tail']['tail_hex']:
                raise ValueError('Last block footer differs from independent 16-byte read')
            previous=state['blocks'].get(str(args.block))
            if previous and previous['payload_sha256']!=parsed['payload_sha256']:
                raise ValueError('Repeated block read differs; keep captures for investigation')
            save(step/f'block-{args.block:03}.record',payload)
            state['blocks'][str(args.block)]={**parsed,'record':str(step/f'block-{args.block:03}.record'),
                                             'successful_reads':(previous or {}).get('successful_reads',0)+1}
        metadata(session/'session.json',state)
    except ValueError as error:
        if args.action in ('scratch','tail'): state.pop(args.action,None)
        if args.action=='block': state['blocked_reason']=str(error)
        metadata(session/'session.json',state)
        report.update(status='failed',error=str(error));metadata(step/'report.json',report)
        raise
    metadata(step/'report.json',report)
    print(json.dumps(dict(status=report['status'],report=str(step/'report.json'),validation=report['validation']),indent=2))

if __name__=='__main__': main()
