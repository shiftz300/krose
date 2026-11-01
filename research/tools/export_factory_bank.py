#!/usr/bin/env python3
"""Explicit offline handoff: selected immutable factory data -> native bundle."""
import hashlib,json,struct,wave
from pathlib import Path
from layout import ROOT,PRODUCT_ROOT
from program_firmware import Firmware

CONFIG=ROOT/'config/native-starter.json'
IDS=json.loads(CONFIG.read_text())['programs']
assert IDS and len(IDS)==len(set(IDS))
DEST=PRODUCT_ROOT/'assets/factory-starter'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 fw=Firmware();source=ROOT/'derived/firmware/KROSS2_V124/sounds/factory/programs.json';factory={p['bank_program']:p for p in json.loads(source.read_text())['programs'] if p['kind']=='factory_A_F'}
 multi=json.loads((ROOT/'derived/firmware/KROSS2_V124/rom/catalog/multisamples.json').read_text());regions=json.loads((ROOT/'derived/firmware/KROSS2_V124/rom/catalog/key-regions.json').read_text())
 drums=json.loads((ROOT/'derived/firmware/KROSS2_V124/rom/decoding/factory-drumkits.json').read_text());kits={k['id']:k for k in drums['kits']}
 manifest=json.loads((ROOT/'output/Factory_ROM_WAV/manifest.json').read_text());samples={s['sample_id']:s for s in manifest['samples']};zones=[];programs=[];used=set();origins={}
 def add(sids,lo,hi,vlo,vhi,roots,fines,osc,level,pan=64,exclusive=0,flags=0,gain=1.,coarse=0,drumfine=0):
  assert 1<=len(sids)<=2 and all(i<4068 for i in sids);used.update(sids)
  zones.append([sids[0],sids[1] if len(sids)==2 else 0xffffffff,lo,hi,vlo,vhi,roots[0],fines[0],roots[-1],fines[-1],osc,level,pan,exclusive,flags,gain,coarse,drumfine,0,0])
 for pid in IDS:
  p=factory[pid];raw=(ROOT/p['program_file']).read_bytes();assert len(raw)==2140 and hashlib.sha256(raw).hexdigest()==p['program_sha256'];origins[pid]=dict(file=p['program_file'],sha256=p['program_sha256'])
  first=len(zones);kitid=drums['program_to_kit'].get(pid)
  if kitid:
   for key,keydata in kits[kitid]['keys'].items():
    top=127
    for layer in keydata['layers']:
     low=layer['bottom']
     if low>top:continue
     add(layer['samples'],int(key),int(key),low,top,[int(key)]*2,[0]*2,0,127,keydata['pan'],keydata['exclusive'],8|(1 if layer['reverse'] else 0),2**((layer['level']-99)/50),layer['coarse'],layer['fine']);top=low-1
  else:
   for osc in p['oscillators']:
    if not osc['active']:continue
    top=127
    for slot in osc['slots']:
     low=slot['bottom_velocity']
     if low>top:continue  # First matching slot; overlap/crossfade is outside this starter scope.
     indices=slot['ROM_multisample_indices'];assert len(indices) in (1,2)
     channel=[]
     for index in indices:
      ms=multi[index];rs=regions[ms['first_region']:ms['first_region']+ms['region_count']]
      channel.append([next((r for r in rs if r['top_key']>=n),rs[-1]) for n in range(128)])
     start=0
     while start<128:
      matches=[ch[start] for ch in channel];end=start
      while end<127 and all(ch[end+1]==ch[start] for ch in channel):end+=1
      roots=[r['root_key_candidate'] for r in matches];fines=[struct.unpack_from('<h',bytes.fromhex(r['raw_hex']),6)[0] for r in matches]
      flags=sum((2<<i) if bytes.fromhex(r['raw_hex'])[5]&1 else 0 for i,r in enumerate(matches))
      add([r['sample_index_raw'] for r in matches],start,end,low,top,roots,fines,osc['oscillator']-1,slot['level'],osc['groups']['pan_sends']['pan'],flags=flags)
      start=end+1
     top=low-1
  programs.append((pid,p['name'],int(bool(kitid)),first,len(zones)-first,raw))
 ids=sorted(used);mapping={sid:i for i,sid in enumerate(ids)}
 for z in zones:
  z[0]=mapping[z[0]]
  if z[1]!=0xffffffff:z[1]=mapping[z[1]]
 DEST.mkdir(parents=True,exist_ok=True);target=DEST/'Factory.samples';payloads=[];source_hashes={}
 for sid in ids:
  s=samples[sid];path=ROOT/'output/Factory_ROM_WAV'/s['file'];assert sha(path)==s['wav_sha256']
  with wave.open(str(path),'rb') as w:assert w.getsampwidth()==3 and w.getnchannels()==1;payloads.append(w.readframes(w.getnframes()))
  source_hashes[str(sid)]=s['wav_sha256']
 offset=24+224*4+256*2+len(ids)*32+len(zones)*80+len(programs)*(80+12+2140)
 with target.open('wb') as f:
  f.write(b'KRPRG001');f.write(struct.pack('<4I',1,len(ids),len(zones),len(programs)))
  f.write(fw.data[0x405b88:0x405b88+224*4]);f.write(fw.data[0x405984:0x405984+256*2])
  for sid,pcm in zip(ids,payloads):
   s=samples[sid];f.write(struct.pack('<5IiQ',sid,s['frames'],s['loop_start_relative'],s['frames']-1,s['flags'],s['pitch_field'],offset));offset+=len(pcm)
  for z in zones:f.write(struct.pack('<7IiIi5If4i',*z))
  for pid,name,kind,first,count,raw in programs:f.write(pid.encode().ljust(16,b'\0')+name.encode().ljust(64,b'\0')+struct.pack('<3I',kind,first,count)+raw)
  for pcm in payloads:f.write(pcm)
 assert target.stat().st_size==offset
 names=['Concert SE Grand']+[p[1] for p in programs]
 (DEST/'FactoryPrograms.h').write_text('#pragma once\nnamespace segrand {\ninline constexpr int kInstrumentProgramCount='+str(len(names))+';\ninline constexpr const char* kInstrumentProgramNames[]={'+','.join(json.dumps(n) for n in names)+'};\n}\n')
 report=dict(format_version=1,kind='Factory starter: shared mono PCM24, regions and original Program controls; effects remain approximate',files=[dict(file=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in [target,DEST/'FactoryPrograms.h']],programs=[dict(id=p[0],name=p[1],drum=bool(p[2]),zones=p[4]) for p in programs],sample_count=len(ids),region_count=len(zones),program_sources=origins,source_WAV_sha256=source_hashes,configuration_sha256=sha(CONFIG),firmware_sha256=hashlib.sha256(fw.data).hexdigest(),ROM_sha256=manifest['ROM_sha256'],exporter_sha256=sha(Path(__file__)),scope='No firmware at runtime. One velocity slot per OSC; full FX, crossfades and drum start-offset semantics are not reconstructed.')
 (DEST/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('sample_count','region_count','programs','files')},indent=2))
if __name__=='__main__':main()
