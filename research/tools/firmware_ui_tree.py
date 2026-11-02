#!/usr/bin/env python3
"""Execute UI tree construction, search order, recycling and virtual dispatch."""
import argparse
import contextlib
import hashlib
import io
import itertools
import json
import struct
from pathlib import Path
from program_firmware import Arm, Firmware, FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args()
    f=Firmware();OUT.mkdir(parents=True,exist_ok=True)
    for name,lo,hi in [('ui-tree-pool',0xDFA2C,0xE02DC),('ui-tree-links',0xE0320,0xE0588),
                       ('ui-tree-edit',0xE09FC,0xE0B3C),('ui-tree-search',0xE10FC,0xE11D0),
                       ('ui-tree-subtree-search',0xE158C,0xE1640),('ui-parameter-lookup',0xDE030,0xDE0D8),
                       ('ui-parameter-match',0xEFE8C,0xEFED4)]:
        out=io.StringIO()
        with contextlib.redirect_stdout(out):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(out.getvalue())
    index_path=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage01/index.json'
    rows=json.loads(index_path.read_text())['vtables']
    slots=[dict(name=r['encoded_name'],address_point=r['address_point_offset'],
                match=r['slots'][30],active=r['slots'][34],changed=r['slots'][45])
           for r in rows if 0x469000<=r['address_point_offset']<0x46D600 and len(r['slots'])>=46]
    for row in slots:
        for key,slot in [('match',0x78),('active',0x88),('changed',0xB4)]:
            assert row[key]==f.pointer(row['address_point']+slot)
    if not args.verify_arm:return
    a=Arm(f)
    def call(p,*args,**kw):return a.call(p,*args,**kw)&0xFFFFFFFF
    def w(p):return struct.unpack('<I',a.uc.mem_read(p,4))[0]
    def ph(p,v):a.uc.mem_write(p,struct.pack('<H',v&65535))
    tree,array,pool,objects=0x11000000,0x11000100,0x11001000,0x11010000
    obj=[objects+0x100*i for i in range(10)]
    allocations=[]
    def alloc_array(m):allocations.append(m.get('R0'));return array
    def alloc_pool(m):allocations.append(m.get('R0'));return pool
    base={0x14E730:alloc_array,0x14DECC:alloc_pool,0x2DC184:lambda m:0,0x2DC1BC:lambda m:0,0x2C4474:lambda m:0}
    a.stubs=dict(base)
    call(0xDFCBC,tree)
    assert allocations==[16,28*384]
    assert [w(tree+off) for off in [4,8,12,16,24]]==[array,0,0,0,0]
    assert [w(array+off) for off in [0,4,8,12]]==[0xC0468CC4,pool,28,384]
    bounds=[]
    for i in [-1,0,1,383,384,385,65535,0x7FFFFFFF]:
        got=call(0xDFA2C,tree,i&0xFFFFFFFF)
        expected=pool+28*i if 0<=i<=384 else 0
        assert got==expected
        bounds.append(dict(index=i,pointer=got,within_allocated_array=bool(got and i<384)))

    # Build R(A(D,E), B(F), C) using original allocation and insertion code.
    parents=[None,0,0,0,1,1,2]
    for i,pointer in enumerate(obj):
        a.uc.mem_write(pointer,bytes(0x100));a.write(pointer,0xC0469880)
        ph(pointer+0xA,65535);ph(pointer+0x58,100);ph(pointer+0x5A,i)
    ph(obj[0]+0xA,call(0xE09FC,tree,obj[0]))
    for i,parent in enumerate(parents[1:],1):
        assert call(0xE0A70,tree,obj[parent],obj[i])==i
        ph(obj[i]+0xA,i)
    assert w(tree+24)==7 and w(tree+16)==pool
    expected_links=[(0,1,None),(0,4,2),(0,6,3),(0,None,None),(1,None,5),(1,None,None),(2,None,None)]
    for i,(parent,child,sibling) in enumerate(expected_links):
        actual=[w(pool+28*i+off) for off in [4,8,12,24]]
        expected=[0 if i==0 else pool+28*parent,0 if child is None else pool+28*child,
                  0 if sibling is None else pool+28*sibling,obj[i]]
        assert actual==expected,(i,actual,expected)
    # The separate circular traversal follows R,A,D,E,B,F,C.
    ring=[];node=pool
    for _ in range(7):
        ring.append((node-pool)//28);nxt=w(node+20);assert w(nxt+16)==node;node=nxt
    assert ring==[0,1,4,5,2,6,3] and node==pool
    orders={0:[0,1,2,3,6,4,5],1:[3,6,2,5,4,1,0]}
    visited=[];mask=0
    def predicate(m):
        i=obj.index(m.get('R0'));visited.append(i);assert m.get('R1')==0x12345678
        return bool(mask&(1<<i))
    a.stubs[0x2FF000]=predicate
    search=[]
    for order,mask in itertools.product([0,1],range(128)):
        visited.clear();expected_order=orders[order]
        first=next((i for i in expected_order if mask&(1<<i)),None)
        expected_visit=expected_order if first is None else expected_order[:expected_order.index(first)+1]
        got=call(0xE158C,tree,obj[0],0xC02FF000,0x12345678,stack=(order,))
        assert got==(0 if first is None else obj[first]) and visited==expected_visit,(order,mask,visited)
        search.append(dict(order=order,mask=mask,visited=visited.copy(),result=first))
    a.write(0xC10042D0,tree)
    lookup=[]
    # All subsets of duplicate bindings, with four different flag combinations.
    for mask,flags in itertools.product(range(128),[0,0x10,0x24,0xFFFF]):
        for i in range(7):
            ph(obj[i]+6,flags);ph(obj[i]+8,flags)
            ph(obj[i]+0x58,100 if mask&(1<<i) else 101);ph(obj[i]+0x5A,2)
        first=next((i for i in orders[1] if mask&(1<<i)),None)
        got=call(0xDE090,obj[0],100,2)
        assert got==(0 if first is None else obj[first])
        lookup.append(dict(mask=mask,flags=flags,result=first))
    # Null/invalid entries are skipped; valid descendants of invalid objects remain searchable.
    for i in range(7):ph(obj[i]+0x58,100);ph(obj[i]+0x5A,2)
    invalid=[]
    for bad in range(7):
        ph(obj[bad]+0xA,65535)
        got=call(0xDE090,obj[0],100,2)
        expected=None if bad==0 else next(i for i in orders[1] if i!=bad)
        assert got==(0 if expected is None else obj[expected])
        invalid.append(dict(invalid_id=bad,result=expected));ph(obj[bad]+0xA,bad)
    a.write(pool+28*3+24,0)
    assert call(0xDE090,obj[0],100,2)==obj[6]
    a.write(pool+28*3+24,obj[3])
    # Signed low-half packing at DE090 sign-extends index before ORing the group.
    packed=[]
    for group,number in itertools.product([0,100,32767,32768,65535],[0,2,32767,32768,65535]):
        for i in range(7):ph(obj[i]+0x58,99);ph(obj[i]+0x5A,3)
        ph(obj[3]+0x58,group);ph(obj[3]+0x5A,number)
        got=call(0xDE090,obj[0],group,number)
        matches=number<32768 or group==65535
        assert got==(obj[3] if matches else 0)
        direct=call(0xEFE8C,obj[3],group,number);assert direct==1
        packed.append(dict(group=group,index=number,lookup_match=matches,direct_match=True))

    # Remove A with children D,E; original destructor dispatch captured.
    # Deleted IDs are invalidated by the fixture recipient, matching the public contract.
    destroyed=[];vt=0x11000800
    a.uc.mem_write(vt,bytes(a.uc.mem_read(0xC0469880,192)));a.write(vt+12,0xC02FF004)
    for pointer in obj:a.write(pointer,vt)
    for i in range(7):ph(obj[i]+0xA,i)
    def destroy(m):
        pointer=m.get('R0');destroyed.append(obj.index(pointer));ph(pointer+0xA,65535);return 0
    a.stubs[0x2FF004]=destroy
    call(0xE0AF8,tree,obj[1])
    assert destroyed==[4,5,1]
    assert w(pool+8)==pool+28*2 and w(tree+8)==pool+28*4 and w(tree+12)==pool+28
    assert w(pool+28*4+8)==pool+28*5 and w(pool+28*5+8)==pool+28
    recycled=[]
    for pointer in obj[7:10]:
        i=call(0xE0A70,tree,obj[0],pointer);ph(pointer+0xA,i);recycled.append(i)
    assert recycled==[4,5,1] and w(tree+24)==7 and w(tree+8)==w(tree+12)==0
    # Final circular list and parent/child links after reuse.
    ring_after=[];node=pool
    for _ in range(7):
        ring_after.append(w(node+24));nxt=w(node+20);assert w(nxt+16)==node;node=nxt
    assert ring_after==[obj[i] for i in [0,2,6,3,7,8,9]] and node==pool

    # Actual no-op callback bodies and menu/window refresh wrappers.
    callback_cases=[];refresh=[];owner=0x11000300
    a.write(0xC1004298,owner)
    a.stubs[0xDE344]=lambda m:refresh.append(m.get('R0')) or 0
    for row in slots:
        if row['changed'] not in [0xEFED0,0xE6E60,0x113D04]:continue
        for valid in [False,True]:
            ph(obj[0]+0xA,0 if valid else 65535);a.write(owner+0x74,0x12345678)
            before=bytes(a.uc.mem_read(obj[0],0x100));refresh.clear()
            call(row['changed'],obj[0],7,3,0,stack=(127,14,0))
            assert bytes(a.uc.mem_read(obj[0],0x100))==before
            expected_refresh=row['changed']!=0xEFED0 and valid
            assert refresh==([obj[0]] if expected_refresh else [])
            assert w(owner+0x74)==(0 if row['changed']!=0xEFED0 else 0x12345678)
            callback_cases.append(dict(name=row['name'],valid=valid,refresh_called=expected_refresh))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,
                allocations=allocations,bounds=bounds,ring=ring,search=search,lookup=lookup,invalid=invalid,
                signed_index_cases=packed,destroyed=destroyed,recycled=recycled,callback_cases=callback_cases,vtables=slots,
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                helper_sha256=hashlib.sha256((ROOT/'research/tools/program_firmware.py').read_bytes()).hexdigest(),
                inputs=[dict(path=str(index_path.relative_to(ROOT)),sha256=hashlib.sha256(index_path.read_bytes()).hexdigest())],
                boundaries=['Original tree constructor, array stride, node allocation, insertion, subtree removal and free-list reuse execute',
                            'Heap allocation and exception scaffolding are controlled; widget objects are synthetic and IDs assigned by fixture',
                            'Lookup executes original predicate and common virtual matcher; duplicate bindings and flag fields are synthetic',
                            'Object destruction recipient invalidates synthetic IDs; actual widget destructor bodies are not executed',
                            'Menu/window callback wrappers execute but DE344 refresh recipient is captured; pixel drawing remains unverified',
                            'Index 384 is accepted by isolated accessor despite 384 allocated entries; real overflow reachability is unproven'])
    (OUT/'ui-tree-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,search_cases=len(search),lookup_cases=len(lookup),packing_cases=len(packed),vtables=len(slots),callback_cases=len(callback_cases),recycled=recycled),indent=2))

if __name__=='__main__':main()
