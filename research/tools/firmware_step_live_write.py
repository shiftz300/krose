#!/usr/bin/env python3
"""Original parameter service and step edit callbacks writing real RAM fields."""
import argparse,hashlib,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();a=Arm(f);app,root,manager,context=0x11000000,0x11000100,0x11000200,0x11000300
    a.write(app+0x18,root);a.write(root+0xC,manager);a.write(root+0x1C,0x11000400)
    a.write(manager+0x10,context);a.write(manager+0x14,0);a.write(0xC0F55850,root);a.write(0xC0F558C0,0)
    a.write(0xC13F948C,0);a.write(0xC1439604,0)
    arena=0x11080000;notices=[]
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def allocate(m):
        nonlocal arena
        size=m.get('R0');ptr=arena;arena+=(size+15)&~15;assert arena<0x11100000
        a.uc.mem_write(ptr,bytes(size));return ptr
    def zero(m):return 0
    a.stubs={0x2DC184:zero,0x2DC1BC:zero,0x14E730:allocate,0x14E760:zero,0x2C4474:zero,
             0x2CD184:lambda m:w(0xC04AEDBC),0x262678:zero,0x324CC:zero,0x208B68:zero,
             0x205818:zero,0x345AC:zero,0x2096FC:lambda m:notices.append([m.get('R1'),m.get('R2'),m.get('R3')]) or 0}
    def entry(group,index):
        table=f.pointer(0x407BD0+group*4);entries=f.pointer(table+4);return f.pointer(entries+4*index)
    def target(group,index):return f.u32(entry(group,index))
    cases=[]
    for group in [8,43,107]:
        pattern=target(group,26)-42
        for step in range(64):
            for callback,shadow,offset,olds,news in [(0x1E0968,243,26,[1,64,128],[1,64,127,128]),(0x1E0A20,244,28,[0,1],[0,1])]:
                for old in olds:
                    for new in news:
                        arena=0x11080000;notices.clear();field=offset+3*step;ptr=target(group,field)
                        assert ptr==pattern+40+8*step+(2 if shadow==243 else 6)
                        before=bytearray([0xA5]*552);before[ptr-pattern]=old
                        a.uc.mem_write(pattern,bytes(before))
                        a.uc.mem_write(target(group,242),bytes([step]));a.uc.mem_write(target(group,shadow),bytes([new]))
                        # The original notification adapter builds the operation-8
                        # context and resolves the descriptor callback itself.
                        a.call(0x205B6C,root,group,shadow,14,stack=(old,new))
                        expect=before.copy();expect[ptr-pattern]=new
                        assert bytes(a.uc.mem_read(pattern,552))==bytes(expect),(group,step,shadow,old,new)
                        assert notices==([[group,field,new]] if new!=old else [])
                        cases.append(dict(group=group,step=step,shadow=shadow,old=old,new=new,target=hex(ptr)))
    # A raw parameter set updates only the shadow; the commit stage is explicit.
    arena=0x11080000;notices.clear();group=8;ptr=target(group,26)
    a.uc.mem_write(ptr,b'\x40');a.uc.mem_write(target(group,242),b'\0');a.uc.mem_write(target(group,243),b'\x40')
    a.call(0x209894,manager,group,243,99,stack=(0,))
    assert a.uc.mem_read(ptr,1)==b'\x40' and a.uc.mem_read(target(group,243),1)==b'\x63'
    a.call(0x205B6C,root,group,243,14,stack=(64,99));assert a.uc.mem_read(ptr,1)==b'\x63'

    # Retain the real song-sync callback for the Sequencer's embedded Pattern.
    # Compare both the complete live Pattern and the complete private song buffer.
    del a.stubs[0x262678]
    cache,song=0x11040000,0x11050000
    a.write(0xC1690248,cache);a.uc.mem_write(0xC1747538+0x208,b'\x07')
    a.write(0xC1747538+8+7*4,song)
    song_cases=[];group=107;pattern=target(group,26)-42
    import itertools
    for step,shadow,present,playing,override,suppress,equal in itertools.product(range(64),[243,244],range(2),range(2),range(2),range(2),range(2)):
        arena=0x11080000;notices.clear()
        field=(26 if shadow==243 else 28)+3*step;ptr=target(group,field)
        old=64 if shadow==243 else 0;new=old if equal else (99 if shadow==243 else 1)
        live=bytearray([0xA5]*552);live[ptr-pattern]=old
        saved=bytearray([0x5A]*0x800);relative=ptr-0xC17456AC;saved[relative]=old
        a.uc.mem_write(pattern,bytes(live));a.uc.mem_write(song,bytes(saved))
        a.uc.mem_write(cache,bytes(0x2224))
        if present:a.write(cache+32*(group-100)+4*(field//32),1<<(field%32))
        a.uc.mem_write(0xC171D516,struct.pack('<H',playing));a.write(0xC17146B4+0x14,override)
        a.write(0xC171C4C4,suppress)
        a.uc.mem_write(target(group,242),bytes([step]));a.uc.mem_write(target(group,shadow),bytes([old]))
        a.call(0x209894,manager,group,shadow,new,stack=(0,))
        assert bytes(a.uc.mem_read(pattern,552))==bytes(live)
        assert bytes(a.uc.mem_read(song,0x800))==bytes(saved)
        a.call(0x205B6C,root,group,shadow,14,stack=(old,new))
        live[ptr-pattern]=new
        mirrored=not equal and not present and (not playing or bool(override)) and not suppress
        if mirrored:saved[relative]=new
        assert bytes(a.uc.mem_read(pattern,552))==bytes(live),(step,shadow,'live')
        assert bytes(a.uc.mem_read(song,0x800))==bytes(saved),(step,shadow,present,playing,override,suppress,equal)
        song_cases.append(dict(step=step,shadow=shadow,field=field,present=present,playing=playing,override=override,suppress=suppress,equal=equal,song_copy=bool(mirrored)))

    # Run the application record processor and its generated change list through
    # the original commit traversal. Only list storage and message handoff are
    # supplied at boundaries; old/new contexts and descriptor calls stay original.
    record,changes,packet=0x11002000,0x11003000,0x11004000
    appended=[];iterators={};handoffs=[]
    def append(m):appended.append(m.get('R1'));return 0
    def begin(m):iterators[m.get('R0')]=iter(appended.copy());return 0
    def next_item(m):return next(iterators[m.get('R0')],0)
    def handoff(m):
        p=w(m.get('R1'));assert m.get('R2')==13
        assert bytes(a.uc.mem_read(p+4,6))==b'\x09\0\0\0\x0c\0'
        assert w(w(p+12))==changes
        handoffs.append(13);return 0
    a.write(manager+0x10,root)
    a.stubs.update({0x29084:append,0x29F14:begin,0x29FE0:next_item,0x29F94:zero,
                    0x2CD594:lambda m:packet,0x205AC0:handoff,0x2CD694:zero})
    integrated=[]
    for group,step,shadow in itertools.product([8,43,107],[0,63],[243,244]):
        arena=0x11080000;appended.clear();iterators.clear();handoffs.clear();notices.clear()
        pattern=target(group,26)-42;field=(26 if shadow==243 else 28)+3*step;ptr=target(group,field)
        old=64 if shadow==243 else 0;new=99 if shadow==243 else 1
        live=bytearray([0xA5]*552);live[ptr-pattern]=old
        a.uc.mem_write(pattern,bytes(live));a.uc.mem_write(target(group,242),bytes([step]))
        a.uc.mem_write(target(group,shadow),bytes([old]));a.uc.mem_write(cache,bytes(0x2224))
        a.uc.mem_write(0xC171D516,b'\0\0');a.write(0xC171C4C4,0)
        a.uc.mem_write(packet,bytes(16))
        a.uc.mem_write(record,struct.pack('<IHHIBBxx',0,group,shadow,new,14,0))
        a.call(0x39BD8,app,changes,record)
        assert len(appended)==1 and a.uc.mem_read(target(group,shadow),1)[0]==new
        assert bytes(a.uc.mem_read(pattern,552))==bytes(live)
        generated=list(struct.unpack('<IHHIIII',a.uc.mem_read(appended[0],24)))
        assert generated==[0xC04714B4,group,shadow,14,new,old,0]
        a.call(0x207C00,manager,changes)
        live[ptr-pattern]=new
        assert bytes(a.uc.mem_read(pattern,552))==bytes(live)
        assert handoffs==[13] and notices==[[group,field,new]]
        assert w(0xC171C4C4)==0
        integrated.append(dict(group=group,step=step,shadow=shadow,field=field,old=old,new=new,change_record=generated,message_command=13))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        cases=cases,song_cases=song_cases,integrated=integrated,two_stage=dict(initial=64,shadow_after_set=99,field_after_set=64,field_after_commit=99),
        boundaries=['Original notification adapter 0x205B6C resolves descriptors and builds operation-8 contexts; edit callback, nested setter 0x209894, data writer and readback execute',
                    'All three mode groups and 64 steps compare complete 552-byte buffers for exactly the intended byte change',
                    'Song cases execute original hook 0x262678 and compare a controlled 2048-byte song buffer, including all 64 steps and both fields',
                    'Integrated cases execute application processor 0x39BD8 and generated 24-byte records through commit traversal 0x207C00',
                    'Heap, exception registration, clock, cache/display/secondary notifications intercepted; song-sync is intercepted only in the first 3072 cases',
                    'List storage/iteration and outgoing message handoff are modeled; incoming OS/MMI delivery, song file load/save, recorded note events and audio remain outside this check'])
    (OUT/'step-live-write-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(cases),song_cases=len(song_cases),integrated=len(integrated),two_stage=result['two_stage']),indent=2))
if __name__=='__main__':main()
