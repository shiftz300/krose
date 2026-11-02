#!/usr/bin/env python3
"""Original ARM note-off, pedal state and voice-list lifecycle research."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,start,end in [('timbre-note-off',0x2743E4,0x274590),('PCM-note-off-and-attach',0x1F60A4,0x1F6244),
        ('voice-release-state',0x1F7CC8,0x1F7E30),('PCM-pedals',0x1F5E44,0x1F5FC8),
        ('voice-release-manager',0x1FD4F4,0x1FD594),('voice-release-envelope',0x1F8AF4,0x1F8BF8)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,start,end)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    a=Arm(f);results={}
    def word(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def half(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def put8(p,v):a.uc.mem_write(p,bytes([v&255]))
    def put16(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def call(entry,*argv,**kw):return a.call(entry,*argv,**kw)&0xFFFFFFFF
    osc,params,timbre,meta,prog,channel,cc,vm,voices,nodes=(0x11000000,0x11001000,0x11002000,
        0x11003000,0x11004000,0x11006000,0x11007000,0x11008000,0x11010000,0x11015000)
    head=osc+0x490
    a.write(osc+8,params);a.write(osc+0x48C,vm);a.write(osc+0x49C,timbre)
    a.write(timbre+4,meta,prog);a.write(timbre+0x10,channel);a.write(timbre+0x8C,cc)
    def voice(i):return voices+588*i
    def empty():a.write(head,head,head,0)
    def order():
        ids=[];ptr=word(head)
        while ptr!=head:
            assert len(ids)<32
            assert word(word(ptr)+4)==ptr and word(word(ptr+4))==ptr
            ids.append((word(ptr+8)-voices)//588);ptr=word(ptr)
        return ids
    # Actual attachment reverses the returned chain and stamps one group token.
    a.stubs={};empty();attachment=[]
    for ids,note in [([0,3,2,1],60),([4,5],60),([6],62)]:
        for j,i in enumerate(ids):
            a.uc.mem_write(voice(i),bytes(588));put8(voice(i)+0x16,i);put8(voice(i)+0x12,note)
            put16(voice(i)+0x10,0x80);a.write(voice(i)+0x240,0xFFFFFFFF)
            a.write(nodes+12*i,nodes+12*ids[j+1] if j+1<len(ids) else 0,0,voice(i))
        call(0x1F61F8,osc,nodes+12*ids[0])
        assert all(a.uc.mem_read(voice(i)+0x17,1)[0]==ids[0] for i in ids)
        attachment.append(dict(returned_chain=ids,list_after_attach=order()))
    assert order()==[6,5,4,1,2,3,0]
    released=[];special=[]
    def release_stub(m):
        v=m.get('R1');released.append((v-voices)//588);put16(v+0x10,half(v+0x10)&~0x80);return 0
    a.stubs={0x1FD4F4:release_stub,0x1FE87C:lambda m:special.append((m.get('R1')-voices)//588) or 0,
        0x1F5FE8:lambda m:0}
    histories=[]
    for note,velocity,expected in [(60,17,[5,4]),(60,81,[1,2,3,0]),(60,127,[]),(62,44,[6])]:
        released.clear();call(0x1F60A4,osc,0x80+(note<<8)+(velocity<<16))
        assert released==expected,(note,released,expected)
        for i in expected:assert a.uc.mem_read(voice(i)+0x1B,1)[0]==velocity
        histories.append(dict(note=note,release_velocity=velocity,released=list(released)))
    results['grouped_note_off']=dict(attachment=attachment,release_sequence=histories,
        group_token='voice +0x17 = first returned voice slot index',
        repeated_pitch_order='most recently attached matching ordinary group first',
        stop_rule='after first match, stop at ordinary voice with different note, no key-on bit, or different group token',
        boundaries='manager release and class-specific handler intercepted')
    # Exhaust the state choices at the individual voice's release entry.
    v=voice(0);eg_calls=[];cases=0;branches={}
    a.stubs={0x2737C8:lambda m:sost_enabled,0x1F8AF4:lambda m:eg_calls.append(m.get('R0')) or 0}
    for note,latched,sost_enabled,damper_enabled,damper,delay,ticks,release_allowed,ready in itertools.product(
        [0,60,127],[0,1],[0,1],[0,1],[0,63,64,79,80,127],[-1,0,3],[0,5],[0,1],[0,1]):
        a.uc.mem_write(v,bytes(588));a.write(v+8,timbre,channel);put8(v+0x12,note)
        initial_flags=0x2C2|(8 if ready else 0)
        put16(v+0x10,initial_flags);put8(v+0x20D,release_allowed);put16(v+0x208,delay)
        a.write(v+0x234,ticks);a.write(v+0x218,1);a.write(v+0x230,voice(1));put8(v+0x18,1)
        a.uc.mem_write(channel+0x128,bytes(16))
        if latched:a.write(channel+0x128+(note//32)*4,1<<(note%32))
        put8(meta+0x19,4*damper_enabled);put8(cc+64,damper);eg_calls.clear()
        result=call(0x1F7CC8,v)
        flags=(initial_flags&~0x82)|1;expected_delay=delay&65535;expected_ticks=ticks;cancel=False;envelope=False
        if latched and sost_enabled:flags|=0x100;branch='sostenuto_hold'
        elif damper_enabled and damper>=80:flags|=3;branch='damper_hold'
        elif delay<0:flags|=8;expected_delay=expected_ticks=0;branch='key_off_trigger'
        elif not release_allowed:branch='release_disabled'
        elif delay or ticks or ready:
            flags=(flags&~9)|4;expected_delay=expected_ticks=0;cancel=True;branch='cancel_before_start'
        else:flags|=5;envelope=True;branch='start_envelope_release'
        assert result==int(cancel)
        assert half(v+0x10)==flags,(note,branch,hex(half(v+0x10)),hex(flags))
        assert half(v+0x208)==expected_delay and word(v+0x234)==expected_ticks
        assert eg_calls==([v] if envelope else [])
        assert word(v+0x218)==(0 if cancel else 1) and word(v+0x230)==(0 if cancel else voice(1))
        assert a.uc.mem_read(v+0x18,1)[0]==(255 if cancel else 1)
        cases+=1;branches[branch]=branches.get(branch,0)+1
    results['voice_release_state']=dict(cases=cases,branches=branches,
        flag_changes='clear0x82, set0x01; sostenuto adds0x100; damper adds0x03; normal release adds0x05',
        negative_delay='key-off trigger: clear both waits and set ready0x08',
        cancel_before_start='clear ready0x08 and released0x01; set0x04; clear pair links; return1',
        release_boundary='0x1f8af4 intercepted; flag and waiting-state logic original')
    # Pedal hooks on an oscillator list. Low flag combinations are behavioral inputs.
    empty();pedal_calls=[];pedal_cases=0
    for i in range(8):
        a.uc.mem_write(voice(i),bytes(588));a.write(nodes+12*i,0,0,voice(i));call(0x272470,head,nodes+12*i)
    a.stubs={0x1FD4F4:lambda m:pedal_calls.append(('release',(m.get('R1')-voices)//588)) or 0,
             0x1FE8FC:lambda m:pedal_calls.append(('class',(m.get('R1')-voices)//588)) or 0}
    for half_damper,release_allowed,classified in itertools.product([0,1],[0,1],[0,1]):
        put8(params+0x2C,half_damper<<7);pedal_calls.clear()
        for i in range(8):
            put16(voice(i)+0x10,i);put8(voice(i)+0x20D,release_allowed)
            put8(voice(i)+0x18E,0);put8(voice(i)+0x18F,0)
            a.write(voice(i)+0x240,0 if classified else 0xFFFFFFFF)
        call(0x1F5E44,osc)
        assert [a.uc.mem_read(voice(i)+0x18E,1)[0] for i in range(8)]==[int(half_damper and not i&1) for i in range(8)]
        call(0x1F5E98,osc)
        expected=[]
        for i in range(8):
            if half_damper:
                if i&1 and release_allowed:expected.append(('release',i))
                assert a.uc.mem_read(voice(i)+0x18F,1)[0]==int(not(i&1 and release_allowed))
            elif i&2:expected.append(('release',i))
            elif classified:expected.append(('class',i))
        assert pedal_calls==expected
        pedal_cases+=8
    for enabled in [0,1]:
        pedal_calls.clear()
        for i in range(8):put16(voice(i)+0x10,i)
        call(0x1F5F4C,osc,enabled)
        assert pedal_calls==([] if enabled else [('release',i) for i in range(8) if i&1])
        assert [half(voice(i)+0x10) for i in range(8)]==[i|(0x100 if enabled and i&2 else 0) for i in range(8)]
        pedal_cases+=8
    results['oscillator_pedals']=dict(voice_cases=pedal_cases,
        conditional_mode='OSC params +0x2c bit7 selects envelope latch path; exact UI parameter label awaits mapping',
        on_latch='+0x18e set for voices without flag0x01',off_latch='+0x18f set unless flag0x01 and release allowed',
        ordinary_off='flag0x02 -> manager release, otherwise classified voice -> special handler',
        sostenuto_on='flag0x02 voices acquire0x100',sostenuto_off='flag0x01 voices sent through manager release')
    # Timbral event routing executes actual virtual dispatch into both oscillators.
    system,oscarray,osc2=0x11020000,0x11021000,0x11022000
    a.write(0xC1743270,system);a.write(system+0x10,1,2);a.write(system+0x34,oscarray)
    a.write(oscarray,osc,osc2);a.write(osc,BASE+0x470DE0);a.write(osc2,BASE+0x470DE0)
    dispatched=[]
    a.stubs={0x291F8C:lambda m:0,0x1F60A4:lambda m:dispatched.append((m.get('R0'),m.get('R1'))) or 0,
        0x274374:lambda m:0,0x54C74:lambda m:0,0x54E40:lambda m:0}
    put8(meta+0x19,0);put8(meta+0x1C,0);put8(prog+0x508,0);put8(prog+0x509,0)
    put8(meta+0x1F,48);put8(meta+0x1E,72);put8(timbre+0x28,0);a.uc.mem_write(channel+0x128,bytes(16))
    timbre_cases=0
    for note,count in itertools.product([0,47,48,60,72,73,127],[0,1,2,65535]):
        put16(timbre+0x46,count);dispatched.clear();packed=0x80+(note<<8)+(64<<16)
        call(0x2743E4,timbre,packed)
        assert half(timbre+0x46)==count-int(48<=note<=72 and count>0)
        assert dispatched==[(osc,packed),(osc2,packed)]
        timbre_cases+=1
    results['timbre_release_fanout']=dict(cases=timbre_cases,oscillators=2,virtual_slot='+0x18',
        key_count='decrement only inside key range and when count>0',
        fanout='ordinary polyphonic mode sends note-off to both oscillator slots even outside timbre key range')
    # Actual allocator -> attach -> ordinary note-off -> steal/recycle lifecycle.
    primary,delaynodes,tg=0x11026000,0x11027000,0x11028000
    assignment=vm+12;delayhead=vm+0xCC;envelopes=[];stops=[]
    a.uc.mem_write(vm,bytes(0x100));a.write(assignment+0x30,primary,nodes,8,0)
    a.write(delayhead,delayhead,delayhead,0,delaynodes,8);empty()
    put8(meta+0x19,0);put8(params+0x80,0);a.uc.mem_write(channel+0x128,bytes(16))
    put8(0xC104728C,1)
    a.stubs={0x1F8BF8:lambda m:0,0x1F8AF4:lambda m:envelopes.append((m.get('R0')-voices)//588) or 0,
        0x12DCDC:lambda m:stops.append(m.get('R1')) or 0,0x2737C8:lambda m:0,0x1F5FE8:lambda m:0}
    for i in range(8):
        a.uc.mem_write(voice(i),bytes(588));put8(voice(i)+0x16,i);put8(voice(i)+0x1A,i)
        a.write(voice(i)+0x1C,tg);a.write(voice(i)+0x240,0xFFFFFFFF)
        for n in [primary,nodes,delaynodes]:a.write(n+12*i,0,0,voice(i))
    call(0x1FBF4C,assignment)
    for ids in [[0,1],[2,3]]:
        for i in ids:
            assert call(0x1FC9D0,assignment)==voice(i)
            a.write(voice(i)+8,timbre,channel);put8(voice(i)+0x12,60);put8(voice(i)+0x20D,1)
            put16(voice(i)+0x10,0xC0)
        a.write(nodes+12*ids[0],nodes+12*ids[1],0,voice(ids[0]))
        a.write(nodes+12*ids[1],0,0,voice(ids[1]))
        call(0x1F61F8,osc,nodes+12*ids[0])
    def queue_ids(h):
        ids=[];p=word(h)
        while p!=h:
            assert len(ids)<16
            ids.append((word(p+8)-voices)//588);p=word(p)
        return ids
    assert order()==[3,2,1,0] and word(assignment+0x3C)==4
    call(0x1F60A4,osc,0x00403C80)
    assert envelopes==[3,2] and word(assignment+0x3C)==4
    assert queue_ids(assignment)==[4,5,6,7,3,2]
    assert queue_ids(assignment+12)==[0,1]
    # Newly acquired nodes are attached before the next acquisition, maintaining
    # the allocator's externally maintained active-membership invariant.
    reclaimed=[]
    for expected in [4,5,6,7,3]:
        selected=call(0x1FC9D0,assignment);assert selected==voice(expected)
        reclaimed.append(expected)
        a.write(nodes+12*expected,0,0,selected);call(0x1F61F8,osc,nodes+12*expected)
    assert word(assignment+0x3C)==0 and queue_ids(assignment)==[2]
    call(0x1FD53C,vm,voice(2))
    assert stops==[2] and word(assignment+0x3C)==1 and half(voice(2)+0x10)==0
    assert word(nodes+24)==0 and word(nodes+28)==0 and 2 not in order()
    results['release_reclaim_lifecycle']=dict(starting_groups=[[0,1],[2,3]],note_off_group=[3,2],
        candidates_after_note_off=[4,5,6,7,3,2],available_after_note_off=4,
        next_forced_allocations=reclaimed,hard_stop_slot=2,available_after_hard_stop=1,
        observation='note-off makes voices replacement candidates while release continues; it does not increment available count',
        executed=['allocator','group attach','oscillator note-off','manager release','individual release state','hard-stop manager and unlink'],
        intercepted=['TG reset','envelope/TG release body','TG stop write','controller gates'])
    result=dict(passed=True,firmware_sha256=FW_SHA,tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        device_access=False,results=results,scope='Synthetic RAM; no TG hardware operations; explicit per-group callback boundaries')
    (OUT/'voice-release-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,groups=list(results),release_state_cases=cases),indent=2))
if __name__=='__main__':main()
