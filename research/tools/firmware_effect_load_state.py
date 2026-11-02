#!/usr/bin/env python3
"""Native effect-loader allocation, tail clearing and buffered upload state."""
import argparse,contextlib,hashlib,io,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,BASE,FW_SHA
from firmware_hall_operands import visible,storage
from firmware_inspect import inspect
from firmware_voice_lfo import OUT
from layout import PRODUCT_ROOT as ROOT

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
class Rig:
    def __init__(self,f):
        self.f=f;self.a=Arm(f);self.ctx=0x11008000;self.obj=0x11009000
        self.cb=0xC0FE9DC8;self.pb=0xC0FEB1C8;self.selected=None;self.units_seen=[]
        self.a.stubs.update({0x132690:self.write,0x1326B4:lambda a:0})
        from unicorn import UC_HOOK_CODE
        self.a.uc.hook_add(UC_HOOK_CODE,self.entry,begin=BASE+0x5C724,end=BASE+0x5C748)
        self.a.uc.hook_add(UC_HOOK_CODE,self.loader,begin=BASE+0x5A51C,end=BASE+0x5A51C)
    def entry(self,uc,address,size,user):
        if address==BASE+0x5C724:
            assert self.selected is not None
            self.a.set('R5',self.obj);self.a.set('R8',BASE+self.selected['definition_offset'])
        elif address==BASE+0x5C748:self.a.set('PC',0x10000000)
    def loader(self,uc,address,size,user):self.units_seen.append(self.a.get('R2'))
    def write(self,a):
        off=a.get('R0')-0x60000000;v=a.get('R1')&65535;self.writes.append((off,v))
        if off==0x700:self.pi=v;self.ps=[]
        elif off==0x718:self.hi=v
        elif off==0x714:self.mid=v
        elif off==0x710:self.ps.append((self.hi<<32)|(self.mid<<16)|v)
        elif off==0x708:
            assert v==1 and 0<len(self.ps)<=16
            self.program[self.pi:self.pi+len(self.ps)]=self.ps
            self.packets.append(dict(kind='program',start=self.pi,count=len(self.ps)))
        elif off==0x720:self.ci=v;self.cs=[]
        elif off==0x73C:self.chi=v
        elif off==0x738:self.cs.append((self.chi<<16)|v)
        elif off==0x728:
            assert v==1 and 0<len(self.cs)<=32
            self.constants[self.ci:self.ci+len(self.cs)]=self.cs
            self.packets.append(dict(kind='constant',start=self.ci,count=len(self.cs)))
        else:raise AssertionError(hex(off))
        return 0
    def seed(self,seed):
        self.raw_constants=[(0x91000000+0x10203*i+seed*0x10101)&0xFFFFFFFF for i in range(640)]
        self.raw_program=b''.join(struct.pack('<II',((i*17+seed)&65535)|0xA55A0000,(0x12345678+i*0x10203+seed)&0xFFFFFFFF) for i in range(1024))
        self.a.uc.mem_write(self.cb,struct.pack('<640I',*self.raw_constants));self.a.uc.mem_write(self.pb,self.raw_program)
        self.a.uc.mem_write(self.ctx,b'\0'*12+b'CANARY!!');self.a.uc.mem_write(self.obj,bytes(0x400));self.a.write(self.obj+0x37C,self.ctx)
        self.program=visible(self.raw_program);self.constants=list(self.raw_constants);self.writes=[];self.packets=[];self.units_seen=[]
    def load(self,e,slot,buffered):
        units=1+int(e['code_words_64']>124);n=e['code_words_64'];k=e['constant_words_32'];assert 0<n<=124*units and k<=80*units
        raw=self.f.data[e['code_offset']:e['code_offset']+8*n];initial=list(struct.unpack_from('<'+'I'*k,self.f.data,e['constants_offset']))
        cb=80*slot;pc=32+124*slot
        want_cpu_c=bytearray(self.a.uc.mem_read(self.cb,2560));want_cpu_p=bytearray(self.a.uc.mem_read(self.pb,8192))
        want_cpu_c[cb*4:(cb+80*units)*4]=struct.pack('<'+'I'*(80*units),*(initial+[0]*(80*units-k)))
        want_cpu_p[pc*8:(pc+n)*8]=raw
        want_c=list(self.constants);want_p=list(self.program);want_c[cb:cb+80*units]=initial+[0]*(80*units-k);want_p[pc:pc+n]=visible(raw)
        self.writes.clear();self.packets.clear();self.units_seen.clear()
        self.a.call(0x5A360,self.ctx)
        if buffered:self.a.call(0x5A63C,self.ctx,1)
        self.a.uc.mem_write(self.obj+0x386,struct.pack('<h',slot));self.selected=e;self.a.call(0x5C724);self.selected=None
        assert self.units_seen==[units]
        assert bytes(self.a.uc.mem_read(self.cb,2560))==want_cpu_c
        assert bytes(self.a.uc.mem_read(self.pb,8192))==want_cpu_p
        state=bytes(self.a.uc.mem_read(self.ctx,12));phases=[]
        if buffered:
            assert not self.writes and (self.constants,self.program)!=(want_c,want_p)
            assert struct.unpack('<BB5h',state)==(1,1,slot,0,n-1,0,80*units-1)
            self.a.call(0x5A7E4,self.ctx,0)
            assert self.constants==want_c and all(x['kind']=='constant' for x in self.packets)
            phases.append(dict(name='constant_flush',packets=len(self.packets),context=bytes(self.a.uc.mem_read(self.ctx,12)).hex()))
            self.a.call(0x5A728,self.ctx,1)
            assert bytes(self.a.uc.mem_read(self.ctx,2))==b'\0\0'
            phases.append(dict(name='program_commit',packets=len(self.packets),context=bytes(self.a.uc.mem_read(self.ctx,12)).hex()))
        assert self.constants==want_c and self.program==want_p
        assert bytes(self.a.uc.mem_read(self.ctx+12,8))==b'CANARY!!'
        p_packets=[x for x in self.packets if x['kind']=='program'];c_packets=[x for x in self.packets if x['kind']=='constant']
        assert p_packets==[dict(kind='program',start=pc+i,count=min(16,n-i)) for i in range(0,n,16)]
        assert c_packets==[dict(kind='constant',start=cb+i,count=min(32,80*units-i)) for i in range(0,80*units,32)]
        return dict(effect=e['id'],slot=slot,buffered=buffered,units=units,code_count=n,initial_count=k,zero_tail=80*units-k,
            context_before_flush=state.hex(),phases=phases,packets=list(self.packets),writes_sha256=digest(json.dumps(self.writes).encode()),
            cpu_constants_sha256=digest(bytes(want_cpu_c)),cpu_program_container_sha256=digest(bytes(want_cpu_p)),
            uploaded_constants_sha256=digest(struct.pack('<640I',*self.constants)),uploaded_visible_program_sha256=digest(storage(self.program)))

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args()
    if not args.verify_arm:return
    f=Firmware();r=Rig(f);rows=[];excluded=[]
    effects=[f.effect(i) for i in ([7] if args.smoke else range(135))]
    for e in effects:
        if e['code_words_64']==0:excluded.append(dict(effect=e['id'],name=e['name'],reason='zero-length code; specialized variant loading not established by this block'));continue
        units=1+int(e['code_words_64']>124)
        for slot in ([0] if args.smoke else (list(range(7)) if units==1 else [0,1,2,3,5])):
            for buffered in [False,True]:
                r.seed(19+slot+e['id']);rows.append(r.load(e,slot,buffered))
    sequences=[]
    for slot in ([0] if args.smoke else range(7)):
        r.seed(201+slot);steps=[]
        for index in [105,7,0]:
            row=r.load(f.effect(index),slot,True)
            assert r.constants[80*slot+50:80*slot+52]==[0,0] if index in [7,0] else True
            steps.append(row)
        sequences.append(dict(slot=slot,steps=steps,eq_a50_a51=[0,0],empty_tail_zero=True))
    for name,lo,hi in [('effect-load-state',0x5A51C,0x5A83C),('effect-load-allocation',0x5C6B4,0x5C748)]:
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(stream.getvalue())
    result=dict(passed=True,smoke_only=args.smoke,firmware_sha256=FW_SHA,device_access=False,actual_DSP_audio_executed=False,
        tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={n:sha(ROOT/'research/tools'/n) for n in ['firmware_hall_operands.py','firmware_inspect.py','firmware_voice_lfo.py']},
        inputs=[dict(path=str((OUT/n).relative_to(ROOT)),sha256=sha(OUT/n)) for n in ['eq-b2-program-check.json','effect-routing-check.json']],
        counts=dict(effects=len({x['effect'] for x in rows}),single_effects=len({x['effect'] for x in rows if x['units']==1}),double_effects=len({x['effect'] for x in rows if x['units']==2}),
            loads=len(rows),sequences=len(sequences),sequence_loads=3*len(sequences),excluded_zero_code=len(excluded)),rows=rows,sequences=sequences,excluded=excluded,
        boundaries=['Original selector block5C724..5C744 chooses1/2 units from code_count<=124; entry registers supply an isolated caller frame and execution stops at5C748 before parameter/UI work',
            'Original5A51C copies program and initial constants, zeroes unused words through80*units, and either uploads immediately or marks full ranges. Entire640-word CPU constant buffer and1024-item program container compare, including adjacent slots and untouched code tails',
            'Bus endpoint records16-bit writes and ready reads. Transport mirror reconstructs actual packets; it does not execute DSP math, read hardware, or determine data-RAM clearing and internal audio state',
            'Buffered path uses original begin5A63C(flag1), constants flush5A7E4(flag0), then program commit5A728(flag1). Original packet boundaries are16 code items and32 constant words',
            'Hall->EQ->NoEffect sequences verify bank clearing from nonzero sentinels. A50/51 are uploaded aszero after EQ load, but their runtime role, updates and smoothing time remain unknown',
            'Thirteen zero-code variants are excluded; double effects check starts0..3 and5(MFX1), single effects0..6. This is the loader/commit block, not full running effect replacement or audible switch acceptance'])
    (OUT/('effect-load-state-smoke.json' if args.smoke else 'effect-load-state-check.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,counts=result['counts'])))
if __name__=='__main__':main()
