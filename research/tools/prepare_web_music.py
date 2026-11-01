#!/usr/bin/env python3
"""Convert complete source-attributed Mutopia MIDI pieces to browser note events."""
import bisect
import hashlib
import struct

from decode_factory_rom import ROOT, DERIVED, save

PIECES=[dict(id='clair-de-lune',title='Clair de lune',composer='Debussy',file='debussy_clair_de_lune_mutopia.mid',
             url='https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=1778',credit='Keith OHara / Mutopia Project',license='Public Domain'),
        dict(id='nocturne-op9-2',title='Nocturne Op.9 No.2',composer='Chopin',file='chopin_nocturne_op9_no2_mutopia.mid',
             url='https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=1590',credit='Renato Biolcati Rinaldi / Mutopia Project',license='CC BY-SA 3.0',license_url='https://creativecommons.org/licenses/by-sa/3.0/'),
        dict(id='gymnopedie-1',title='Gymnopédie No.1',composer='Satie',file='satie_gymnopedie_no1_mutopia.mid',
             url='https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=37',credit='Evin Robertson / Mutopia Project',license='Public Domain')]


def variable(raw,pos):
    value=0
    while True:
        b=raw[pos];pos+=1;value=value*128+(b&127)
        if not b&128:return value,pos


def parse_midi(raw):
    assert raw[:4]==b'MThd';size,kind,tracks,division=struct.unpack_from('>IHHH',raw,4)
    assert kind in (0,1) and not division&0x8000
    pos=8+size;events=[];tempo=[(0,500000)]
    for track in range(tracks):
        assert raw[pos:pos+4]==b'MTrk';length=struct.unpack_from('>I',raw,pos+4)[0];body=raw[pos+8:pos+8+length];pos+=8+length
        i=tick=running=0
        while i<len(body):
            delta,i=variable(body,i);tick+=delta;status=body[i]
            if status>=128:i+=1
            else:status=running
            if status==255:
                meta=body[i];i+=1;count,i=variable(body,i);payload=body[i:i+count];i+=count
                if meta==81:tempo.append((tick,int.from_bytes(payload,'big')))
            elif status in (240,247):count,i=variable(body,i);i+=count
            else:
                assert 128<=status<240;running=status;count=1 if status&240 in (192,208) else 2
                payload=body[i:i+count];i+=count;events.append((tick,track,status,*payload))
    assert pos==len(raw)
    timeline=[];last=0;seconds=0;previous=500000
    for tick,speed in sorted(tempo):
        seconds+=(tick-last)*previous/(division*1e6);timeline.append((tick,seconds,speed));last=tick;previous=speed
    ticks=[t[0] for t in timeline]
    def time(tick):
        t,s,speed=timeline[bisect.bisect_right(ticks,tick)-1];return s+(tick-t)*speed/(division*1e6)
    active={};notes=[];pedal=[]
    for event in sorted(events,key=lambda e:(e[0],e[1])):
        tick,track,status,*payload=event;kind=status&240;channel=status&15;key=(track,channel,payload[0]);at=time(tick)
        if kind==144 and payload[1]:active.setdefault(key,[]).append((at,payload[1]))
        elif kind==128 or kind==144 and not payload[1]:
            if active.get(key):
                start,velocity=active[key].pop(0);notes.append([start,max(.03,at-start),payload[0],velocity])
        elif kind==176 and payload[0]==64:pedal.append([at,payload[1]>=64])
    assert notes and not any(active.values())
    return sorted(notes),sorted(pedal)


def main():
    pieces=[]
    for spec in PIECES:
        source=ROOT/'research/downloads'/spec['file'];raw=source.read_bytes();notes,pedal=parse_midi(raw)
        begin=min(n[0] for n in notes)
        full_notes=[[round(t-begin,5),round(d,5),n,v] for t,d,n,v in notes]
        duration=max(t+d for t,d,n,v in full_notes)
        pedals=[[round(max(0,t-begin),5),on] for t,on in pedal if t<=begin+duration]
        if not pedals:
            if spec['id']=='clair-de-lune':
                changes=[4,8.5,13,17.5,22,25,26.5,29.5,31,34,36.5,40.5,43]
                pedals=[[.065,True]]
                for t in changes:
                    if t<duration-.2:pedals.extend([[round(t+.015,5),False],[round(t+.085,5),True]])
                basis='Editorial syncopated damper pedaling at opening harmonic/left-voice changes; the supplied Debussy MIDI has no CC64.'
                release=.32
            elif spec['id']=='nocturne-op9-2':
                # The source LilyPond lower staff prints ped/pes by accompaniment
                # group. Preserve the extended spans in bars4-6 and8; short lifts
                # and delayed presses are an audition interpretation, not a claim
                # of an original recorded performance.
                eighth=60/132;beat=eighth*3;upbeat=eighth
                down=list(range(15))+[17,18,19,20,22,23,24,25,26,27,28,29,30,32]
                up=list(range(14))+[16,17,18,19,21,22,23,24,25,26,27,28,29,31]
                pedals=[[round(upbeat+g*beat+.045,5),True] for g in down]
                pedals += [[round(upbeat+(g+1)*beat-.055,5),False] for g in up]
                pedals=sorted([p for p in pedals if p[0]<duration-.2])
                basis='Audition pedal arrangement follows printed lower-staff ped/pes accompaniment group spans in Mutopia source, with brief lifts and delayed re-presses.'
                release=.23
            else:
                low_notes=[n for n in full_notes if n[2]<55];changes=sorted(set(n[0] for n in low_notes))
                pedals=[[.06,True]]
                for t in changes:
                    if .3<t<duration-.2:pedals.extend([[round(t+.015,5),False],[round(t+.085,5),True]])
                basis='Editorial syncopated damper pedaling at low accompaniment/bass changes for the audition.'
                release=.3
            if spec['id'] in ('clair-de-lune','nocturne-op9-2'):
                # Retain the curated opening. Continue with editorial bass-led
                # changes, limiting holds across sparse passages/cadenzas.
                pedals=[p for p in pedals if p[0]<45]
                changes=[]
                for t,d,n,v in full_notes:
                    if n<55 and 45<=t<duration-.2 and (not changes or t-changes[-1]>=.3):
                        changes.append(t)
                last_down=max(t for t,on in pedals if on)
                for t in changes:
                    pedals.extend([[round(min(t+.015,last_down+4),5),False],
                                   [round(t+.085,5),True]])
                    last_down=t+.085
                pedals.append([round(min(duration,last_down+4),5),False])
                basis+=' After the opening, editorial bass-led pedal changes with holds capped at four seconds; not a transcription of the printed pedal markings.'
            pedals.append([round(duration,5),False])
        else:basis='Original MIDI CC64';release=.25
        # Always finish with the pedal released, including source MIDI CC64.
        pedals=sorted(pedals,key=lambda p:p[0])
        if pedals[-1][1]:pedals.append([round(duration,5),False])
        score=ROOT/'research/downloads'/spec['file'].replace('.mid','.ly')
        pieces.append({**spec,'source_sha256':hashlib.sha256(raw).hexdigest(),'duration':round(duration,5),'notes':full_notes,'pedal':pedals,
                       'release_seconds':release,'pedal_basis':basis,'score_sha256':hashlib.sha256(score.read_bytes()).hexdigest(),
                       'adaptation':'Complete MIDI piece, leading silence removed; all MIDI notes converted to timed JSON and editorial pedal/release added. No audio performance recording included.'})
        source.chmod(0o400)
        score.chmod(0o400)
        print(spec['title'],len(full_notes),'notes',duration,'seconds',flush=True)
    save(DERIVED/'web-music.json',dict(pieces=pieces))


if __name__=='__main__':main()
