#!/usr/bin/env python3
"""KROSS 2 v1.2.4 runtime-flow research, stage 02.

Original ARM runs only in synthetic RAM. Device reads, voice reset bodies,
blocking waits and business callbacks are intercepted at documented boundaries.
No device API, firmware patch, product code, or historical result is modified.
"""
import argparse
import contextlib
import hashlib
import io
import json
import random
import struct
from pathlib import Path
from program_firmware import Arm, Firmware, BASE, FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage02'
RANGES={
    'voice-assignment':(0x1FBF4C,0x1FCC78),
    'voice-list-primitives':(0x272414,0x272488),
    'voice-TG-status':(0x12D350,0x12D388),
    'rdapi-messages':(0x2CCEB4,0x2CD914),
    'midi-channel-routing':(0x2BDB7C,0x2BE01C),
    'midi-top-routing':(0x2C1A6C,0x2C1AF8),
    'sound-channel-routing':(0x271500,0x2715B4),
    'sync-loop':(0x2B5440,0x2B55A8),
    'sync-callback-timers':(0x2B4AA8,0x2B521C),
    'sound-channel-note-dispatch':(0x26EC34,0x26ED7C),
    'sound-note-parity':(0x26E0EC,0x26E124),
    'sound-pedals':(0x26ED7C,0x26F034),
    'timbre-note-entry':(0x274590,0x2746C8),
    'timbre-note-start':(0x273D4C,0x273E30),
    'timbre-oscillator-dispatch':(0x2737F8,0x2738E8),
    'PCM-oscillator-note-on':(0x1F62F0,0x1F6588),
}
NAMES={
0x1FBF4C:'voice_assignment_initialize_lists',0x1FC548:'voice_take_available',
0x1FC5B4:'voice_move_unreserved_to_candidate_tail',0x1FC600:'voice_return_if_active',
0x1FC6B0:'voice_return_unconditionally',0x1FC738:'voice_clear_secondary_links_unless_flag9',
0x1FC76C:'voice_detach_non_sentinel_node',0x1FC790:'voice_take_class_head',
0x1FC7F0:'voice_select_status_score_candidate',0x1FC89C:'voice_reclaim_pair_and_secondary_membership',
0x1FC9D0:'voice_allocate_forced',0x1FCA9C:'voice_allocate_forced_batch',
0x1FCAE4:'voice_allocate_class',0x1FCBC4:'voice_allocate_class_batch_checked',
0x1FCC70:'voice_available_count',0x2CD344:'RDAPI_receive_message',
0x2CD3B4:'RDAPI_receive_message_or_events',0x2CD594:'RDAPI_pool_take',
0x2CD608:'RDAPI_send_message_common',0x2CD684:'RDAPI_send_message_task_context',
0x2CD68C:'RDAPI_send_message_interrupt_context',0x2CD8C0:'RDAPI_deadline_remaining',
0x2CD8E8:'RDAPI_deadline_set',0x2C1A6C:'MIDI_route_by_status',
0x2BDF5C:'MIDI_normalize_note_and_preprocess',0x2BDB7C:'MIDI_channel_controls_and_sound_forward',
0x271500:'sound_route_event_to_channel',0x26EC34:'sound_channel_event_dispatch',
0x2B4AA8:'CSync_timer_countdown',0x2B4C04:'CSync_timer_allocate',
0x2B4C88:'CSync_timer_release',0x2B50CC:'CSync_timers_advance',
0x26E0EC:'sound_note_parity_filter',0x274590:'timbre_note_on',0x2743E4:'timbre_note_off',
0x273D4C:'timbre_note_start',0x2737F8:'timbre_dispatch_oscillator_note_on',
0x1F62F0:'CPCMOsc_note_on',0x1FDC8C:'PCM_build_note_voices',
}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def static(f):
    OUT.mkdir(parents=True,exist_ok=True)
    for name,(start,end) in RANGES.items():
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,start,end)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    callers={hex(k):[] for k in NAMES};pointers={hex(k):[] for k in NAMES}
    for o in range(0,len(f.data)-3,4):
        target=f.u32(o)-BASE
        if target in NAMES:pointers[hex(target)].append(hex(o))
    for o in range(0,0x330000,4):
        w=f.u32(o)
        if w&0x0F000000!=0x0B000000:continue
        rel=w&0xFFFFFF
        if rel&0x800000:rel-=1<<24
        target=o+8+4*rel
        if target in NAMES:callers[hex(target)].append(hex(o))
    save('index.json',dict(firmware_sha256=FW_SHA,names={hex(k):v for k,v in NAMES.items()},
        ranges={k:[hex(x) for x in v] for k,v in RANGES.items()},
        direct_call_candidates=callers,aligned_pointer_candidates=pointers,
        scope='Analyst aliases; BL and aligned pointer candidates require control-flow review; computed references may be absent'))


def verify(f):
    a=Arm(f);results={}
    def word(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def put8(p,v):a.uc.mem_write(p,bytes([v&255]))
    def put16(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    def fatal(m):raise AssertionError(('unexpected firmware error',hex(m.get('R1')),m.get('R2')))
    def call(entry,*args,**kw):return a.call(entry,*args,**kw)&0xFFFFFFFF
    a.stubs={0x2C5220:fatal}
    # 12-byte intrusive nodes: next, previous, voice pointer.
    manager,nodes,secondary,voices,aux,tg=(0x11000000,0x11001000,0x11002000,0x11010000,0x11070000,0x11080000)
    def voice(i):return voices+i*0x24C
    def list_ids(head):
        seen=[];p=word(head)
        while p!=head:
            assert len(seen)<256 and word(p+8)>=voices,(hex(head),seen,hex(p))
            assert word(word(p)+4)==p and word(word(p+4))==p
            seen.append((word(p+8)-voices)//0x24C);p=word(p)
        return seen
    resets=[]
    def init(n=120):
        a.uc.mem_write(manager,bytes(0x4000));a.uc.mem_write(voices,bytes(0x14000))
        a.write(manager+0x30,nodes,secondary,n,0)
        a.write(aux,aux,aux,0)
        for i in range(n):
            a.write(nodes+12*i,0,0,voice(i));a.write(secondary+12*i,0,0,voice(i))
            put8(voice(i)+0x16,i);put8(voice(i)+0x1A,i)
            a.write(voice(i)+0x1C,tg);a.write(voice(i)+0x240,0xFFFFFFFF)
            put16(voice(i)+0x23C,100+i)
        # All synthetic TG status bits on; preserve the driver's high-half-first order.
        a.uc.mem_write(tg+0x240,b'\xff'*32)
        a.stubs={0x2C5220:fatal,0x1F8BF8:lambda m:resets.append(m.get('R0')) or 0}
        resets.clear();call(0x1FBF4C,manager)
    def track(i):call(0x272458,aux,secondary+12*i)
    def claim(entry=0x1FC9D0,group=0):
        p=call(entry,manager,group);i=(p-voices)//0x24C
        assert p==voice(i);track(i);return i
    init(128)
    assert list_ids(manager)==list(range(120)) and list_ids(manager+0x18)==list(range(120,128))
    assert all(list_ids(manager+0x40+12*g)==[] for g in range(8))
    assert word(manager+0x3C)==128
    results['assignment_layout']=dict(initialized_nodes=128,voice_stride=588,node_stride=12,
        normal_partition=list(range(120)),upper_partition=list(range(120,128)),class_queues=8)
    init()
    seq=[claim() for _ in range(120)]
    assert seq==list(range(120)) and word(manager+0x3C)==0
    assert list_ids(manager)==[] and list_ids(manager+12)==seq
    # Reserve a fresh pool by class, then force replacement in descending class order.
    init(16)
    expected_groups={g:[] for g in range(8)}
    for i in range(16):
        g=i%8;assert claim(0x1FCAE4,g)==i;expected_groups[g].append(i)
    stolen=[]
    for g in reversed(range(8)):
        for i in expected_groups[g]:
            actual=claim();assert actual==i,(g,i,actual);stolen.append(actual)
        assert word(manager+0xA0+g*4)==0
    assert word(manager+0x3C)==0
    results['forced_allocation']=dict(first_120=seq,descending_class_fifo=stolen,
        reset_boundary='0x1f8bf8 intercepted; list/counter/pair cleanup executes original ARM')
    # Checked class allocation must fail atomically when demand exceeds eligible counts.
    checked=[];output=0x11090000
    for threshold in range(8):
        for requested in [0,1,8-threshold,9-threshold,9]:
            init(8)
            for g in range(8):assert claim(0x1FCAE4,g)==g
            a.uc.mem_write(output,b'\xa5'*64)
            before=bytes(a.uc.mem_read(manager,0x3000));vbefore=bytes(a.uc.mem_read(voices,8*0x24C))
            result=call(0x1FCBC4,manager,output,requested,threshold)
            expected=requested<=8-threshold
            assert result==int(expected),(threshold,requested,result)
            if not expected:
                assert bytes(a.uc.mem_read(manager,0x3000))==before
                assert bytes(a.uc.mem_read(voices,8*0x24C))==vbefore
                assert bytes(a.uc.mem_read(output,64))==b'\xa5'*64
            else:
                selected=[(word(output+4*i)-voices)//0x24C for i in range(requested)]
                assert selected==list(range(7,7-requested,-1)),(threshold,requested,selected)
            checked.append(dict(threshold=threshold,requested=requested,success=bool(result)))
    results['checked_class_allocation']=dict(cases=checked,failure_mutations=0)
    # Candidate score selection: strict improvement; early exit <=4; first node fallback.
    rng=random.Random(0x124);score_cases=[]
    samples=[([100,20,30],[1,1,1]),([100,20,30],[0,0,0]),([100,3,0],[1,1,1]),
             ([9,9,9],[1,1,1]),([65535]*3,[1]*3),([],[])]
    for _ in range(250):
        n=rng.randrange(1,17);samples.append(([rng.choice([0,1,4,5,20,65535,rng.randrange(65536)]) for i in range(n)],
                                           [rng.randrange(2) for i in range(n)]))
    for scores,status in samples:
        init(len(scores));mask=sum(s<<i for i,s in enumerate(status))
        put16(tg+0x240,mask>>16);put16(tg+0x242,mask)
        for i,s in enumerate(scores):put16(voice(i)+0x23C,s)
        chosen=None if not scores else 0;best=65535
        for i,(s,ok) in enumerate(zip(scores,status)):
            if ok and s<best:
                chosen=i;best=s
                if s<=4:break
        p=call(0x1FC7F0,manager,word(manager))
        assert p==(0 if chosen is None else nodes+12*chosen),(scores,status,chosen,hex(p))
        assert list_ids(manager)==[i for i in range(len(scores)) if i!=chosen]
        score_cases.append(dict(scores=scores,status_bits=status,selected=chosen))
    results['score_selection']=dict(cases=len(score_cases),examples=score_cases[:6],
        policy='first strictly lower score among TG status=1; stop <=4; default first node if no improvement',
        meaning_of_score='voice +0x23c unsigned 16-bit; perceptual meaning not assumed')
    # Return a class voice to the ordinary candidate head; clear secondary links.
    init(8)
    for g in range(8):claim(0x1FCAE4,g)
    for i in [3,7,0]:
        call(0x1FC600,manager,voice(i));call(0x1FC738,manager,voice(i))
    assert list_ids(manager)==[0,7,3] and word(manager+0x3C)==3
    assert [word(manager+0xA0+i*4) for i in range(8)]==[0,1,1,0,1,1,1,0]
    results['return_and_reuse']=dict(returned=[3,7,0],candidate_head_order=[0,7,3],available_count=3)

    # RDAPI constructor: 500 usable 16-byte pool nodes and 13 queue/deadline records.
    osobj=0x110A0000;heap=[0x110B0000];allocs=[]
    def alloc(m):
        n=m.get('R0');p=heap[0];heap[0]+=(n+15)&~15;allocs.append(n)
        a.uc.mem_write(p,bytes((n+15)&~15));return p
    a.stubs={0x2C5220:fatal,0x2DC184:lambda m:0,0x2DC1BC:lambda m:0,
             0x2E2F9C:alloc,0x14E730:alloc}
    call(0x2CCEB4,osobj,500,12)
    assert allocs==[13*12]+[16,16]*13+[501*16],allocs
    pool,queues=word(osobj),word(osobj+4)
    for tid in range(13):
        q=queues+12*tid;head,tail=word(q),word(q+4)
        assert word(head)==tail and word(tail)==head and word(q+8)==0
    a.stubs={0x2C5220:fatal,0x132660:lambda m:0x55,0x132670:lambda m:0}
    acquired=[call(0x2CD594,osobj,0) for _ in range(501)]
    assert acquired==[pool+16*i for i in range(1,501)]+[0]
    ref=0x110A0100
    for ptr in reversed(acquired[:-1]):a.write(ref,ptr);call(0x2CD694,osobj,ref)
    assert word(pool)==pool+16
    results['RDAPI_pool_and_queues']=dict(usable_pool_nodes=500,pool_node_bytes=16,queue_records=13,
        queue_record_bytes=12,record_fields=['head_sentinel_ptr','tail_sentinel_ptr','deadline'])
    # Send actual queue nodes, intercept only event flag entrypoints.
    signal=[]
    a.stubs.update({0x2FC618:lambda m:signal.append(('task',m.get('R0'),m.get('R1'))) or 0,
                   0x2FC6FC:lambda m:signal.append(('irq',m.get('R0'),m.get('R1'))) or 0})
    for tid in range(1,12):
        for interrupt in [0,1]:
            ptr=call(0x2CD594,osobj,0);a.write(ref,ptr)
            call(0x2CD608,osobj,tid,ref,interrupt)
            assert signal[-1]==('irq' if interrupt else 'task',tid,0x80000000)
        q=queues+tid*12
        values=[call(0x2CD7F4,q),call(0x2CD7F4,q),call(0x2CD7F4,q)]
        assert values==[pool+(tid*2-1)*16,pool+tid*2*16,0],values
    # Blocking receive: first empty wake-up may be unrelated; retry until a message exists.
    tid=3;wakes=[];payload=pool+16*100
    a.stubs[0x2CD184]=lambda m:tid
    def wake(m):
        wakes.append((m.get('R1'),m.get('R2'),m.get('R3')))
        if len(wakes)==2:
            a.write(word(queues+tid*12),payload)
            a.write(payload,word(queues+tid*12+4))
            a.write(word(queues+tid*12+4),payload)
        return 0
    a.stubs[0x2CD2D0]=wake
    call(0x2CD344,osobj,ref,count=2000)
    assert word(ref)==payload and len(wakes)==2 and all(x==(0x80000000,0,0xFFFFFFFF) for x in wakes)
    results['RDAPI_send_and_receive']=dict(sends=len(signal),destinations=11,wakeup_mask='0x80000000',
        task_and_interrupt_entrypoints_verified=True,spurious_wakeup_retries=len(wakes))
    # Deadline wrap and positive-delay branch; kernel sleeping is intercepted.
    delays=[];now=[0]
    a.stubs={0x2CD184:lambda m:tid,0x2CD744:lambda m:now[0],0x2FC084:lambda m:delays.append(m.get('R0')) or 0}
    timer_cases=[]
    for start in [0,100,0xFFFFFFF0]:
        for delay in [0,1,32,1000]:
            now[0]=start;call(0x2CD6D0,osobj,delay)
            assert word(queues+tid*12+8)==(start+delay)&0xFFFFFFFF
            for elapsed in [0,1,delay,delay+1]:
                for early in [0,1]:
                    now[0]=(start+elapsed)&0xFFFFFFFF;delays.clear()
                    ret=call(0x2CD704,osobj,early)
                    left=(delay-elapsed-early)&0xFFFFFFFF;signed=left if left<0x80000000 else left-0x100000000
                    assert delays==([left] if signed>0 else []) and ret==0x40000000
                    timer_cases.append([start,delay,elapsed,early,left])
    results['RDAPI_deadlines']=dict(cases=len(timer_cases),formula='signed32(deadline - early - current_time)',return_mask='0x40000000')

    # Status-byte routing with all 256 byte values. Downstream consumers are stubs.
    msg,context=0x110D0000,0x110D0100;routes=[]
    router_cases=0
    for ready in [0,1]:
        for accept in [0,1]:
            a.stubs={0x14D744:lambda m:ready,0x2BDF5C:lambda m:accept}
            for dest in [0x2C11A0,0x2BDB7C,0x2BD064]:
                a.stubs[dest]=lambda m,d=dest:routes.append((d,m.get('R0'),m.get('R1'),m.get('R2'))) or 0
            for status in range(256):
                routes.clear();a.uc.mem_write(msg,bytes([status,60,100,8,0,0,0,0]))
                call(0x2C1A6C,msg,context)
                expected=[]
                if ready:
                    if status<128:expected=[(0x2C11A0,msg,context,status)]
                    elif status<=239 and accept:expected=[(0x2BDB7C,msg,context,status&0xF0)]
                    elif status>=240:expected=[(0x2BD064,msg,context,status)]
                assert routes==expected,(ready,accept,status,routes);router_cases+=1
    results['MIDI_status_router']=dict(cases=router_cases,classes={'00-7f':'internal/SysEx command','80-ef':'channel voice','f0-ff':'system'})
    # Note normalization uses original status for preprocessing selection, then mutates zero-velocity status.
    config=0xC1DCC2D8;events=[];normal_cases=0
    a.stubs={0x2BDE4C:lambda m:events.append(('note_on_path',m.get('R2'),m.get('R3'))) or 1,
             0x2BDEDC:lambda m:events.append(('note_off_path',m.get('R2'),m.get('R3'))) or 1,
             0x02AA44:lambda m:events.append(('other',)) or 0}
    for enabled in [0,1]:
        put8(config+4,4 if enabled else 0)
        for source in [0,1,8]:
            for transpose in [-24,-1,0,1,24]:
                put8(config+1,transpose)
                for status in [0x80,0x8F,0x90,0x9F]:
                    for note in range(128):
                        for velocity in [0,1,127]:
                            events.clear();a.uc.mem_write(msg,bytes([status,note,velocity,source,0,0,0,0]))
                            actual=call(0x2BDF5C,msg,context)
                            expected_note=note
                            if enabled and source:
                                expected_note=(note+transpose)&255
                                if expected_note&128:expected_note=(expected_note-12)&255
                            expected_status=status-16 if status&0xF0==0x90 and velocity==0 else status
                            assert bytes(a.uc.mem_read(msg,4))==bytes([expected_status,expected_note,velocity,source])
                            assert events==[('note_on_path' if status&0xF0==0x90 else 'note_off_path',expected_note,velocity)]
                            assert actual==1;normal_cases+=1
    results['MIDI_note_normalization']=dict(cases=normal_cases,velocity_zero='90+n becomes 80+n; preprocess still selected using original status',
        transpose='if config+4 bit2 and source !=0: uint8(note + int8(transpose)); if bit7 set subtract12 once',
        limits='Synthetically covers every input note; extreme transformed values may be excluded by other layers')
    # Sound-system routes channel events to 0x1b4-byte channel records.
    system,channels,event=0x110E0000,0x110E1000,0x110E9000;forward=[];route_cases=0
    a.write(system+0x18,channels)
    a.stubs={0x26EC34:lambda m:forward.append((m.get('R0'),m.get('R1'))) or 0}
    for muted in [0,1]:
        a.write(system+0x2C,muted)
        for kind in [0,1,0xFFFFFFFF]:
            for status in range(128,240):
                forward.clear();a.write(event,kind,status,0)
                call(0x271500,system,event)
                allowed=kind==0 and (not muted or status&0xF0==0xC0)
                assert forward==([(channels+(status&15)*0x1B4,event+4)] if allowed else [])
                route_cases+=1
    results['sound_channel_routing']=dict(cases=route_cases,channels=16,channel_stride=436,
        inhibit_field='+0x2c; when nonzero only program-change family passes',event_kind_required=0)
    # Channel note bitmap, parity admission, enabled-timbre fanout and velocity-zero off.
    chan=channels;listbase=0x110F0000;timbres=0x110F1000;fanout=[];note_cases=0
    a.write(0xC1743270,system)
    a.write(chan+0xFC,listbase);a.write(chan+0x108,listbase+0x80)
    for i in range(3):
        a.write(listbase+12*i,listbase+12*(i+1),0,timbres+i*0x100)
        put8(timbres+i*0x100+0x28,i)
    a.write(listbase+36,listbase+36,0,0);a.write(listbase+0x80,0,0,0)
    a.stubs={0x274590:lambda m:fanout.append(('on',(m.get('R0')-timbres)//0x100)) or 0,
             0x2743E4:lambda m:fanout.append(('off',(m.get('R0')-timbres)//0x100)) or 0}
    for inhibit in [0,1]:
        a.write(system+0x2C,inhibit)
        for parity in range(4):
            put8(config+0x1354,parity)
            for enabled_mask in range(8):
                a.write(0xC04AE3A8,enabled_mask)
                for note in range(128):
                    for status,velocity in [(0x90,100),(0x90,0),(0x80,64)]:
                        fanout.clear();a.uc.mem_write(chan+0x118,b'\x00'*16 if velocity==100 else b'\xff'*16)
                        a.uc.mem_write(msg,bytes([status,note,velocity,8]))
                        call(0x26EC34,chan,msg)
                        admitted=not inhibit and (parity==0 or (note&1)==(0 if parity==1 else 1))
                        on=status==0x90 and velocity>0
                        expected=[('on',i) for i in range(3) if enabled_mask>>i&1] if on and admitted else []
                        if not on and not inhibit:expected=[('off',i) for i in range(3)]
                        assert fanout==expected,(inhibit,parity,enabled_mask,note,status,fanout)
                        bit=word(chan+0x118+(note//32)*4)>>(note%32)&1
                        assert bit==(int(admitted) if on else int(bool(inhibit)))
                        note_cases+=1
    results['channel_note_fanout']=dict(cases=note_cases,timbres_in_fixture=3,
        note_on='parity gate; set note bitmap; deliver only enabled timbres',
        note_off='clear note bitmap; deliver to all attached timbres, including disabled ones',
        velocity_zero='handled as note-off again at channel layer',
        parity_modes={'0':'all notes','1':'even notes','2':'odd notes','3':'odd notes'})
    # Pedal transitions in the channel body, including CC66's distinct damper branches.
    pedals=[];pedal_cases=0
    a.write(system+0x2C,0)
    a.stubs={0x26E744:lambda m:0,0x58E74:lambda m:0,
             0x272F68:lambda m:pedals.append(('damper_off',m.get('R0'))) or 0,
             0x272EF0:lambda m:pedals.append(('damper_on',m.get('R0'))) or 0,
             0x273008:lambda m:pedals.append(('sostenuto',m.get('R0'),m.get('R1'))) or 0}
    held=bytes.fromhex('01000080000001000000000000000080')
    old_latch=b'\xa5'*16
    for cc in [64,66]:
        for old in [0,63,64,79,80,127]:
            for new in range(128):
                for damper in ([0] if cc==64 else [0,63,64,79,80,127]):
                    pedals.clear();put8(chan+0xC2,damper);put8(chan+0x82+cc,old)
                    a.uc.mem_write(chan+0x118,held);a.uc.mem_write(chan+0x128,old_latch)
                    a.uc.mem_write(msg,bytes([0xB0,cc,new,1]))
                    call(0x26EC34,chan,msg)
                    expected=[];latch=old_latch
                    if cc==64:
                        kind='damper_off' if new<80 else ('damper_on' if old<80 else None)
                        if kind:expected=[(kind,timbres+i*0x100) for i in range(3)]
                    elif old>=64 and new<64:
                        latch=bytes(16);expected=[('sostenuto',timbres+i*0x100,0) for i in range(3)]
                    elif old<64 and new>=64:
                        latch=b'\xff'*16 if damper>=64 else held
                        if damper>=64:expected=[('sostenuto',timbres+i*0x100,1) for i in range(3)]
                    assert pedals==expected,(cc,old,new,damper,pedals,expected)
                    assert bytes(a.uc.mem_read(chan+0x128,16))==latch
                    assert a.uc.mem_read(chan+0x82+cc,1)[0]==new
                    pedal_cases+=1
    results['channel_pedals']=dict(cases=pedal_cases,damper_callback_threshold=80,
        damper_low_values='every value 0..79 invokes release callbacks, including repeated low values',
        sostenuto_threshold=64,sostenuto_on_damper_low='copy held-note bitmap; no immediate timbre callback',
        sostenuto_on_damper_high='set all 128 latch bits; invoke timbre callback with 1',
        sostenuto_off='clear latch bitmap and invoke timbre callback with 0',
        intercepted=['CC parameter propagation 0x26e744','UI notification 0x58e74','timbre pedal bodies'])
    # Original instructions across MIDI -> channel -> timbre -> virtual oscillator call.
    # Fixed polyphonic mode; manager entry is captured before sample/TG construction.
    timbre,meta,prog,oscbase,oscparams,osclist,empty,cs=(0x11110000,0x11111000,0x11112000,
        0x11114000,0x11116000,0x11117000,0x11117100,0x11118000)
    a.uc.mem_write(timbre,bytes(0x100));a.uc.mem_write(prog,bytes(0x1000))
    a.write(timbre+4,meta,prog);a.write(timbre+0x14,osclist);put8(timbre+0x28,0)
    a.write(listbase,listbase+12,0,timbre);a.write(listbase+12,0,0,0)
    a.write(empty,empty,empty,0);a.write(0xC0F55850,cs);a.write(cs+0x38,cs)
    for i in range(2):
        osc=oscbase+i*0x800
        a.uc.mem_write(osc,bytes(0x500));a.write(osc,BASE+0x470DE0)
        a.write(osc+8,oscparams);a.write(osc+0x48C,manager,empty)
        a.write(osc+0x49C,timbre)
        a.write(osclist+12*i,osclist+12*(i+1),0,osc)
    a.write(osclist+24,0,0,0)
    assert f.u32(0x470DE0+0x14)==BASE+0x1F62F0
    put8(config+4,0);put8(config+0x1354,0);a.write(0xC04AE3A8,1)
    a.write(system+0x2C,0);a.write(system+0x3C,0)
    allocations=[];priorities=[];integration_cases=0
    def capture_build(m):
        allocations.append((m.get('R0'),m.get('R1'),m.get('R2'),m.get('R3'),word(m.get('SP'))))
        return 0
    a.stubs={k:lambda m:0 for k in [0xD55B4,0xD58C0,0x324CC,0x274374,0x272824,
        0x2728A0,0x272CC0,0x54C74,0x273A00,0x1FED94,0x1FEDB8,0x1F5FE8,0x272BBC,0x1F61F8]}
    a.stubs.update({0x14D744:lambda m:1,0x2BDE4C:lambda m:1,0x2CD2AC:lambda m:3,
        0x2CD2A0:lambda m:priorities.append(m.get('R2')) or 0,0x1FDC8C:capture_build})
    for channel in [0,7,15]:
        target=channels+channel*0x1B4
        a.write(target+0xFC,listbase);a.write(target+0x108,empty)
        for selection in range(4):
            put8(meta+0x1C,selection<<2)
            for mode in [0,3]:
                put8(prog+0x508,mode)
                for key_low,key_high,vel_low,vel_high in [(0,127,1,127),(48,72,40,100)]:
                    for p,v in [(0x1F,key_low),(0x1E,key_high),(0x22,vel_low),(0x21,vel_high)]:put8(meta+p,v)
                    for note in [0,47,48,60,72,73,127]:
                        for velocity in [1,39,40,80,100,101,127]:
                            allocations.clear();priorities.clear();put16(timbre+0x46,0)
                            message=bytes([0x90+channel,note,velocity,1,0,0,0,0])
                            a.uc.mem_write(msg,message);call(0x2C1A6C,msg,context,count=20000)
                            accepted=key_low<=note<=key_high and vel_low<=velocity<=vel_high
                            selected=[i for i in range(2) if mode==3 or selection==0 or i==selection-1]
                            packed=int.from_bytes(message[:4],'little')
                            expected=[(manager,packed,oscbase+i*0x800,0,0xFFFFFFFF) for i in selected] if accepted else []
                            assert allocations==expected,(channel,selection,mode,note,velocity,allocations,expected)
                            assert priorities==([5,3] if accepted else [])
                            assert int.from_bytes(a.uc.mem_read(timbre+0x46,2),'little')==int(key_low<=note<=key_high)
                            integration_cases+=1
    results['MIDI_to_PCM_manager']=dict(cases=integration_cases,channels=[0,7,15],oscillators=2,
        entry='0x2c1a6c',captured_boundary='0x1fdc8c',virtual_slot='CPCMOsc address point 0x470de0 +0x14 -> 0x1f62f0',
        path=['0x2c1a6c','0x2bdf5c','0x2bdb7c','0x2bce90','0x271500','0x26ec34','0x274590','0x273d4c','0x2737f8','0x1f62f0','0x1fdc8c'],
        key_and_velocity_bounds='inclusive; key admission increments +0x46 before velocity admission',
        oscillator_selection='metadata +0x1c bits 2..3: 0 all, 1 first, 2 second, 3 third; program +0x508 low3=3 overrides to all',
        temporary_task_priority=[5,3],limitations='Fixed polyphonic branch and admitted preprocessing; pitch/side effects intercepted; manager returns no voice')
    # 48 software callback slots. Counts are loop visits; wall time is not assumed.
    sync,slots=0x11100000,0x11101000
    a.uc.mem_write(sync,bytes(0x200));a.uc.mem_write(slots,bytes(48*24))
    for i in range(48):a.write(sync+8+i*4,slots+i*24)
    a.write(0xC1B554C4,0x7FFFFFFE)
    a.stubs={};timer_alloc=[]
    for i in range(48):
        delay=i
        p=call(0x2B4C04,sync,delay,BASE+0x2C8808,0x12340000+i)
        assert p==slots+i*24 and word(p+4)==(delay+1)//2
        assert word(p+8)==0x12340000+i and word(p+12)==BASE+0x2C8808 and word(p+20)==1
        assert word(p+16)==(0x7FFFFFFF+i)&0x7FFFFFFF
        timer_alloc.append(word(p+16))
    assert call(0x2B4C04,sync,1,0,0)==0
    call(0x2B4C88,sync,slots+3*24)
    assert word(slots+3*24+20)==0 and word(slots+3*24+16)==0xFFFFFFFF
    assert call(0x2B4C04,sync,10,0,0)==slots+3*24
    for n in [0,1,2,3,48,1000]:
        a.write(slots+4,n)
        for visit in range(max(n,1)+2):
            assert call(0x2B4AA8,slots)==int(n>0 and visit==n-1)
    # Execute actual timer sweep; only generic iterator plumbing is replaced.
    for i,n in enumerate([0,1,2]):a.write(slots+i*24,0,n,0xCA00+i,BASE+0x2C8808,0xD000+i,1)
    a.write(sync+4,0x11104000)
    remaining=iter([slots,slots+24,slots+48,0]);sweep=[]
    def callback(m):
        assert word(slots+24+20)==0 and word(slots+24+16)==0xFFFFFFFF
        sweep.append(('callback',m.get('R0'),m.get('R1')));return 0
    a.stubs={0x2DC184:lambda m:0,0x2DC1BC:lambda m:0,
             0x029F14:lambda m:0,0x029FB0:lambda m:next(remaining),
             0x029FE0:lambda m:0,0x029F94:lambda m:0,
             0x029228:lambda m:sweep.append(('remove',m.get('R1'))) or 0,
             0x2C8808:callback}
    call(0x2B50CC,sync)
    assert sweep==[('remove',slots+24),('callback',0xD001,0xCA01)]
    assert word(slots+48+4)==1 and word(slots+20)==1
    results['CSync_callback_timers']=dict(slots=48,record_bytes=24,
        fields={'+4':'remaining visits','+8':'callback user argument','+c':'callback pointer','+10':'token','+14':'in-use'},
        count_conversion='uint32(delay+1)>>1',token_wrap_examples=timer_alloc[:4],
        zero_count='never expires through countdown helper',pool_exhaustion_returns=0,
        callback_order='unlink, release slot, invoke callback(token,user_arg)',
        countdown_visits_checked=sum(max(n,1)+2 for n in [0,1,2,3,48,1000]))
    save('arm-check.json',dict(passed=True,firmware_sha256=FW_SHA,tool_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),results=results,
        device_access=False,limits=['Synthetic RAM only','No OS startup, device, IRQ body or real audio executed',
        'Voice reset 0x1f8bf8 intercepted; downstream note processors intercepted',
        'Class numbers are recovered internal allocation classes; musical meaning awaits callers']))
    print(json.dumps(dict(passed=True,groups=list(results),MIDI_note_cases=normal_cases),indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-arm',action='store_true');args=parser.parse_args()
    f=Firmware();static(f)
    if args.verify_arm:verify(f)
    else:print(OUT)
if __name__=='__main__':main()
