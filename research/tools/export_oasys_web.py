"""Export EXPCM001 source-wave auditions into the independent website catalog."""
import sys,json,struct,hashlib,math,os
from pathlib import Path
sys.path.insert(0,'research/tools')
from layout import ROOT,PRODUCT_ROOT
from decode_korg_pcm import Decoder,load_lut,write_wav
from program_firmware import Firmware
from voice_math import VoiceMath,EnvelopeSegment
import compress_web_samples as codec
site=PRODUCT_ROOT.parent/'krose-website/public'
lib=json.loads((ROOT/'derived/kep/EXPCM001/library.json').read_text());raw=(ROOT/lib['decoded']).read_bytes();assert hashlib.sha256(raw).hexdigest()==lib['decoded_sha256']
fw=Firmware();decoder=Decoder(load_lut(),ROOT/'build/oasys-decode');out=ROOT/'output/OASYS_Piano_WAV';out.mkdir(exist_ok=True)
records=[]
for s in lib['samples']:
 sid=10000+s['id'];desc=bytes.fromhex(s['descriptor_hex']);native=raw[s['offset']:s['offset']+s['frames']];assert hashlib.sha256(native).hexdigest()==s['sha256']
 target=out/f'{sid}.wav';pitch=struct.unpack_from('<h',desc)[0];rate=round(48000*fw.phase_increment(pitch*2)/8192)
 if not target.exists():
  audio,counts=decoder.decode(native,*struct.unpack_from('<2h',desc,8));assert counts==[0,0];write_wav(target,audio,1,rate)
 records.append(dict(sample_id=sid,file=target.name,frames=s['frames'],loop_start_relative=s['loop'],flags=desc[7],pitch_field=pitch,wav_rate_hz=rate,wav_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),file_bytes=target.stat().st_size))
(out/'manifest.json').write_text(json.dumps({'samples':records},indent=2)+'\n')
codec.OUTPUT=out;codec.DERIVED=out;codec.opus_main()
encoded={r['id']:r for r in json.loads((out/'web-opus-manifest.json').read_text())['samples']}
data=json.loads((site/'catalog.json').read_text());data['programs']=[p for p in data['programs'] if p.get('library')!='oasys-piano'];data['waveforms']=[w for w in data['waveforms'] if not w['id'].startswith('OP-')];data['samples']={k:v for k,v in data['samples'].items() if int(k)<10000};data['packs']=[p for p in data['packs'] if not Path(p['file']).name.startswith('oasys-')]
pending=[];payload=bytearray();packs=[]
def flush():
 if not pending:return
 content=bytes(payload);sha=hashlib.sha256(content).hexdigest();name=f'assets/oasys-{len(packs):03d}-{sha[:12]}.bin';(site/name).write_bytes(content)
 index=len(data['packs']);pack=dict(file=name,bytes=len(content),sha256=sha);data['packs'].append(pack);packs.append(pack)
 for s,offset,length in pending:
  sid=s['sample_id'];e=encoded[sid];data['samples'][str(sid)]=dict(pack=index,offset=offset,length=length,frames=s['frames'],rate=s['wav_rate_hz'],pitch=s['pitch_field'],flags=s['flags'],loop=s['loop_start_relative'],loopStart=e['loop_start_seconds'],loopEnd=e['loop_end_seconds'],duration=e['decoded_frames_48000']/48000)
 pending.clear();payload.clear()
for s in records:
 content=(ROOT/encoded[s['sample_id']]['file']).read_bytes();assert hashlib.sha256(content).hexdigest()==encoded[s['sample_id']]['opus_sha256']
 if len(payload)+len(content)>1024*1024:flush()
 pending.append((s,len(payload),len(content)));payload.extend(content)
flush()
# Map every original ROM multisample index to its existing decoded channel.
factory=json.loads((ROOT/'output/Factory_Sound_Selection/rom-sound-catalog.json').read_text());webwaves={w['id']:w for w in data['waveforms']};rom={}
for w in factory['waveforms']:
 for ms,ch in zip(w['indices'],webwaves[w['id']]['channels']):rom[ms]=(w['name'],ch)
waves={}
def getwave(source):
 indices=source['multisample_indices'];kind=source['kind'];key=(kind,tuple(indices))
 if key in waves:return waves[key]
 wid='OP-'+('PCM' if kind=='expansion' else 'ROM')+'-'.join(f'{n:03}' for n in indices);channels=[];names=[]
 for index in indices:
  if kind=='expansion':
   ms=lib['multisamples'][index];names.append(ms['name']);channels.append([dict(sample=10000+r['sample_id'],top=r['top'],root=r['root'],fine=struct.unpack_from('<h',bytes.fromhex(r['raw_hex']),6)[0],fixed=bool(bytes.fromhex(r['raw_hex'])[5]&1)) for r in ms['regions']])
  else:
   name,ch=rom[index];names.append(name);channels.append(ch)
 w=dict(id=wid,name=names[0].removesuffix(' -L').removesuffix('-L'),category='PIANO',categories=['PIANO'],channels=channels,used_by=[]);data['waveforms'].append(w);waves[key]=w;return w
programs=[p for p in json.loads((ROOT/'derived/firmware/KROSS2_V124/sounds/programs.json').read_text())['programs'] if p['library_id']==1]
vm=VoiceMath(fw)
for p in programs:
 pid=f'OP{p["index"]:03}';mapping={};configs={};ids=[];prg=(ROOT/p['path']).read_bytes();assert hashlib.sha256(prg).hexdigest()==p['sha256']
 for osc in p['oscillators']:
  if not osc['active']:continue
  for slot in osc['slots']:
   source=slot['source'];assert source['kind'] in ('expansion','ROM'),source
   w=getwave(source);wid=w['id']
   if wid in ids:continue
   ids.append(wid);w['used_by'].append(pid)
   eg=osc['groups']['amp_eg'];index=eg['release_time'];curve=eg['curve_release'];key=f'{index}:{curve}'
   if key not in data['releaseProfiles']:
    seg=EnvelopeSegment(vm,32767,0,index,0,curve,stage=8);units=seg.total;steps=max(1,math.ceil(units/24));values=[1.0]
    for _ in range(steps):level,done=seg.step();values.append(round(max(0,min(1,level/32767)),7))
    assert done;values[-1]=0.;data['releaseProfiles'][key]=dict(time_index=index,curve_index=curve,base_seconds=units/1500,seconds=steps*.016,values=values)
   mapping[wid]=key;base=0x564+380*(osc['oscillator']-1)
   configs[wid]=dict(base_units=fw.u32(0x3FD5A4+index*4),curve=curve,time_ams=[dict(source=eg[f'time_ams_source_{i}'],intensity=eg[f'time_ams_{i}_release']) for i in (1,2,3)],tracking=[list(vm.keyboard_tracking(prg[offset:offset+7],note,amp) for note in range(128)) for offset,amp in [(base+0xFC,False),(base+0x13C,True),(0x554,False),(0x55C,False)]],mixers=[list(prg[base+offset:base+offset+24]) for offset in (0x14C,0x164)])
 data['programs'].append(dict(id=pid,name=p['name'],library='oasys-piano',category='PIANO',subcategory='OASYS Piano',waveform_ids=ids,recommended=p['index']==2,effects=p['effects'],release_profiles=mapping,release_ams=configs,drumkit_id=None))
(site/'catalog.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
expected={p['file'] for p in packs}
for path in (site/'assets').glob('oasys-*.bin'):
 if str(path.relative_to(site)) not in expected:path.unlink()
(out/'web-export.json').write_text(json.dumps({'programs':32,'samples':len(records),'packs':packs,'scope':'Selected source waveform audition; full Program layering and original effects are not rendered.'},indent=2)+'\n')
print('OASYS exported',len(programs),'Programs,',len(records),'samples,',len(packs),'packs')
