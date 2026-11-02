#!/usr/bin/env python3
"""Run original effect routing/control paths with TG I/O captured in private RAM."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from collections import Counter
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
PRELOAD=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
IFX,MFX,CHAIN=0xC0FEF65C,0xC0FEF714,0xC0FEF700
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def gain(v):return 258*v+(v>63)
def packed(v,old):return gain(v)|((85 if v>old else -85)&65535)<<16
def physical(layout,i):return -1 if layout[i]==0 else i+(layout[i]==2)
def layout_for(f,ids):
    result=[]
    for effect in ids:result.append(0 if result and result[-1]==2 else 1+(f.effect(effect)['code_words_64']>124))
    return result

class RoutingRig:
    def __init__(self,f):
        self.a=Arm(f);self.writes=[];self.setups=[]
        self.manager,self.si,self.sm,self.raw=0x11000000,0x11000100,0x11000120,0x11002000
        self.objects=0x11004000
        self.a.write(0xC0FE9DC0,self.manager)
        self.a.write(self.manager+4,self.raw+0x194,self.raw+0x18,0x11000200,0x11000220)
        self.a.write(self.manager+0x1c,self.si,self.sm,5,2,0,5,2,0)
        for i in range(7):self.a.write(0x11000200+4*i,self.objects+0x400*i)
        # MFX pointer array is separate from the IFX array.
        for i in range(2):self.a.write(0x11000220+4*i,self.objects+0x400*(i+5))
        def write(a):
            address,value=a.get('R0'),a.get('R1')
            assert 0x60000400<=address<0x60000700,hex(address)
            self.writes.append([address-0x60000000,value]);return 0
        self.a.stubs[0x132690]=write
        self.a.stubs[0x1326B4]=lambda a:0
    def bytes(self,p,n):return bytes(self.a.uc.mem_read(p,n))
    def reset(self,layout=(1,1,1,1,1),master=(1,1)):
        self.a.uc.mem_write(self.si,bytes(layout));self.a.uc.mem_write(self.sm,bytes(master))
        self.a.uc.mem_write(IFX,bytes(0xB0));self.a.uc.mem_write(CHAIN,bytes(20));self.a.uc.mem_write(MFX,bytes(40))
        self.a.uc.mem_write(self.raw,bytes(2140))
        for i in range(5):self.a.write(IFX+0x7c+4*i,self.raw+0x18+76*i)
        self.a.call(0x5CF50,IFX);self.a.call(0x5E660,MFX);self.writes.clear()
    def slot(self,i,chain,target,bus,pan,send1,send2):
        p=self.raw+0x18+76*i
        self.a.uc.mem_write(p+0x40,bytes([7,64|(chain<<7),target,0,pan,bus,send1,send2]))
        return p
    def batch_master(self):
        self.a.uc.mem_write(MFX+0x20,b'\x08');self.a.call(0x5E6B0,MFX)
    def factory(self,record):
        self.reset();self.a.uc.mem_write(self.raw,record);self.setups.clear()
        def setup(a):
            size,effect,payload,enabled,channel=struct.unpack('<5I',self.bytes(a.get('SP'),20))
            self.setups.append(dict(logical=a.get('R2'),physical=struct.unpack('<i',struct.pack('<I',a.get('R3')))[0],
                size=size,effect=effect,payload=payload-self.raw,enabled=enabled,channel=channel))
            return 0
        self.a.stubs.update({0x55830:lambda a:0,0x170230:lambda a:777,0x1702BC:lambda a:778,0x5CC7C:setup})
        # Reset original effect objects, allocate slot widths and normalize chain
        # targets in original code; resource release/getter/setup are boundaries.
        self.a.call(0x59EB8,self.manager,2);self.a.call(0x58854,self.manager,2)
        for p in [0x55830,0x170230,0x1702BC,0x5CC7C]:del self.a.stubs[p]
        return self.bytes(self.si,5),self.bytes(self.sm,2)

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('effects-ifx-routing',0x5CE48,0x5D8F0),('effects-mfx-routing',0x5E610,0x5E884),
                       ('effects-layout',0x59E64,0x5A094),('effects-route-gains',0x12DF24,0x12E168)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    r=RoutingRig(f);a=r.a;r.reset();gain_cases=[];pan_cases=[]
    for value in range(128):
        assert a.call(0x12C4C0,value)==gain(value)
        for old in [0,64,127]:
            r.writes.clear();a.call(0x12C894,0x60000000,0x5A8,3,value,stack=(old,))
            expected=[] if old==value else [[0x5B4,packed(value,old)]]
            assert r.writes==expected,(value,old,r.writes,expected)
            gain_cases.append(dict(value=value,old=old,writes=r.writes.copy()))
        # Original pan translates raw position to two 16-bit control targets.
        a.call(0x12DF24,value,0x11001000,0x11001002)
        targets=list(struct.unpack('<HH',r.bytes(0x11001000,4)))
        expect=[0,2*max(0,value-1)*256+256] if value<=64 else [(2*value-127)*256,0x7F00]
        assert targets==expect,(value,targets,expect)
        old=127-value;r.writes.clear();a.call(0x12DFA0,0x60000000,2,value,old)
        step=43 if value>old else -43
        assert r.writes==[[off,target|((step&65535)<<16)] for off,target in zip([0x5EC,0x600],targets)]
        pan_cases.append(dict(value=value,targets=targets,writes=r.writes.copy()))
    layouts=[[1]*5,[0]*5,[2,0,1,1,1],[1,2,0,1,1],[1,1,1,2,0]];ifx=[]
    for layout in layouts:
        r.reset(layout)
        for i,chain,bus,level in itertools.product(range(5),range(2),range(16),[0,1,64,127]):
            physical_slot=physical(layout,i);target=min(i+1,4)+1;pan=127-level
            payload=r.slot(i,chain,target,bus,pan,level,127-level)
            effective=bool(i!=4 and chain and layout[target-1])
            assert a.call(0x5CF08,payload,i)==effective
            a.uc.mem_write(payload+0x41,bytes([chain<<7]))
            assert a.call(0x5CF08,payload,i)==effective
            a.uc.mem_write(payload+0x41,bytes([64|(chain<<7)]))
            a.call(0x5D574,IFX,i,pan);a.call(0x5D4E4,IFX,i,level);a.call(0x5D454,IFX,i,127-level)
            a.call(0x5D5F4,IFX,i,int(effective),bus)
            assert r.bytes(IFX+0x90+4*i,3)==bytes([pan,level,127-level])
            if physical_slot>=0:
                sends_allowed=not(effective and physical_slot!=4) and bus<=7
                expected=[pan,level if sends_allowed else 0,127-level if sends_allowed else 0,
                          127 if bus!=7 and (not effective or physical_slot==4) else 0]
                actual=list(r.bytes(IFX+24*physical_slot,4));assert actual==expected,(layout,i,chain,bus,level,actual,expected)
            else:actual=None
            ifx.append(dict(layout=layout,slot=i,physical=physical_slot,chain=chain,target=target,bus=bus,level=level,targets=actual))
    masters=[]
    for layout,flags,level,returns in itertools.product([[1,1],[2,0],[0,1]],range(4),[0,1,64,127],[(0,127),(101,101)]):
        r.reset(master=layout);a.uc.mem_write(r.raw+0x21C,bytes([*returns,flags,level]));a.call(0x5E81C,MFX,r.raw+0x194)
        expected_returns=[0,0]
        for i,v in enumerate(returns):
            slot=physical(layout,i)
            if slot>=0:expected_returns[slot]=v
        expected_cross=[0,0]
        if flags&2 and layout[0]!=2:expected_cross[0 if flags&1 else 1]=level
        actual=[r.bytes(MFX+i*16,2) for i in range(2)]
        assert [v[0] for v in actual]==expected_returns and [v[1] for v in actual]==expected_cross
        r.writes.clear();r.batch_master()
        expected=[[0x61C+4*i,packed(v,0)] for i,v in enumerate(expected_returns) if v]
        # Both cross-send entries use the same base/register in this original
        # initializer; do not infer distinct physical audio buses from them.
        expected += [[0x614,packed(v,0)] for v in expected_cross if v]
        assert r.writes==expected,(layout,flags,level,returns,r.writes,expected)
        masters.append(dict(layout=layout,flags=flags,level=level,returns=expected_returns,cross=expected_cross,writes=r.writes.copy()))
    transitions=[]
    for old_flags,new_flags in [(3,2),(2,3),(3,0),(0,3)]:
        r.reset();a.uc.mem_write(r.raw+0x21C,bytes([101,101,old_flags,127]));a.call(0x5E81C,MFX,r.raw+0x194);r.batch_master()
        a.uc.mem_write(r.raw+0x21E,bytes([new_flags]));a.call(0x5E81C,MFX,r.raw+0x194)
        batches=[]
        for _ in range(2):
            r.writes.clear();r.batch_master();cached=[r.bytes(MFX+5+16*i,1)[0] for i in range(2)]
            assert not(cached[0] and cached[1]);batches.append(dict(cached=cached,writes=r.writes.copy()))
        target=[127,0] if new_flags==3 else [0,127] if new_flags==2 else [0,0]
        expected_cache=([[0,127],[0,127]] if (old_flags,new_flags)==(3,2) else
                        [[0,0],[127,0]] if (old_flags,new_flags)==(2,3) else
                        [[0,0],[0,0]] if new_flags==0 else [[127,0],[127,0]])
        expected_writes=([[[0x614,packed(0,127)],[0x614,packed(127,0)]],[]] if (old_flags,new_flags)==(3,2) else
                         [[[0x614,packed(0,127)]],[[0x614,packed(127,0)]]] if (old_flags,new_flags)==(2,3) else
                         [[[0x614,packed(0,127)]],[]] if new_flags==0 else [[[0x614,packed(127,0)]],[]])
        assert [b['cached'] for b in batches]==expected_cache
        assert [b['writes'] for b in batches]==expected_writes
        assert batches[-1]['cached']==target
        transitions.append(dict(old_flags=old_flags,new_flags=new_flags,batches=batches))
    # IFX: zero the previous send legs before applying/changing a chain.
    r.reset();r.slot(0,0,2,0,64,101,79);a.call(0x5D794,IFX,0,2);a.call(0x5D128,IFX,1)
    ifx_transitions=[]
    for enabled,target in [(1,2),(1,4),(0,4)]:
        r.slot(0,enabled,target,0,64,101,79);a.call(0x5D794,IFX,0,target);batches=[]
        for _ in range(3):
            r.writes.clear();a.call(0x5D128,IFX,1)
            batches.append(dict(writes=r.writes.copy(),cached=list(r.bytes(IFX+8,6)),chain=list(r.bytes(CHAIN+10,2))))
        if enabled:
            assert batches[-1]['chain']==[target-2,127]
            expected_writes=[[[0x5A8,packed(0,101 if target==2 else 127)],
                              [0x5BC,packed(0,79 if target==2 else 127)]]+
                             ([[0x594,packed(0,127)]] if target==2 else []),
                             [[0x4A0,0 if target==2 else 1],[0x5BC,packed(127,0)]],[]]
        else:
            assert batches[-1]['chain'][1]==0
            expected_writes=[[[0x5A8,packed(0,127)],[0x5BC,packed(0,127)],[0x594,packed(127,0)]],
                             [[0x480,3],[0x4A0,2],[0x5A8,packed(101,0)],[0x5BC,packed(79,0)]],[]]
        assert [b['writes'] for b in batches]==expected_writes
        ifx_transitions.append(dict(enabled=enabled,target=target,batches=batches))
    # Eight ordinary visits defer the batch; the ninth commits it.
    r.reset();r.slot(0,0,2,0,64,101,79);a.call(0x5D794,IFX,0,2);r.writes.clear()
    for _ in range(8):a.call(0x5D128,IFX,0);assert not r.writes
    a.call(0x5D128,IFX,0);assert r.writes==[[0x5A8,packed(101,0)],[0x5BC,packed(79,0)],[0x594,packed(127,0)]]
    ifx_batch=r.writes.copy()
    r.reset();a.uc.mem_write(r.raw+0x21C,bytes([101,79,0,127]));a.call(0x5E81C,MFX,r.raw+0x194);r.writes.clear()
    for _ in range(8):a.call(0x5E6B0,MFX);assert not r.writes
    a.call(0x5E6B0,MFX);assert r.writes==[[0x61C,packed(101,0)],[0x620,packed(79,0)]]
    mfx_batch=r.writes.copy()
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory=[];enabled_count=Counter();layout_counts=Counter()
    for index in range(768):
        offset=0x1EF220+2140*index;record=raw[offset:offset+2140];si,sm=r.factory(record)
        ids=[record[0x18+76*i+64] for i in range(5)]+[record[0x194+68*i+64] for i in range(2)]
        assert list(si)==layout_for(f,ids[:5]) and list(sm)==layout_for(f,ids[5:]),(index,list(si),list(sm),ids)
        assert len(r.setups)==7
        for setup,i in zip(r.setups,range(7)):
            layout=si if i<5 else sm;logical=i if i<5 else i-5
            payload=0x18+76*i if i<5 else 0x194+68*logical
            assert setup==dict(logical=logical,physical=i if layout[logical] else -1,size=layout[logical],
                               effect=ids[i],payload=payload,enabled=(record[payload+65]>>6)&1,channel=record[payload+65]&63)
        slots=[]
        for i in range(5):
            header=0x18+76*i+64;p=r.raw+header;original_target=record[header+2]&15
            target=6 if i==4 else min(5,max(i+2,original_target))
            assert r.bytes(p+2,1)[0]==target
            slot=physical(si,i);effective=bool(i!=4 and record[header+1]&128 and si[target-1])
            bus=record[header+5]&15
            if slot>=0:
                # Full refresh maps legacy output values 1..6 to Off (7).
                expected=[record[header+4],record[header+6] if not effective or slot==4 else 0,
                          record[header+7] if not effective or slot==4 else 0,
                          127 if bus not in range(1,8) and (not effective or slot==4) else 0]
                if bus>7:expected[1:3]=[0,0]
                assert list(r.bytes(IFX+24*slot,4))==expected,(index,i,si.hex(),expected,list(r.bytes(IFX+24*slot,4)))
            row=dict(slot=i+1,effect=ids[i],allocation=si[i],physical=slot,enabled=bool(record[header+1]&64),
                     chain=effective,target=target,output_bus=bus,targets=list(r.bytes(IFX+24*slot,6)) if slot>=0 else None)
            slots.append(row)
            if row['enabled'] and row['allocation']:enabled_count[ids[i]]+=1
        layout_counts[tuple(si)]+=1
        master_returns=[0,0]
        for i in range(2):
            slot=physical(sm,i)
            if slot>=0:master_returns[slot]=record[0x21c+i]
        master_cross=[0,0]
        if record[0x21e]&2 and sm[0]!=2:master_cross[0 if record[0x21e]&1 else 1]=record[0x21f]
        assert [r.bytes(MFX+16*i,1)[0] for i in range(2)]==master_returns
        assert [r.bytes(MFX+16*i+1,1)[0] for i in range(2)]==master_cross
        factory.append(dict(program=chr(65+index//128)+str(index%128).zfill(3),source_offset=offset,source_sha256=hashlib.sha256(record).hexdigest(),
                            name=record[:16].decode('ascii').strip(),source_bus=record[0x50F]&31,ifx_layout=list(si),mfx_layout=list(sm),ifx=slots,
                            mfx_returns=master_returns,mfx_cross=master_cross))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],gain=gain_cases,pan=pan_cases,ifx=ifx,mfx=masters,
        mfx_transitions=transitions,ifx_transitions=ifx_transitions,batch_cadence=dict(deferred_visits=8,ifx_writes=ifx_batch,mfx_writes=mfx_batch),factory=factory,
        factory_layout_counts=[dict(layout=list(k),programs=v) for k,v in sorted(layout_counts.items())],
        enabled_allocated_ifx=[dict(effect=k,slots=v) for k,v in enabled_count.most_common()],
        boundaries=['TG reads at 0x1326B4 return ready and writes at 0x132690 are captured, never sent to hardware',
                    'Gain conversion, direction-step packing, pan conversion, IFX send/direct/chain logic and MFX returns/cross-send logic execute original ARM',
                    'Factory Programs use original 0x59EB8 and 0x58854 allocation/chain normalization loops and original routing refresh',
                    'Factory boundaries: resource release 0x55830, namespace getters 0x170230/0x1702BC, effect object setup 0x5CC7C; algorithm loading/audio do not execute',
                    'Allocation and requested routing do not prove source reachability, audible contribution, TG pan audio law, ramp duration, or effect algorithm fidelity',
                    'IFX transition tests preserve original batching, but TG completion/audio readback is not simulated; no OS or GUI executes'])
    (OUT/'effect-routing-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,gain_cases=len(gain_cases),pan_cases=len(pan_cases),ifx_cases=len(ifx),mfx_cases=len(masters),
                         ifx_transitions=len(ifx_transitions),mfx_transitions=len(transitions),factory_programs=len(factory),layouts=result['factory_layout_counts']),indent=2))
if __name__=='__main__':main()
