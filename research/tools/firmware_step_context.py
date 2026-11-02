#!/usr/bin/env python3
"""Original step-progress context gates and parameter write requests."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('step-context-progress',0x6018,0x624C),('step-context-fields',0x1C703C,0x1C7158),('step-context-edit',0x1E0968,0x1E0B1C)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    if not args.verify_arm:return
    a=Arm(f);engine,context,controller,node,mode,vt,edit=0x11000000,0x11001000,0x11002000,0x11003000,0x11004000,0x11005000,0x11006000
    a.write(engine+0x18,2,context);a.write(0xC199BD3C,mode)
    a.write(0xC1439604,node);a.write(node+8,controller)
    a.write(context+0xC,0x11007000);a.write(context+0x1C,0x11008000)
    a.write(0xC143A300,vt);a.write(vt+0x38,0xC02FF000)
    a.write(0xC13F948C,0);a.uc.mem_write(0xC0A0000D,b'\xff')
    writes=[];notices=[];indicators=[];queries=[];current_group=0;step=0;target=0
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def call(p,*v):return a.call(p,*v)
    def getter(m):
        g,i=m.get('R1'),m.get('R2');queries.append([g,i])
        if i==0xF5:return target
        if i==26+3*step:return 40+step
        if i==28+3*step:return step%2
        raise AssertionError((g,i,step))
    def setter(m):writes.append([m.get('R1'),m.get('R2'),m.get('R3'),w(m.get('SP'))]);return 0
    a.stubs={0x2FF000:lambda m:0,0x206C54:getter,0x207DCC:setter,
        0x345AC:lambda m:notices.append([m.get('R1'),m.get('R2'),m.get('R3')]) or 0,
        0x1C6C54:lambda m:indicators.append('refresh') or 0,0x1C6D54:lambda m:indicators.append('record') or 0}
    cases=[]
    for raw_mode,state,triplet,step,target,previous in itertools.product([0,1,3],range(7),[0,1],[0,1,11,12,15,16,31,63],[0,1,3],[0,1]):
        a.write(mode,raw_mode);a.write(controller+4,state);a.write(engine+0x44,step)
        a.stubs[0x2FF000]=lambda m,v=triplet:v
        group={0:8,1:43,3:107}[raw_mode];grid=12 if triplet else 16;bank=step//grid
        a.write(0xC0483420,target if previous else target+1)
        writes.clear();notices.clear();indicators.clear();queries.clear()
        call(0x6018,engine)
        expected=[];expected_notices=[];active=state in [1,2,5,6]
        if active:
            expected += [[group,242,step,0],[group,243,40+step,0],[group,244,step%2,0]]
            expected_notices += [[group,i,1] for i in [242,243,244]]
            if step%grid==0 and previous:
                expected.append([group,245,bank,0]);expected_notices.append([group,245,1])
                if state in [1,2]:expected.append([314,16,bank,0]);expected_notices.append([314,16,1])
        assert writes==expected and notices==expected_notices,(raw_mode,state,triplet,step,target,previous,writes,expected)
        expected_indicators=(['refresh'] if active and state in [1,2] and step%grid==0 and previous else [])+(['record'] if state==1 else [])
        assert indicators==expected_indicators
        assert w(engine+0x44)==step+1
        assert w(0xC0483420)==(bank if active else (target if previous else target+1))
        cases.append(dict(mode=raw_mode,state=state,triplet=triplet,step=step,target=target,matched=previous,writes=writes.copy()))
    # Edit callbacks map current step's velocity/Accent back to the actual field IDs.
    edit_cases=[];edits=[]
    a.stubs[0x209894]=lambda m:edits.append([m.get('R1'),m.get('R2'),m.get('R3')]) or 0
    a.stubs[0x20A9B0]=lambda m:0
    a.write(edit+4,context)
    a.write(controller+4,0)
    for group,index,new,old in itertools.product([8,43,107],range(64),[0,1,64,127],[0,64]):
        ptr={8:0xC143A2DB,43:0xC143A2DF,107:0xC143A2D7}[group]
        a.uc.mem_write(ptr,bytes([index]));a.uc.mem_write(edit,struct.pack('<H',group));a.write(edit+0x1C,new,old)
        for fn,offset in [(0x1E0968,26),(0x1E0A20,28)]:
            edits.clear();call(fn,8,edit)
            assert edits==([[group,offset+3*index,new]] if new!=old else [])
            edit_cases.append(dict(group=group,step=index,field=offset,new=new,old=old))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        cases=cases,edit_cases=edit_cases,
        boundaries=['Original progress context selector, grid getter, parameter-map helper and velocity/Accent edit callbacks execute',
                    'Parameter getter/setter and refresh/record indicators captured at service boundaries; state writes use independent expectations',
                    'This verifies parameter write requests and context gating, not committed song edits or recorded note events',
                    'UI context and mode values are synthetic; no hardware or audio executes'])
    (OUT/'step-context-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,progress_cases=len(cases),edit_cases=len(edit_cases)),indent=2))
if __name__=='__main__':main()
