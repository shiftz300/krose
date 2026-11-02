#!/usr/bin/env python3
"""Original Stereo Chorus delay/LFO/mix controls and pre-EQ tables."""
import argparse,contextlib,hashlib,io,itertools,json,math,struct
from pathlib import Path
from program_firmware import Arm,Firmware,FW_SHA
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT
OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
PRELOAD=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
Q23=0x7FFFFF
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def trunc(v,d):return (abs(v)//d)*(1 if v>=0 else -1)
def u32(v):return v&0xFFFFFFFF
def centihz(raw):
    v=abs(raw);result=2*v if v<=99 else 5*v-300 if v<=159 else 10*v-1100 if v<=209 else 50*v-9500
    return result if raw>=0 else -result
def rate_word(cents):return trunc(cents*32768,9375)*256+256
def delay_samples(raw):return 48*raw//10 if raw<100 else 48*(raw-90)
def depth_word(raw):return (18*raw if raw<=39 else 36*raw-721 if raw<=79 else 144*raw-9359)//7
def mix(raw):
    v=abs(raw)
    wet=(3*v*Q23 if v<50 else (v+100)*Q23)//200
    dry=((200-v)*Q23 if v<50 else 3*(100-v)*Q23)//200
    return wet if raw>=0 else -wet,dry
FACTORS=[32,24,16,12,8,6,4,3,2,1]
def sync_word(bpm,note,multiplier,tempo):return ((tempo if bpm<4000 else bpm)*FACTORS[note]<<21)//(562500*multiplier)
def shelf_table(f,band,gain,fc):
    base=([0x337448,0x3370DC] if band==0 else [0x337E8C,0x3377B4])[fc]
    return [f.u32(base+12*(gain+36)+4*i) for i in range(3)]
def shelf_decode(words,band):return [(w-2**24 if w&0x800000 else w)/2**(22 if band==0 else 20) for w in words]
def shelf_reference(band,gain,fc):
    # Original high shelf table for Fc=1 repeats the +12.5 dB row above it.
    effective=min(gain,25) if band==1 and fc==1 else gain
    g=10**(abs(effective)/40);t=math.tan(math.pi*[500,1500][band]/48000)
    if band==0:
        num,den=([1+g*t,g*t-1],[1+t,t-1]) if fc==1 else ([1+t,t-1],[1+t/g,t/g-1])
    else:
        num,den=([g+t,t-g],[1+t,t-1]) if fc==1 else ([g*(1+t),g*(t-1)],[1+g*t,g*t-1])
    if effective<0:num,den=den,num
    return [num[0]/den[0],num[1]/den[0],-den[1]/den[0]]

class ChorusRig:
    def __init__(self,f):
        self.f=f;self.a=Arm(f);self.ctx,self.request,self.owner,self.root=0x11008000,0x11009000,0x1100A000,0x1100B000
        self.params={};self.queries=[];self.notifications=[];self.tempo=12000;self.slot=0
        def getter(a):
            assert a.get('R0')==777 and a.get('R2')==a.get('R3')==0
            i=a.get('R1');self.queries.append(i);return self.params[i]
        self.a.stubs[0xD5AC4]=getter
        self.a.stubs[0x207DCC]=lambda a:self.notifications.append(['parameter-listener',a.get('R1'),a.get('R2'),a.get('R3')]) or 0
        self.a.stubs[0x345AC]=lambda a:self.notifications.append(['display',a.get('R1'),a.get('R2'),a.get('R3')]) or 0
        self.a.stubs[0x551C4]=lambda a:self.tempo
        self.a.write(0xC0F55850,self.root);self.a.write(self.root+0x1C,778);self.a.write(self.owner+0xC,779)
    def words(self):return list(struct.unpack('<80I',self.a.uc.mem_read(0xC0FE9DC8+320*self.slot,320)))
    def reset(self,load=False,slot=0):
        self.slot=slot;self.a.uc.mem_write(self.ctx,b'\x01\x01'+bytes(30));self.a.uc.mem_write(0xC0FE9DC8,bytes(2560))
        self.queries.clear();self.notifications.clear();self.a.write(0xC04842B0,self.tempo)
        if load:
            e=self.f.effect(64);self.a.call(0x5A51C,self.ctx,slot,2,0xC0000000+e['definition_offset'])
            assert self.words()==[self.f.u32(e['constants_offset']+4*i) for i in range(27)]+[0]*53
    def callback(self,index,value,enabled=1):
        cb=self.f.effect(64)['parameters'][index]['descriptor']['callback']
        self.a.uc.mem_write(self.request,bytes(40));self.a.write(self.request,777,self.owner,value,self.slot,self.ctx,enabled)
        self.a.call(cb,20,self.request)
    def scalar(self,index,value,expected,enabled=1):
        self.reset();self.callback(index,value,enabled);want=[0]*80
        for k,v in expected.items():want[k]=u32(v)
        assert self.words()==want,(index,value,[(i,x,y) for i,(x,y) in enumerate(zip(self.words(),want)) if x!=y])
        return dict(parameter=index,value=value,enabled=enabled,writes={str(k):u32(v) for k,v in expected.items()})
    def static_expected(self,p,baseline):
        w=baseline.copy();w[0]=p[15]*Q23//100
        w[3]=sync_word(p[6],p[7],p[8],self.tempo) if p[5] else rate_word(centihz(p[2]))
        w[4]=0 if p[0] else Q23;w[5]=Q23 if p[0] else 0;w[6]=u32(trunc(10*p[1]*Q23,180));w[7]=delay_samples(p[10])+1;w[8]=delay_samples(p[11])+1;w[9]=depth_word(p[12])
        w[11],w[12]=map(u32,mix(p[18]));w[13:16]=shelf_table(self.f,0,p[16],p[23]);w[16:19]=shelf_table(self.f,1,p[17],p[24]);w[26]=0
        return w

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('chorus-parameters',0x676A0,0x67B94),('chorus-lfo-rate',0x950E8,0x95C14),
                       ('chorus-delay-depth',0x969F4,0x96BC8),('chorus-mix',0x97AC4,0x97B54),('chorus-pre-eq',0x9A8D8,0x9AD88),
                       ('chorus-pre-eq-labels',0x9D3A0,0x9D3E0),('chorus-pre-eq-tables',0x60E28,0x60F70)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    assert list(f.data[0x37C568:0x37C572])==FACTORS
    r=ChorusRig(f);a=r.a;r.params.update({i:0 for i in range(25)});r.params.update({2:25,6:12000,7:6,8:1})
    scalar=[]
    for i in range(136):
        for index,target in [(10,7),(11,8)]:scalar.append(r.scalar(index,i,{target:delay_samples(i)+1}))
    for i in range(101):
        scalar.append(r.scalar(12,i,{9:depth_word(i)}));scalar.append(r.scalar(15,i,{0:i*Q23//100}))
    for i in range(-18,19):scalar.append(r.scalar(1,i,{6:trunc(i*10*Q23,180)}))
    for i in range(2):scalar.append(r.scalar(0,i,{4:0 if i else Q23,5:Q23 if i else 0}))
    for raw in range(1,231):
        r.params[5]=0;scalar.append(r.scalar(2,raw,{3:rate_word(centihz(raw))}))
        r.params[5]=1;scalar.append(r.scalar(2,raw,{}))
    for wet,enabled in itertools.product(range(-100,101),range(2)):
        w,d=mix(wet if enabled else 0);scalar.append(r.scalar(18,wet,{11:w,12:d},enabled))
    scalar.append(r.scalar(21,0,{}));scalar.append(r.scalar(22,0,{26:0}))
    eq=[]
    for band,gain,fc in itertools.product(range(2),range(-30,31),range(2)):
        r.params[23+band]=fc;words=shelf_table(f,band,gain,fc);coeff=shelf_decode(words,band);expect=shelf_reference(band,gain,fc)
        error=max(abs(a-b) for a,b in zip(coeff,expect));assert error<0.000003 and abs(coeff[2])<1,(band,gain,fc,coeff,expect,error)
        index=16+band;target=13+3*band;r.reset();r.callback(index,gain);want=[0]*80;want[target:target+3]=words;assert r.words()==want,(band,gain,fc,r.words()[target:target+3],words)
        r.params[index]=gain;r.reset();r.callback(23+band,fc);assert r.words()==want
        eq.append(dict(band=band,gain_raw=gain,fc=fc,native=words,coefficients=coeff,max_error=error))
    synced=[]
    for sync,bpm,note,multiplier,tempo in itertools.product(range(2),[3999,4000,12000,30000],range(10),[1,2,32],[4000,12000,30000]):
        r.tempo=tempo;r.params.update({2:25,5:sync,6:bpm,7:note,8:multiplier})
        for index,value in [(5,sync),(6,bpm),(7,note),(8,multiplier)]:
            r.reset();r.callback(index,value);want=[0]*80
            if sync:want[3]=sync_word(bpm,note,multiplier,tempo)
            elif index==5:want[3]=rate_word(centihz(25))
            assert r.words()==want,(sync,bpm,note,multiplier,tempo,index,r.words()[3],want[3])
        synced.append(dict(sync=sync,bpm=bpm,note=note,multiplier=multiplier,tempo=tempo,word=want[3]))
    initialized=[]
    for slot in [0,1,4,5,6]:
        r.reset(True,slot);baseline=r.words();a.call(0x6793C,r.ctx,slot)
        base=f.u32(0x38CCE8+4*slot);want=baseline.copy();want[1]=base;want[2]=base+2881
        assert r.words()==want,(slot,r.words(),want)
        initialized.append(dict(slot=slot,base=base,right_base=base+2881))
    dynamic=[]
    for sync,bpm,clock_source,source,value,enabled in itertools.product(range(2),[3999,12000],[0,1],[6,11,37],[-127,0,64,127],range(2)):
        r.tempo=14000;r.params.update({2:25,3:6,4:-115,5:sync,6:bpm,7:6,8:2,9:clock_source,12:70,13:0,14:0,18:-50,19:11,20:100})
        r.reset();a.call(0x679C8,r.ctx,0,enabled,777,stack=(source,value));want=[0]*80
        if enabled:
            if not sync and source==6:want[3]=max(0x700,rate_word(centihz(25)+trunc(centihz(-230)*value,127)))
            if sync and clock_source==1 and source==37:want[3]=sync_word(r.tempo,6,2,r.tempo)
            if source==11:want[11],want[12]=map(u32,mix(max(-100,min(100,-50+trunc(value*100,127)))))
        assert r.words()==want,(sync,bpm,clock_source,source,value,enabled,r.words(),want)
        dynamic.append(dict(sync=sync,bpm=bpm,clock_source=clock_source,source=source,value=value,enabled=enabled,rate_word=want[3],wet_word=want[11],dry_word=want[12]))
    free_modulation=[]
    for base,amount,value,source in itertools.product([1,99,100,159,160,209,210,230],[-115,-1,0,1,115],[-127,-64,0,64,127],[6,37]):
        r.params.update({2:base,3:6,4:amount,5:0,12:70,13:0,14:0,18:0,19:11,20:0})
        r.reset();a.call(0x679C8,r.ctx,0,1,777,stack=(source,value));want=[0]*80
        if source==6:want[3]=max(0x700,rate_word(centihz(base)+trunc(centihz(2*amount)*value,127)))
        assert r.words()==want,(base,amount,value,source,r.words()[3],want[3])
        free_modulation.append(dict(base=base,amount=amount,value=value,source=source,word=want[3]))
    # Keep the original buffer across free-rate, fixed-sync and clock updates.
    r.tempo=12000;r.params.update({2:25,3:6,4:0,5:0,6:12000,7:6,8:1,9:0,12:70,13:0,14:0,18:50,19:11,20:50})
    r.reset();r.callback(2,25);previous=r.words();trajectory=[]
    operations=[('sync-on',5,1,0),('manual-bpm',6,18000,0),('unmatched-source',None,37,1),
                ('enable-clock',None,None,0),('clock-change',None,37,1),('wet-change',None,11,-127),
                ('sync-off',5,0,0),('disabled-update',None,11,127)]
    for name,index,value,source_value in operations:
        want=previous.copy()
        if index is not None:
            r.params[index]=value;r.callback(index,value)
            want[3]=sync_word(r.params[6],6,1,r.tempo) if r.params[5] else rate_word(centihz(25))
        elif name=='enable-clock':r.params[9]=1;r.tempo=9000
        else:
            enabled=0 if name=='disabled-update' else 1
            a.call(0x679C8,r.ctx,0,enabled,777,stack=(value,source_value))
            if name=='clock-change':want[3]=sync_word(9000,6,1,9000)
            if name=='wet-change':want[11],want[12]=map(u32,mix(0))
        assert r.words()==want,(name,r.words(),want)
        trajectory.append(dict(operation=name,rate_word=want[3],wet_word=want[11],dry_word=want[12]));previous=want
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b';factory=[]
    for program in range(768):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140]
        for slot in range(7):
            payload=0x18+76*slot if slot<5 else 0x194+68*(slot-5)
            if record[payload+64]!=64 or not record[payload+65]&64:continue
            definition=f.effect(64);params=[f.read_value(record,payload+p['payload_offset'],p['descriptor']) for p in definition['parameters']]
            assert all(p['descriptor']['minimum']<=v<=p['descriptor']['maximum'] for p,v in zip(definition['parameters'],params))
            r.tempo=12000;r.params.clear();r.params.update(enumerate(params));r.reset(True,slot);a.call(0x6793C,r.ctx,slot);baseline=r.words()
            for i,value in enumerate(params):r.callback(i,value)
            want=r.static_expected(params,baseline);assert r.words()==want,(program,slot,[(i,x,y) for i,(x,y) in enumerate(zip(r.words(),want)) if x!=y])
            factory.append(dict(program=chr(65+program//128)+str(program%128).zfill(3),slot='IFX'+str(slot+1) if slot<5 else 'MFX'+str(slot-4),
                source_offset=offset,source_sha256=hashlib.sha256(record).hexdigest(),payload_offset=payload,parameters=params,words=r.words()[:27]))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],scalars=scalar,pre_eq=eq,sync=synced,initialized=initialized,dynamic=dynamic,
        free_modulation=free_modulation,continuous_updates=trajectory,factory=factory,
        max_eq_error=max(row['max_error'] for row in eq),
        boundaries=['Original Stereo Chorus buffered loader, slot initializer, parameter callbacks and dynamic update execute; no TG audio code executes',
                    'Only parameter getter 0xD5AC4, tempo getter 0x551C4 and listener/display notifications 0x207DCC/0x345AC are supplied at boundaries',
                    'Full 80-word slot buffers compare against independent delay, depth, free/synced LFO, phase, signed Wet/Dry and exact pre-EQ table references',
                    'All legal pre-EQ gain/Fc combinations compare normalized native one-pole coefficients against independent shelf equations, including the repeated high-shelf +12.5 dB cap row',
                    'Factory enabled slots execute original initialization and all static callbacks at their actual slot index with nominal external tempo 120 BPM',
                    'Audio delay interpolation, oscillator waveform/sample timing, feedback topology, internal headroom, physical output and audibility remain unverified'])
    (OUT/'chorus-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,scalar_cases=len(scalar),pre_eq_cases=len(eq),sync_cases=len(synced),initializer_slots=len(initialized),dynamic_cases=len(dynamic),
                         free_modulation_cases=len(free_modulation),continuous_updates=len(trajectory),factory_slots=len(factory),max_eq_error=result['max_eq_error']),indent=2))
if __name__=='__main__':main()
