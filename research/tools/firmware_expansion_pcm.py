#!/usr/bin/env python3
"""Offline expansion PCM export and native bank/directory/region verification."""
import argparse,collections,contextlib,hashlib,io,json,struct,sys,wave
from pathlib import Path
from decode_korg_pcm import Decoder,decode_reference,load_lut,write_wav
from firmware_factory_voice_chain import Rig as FactoryRig,sb
from firmware_voice_lfo import sha,OUT,h,w
from program_firmware import Firmware,Arm,FW_SHA,BASE
from test_korg_pcm import FirmwareFeedback
from firmware_inspect import inspect
from layout import ROOT as RESEARCH,PRODUCT_ROOT as ROOT

EXPECTED={1:('ca8e77bac45e731a09b50a4e9446ec72d8fad81a423e243cac34c9ae3e75be8c','adf726d84c88f7614399cce89535f59db7c25d923e167f4f99b1594bc7ad123c'),
          2:('4ec7d6c8f740fadce55aa257628e4e284449ef44e75d400eb0d5156405e49688','0c44115badf03e9c0c64d7fd0641a2241d69a194526b9ef4fb2fda897cc447be'),
          4:('297d8687f4aa339927c1b792e69a44370b7746ec6eeb7ee109fe9a92b1594864','4bb3dd70b0cf8276fb48cd1afda23350181df69825dd3add82c4f0cecba79baa')}
EXPORT=ROOT/'research/output/Expansion_PCM_WAV'

def read_library(number):
    catalog=ROOT/f'research/derived/kep/EXPCM{number:03d}/library.json';lib=json.loads(catalog.read_text())
    source=RESEARCH/lib['source'];decoded=RESEARCH/lib['decoded'];assert sha(source)==lib['source_sha256']==EXPECTED[number][0]
    data=decoded.read_bytes();assert hashlib.sha256(data).hexdigest()==lib['decoded_sha256']==EXPECTED[number][1]
    for section in lib['sections'].values():
        payload=data[section['payload_offset']:section['payload_offset']+section['bytes']]
        assert len(payload)==section['bytes'] and len(payload)%4==0
        assert sum(x[0] for x in struct.iter_unpack('<I',payload))&0xFFFFFFFF==int(section['checksum'],16)
    ns,nr,nm,nd=struct.unpack_from('<4I',data,0x9C);assert ns==len(lib['samples']) and nm==len(lib['multisamples'])
    prm=lib['sections']['PRM1'];raw=data[prm['payload_offset']:prm['payload_offset']+prm['bytes']]
    assert ns*64+nr*20+nm*28+nd*32==len(raw)
    lib.update(raw_prm=raw,region_count=nr,declared_drumsamples=nd,decoded_bytes=data,inputs=[catalog,source,decoded])
    return lib

def native_resources(f,libraries):
    r=FactoryRig(f);a=r.a;a.uc.mem_map(0x12000000,0x400000);banks=[];maps=[]
    for slot,lib in enumerate(libraries,1):
        logical=lib['id']+1;address=0x12000000+(slot-1)*0x100000;raw=lib['raw_prm'];a.uc.mem_write(address,raw)
        ns=len(lib['samples']);nr=lib['region_count'];nm=len(lib['multisamples']);used=ns*64+nr*20+nm*28;aux=raw[used:]
        assert len(aux)%32==0;nd=len(aux)//32;assert nd==lib['declared_drumsamples'];header=r.banks+52*slot
        a.write(header+0x14,ns,nr,nm,nd);a.write(header+0x24,address,address+64*ns,address+64*ns+20*nr,address+used if nd else 0)
        a.write(r.banks+0x1A34+8*slot,logical,slot)
        direct=address+0x80000;stereo=address+0x80020;da=address+0x81000;sa=address+0x82000;encoded=2*logical
        a.write(direct,da,nm);a.write(stereo,sa,nm//2);a.write(r.registry+4*encoded,direct,stereo)
        a.call(0x283AF8,direct,encoded,0);a.call(0x283E04,stereo,encoded+1,direct,0)
        pairs=[]
        for i in range(r.word(stereo+4)):
            ptr=r.word(sa+4*i);pair=[r.half(ptr+4)&32767,r.half(ptr+6)&32767];pairs.append(pair)
            for side in range(2):assert a.call(0x28543C,r.registry,encoded+1,i,side,stack=(0,))==pair[side]
        expected=[[i,i+1] for i in range(nm-1) if lib['multisamples'][i]['name'].endswith('-L') and lib['multisamples'][i+1]['name']==lib['multisamples'][i]['name'][:-1]+'R']
        assert pairs==expected,(lib['id'],pairs,expected)
        reverse=[]
        for ms in lib['multisamples']:
            allowed=all(not bytes.fromhex(lib['samples'][reg['sample_id']]['descriptor_hex'])[7]&1 for reg in ms['regions'])
            assert a.call(0x285758,r.registry,encoded,ms['id'])==int(allowed);reverse.append(allowed)
            mapping=address+0x90000+144*ms['id'];a.uc.mem_write(mapping,bytes(144));a.call(0x1F5928,mapping,logical,ms['id'])
            expected_map=[0]*128;previous=-1
            for index,region in enumerate(ms['regions']):
                if region['top']>0:
                    for note in range(previous+1,region['top']+1):expected_map[note]=index
                previous=region['top']
            for note in range(previous+1,128):expected_map[note]=255
            assert list(a.uc.mem_read(mapping+12,128))==expected_map
            for note,index in enumerate(expected_map):
                ptr=a.call(0x1F5B24,mapping,note)&0xFFFFFFFF
                wanted=0 if index==255 else address+64*ns+20*(ms['region_first']+index);assert ptr==wanted
                sample=None if not ptr else r.half(ptr)
                if ptr:
                    assert bytes(a.uc.mem_read(ptr,20))==bytes.fromhex(ms['regions'][index]['raw_hex'])
                    assert bytes(a.uc.mem_read(ptr+2,1))[0]==logical and sample<ns
                maps.append(dict(library=lib['id'],multisample=ms['id'],note=note,region=None if index==255 else ms['region_first']+index,sample=sample))
        drums=[]
        if nd:
            drumdir=address+0x80040;drumstereo=address+0x80060;drumarray=address+0x83000;drumstereoarray=address+0x84000
            a.write(drumdir,drumarray,nd);a.write(drumstereo,drumstereoarray,nd//2);a.write(r.registry+0x400+4*encoded,drumdir,drumstereo)
            a.call(0x283AF8,drumdir,encoded,1);a.call(0x283E04,drumstereo,encoded+1,drumdir,1)
            for i in range(nd):
                rawdrum=aux[32*i:32*(i+1)];sample=h(rawdrum,0);assert sample<ns and rawdrum[2]==logical
                allowed=not bytes.fromhex(lib['samples'][sample]['descriptor_hex'])[7]&1
                assert a.call(0x2857B8,r.registry,encoded,i)==int(allowed)
                drums.append(dict(index=i,sample=sample,logical_bank=rawdrum[2],start_boundary=rawdrum[3],name=rawdrum[4:28].decode('ascii').rstrip(' \0'),level=sb(rawdrum,28),raw_hex=rawdrum.hex()))
        banks.append(dict(library=lib['id'],logical_bank=logical,physical_slot=slot,samples=ns,regions=nr,multisamples=nm,stereo_pairs=pairs,reverse_capabilities=reverse,drumsamples=drums))
    lookups=[]
    for logical in range(256):
        expected=next((i+1 for i,lib in enumerate(libraries) if lib['id']+1==logical),0)
        actual=a.call(0x1E2974,r.banks,logical);assert actual==expected
        lookups.append([logical,actual])
    return dict(banks=banks,maps=maps,lookups=lookups)

def export_pcm(f,lib,decoder,feedback,rate_arm,lut,smoke):
    folder=EXPORT/f"EXPCM{lib['id']:03d}";folder.mkdir(parents=True,exist_ok=True);rows=[];rate_cache={}
    for s in lib['samples'][:3] if smoke else lib['samples']:
        desc=bytes.fromhex(s['descriptor_hex']);source=lib['decoded_bytes'][s['offset']:s['offset']+s['frames']]
        assert hashlib.sha256(source).hexdigest()==s['sha256'];assert desc[7]&1
        assert w(desc,24)-w(desc,12)+1==len(source) and w(desc,20)-w(desc,12)==s['loop']
        a1,a2=struct.unpack_from('<2h',desc,8);reference,counts=decode_reference(source,a1,a2,lut);audio,c_counts=decoder.decode(source,a1,a2)
        assert reference==audio and counts==c_counts
        points=set(range(min(32,len(source))));points.update(range(max(0,s['loop']-2),min(len(source),s['loop']+3)));points.update(range(max(0,len(source)-4),len(source)))
        saturation=[i for i,x in enumerate(reference) if abs(x)==2147483647];points.update(saturation[:8]);points.update(saturation[-8:])
        for index in sorted(points):
            actual=feedback.step(source[index],a1,a2,reference[index-1] if index else 0,reference[index-2] if index>1 else 0)
            assert actual==reference[index],(lib['id'],s['id'],index)
        pitch=struct.unpack_from('<h',desc)[0];increment=f.phase_increment(2*pitch)
        if pitch not in rate_cache:
            assert rate_arm.pitch_rate(pitch)==increment;rate_cache[pitch]=increment
        exact=48000*increment/8192;rate=round(exact);path=folder/f"{s['id']:04d}.wav"
        buffer=io.BytesIO();buffer.write_bytes=buffer.write
        write_wav(buffer,audio,1,rate);content=buffer.getvalue()
        if path.exists():assert path.read_bytes()==content,path
        else:path.write_bytes(content)
        with wave.open(io.BytesIO(content),'rb') as wav:
            assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())==(1,3,rate,len(audio))
            payload=wav.readframes(wav.getnframes())
        raw=reference.tobytes()
        if sys.byteorder!='little':copy=reference[:];copy.byteswap();raw=copy.tobytes()
        assert payload[0::3]==raw[1::4] and payload[1::3]==raw[2::4] and payload[2::3]==raw[3::4]
        rows.append(dict(id=s['id'],file=str(path.relative_to(ROOT)),sha256=hashlib.sha256(content).hexdigest(),frames=len(audio),loop=s['loop'],flags=desc[7],pitch=pitch,
            nominal_rate_exact=exact,wav_rate_hz=rate,coefficients=[a1,a2],saturations=counts,arm_points=sorted(points),source_sha256=s['sha256'],source_offset=s['offset'],
            relative_start=w(desc,12),relative_end_inclusive=w(desc,24),bytes=len(content)))
        if s['id']%100==0:print('Expansion PCM',lib['id'],s['id'],'frames',len(audio),flush=True)
    return dict(library=lib['id'],name=lib['name'],samples=rows,rates=rate_cache)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');parser.add_argument('--smoke',action='store_true');args=parser.parse_args();f=Firmware()
    libs=[read_library(n) for n in [1,2,4]]
    if not args.verify_arm:return
    for name,lo,hi in [('expansion-region-map',0x1F5928,0x1F5AA0),('expansion-bank-lookup',0x1E2974,0x1E29AC)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    resources=native_resources(f,libs);print('Expansion native regions',len(resources['maps']),flush=True)
    lut=load_lut();decoder=Decoder(lut,ROOT/'research/build/expansion-pcm');feedback=FirmwareFeedback();rate_arm=Arm(f)
    exports=[export_pcm(f,lib,decoder,feedback,rate_arm,lut,args.smoke) for lib in libs if lib['id'] in [2,4]]
    kits=[];future=libs[-1];section=future['sections']['1KBD'];rawkits=future['decoded_bytes'][section['payload_offset']:section['payload_offset']+section['bytes']]
    assert section['count']==4 and section['stride']==8728
    for kit in range(4):
        raw=rawkits[8728*kit:8728*(kit+1)];keys=[]
        for note in range(128):
            key=raw[24+68*note:24+68*(note+1)]
            if not key[65]&1:continue
            slots=[]
            for slot in range(4):
                desc=key[12*slot:12*(slot+1)]
                if not desc[0]&1:continue
                reachable=[]
                for vel in range(1,128):
                    chosen=next((i for i in range(3) if vel>=key[48+4*i]),3);selected=[chosen]
                    if chosen<3 and key[49+4*chosen] and vel<key[48+4*chosen]+key[49+4*chosen]:selected.append(chosen+1)
                    if slot in selected:reachable.append(vel)
                slots.append(dict(slot=slot,bank=desc[1],number=h(desc,2),available_bank=desc[1] in [0,1,10,11],reachable_velocities=reachable))
                if desc[1]==10:assert h(desc,2)<45
            keys.append(dict(note=note,slots=slots))
        kits.append(dict(index=kit,name=raw[:24].decode('ascii').rstrip(' \0'),keys=keys))
    inputs=[]
    for lib in libs:inputs.extend(lib['inputs'])
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_factory_voice_chain.py','firmware_voice_lfo.py','voice_math.py','decode_korg_pcm.py','korg_pcm_decode.c','test_korg_pcm.py']},
        inputs=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in inputs],resources=resources,exports=exports,expansion_drumkits=kits,
        boundaries=['Immutable KEP/plaintext fingerprints and all existing section word checksums verified; ciphertext extraction not rerun',
            'Original bank lookup, capability/stereo directory construction, key-map builder and region lookup execute over private copies of all three expansion PRM tables',
            'Every exported frame compares C with independent Python; exported PCM24 is compared byte-for-byte to high24 bits of the reconstruction',
            'Original ARM encoder prediction/inverse-quantizer feedback checks sample prefixes, loop/tail neighborhoods and selected saturation points, not every frame or TG hardware decoding',
            'Nominal sample rates compare original isolated CPU pitch computation; integer WAV rounding, native flags/loops/starts remain separate metadata',
            'Future Synth trailing1440 bytes parsed as45 native32-byte drum records and used by original capability/directory scans; four kits parsed for assignments',
            'Header slots1/2/3 and bank-table bindings are controlled fixture placements; no full loader, upload relocation, voice startup, effects, device or continuous audio executes',
            'WAVs contain mono source material without global root/loop smpl tags; roots remain per-region and loops/flags are retained in this manifest'])
    target=OUT/('expansion-pcm-smoke.json' if args.smoke else 'expansion-pcm-check.json');target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,samples=sum(len(e['samples']) for e in exports),frames=sum(s['frames'] for e in exports for s in e['samples']),
        arm_points=sum(len(s['arm_points']) for e in exports for s in e['samples']),native_regions=len(resources['maps']),drumkits=len(kits)),indent=2))
if __name__=='__main__':main()
