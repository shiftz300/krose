#!/usr/bin/env python3
"""Version-locked original-ARM note layer selection and voice assembly checks."""
import argparse
from collections import Counter
import contextlib
import hashlib
import io
import json
import struct
from pathlib import Path
from program_firmware import Arm, Firmware, BASE, FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage02'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,start,end in [('note-layer-selection',0x1FD6B4,0x1FDB6C),('note-voice-assembly',0x1FDC8C,0x1FE18C)]:
        text=io.StringIO()
        with contextlib.redirect_stdout(text):inspect(f.data,start,end)
        (OUT/(name+'.arm.txt')).write_text(text.getvalue())
    if not args.verify_arm:return
    a=Arm(f);results={}
    def word(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def half(p):return struct.unpack('<H',a.uc.mem_read(p,2))[0]
    def put8(p,v):a.uc.mem_write(p,bytes([v&255]))
    def put16(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def call(entry,*argv,**kw):return a.call(entry,*argv,**kw)&0xFFFFFFFF
    osc,params,timbre,meta,prog,runtime,out=(0x11000000,0x11001000,0x11002000,
        0x11003000,0x11004000,0x11006000,0x11007000)
    a.write(osc+8,params);a.write(osc+0x49C,timbre)
    a.write(timbre+4,meta,prog);a.write(timbre+0x10,runtime)
    put8(params+0x2E,127);put8(prog+0x519,127);put8(prog+0x51B,127)
    # UI/AMS parameter getters return zero; pitch helper is separately intercepted.
    a.stubs={0x275508:lambda m:0,0x275564:lambda m:0,0x2753DC:lambda m:0,0x1FF958:lambda m:0x4567}
    table=list(struct.unpack_from('<129H',f.data,0x40585C))
    assert table[0]==0 and table[-1]==32768 and all(x<=y for x,y in zip(table,table[1:]))
    def curve(x):
        if x>=32768:return x
        index,fraction=divmod(x,256)
        return table[index]+((table[index+1]-table[index])*fraction>>8)
    for x in range(32769):assert call(0x1FD6E0,x)==curve(x)
    for note in range(-512,640):
        expected=note
        while expected<0:expected+=12
        while expected>127:expected-=12
        assert call(0x1FD6B4,note)==expected
    results['helpers']=dict(curve_cases=32769,curve_table_offset='0x40585c',curve_table=table,
        curve_formula='linear interpolation of 129 unsigned 16-bit values; 8 fractional bits',
        octave_fold_cases=1152,octave_fold='add/subtract 12 repeatedly until 0..127')
    thresholds=[100,70,30];cases=0;examples=[]
    def expected_layers(velocity,width,kind,mask,bottoms=None):
        bottoms=thresholds if bottoms is None else bottoms
        slot=next((i for i,bottom in enumerate(bottoms) if velocity>=bottom),3)
        selected=[slot];gains=[32768]
        if slot<3 and width and velocity<bottoms[slot]+width:
            selected.append(slot+1)
            incoming=((velocity-bottoms[slot])*32768)//width
            outgoing=32768-incoming
            gains=[32768,32768] if kind==2 else ([curve(incoming),curve(outgoing)] if kind==1 else [incoming,outgoing])
        return selected,gains
    for width in [0,1,12,32]:
        for kind in range(4):
            for i,bottom in enumerate(thresholds):
                a.uc.mem_write(params+0x20+4*i,bytes([bottom,width,kind,0]))
            for mask in range(16):
                for slot in range(4):put8(params+slot*8+1,(mask>>slot)&1)
                for velocity in range(128):
                    a.uc.mem_write(out,b'\xa5'*64)
                    count=call(0x1FD718,0,osc,60,velocity,stack=(out,))
                    selected,gains=expected_layers(velocity,width,kind,mask)
                    assert count==len(selected)
                    assert half(out)==60 and half(out+2)==0x4567
                    for j,(slot,gain) in enumerate(zip(selected,gains)):
                        p=out+4+j*20;stereo=(mask>>slot)&1
                        assert half(p)==gain,(velocity,width,kind,slot,half(p),gain)
                        assert word(p+4)==params+8*slot and word(p+8)==osc+12+288*slot
                        assert a.uc.mem_read(p+16,1)[0]==stereo
                        if stereo:assert word(p+12)==osc+12+288*slot+144
                    if mask==15 and kind<3 and width==12 and velocity in [70,76,81,82]:
                        examples.append(dict(velocity=velocity,curve=kind,slots=selected,gains=gains))
                    cases+=1
    results['melodic_layers']=dict(cases=cases,slots=4,threshold_order=thresholds,
        selected='first threshold <= velocity; fourth slot is fallback',max_simultaneous_layers=2,
        overlap='bottom <= velocity < bottom+width; at upper endpoint use one layer',
        curves={'0':'linear complementary gains','1':'interpolated table on each complementary gain',
                '2':'both layers at 32768','3':'same linear branch as 0'},
        output_header_bytes=4,output_layer_bytes=20,stereo_flag='descriptor +1 bit0',
        examples=examples,limits='pitch helper and three parameter getters intercepted')
    # Independent key/velocity gate tests, reversed endpoint pairs, mute, and oscillator index.
    gate_cases=0
    for oscillator in [0,1]:
        put8(osc+4,oscillator)
        for key_range in [(0,127),(48,72),(72,48)]:
            put8(prog+0x518+oscillator*2,key_range[0]);put8(prog+0x519+oscillator*2,key_range[1])
            for velocity_range in [(0,127),(40,100),(100,40)]:
                put8(params+0x2D,velocity_range[0]);put8(params+0x2E,velocity_range[1])
                for muted in [0,1]:
                    put8(runtime,muted*128)
                    for note in [0,47,48,60,72,73,127]:
                        for velocity in [0,39,40,80,100,101,127]:
                            result=call(0x1FD718,0,osc,note,velocity,stack=(out,))
                            accepted=not muted and min(key_range)<=note<=max(key_range) and min(velocity_range)<=velocity<=max(velocity_range)
                            assert (result>0)==accepted,(oscillator,key_range,velocity_range,muted,note,velocity,result)
                            gate_cases+=1
    results['layer_gates']=dict(cases=gate_cases,endpoint_order='both forward and reversed endpoints accepted inclusively',
        oscillator_key_ranges=['Program +0x518/+0x519','Program +0x51a/+0x51b'],
        velocity_range='OSC params +0x2d/+0x2e',mute='timbre runtime +0 bit7')
    # Drum layer selection: 68-byte key record, 12-byte descriptors, per-key region pointer.
    drums,regions=0x11010000,0x11018000
    put8(osc+4,0);put8(runtime,0);put8(params+0x2D,0);put8(params+0x2E,127)
    put8(prog+0x518,0);put8(prog+0x519,127);put8(prog+0x508,2)
    put8(meta+7,0);put8(params+0x78,0);put8(params+0x79,0)
    a.write(osc+0x10,drums);a.write(runtime+0x138,regions)
    for note in range(128):put8(osc+0x18+note,0)
    key=60;record=drums+key*68;descriptor=record+24
    drum_cases=0
    for enabled in [0,1]:
        put8(descriptor+0x41,enabled*4)
        for width in [0,1,12,32]:
            for kind in range(4):
                for i,bottom in enumerate(thresholds):
                    a.uc.mem_write(descriptor+0x30+4*i,bytes([bottom,width,kind,0]))
                for mask in [0,5,10,15]:
                    for slot in range(4):put8(descriptor+slot*12+1,(mask>>slot)&1)
                    for velocity in range(128):
                        a.uc.mem_write(out,b'\xa5'*64)
                        count=call(0x1FD718,0,osc,key,velocity,stack=(out,))
                        selected,gains=expected_layers(velocity,width,kind,mask)
                        assert count==(len(selected) if enabled else 0)
                        if enabled:
                            for j,(slot,gain) in enumerate(zip(selected,gains)):
                                p=out+4+j*20
                                assert half(p)==gain and word(p+4)==descriptor
                                assert word(p+8)==descriptor+12*slot and word(p+12)==regions+key*12
                                assert a.uc.mem_read(p+16,1)[0]==(mask>>slot)&1
                        drum_cases+=1
    # Negative note remap suppresses a drum hit before slot selection.
    put8(osc+0x18+key,255)
    assert call(0x1FD718,0,osc,key,100,stack=(out,))==0
    results['drum_layers']=dict(cases=drum_cases,table_header_bytes=24,record_stride=68,layer_descriptor_stride=12,
        admission_field='key record +0x41 bit2',thresholds='key record +0x30, +0x34, +0x38',
        key_region_stride=12,negative_remap_suppresses_hit=True,
        shared_crossfade='same weight calculation as melodic selector',
        limits='special drum remapping table at 0x40595e not exercised')
    # Execute layer selection, forced allocator and paired-voice assembly together.
    # Voice parameter construction and TG start/reset remain explicit boundaries.
    vm,nodes,secondary,voices,delaynodes,tg=(0x11020000,0x11021000,0x11022000,0x11024000,0x11026000,0x11028000)
    assignment=vm+12;delayhead=vm+0xCC
    def voice(i):return voices+i*588
    def list_ids(head):
        ids=[];p=word(head)
        while p!=head:
            assert len(ids)<8 and word(p+8)>=voices
            ids.append((word(p+8)-voices)//588);p=word(p)
        return ids
    def reset_fixture(order):
        a.uc.mem_write(vm,bytes(0x100));a.uc.mem_write(voices,bytes(8*588))
        a.write(assignment+0x30,nodes,secondary,8,0)
        a.write(delayhead,delayhead,delayhead,0,delaynodes,8)
        for i in range(8):
            for nodebase in [nodes,secondary,delaynodes]:a.write(nodebase+12*i,0,0,voice(i))
            put8(voice(i)+0x16,i);put8(voice(i)+0x1A,order[i])
            a.write(voice(i)+0x1C,tg);a.write(voice(i)+0x240,0xFFFFFFFF)
        call(0x1FBF4C,assignment)
    prepared=[];started=[];copied=[];delay_mode=0
    def prepare(m):
        sp=m.get('SP');selection=word(sp+8);layer=word(sp+12);side=word(sp+16)
        prepared.append((layer,side,half(selection+4+20*layer)))
        return 0
    def copy_params(m):
        copied.append(m.get('R0'))
        put16(m.get('R0')+0x208,delay_mode)
        return 0
    a.stubs.update({k:lambda m:0 for k in [0x2DC184,0x2DC1BC,0x272BBC,0x1F68D4,0x272488,0x1F8BF8]})
    a.stubs.update({0x1F6958:prepare,0x1F716C:copy_params,
        0x1F7278:lambda m:started.append((m.get('R0'),m.get('R2'))) or 1})
    put8(prog+0x508,0);put8(osc+0x18+60,0)
    for i,bottom in enumerate(thresholds):a.uc.mem_write(params+0x20+4*i,bytes([bottom,12,0,0]))
    assembly_cases=0;assembly_examples=[]
    for order in [list(range(8)),list(reversed(range(8)))]:
        for delay_mode in [0,3]:
            for mask in range(16):
                for slot in range(4):put8(params+slot*8+1,(mask>>slot)&1)
                for velocity in [29,30,36,41,42,69,70,76,81,82,99,100,106,111,112,127]:
                    reset_fixture(order);prepared.clear();started.clear();copied.clear()
                    result=call(0x1FDC8C,vm,0x01003C90+(velocity<<16),osc,0,stack=(0xFFFFFFFF,))
                    selected,gains=expected_layers(velocity,12,0,mask)
                    spent=sum(1+((mask>>slot)&1) for slot in selected)
                    expected_ids=[];expected_prepared=[];pairs=[];index=0
                    for layer,(slot,gain) in enumerate(zip(selected,gains)):
                        stereo=(mask>>slot)&1
                        ids=list(range(index,index+1+stereo))
                        if stereo:ids.sort(key=lambda i:order[i]);pairs.append(ids)
                        expected_ids.extend(ids);index+=len(ids)
                        expected_prepared.extend((layer,side,gain) for side in range(1+stereo))
                    assert copied==[voice(i) for i in expected_ids] and prepared==expected_prepared
                    assert list_ids(assignment+12)==list(range(spent)) and word(assignment+0x3C)==8-spent
                    assert result==secondary+12*expected_ids[0]
                    # The first node remains head; later nodes are inserted immediately after it.
                    chain=[];p=result
                    while p:
                        assert len(chain)<8
                        chain.append((word(p+8)-voices)//588);p=word(p)
                    assert chain==expected_ids[:1]+list(reversed(expected_ids[1:]))
                    assert list_ids(delayhead)==(list(reversed(expected_ids)) if delay_mode else [])
                    for left,right in pairs:
                        assert word(voice(left)+0x218)==1 and word(voice(right)+0x218)==2
                        assert word(voice(left)+0x230)==voice(right) and word(voice(right)+0x230)==voice(left)
                        assert a.uc.mem_read(voice(left)+0x18,1)[0]==order[right]
                    assert a.uc.mem_read(vm+0xE0,1)[0]==0
                    if mask==15 and velocity==76:
                        assembly_examples.append(dict(tg_indices=order[:spent],voice_order=expected_ids,returned_chain=chain,
                            paired_indices=pairs,delay_visits=delay_mode,slots_used=spent))
                    assembly_cases+=1
    results['voice_assembly']=dict(cases=assembly_cases,max_slots_per_oscillator_in_fixture=4,
        formula='sum(1 + stereo_bit) for selected layers',allocator_path='0x1fdc8c -> 0x1fca9c -> 0x1fc9d0',
        pair_order='ascending TG slot index within each stereo pair',
        partner_fields=['+0x218 pair type 1/2','+0x230 reciprocal partner pointer','primary +0x18 partner TG index'],
        returned_list='secondary-node chain, newest nodes inserted after first',examples=assembly_examples,
        limits=['Only successful parameter/start branches','Voice parameter construction 0x1f6958 intercepted',
                'Parameter copy 0x1f716c intercepted','TG start 0x1f7278 and reset 0x1f8bf8 intercepted'])
    # Delay list: elapsed-time field expires first, then visit counter; bit3 signals readiness.
    delay_cases=[]
    for ticks,visits in [(0,0),(0,1),(0,3),(5,0),(5,2)]:
        reset_fixture(list(range(8)))
        put16(voice(0)+0x208,visits);a.write(voice(0)+0x234,ticks)
        call(0x1FCF58,delayhead,voice(0));trajectory=[]
        expected_ticks,expected_visits,ready=ticks,visits,False
        for elapsed in [1,2,3,1,1,1]:
            if expected_ticks:
                expected_ticks=max(0,expected_ticks-elapsed)
                if expected_ticks==0 and expected_visits==0:ready=True
            elif expected_visits>0:
                expected_visits-=1
                if expected_visits==0:ready=True
            call(0x1FCECC,delayhead,elapsed)
            actual=(word(voice(0)+0x234),half(voice(0)+0x208),bool(half(voice(0)+0x10)&8))
            assert actual==(expected_ticks,expected_visits,ready)
            trajectory.append(dict(elapsed=elapsed,ticks_left=actual[0],visits_left=actual[1],ready=actual[2]))
        delay_cases.append(dict(initial_ticks=ticks,initial_visits=visits,trajectory=trajectory))
    results['delayed_voices']=dict(cases=delay_cases,ready_flag='voice +0x10 bit3',
        time_basis='elapsed argument and loop visits; physical units not assigned')
    # Sweep actual factory Program fields through the selector, retaining disabled
    # descriptors as candidates; the later parameter builder applies their flags.
    preload_path=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
    preload=preload_path.read_bytes();preload_sha=hashlib.sha256(preload).hexdigest()
    assert preload_sha=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory=[];factory_cases=0;overlap_programs=set();curves=Counter();active_oscillators=0
    a.stubs={0x275508:lambda m:0,0x275564:lambda m:0,0x2753DC:lambda m:0,0x1FF958:lambda m:0x4567}
    a.uc.mem_write(meta,bytes(0x100));a.uc.mem_write(runtime,bytes(0x200))
    for index in range(768):
        data=preload[0x1EF220+index*2140:0x1EF220+(index+1)*2140]
        mode=data[0x508]&7
        if mode==2:continue
        assert mode in [0,1]
        bank=f'{chr(65+index//128)}{index%128:03d}'
        a.uc.mem_write(prog,data)
        for oscillator in range(1+mode):
            active_oscillators+=1;put8(osc+4,oscillator)
            block=data[0x564+oscillator*380:0x564+(oscillator+1)*380]
            a.uc.mem_write(params,block)
            bottoms=[block[32+4*i] for i in range(3)]
            keylo,keyhi=sorted(data[0x518+2*oscillator:0x51A+2*oscillator])
            vello,velhi=sorted(block[0x2D:0x2F]);records=[]
            for velocity in range(1,128):
                count=call(0x1FD718,0,osc,60,velocity,stack=(out,))
                slot=next((i for i,bottom in enumerate(bottoms) if velocity>=bottom),3)
                width=block[33+slot*4] if slot<3 else 0
                kind=block[34+slot*4]&3 if slot<3 else 0
                selected,gains=expected_layers(velocity,width,kind,0,bottoms)
                if not (keylo<=60<=keyhi and vello<=velocity<=velhi):selected=[];gains=[]
                assert count==len(selected),(bank,oscillator,velocity,count,selected)
                flags=[]
                for j,(slot,gain) in enumerate(zip(selected,gains)):
                    p=out+4+j*20
                    assert word(p+4)==params+slot*8 and half(p)==gain
                    flags.append(block[slot*8]&3)
                if len(selected)==2:
                    overlap_programs.add(bank);curves[str(kind)]+=1
                records.append(dict(velocity=velocity,slots=[i+1 for i in selected],gains_q15=gains,descriptor_low_flags=flags))
                factory_cases+=1
            factory.append(dict(program=bank,name=data[:24].decode('ascii').strip(' \0'),oscillator=oscillator+1,
                note=60,program_sha256=hashlib.sha256(data).hexdigest(),velocities=records))
        if index%128==127:print('Factory selector bank',bank[0],flush=True)
    (OUT/'factory-note-layer-map.json').write_text(json.dumps(dict(firmware_sha256=FW_SHA,preload_sha256=preload_sha,
        scope='Selector at note60, velocities1..127 for active melodic oscillators; disabled candidate flags preserved; no sample loader or audio',
        oscillators=factory),ensure_ascii=False,separators=(',',':'))+'\n')
    results['factory_layer_selection']=dict(cases=factory_cases,programs=len({row['program'] for row in factory}),
        active_oscillators=active_oscillators,note=60,velocities=[1,127],
        programs_with_two_candidates=sorted(overlap_programs),two_candidate_cases_by_curve=dict(curves),
        preload_sha256=preload_sha,limits='Candidate selection only; descriptor flags, region availability and sample loading remain downstream')
    result=dict(passed=True,firmware_sha256=FW_SHA,
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        device_access=False,results=results)
    (OUT/'note-layers-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,groups=list(results),melodic_cases=cases,drum_cases=drum_cases),indent=2))

if __name__=='__main__':main()
