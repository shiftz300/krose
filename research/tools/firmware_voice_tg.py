#!/usr/bin/env python3
"""Run original PCM start/release through the TG bus boundary in private RAM."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import struct
from pathlib import Path
from program_firmware import FW_SHA
from voice_firmware import VoiceOracle
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage03'

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    oracle=VoiceOracle();a=oracle.arm;f=oracle.firmware;OUT.mkdir(parents=True,exist_ok=True)
    for name,start,end in [('TG-voice-start',0x1F9028,0x1F9440),('TG-sample-registers',0x12CDE4,0x12CEE4),
        ('TG-amplitude-release',0x12D238,0x12D3A4),('TG-bus',0x132690,0x1326E4),
        ('voice-completion-and-ready',0x1F963C,0x1F9828),('voice-manager-poll',0x1FE404,0x1FE80C)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,start,end)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    catalog=ROOT/'research/derived/firmware/KROSS2_V124/rom/catalog'
    region_path=catalog/'key-regions.json';sample_path=catalog/'sample-descriptors.json'
    region_record=json.loads(region_path.read_text())[0]
    sample_record=json.loads(sample_path.read_text())[region_record['sample_index_raw']]
    sample_raw=bytes.fromhex(sample_record['raw_hex']);region_raw=bytes.fromhex(region_record['raw_hex'])
    v=oracle.voice;sample,region,clock,tg=0x11040000,0x11041000,0x11042000,0x60000000
    writes=[];reads=[];current=0;status_words=[0]*4;busy=0
    def bus_write(m):writes.append((m.get('R0')-tg,m.get('R1')));return 0
    def bus_read(m):
        off=m.get('R0')-tg;reads.append(off)
        if off==0x42C:return current
        if off in [0x240,0x244,0x248,0x24C]:return status_words[(off-0x240)//4]
        return 8*busy if off==0 else 0
    a.stubs.update({0x132690:bus_write,0x1326B4:bus_read})
    def put8(p,x):a.uc.mem_write(p,bytes([x&255]))
    def put16(p,x):a.uc.mem_write(p,struct.pack('<H',x&65535))
    def call(entry,*argv,**kw):return a.call(entry,*argv,**kw)&0xFFFFFFFF
    def initialize(note=60,velocity=100,oscillator=0,slot=7):
        oracle.initialize(note,velocity,oscillator)
        a.write(v+0x0C,oracle.controls);a.write(v+0x20,sample);a.write(v+0x22C,region)
        a.write(v+0x1C,tg);put8(v+0x1A,slot);put8(v+0x18,255);put8(v+0x23E,1)
        a.write(oracle.context+0x10,oracle.controls)
        a.uc.mem_write(sample,sample_raw);a.uc.mem_write(region,region_raw)
        a.write(0xC1B5720C,clock);a.write(clock,0,123)
        a.write(0xC165D9B0,region_record['root_key_candidate']<<8)
        a.write(0xC165D9AC,struct.unpack_from('<h',region_raw,6)[0]);a.write(0xC165D9A0,64)
        a.write(0xC165D9B4,note);a.write(0xC165D9A8,note<<8)
        put8(0xC165D9A4,127);put8(0xC165D9A5,0);put8(0xC165D9B8,0)
        put8(0xC104728C,1);a.uc.mem_write(0xC165DA38,bytes(24))
        writes.clear();reads.clear();assert call(0x1F7278,v,oracle.runtime,0)==1
        assert oracle.u16(v+0x23C)==32767 and oracle.byte(v+0x23E)==0
        assert oracle.u16(0xC165DA38+2*(slot//16))==1<<(slot%16)
        assert oracle.byte(0xC165DA38+0x14)==1
    # Complete control initialization executes all TG programming calls. The bus
    # returns ready status; no chip stepping, register persistence or audio model.
    initializations=[]
    for osc,note,velocity,slot in itertools.product([0,1],[24,60,96],[1,85,127],[0,15,16,119]):
        initialize(note,velocity,osc,slot)
        assert all(0<=off<0x4000 for off,_ in writes)
        selected_slots=[value for off,value in writes if off==0x400]
        assert selected_slots==[slot]*2,selected_slots
        assert any(off==0x200 for off,_ in writes) and any(off==0x418 for off,_ in writes)
        if note==60 and velocity==85 and slot==16:
            initializations.append(dict(oscillator=osc+1,note=note,velocity=velocity,slot=slot,
                writes=[dict(register=hex(off),value=hex(value)) for off,value in writes],
                read_registers=[hex(off) for off in reads]))
    # Exhaust descriptor mode bits and the reverse switch; use distinct sample
    # address fields to disambiguate each selector branch.
    initialize();mode_cases=0;examples=[]
    addresses={0x0C:0x100,0x10:0x200,0x14:0x300,0x18:0x400,0x1C:0x500,
               0x20:0x600,0x24:0x700,0x28:0x800,0x2C:0x900,0x30:0xA00,0x34:0xB00,0x38:0xC00,0x3C:0xD00}
    for off,value in addresses.items():a.write(sample+off,value)
    for flags,reverse,offset,boundary in itertools.product(range(64),[0,1],[0,1,2,3,7,8],[0,1,3]):
        put8(sample+7,flags);put8(v+0x20C,reverse);put8(v+0x20A,offset);put8(v+0x20B,boundary)
        put8(v+0x23E,1);writes.clear();reads.clear();call(0x1F9028,v,sample,0)
        field=0x0C if offset==0 else (0x38 if offset-boundary+8==7 else
              (0x3C if offset-boundary+8==8 else (0x10 if offset==1 else 0x20+4*(offset-1))))
        selected=addresses[field]
        mode=flags;start=addresses[0x14];loop=selected
        if mode&8:
            loop=addresses[0x18]
            if mode&32:start=addresses[0x0C]
            elif reverse:mode|=32
        elif reverse:start=addresses[0x1C];loop=addresses[0x20];mode|=40
        expected_mode=((mode>>2)&14)|(mode&1)
        values={off:value for off,value in writes}
        assert values[0x200]==expected_mode and values[0x208]==start
        assert values[0x210]==loop and values[0x20C]==addresses[0x18]-1,(flags,reverse,offset,boundary,values[0x210],loop)
        assert values[0x21C]==struct.unpack_from('<H',f.data,0x3A8D72+0x190+2*struct.unpack_from('<h',sample_raw,2)[0])[0]
        if flags in [0,8,32,40] and offset==0 and boundary==0:examples.append(dict(descriptor_flags=flags,reverse=reverse,
            mode_register=expected_mode,start_register=start,loop_register=loop,end_register=addresses[0x18]-1))
        mode_cases+=1
    # Original release EG, target calculation and TG amplitude command. Select
    # bus read values around the computed target to cover the equality nudge.
    coefficients=struct.unpack_from('<25H',f.data,0x3A8D40);release_cases=[]
    for oscillator,velocity,advances in itertools.product([0,1],[1,85,127],[0,1,8,32]):
        initialize(60,velocity,oscillator)
        for _ in range(advances):oracle.advance()
        saved=bytes(a.uc.mem_read(v,588));current=12345
        writes.clear();call(0x1F8AF4,v);target=oracle.u16(v+0x150)
        for readback in sorted(set([0,target,max(0,target-1),min(32767,target+1),32767])):
            a.uc.mem_write(v,saved);current=readback;writes.clear();reads.clear();call(0x1F8AF4,v)
            assert oracle.u16(v+0x150)==target
            cached=readback if readback!=target else (readback-1 if readback else 1)
            assert oracle.u16(v+0x152)==cached
            duration=oracle.u32(v+0x178)
            product=(coefficients[min(duration,24)]*(target-cached))>>16
            step=product+(1 if product>=0 else -1)
            expected=((step&65535)<<16)|target
            assert [value for off,value in writes if off==0x418]==[expected]
            assert reads.count(0x42C)==2 and oracle.u16(v+0x10)&0x10==0
            release_cases.append(dict(oscillator=oscillator+1,velocity=velocity,advances=advances,
                readback=readback,cached=cached,target=target,duration=duration,step=step,
                EG_stage=oracle.byte(v+0x162),register_word=expected))
    # Polling executes original status readers and stop commands. A synthetic
    # slot-status bit and the chip-wide bit3 are varied independently.
    completion_cases=0;completion_branches={}
    for enabled,flags,delay,ticks,active,chip_busy in itertools.product([0,1],
        [0,1,0x80,0x81,0x20,0x30,0x400,0x410,0x480,0x490,0x10,0x90],[-1,0,1],[0,5],[0,1],[0,1]):
        put8(0xC104728C,enabled);put16(v+0x10,flags);put16(v+0x208,delay);a.write(v+0x234,ticks)
        put8(v+0x1A,119);a.write(v+0x1C,tg);status_words[:]=[0,0,0,active<<(119%32)];busy=chip_busy
        writes.clear();reads.clear();result=call(0x1F969C,v)
        expected_flags=flags;expected=0
        if not enabled:branch='global_disabled'
        elif flags&0x20:
            expected_flags=0;expected=1|(10 if flags&0x10 else 0);branch='already_finished'
        elif flags&(0x400|0x81):
            if not delay and not ticks and not active and not busy:
                expected=1;expected_flags=0;branch='TG_finished'
            else:
                expected=10 if flags&0x10 else 0;expected_flags=flags&~0x10;branch='waiting_or_running'
        else:branch='inactive'
        assert result==expected and oracle.u16(v+0x10)==expected_flags,(enabled,flags,delay,ticks,active,busy,result,expected)
        if branch=='TG_finished':assert any(off==0x418 and value==0xFC000000 for off,value in writes)
        if enabled and flags&(0x400|0x81) and not flags&0x20 and not delay and not ticks:
            assert 0x24C in reads
            assert (0 in reads)==(not active)
        completion_cases+=1;completion_branches[branch]=completion_branches.get(branch,0)+1
    status_words[:]=[0]*4;busy=0;current=0
    # A ready primary starts both stereo members, then commits the 128-bit slot
    # mask through +230..+23c and command2 through +22c. A secondary never starts
    # itself from this entry.
    delayed_cases=[];partner=0x11044000
    for pair,slot,other_slot in itertools.product([0,1,2],[0,15,16,63,119],[1,31,64]):
        initialize(slot=slot);a.uc.mem_write(partner,bytes(a.uc.mem_read(v,588)))
        put8(partner+0x1A,other_slot);a.write(partner+0x218,2);a.write(partner+0x230,v)
        a.write(v+0x218,pair);a.write(v+0x230,partner if pair==1 else 0)
        for address in [v,partner]:
            put16(address+0x10,0x88);put16(address+0x208,3);a.write(address+0x234,9);put8(address+0x23E,1)
        a.write(0xC165DA38+0x10,tg);writes.clear();reads.clear()
        # Original short wait helper accesses a timer; this branch only needs
        # its ordering, so record the requested wait argument at the boundary.
        waits=[];a.stubs[0x12F1D0]=lambda m:waits.append(m.get('R1')) or 0
        result=call(0x1F969C,v)
        if pair==2:
            assert result==0 and not writes and oracle.u16(v+0x10)==0x88
        else:
            assert result==6 and oracle.u16(v+0x10)==0x80
            assert oracle.u16(v+0x208)==0 and oracle.u32(v+0x234)==0
            mask=(1<<slot)|((1<<other_slot) if pair==1 else 0)
            assert [(off,value) for off,value in writes if 0x230<=off<=0x23C]==[(0x230+4*i,(mask>>(32*i))&0xFFFFFFFF) for i in range(4)]
            assert [(off,value) for off,value in writes if off==0x22C]==[(0x22C,2)]
            assert waits==([21] if pair==1 else [])
            if pair==1:assert oracle.u16(partner+0x10)==0x80 and oracle.u16(partner+0x208)==0 and oracle.u32(partner+0x234)==0
        delayed_cases.append(dict(pair_type=pair,slot=slot,partner_slot=other_slot,return_flags=result))
    # Manager polling consumes the completion bit and returns all four active
    # slots to its real free/candidate queue, including the membership cleanup.
    manager,voices,primary,nodes,delaynodes,oscillator=0x11080000,0x11090000,0x110A0000,0x110A1000,0x110A2000,0x110A3000
    assignment=manager+12;head=oscillator+0x490;delayhead=manager+0xCC
    a.uc.mem_write(manager,bytes(0x100));a.write(manager+4,voices);a.write(manager+0xE4,8)
    put8(manager+0xE8,2);a.write(assignment+0x30,primary,nodes,8,0)
    a.write(delayhead,delayhead,delayhead,0,delaynodes,8);a.write(head,head,head,0)
    for i in range(8):
        address=voices+588*i;a.uc.mem_write(address,bytes(588))
        put8(address+0x16,i);put8(address+0x1A,i);a.write(address+0x1C,tg);a.write(address+0x240,0xFFFFFFFF)
        for array in [primary,nodes,delaynodes]:a.write(array+12*i,0,0,address)
    call(0x1FBF4C,assignment)
    a.stubs[0x1F8BF8]=lambda m:0  # allocator acquisition reset already studied separately
    for i in range(4):
        address=voices+588*i;assert call(0x1FC9D0,assignment)==address
        put16(address+0x10,0x80);a.write(nodes+12*i,0,0,address);call(0x1F61F8,oscillator,nodes+12*i)
    assert oracle.u32(assignment+0x3C)==4
    writes.clear();reads.clear();status_words[:]=[0]*4;busy=0
    call(0x1FE404,manager)
    assert oracle.u32(assignment+0x3C)==8 and oracle.byte(manager+0xE0)==0
    assert all(oracle.u16(voices+588*i+0x10)==0 for i in range(8))
    assert all(oracle.u32(nodes+12*i)==0 and oracle.u32(nodes+12*i+4)==0 for i in range(4))
    queue=[];ptr=oracle.u32(assignment)
    while ptr!=assignment:
        assert len(queue)<8;queue.append((oracle.u32(ptr+8)-voices)//588);ptr=oracle.u32(ptr)
    assert sorted(queue)==list(range(8))
    reclaimed=dict(initial_available=4,finished_slots=[0,1,2,3],final_available=8,candidate_queue=queue,
        manager_cursor=oracle.byte(manager+0xE9),membership_nodes_cleared=True)
    # The real bus primitives use two 16-bit accesses, high half first, even on
    # this little-endian CPU. Run those primitives against synthetic RAM too.
    from unicorn import UC_HOOK_MEM_WRITE
    memory=0x110B0000;accesses=[]
    hook=a.uc.hook_add(UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:accesses.append((address-memory,size,value)),begin=memory,end=memory+3)
    saved_stubs={entry:a.stubs.pop(entry) for entry in [0x132690,0x1326B4]}
    bus_values=[0,1,0xFFFF,0x10000,0x12345678,0x80000000,0xFFFFFFFF]
    for value in bus_values:
        accesses.clear();call(0x132690,memory,value)
        assert [(off,size,x&65535) for off,size,x in accesses]==[(0,2,value>>16),(2,2,value&65535)],accesses
        assert bytes(a.uc.mem_read(memory,4))==struct.pack('<HH',value>>16,value&65535)
        assert call(0x1326B4,memory)==value
    a.uc.hook_del(hook);a.stubs.update(saved_stubs)
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
        full_initialization_cases=72,initialization_examples=initializations,
        sample_address_cases=mode_cases,sample_address_examples=examples,
        release_cases=release_cases,completion_cases=completion_cases,completion_branches=completion_branches,
        delayed_start_cases=delayed_cases,automatic_reclaim=reclaimed,
        bus_primitive_cases=len(bus_values),bus_halfword_order='high16 at base, low16 at base+2',
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
        additional_helpers={name:hashlib.sha256((ROOT/'research/tools'/name).read_bytes()).hexdigest() for name in ['voice_firmware.py']},
        inputs=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in
                [region_path,sample_path,ROOT/'research/output/kep-analysis/Concert_SE_Grand/program.bin']],
        boundaries=['TG bus writes 0x132690 captured; reads 0x1326b4 supply ready and chosen amplitude readback',
            'Tone Adjust zero, external MIDI override off, mute gate open; stereo short wait argument captured',
            'No chip execution or audio; arbitrary mode combinations test packing, not valid ROM material modes',
            'One independent real region/sample with Concert parameters; full factory mapping not implied'])
    (OUT/'voice-tg-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,full_initialization_cases=72,sample_address_cases=mode_cases,release_cases=len(release_cases),
        completion_cases=completion_cases,delayed_start_cases=len(delayed_cases),automatic_reclaim=reclaimed,
        bus_primitive_cases=len(bus_values)),indent=2))
if __name__=='__main__':main()
