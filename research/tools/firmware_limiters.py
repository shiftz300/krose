#!/usr/bin/env python3
"""Recover original Stereo/Mastering Limiter controls and sidechain EQ."""
import argparse,contextlib,hashlib,io,itertools,json,math,struct
from pathlib import Path
from program_firmware import Firmware,FW_SHA
from firmware_inspect import inspect
from firmware_parametric_eq import EqRig,decode,radius
from layout import PRODUCT_ROOT as ROOT

OUT=ROOT/'research/derived/firmware/KROSS2_V124/architecture/stage04'
PRELOAD=ROOT/'research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all'
Q23=0x7FFFFF
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def trunc(v,d):return (abs(v)//d)*(1 if v>=0 else -1)
def ratio(raw):return (raw+10)/10 if raw<=90 else raw-80 if raw<=130 else None
def ratio_word(raw):return 10*Q23//(raw+10 if raw<=90 else 10*(raw-80)) if raw<=130 else 0
def attack_word(raw):
    u=101-raw
    return (u*256+512 if u<=46 else u*1024-34816 if u<=66 else u*4096-237568 if u<=74 else
            u*32768-2359296 if u<=88 else u*65536-5242880 if u<=96 else u*1048576-99614720 if u<=99 else Q23)
def release_word(raw):
    u=101-raw
    return (u if u<=80 else u*16-1200 if u<=91 else u*256-23040 if u<=98 else 3072 if u==99 else 4096)*256
def release_ms(raw):return raw*.05 if raw<20 else (raw-10)/10 if raw<110 else raw-100 if raw<200 else 10*raw-1900
def side_hz(raw):return 20*raw if raw<=50 else 50*raw-1500 if raw<=130 else 100*raw-8000
def peak(hz,q,gain,constants):
    theta=hz*constants['angle_step']*5/(q+5)
    alpha=constants['tangent_cap'] if theta>=constants['angle_limit'] else math.tan(theta)
    c=math.cos(2*math.pi*hz/48000);g=10**(abs(gain)/40);d=1+alpha if gain>=0 else 1+g*alpha
    return [(1+g*alpha)/d if gain>=0 else (1+alpha)/d,-2*c/d,
            (1-g*alpha)/d if gain>=0 else (1-alpha)/d,2*c/d,
            (alpha-1)/d if gain>=0 else (g*alpha-1)/d]

class LimiterRig:
    def __init__(self,f):
        self.f=f;self.eq=EqRig(f);self.a=self.eq.a;self.ctx=self.eq.ctx;self.request=0x1100A000
        self.params={};self.queries=[]
        def get(a):
            assert a.get('R0')==777 and a.get('R2')==a.get('R3')==0
            i=a.get('R1');self.queries.append(i);return self.params[i]
        self.a.stubs[0xD5AC4]=get
        self.db_table=[f.u32(0x37C934+4*i) for i in range(64)]
        self.master_table=[f.u32(0x365178+4*i) for i in range(301)]
        self.master_release=[f.u32(0x36562C+4*i) for i in range(281)]
        self.env_table=[[f.u32(0x35F6B4+16*env+4*i) for i in range(4)] for env in range(4)]
    def words(self):return list(struct.unpack('<80I',self.a.uc.mem_read(0xC0FE9DC8,320)))
    def reset(self,effect=None):
        self.a.uc.mem_write(self.ctx,b'\x01\x01'+bytes(30));self.a.uc.mem_write(0xC0FE9DC8,bytes(320));self.queries.clear()
        if effect is not None:
            self.a.call(0x5A51C,self.ctx,0,2,0xC0000000+self.f.effect(effect)['definition_offset'])
            count=self.f.effect(effect)['constant_words_32'];expected=[self.f.u32(self.f.effect(effect)['constants_offset']+4*i) for i in range(count)]+[0]*(80-count)
            assert self.words()==expected
    def callback(self,effect,index,value,enabled=1,inhibit=0):
        callback=self.f.effect(effect)['parameters'][index]['descriptor']['callback']
        self.a.uc.mem_write(self.request,bytes(40));self.a.write(self.request,777,0,value,0,self.ctx,enabled,inhibit)
        self.a.call(callback,20,self.request)
    def scalar(self,effect,index,value,expected,enabled=1):
        self.reset();self.callback(effect,index,value,enabled);words=self.words();want=[0]*80
        for k,v in expected.items():want[k]=v
        assert words==want,(effect,index,value,[(i,x,y) for i,(x,y) in enumerate(zip(words,want)) if x!=y])
        return dict(effect=effect,parameter=index,value=value,enabled=enabled,writes={str(k):words[k] for k in expected})
    def env_words(self,env,source,trim):
        if source in [1,2]:return {2:0,3:Q23,28:0,29:0,30:trim*Q23//100 if source==1 else 0,31:trim*Q23//100 if source==2 else 0}
        v=self.env_table[env];return {2:v[3],3:v[0],28:v[1],29:v[2],30:0,31:0}
    def side(self,freq,q,gain):
        self.params.update({10:freq,11:q,12:gain});self.reset();self.callback(3,10,freq)
        words=self.words();assert all(v==0 for i,v in enumerate(words) if i not in range(18,28))
        coeff=decode(words[18:28],1,3);reference=peak(side_hz(freq),q,gain,self.eq.constants)
        err=max(abs(a-b) for a,b in zip(coeff,reference));pole=radius(coeff)
        assert err<0.00005 and pole<1,(freq,q,gain,coeff,reference,err,pole)
        # The Q and gain callbacks must reach the same whole-band programmer.
        for index,value in [(11,q),(12,gain)]:
            self.reset();self.callback(3,index,value);assert self.words()==words
            self.reset();self.callback(3,index,value,inhibit=1);assert self.words()==[0]*80
        return dict(frequency_raw=freq,hz=side_hz(freq),q_raw=q,gain_raw=gain,native=words[18:28],coefficients=coeff,max_error=err,pole_radius=pole)
    def expected_static(self,effect,params,baseline,side=None):
        w=baseline.copy()
        if effect==3:
            for i,v in self.env_words(params[0],params[16],params[17]).items():w[i]=v
            w[8]=ratio_word(params[1]);w[7]=self.db_table[-params[2]];w[5]=attack_word(params[3]);w[6]=release_word(params[4]);w[9]=self.db_table[24-params[5]]
            w[15]=0 if params[8] else Q23;w[14]=Q23 if params[8] else 0;w[17]=0 if params[9] else Q23;w[16]=Q23 if params[9] else 0
            w[18:28]=side['native'];w[10]=params[13]*Q23//100
        else:
            w[28]=self.master_table[-params[3]];w[27]=self.master_table[-params[4]]-1;w[26]=self.master_release[params[5]-10];w[29]=params[0]*Q23//100
        return w

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('limiter-common-parameters',0x741D0,0x744F8),('limiter-sidechain-parameters',0x7C88C,0x7D190),
                       ('mastering-limiter-parameters',0x8085C,0x80D38),('effects-dynamic-wet',0x9BF48,0x9C0B0)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    r=LimiterRig(f);a=r.a;scalars=[];table_errors=[]
    for attenuation,word in enumerate(r.db_table[:63]):
        # The final finite table entry jumps from -61 dB to -63 dB.
        db=63 if attenuation==62 else attenuation
        error=abs(word-Q23*10**(-db/20));assert error<=1;table_errors.append(error)
    assert r.db_table[63]==0
    for attenuation,word in enumerate(r.master_table):
        error=abs(word-Q23*10**(-attenuation/200));assert error<1;table_errors.append(error)
    for raw,word in enumerate(r.master_release,10):
        expect=0 if raw==10 else Q23*10**(-1/(48*(release_ms(raw)-.5)))
        assert abs(word-expect)<1,(raw,word,expect)
    for raw in range(132):scalars.append(r.scalar(3,1,raw,{8:ratio_word(raw)}))
    for raw in range(-40,1):scalars.append(r.scalar(3,2,raw,{7:r.db_table[-raw]}))
    for raw in range(1,101):
        scalars.append(r.scalar(3,3,raw,{5:attack_word(raw)}));scalars.append(r.scalar(3,4,raw,{6:release_word(raw)}))
    for raw in range(-39,25):scalars.append(r.scalar(3,5,raw,{9:r.db_table[24-raw]}))
    for raw in range(-300,1):
        scalars.append(r.scalar(5,3,raw,{28:r.master_table[-raw]}));scalars.append(r.scalar(5,4,raw,{27:r.master_table[-raw]-1}))
    for raw in range(10,291):scalars.append(r.scalar(5,5,raw,{26:r.master_release[raw-10]}))
    for effect,index,target in [(3,13,10),(5,0,29)]:
        for raw,enabled in itertools.product(range(101),range(2)):
            scalars.append(r.scalar(effect,index,raw,{target:raw*Q23//100 if enabled else 0},enabled))
    for index,indices in [(8,(15,14)),(9,(17,16))]:
        for raw in range(2):scalars.append(r.scalar(3,index,raw,{indices[0]:0 if raw else Q23,indices[1]:Q23 if raw else 0}))
    env=[]
    for mode,source,trim in itertools.product(range(4),range(3),[0,1,50,100]):
        r.params.clear();r.params.update({0:mode,16:source,17:trim});expected=r.env_words(mode,source,trim)
        for index,value in [(0,mode),(16,source),(17,trim)]:
            row=r.scalar(3,index,value,expected);env.append(row)
    side=[]
    for freq,q,gain in itertools.product([1,2,49,50,51,129,130,131,199,200],[0,12,95],[-36,-12,0,12,36]):side.append(r.side(freq,q,gain))
    dynamic=[]
    for effect in [3,5]:
        base_values=[-39,-12,0,24] if effect==3 else [0]
        amounts=[-63,0,63] if effect==3 else [0]
        for base,amount,wet,wet_amount,value,source,enabled in itertools.product(base_values,amounts,[0,37,100],[-100,0,100],[-127,0,64,127],[6,11,37],range(2)):
            r.params.clear()
            if effect==3:r.params.update({5:base,6:6,7:amount,13:wet,14:11,15:wet_amount})
            else:r.params.update({0:wet,1:11,2:wet_amount})
            r.reset();before=r.words();a.call(0x7D038 if effect==3 else 0x80C88,r.ctx,0,enabled,777,stack=(source,value));expected=before.copy()
            if enabled and effect==3 and source==6:expected[9]=r.db_table[24-max(-39,min(24,base+trunc(value*amount,127)))]
            if enabled and source==11:
                w=max(0,min(100,wet+trunc(value*wet_amount,127)));expected[10 if effect==3 else 29]=w*Q23//100
            assert r.words()==expected,(effect,base,amount,wet,wet_amount,value,source,enabled)
            dynamic.append(dict(effect=effect,gain=base,gain_amount=amount,wet=wet,wet_amount=wet_amount,source=source,value=value,enabled=enabled,
                                gain_word=expected[9] if effect==3 else None,wet_word=expected[10 if effect==3 else 29]))
    trajectories=[]
    for base,amount,wet,wet_amount in [(-38,63,37,-100),(24,-63,100,100),(0,1,0,1)]:
        r.params.clear();r.params.update({5:base,6:6,7:amount,13:wet,14:6,15:wet_amount});r.reset(3);previous=r.words();steps=[]
        for source,value,enabled in [(6,-127,1),(6,-64,1),(37,127,1),(6,0,1),(6,64,0),(6,64,1),(6,127,1)]:
            a.call(0x7D038,r.ctx,0,enabled,777,stack=(source,value));expected=previous.copy()
            if enabled and source==6:
                g=max(-39,min(24,base+trunc(value*amount,127)));w=max(0,min(100,wet+trunc(value*wet_amount,127)))
                expected[9]=r.db_table[24-g];expected[10]=w*Q23//100
            assert r.words()==expected
            steps.append(dict(source=source,value=value,enabled=enabled,gain_word=expected[9],wet_word=expected[10]));previous=expected
        trajectories.append(dict(gain=base,gain_amount=amount,wet=wet,wet_amount=wet_amount,shared_source=6,steps=steps))
    raw=PRELOAD.read_bytes();assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    factory=[]
    for program in range(768):
        offset=0x1EF220+2140*program;record=raw[offset:offset+2140]
        for slot in range(7):
            payload=0x18+76*slot if slot<5 else 0x194+68*(slot-5);effect=record[payload+64]
            if effect not in [3,5] or not record[payload+65]&64:continue
            definition=f.effect(effect);params=[f.read_value(record,payload+p['payload_offset'],p['descriptor']) for p in definition['parameters']]
            assert all(p['descriptor']['minimum']<=v<=p['descriptor']['maximum'] for p,v in zip(definition['parameters'],params))
            side_row=r.side(params[10],params[11],params[12]) if effect==3 else None
            r.params.clear();r.params.update(enumerate(params));r.reset(effect);baseline=r.words()
            for i,value in enumerate(params):r.callback(effect,i,value)
            expected=r.expected_static(effect,params,baseline,side_row);assert r.words()==expected,(program,slot,effect,[(i,v,e) for i,(v,e) in enumerate(zip(r.words(),expected)) if v!=e])
            factory.append(dict(program=chr(65+program//128)+str(program%128).zfill(3),slot='IFX'+str(slot+1) if slot<5 else 'MFX'+str(slot-4),effect=effect,
                                source_offset=offset,source_sha256=hashlib.sha256(record).hexdigest(),payload_offset=payload,parameters=params,words=r.words()[:definition['constant_words_32']],side=side_row))
    result=dict(passed=True,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
                additional_helpers={'firmware_parametric_eq.py':sha(ROOT/'research/tools/firmware_parametric_eq.py')},inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD))],
                db_table=r.db_table,master_db_table=r.master_table,master_release_table=r.master_release,env_table=r.env_table,
                scalars=scalars,environment=env,side=side,dynamic=dynamic,shared_source_trajectories=trajectories,factory=factory,
                max_table_error=max(table_errors),max_side_error=max(v['max_error'] for v in side+[row['side'] for row in factory if row['side']]),
                boundaries=['Original Stereo Limiter and Mastering Limiter parameter callbacks, buffered writes and math execute with only parameter getter 0xD5AC4 supplied',
                            'All legal ratio, threshold, attack/release, output gain, master threshold/ceiling/release and Wet/Dry values are checked',
                            'Original side PEQ frequency/Q/gain callbacks compare full 80-word buffer and independent normalized host SOS equations; inhibited Q/gain writes are also checked',
                            'All enabled limiter slots in 768 A-F Programs run the original buffered code/constants loader and every static parameter callback; allocation/audibility is not asserted',
                            'Release-table analytic fit is coefficient evidence, not a measured audio decay; detector, knee, lookahead, mixing and silicon audio remain unresolved',
                            'No TG audio instructions, MMIO, GUI, OS or physical device executes'])
    (OUT/'limiters-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,scalar_cases=len(scalars),environment_cases=len(env),side_eq_cases=len(side),dynamic_cases=len(dynamic),factory_slots=len(factory),
                         shared_source_trajectories=len(trajectories),
                         stereo_limiter_slots=sum(v['effect']==3 for v in factory),master_limiter_slots=sum(v['effect']==5 for v in factory),
                         max_side_error=result['max_side_error'],max_table_error=result['max_table_error']),indent=2))
if __name__=='__main__':main()
