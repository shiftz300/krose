#!/usr/bin/env python3
"""CC121 channel/default state and live sustain handoff via original ARM."""
import argparse,contextlib,hashlib,io,itertools,json,struct
from pathlib import Path
from firmware_midi_parameters import Rig as ParameterRig
from firmware_midi_voice_refresh import Rig as LiveRig,compare as compare_live
from firmware_gm_programs import sources,IMAGE,IMAGE_SHA
from firmware_voice_lfo import PRELOAD,OUT,h,sh,w
from program_firmware import Firmware,BASE,FW_SHA
from firmware_midi_program_load import sha
from firmware_inspect import inspect
from layout import PRODUCT_ROOT as ROOT

def reset_channel(before):
    out=bytearray(before)
    for cc in list(range(1,32))+list(range(33,120)):out[0x82+cc]=0
    for cc in [8,10,16,118,119,*range(70,80)]:out[0x82+cc]=64
    for cc in [5,17,19,20,21,65]:out[0x82+cc]=255
    for cc in [7,11]:out[0x82+cc]=127
    out[1:0x82]=bytes(129);out[0xFA:0xFC]=bytes(2);out[0x114]=0
    out[0x118:0x138]=bytes(32);out[0x13C:0x1B4]=out[0x82:0xFA]
    return bytes(out)

class Rig(ParameterRig):
    def __init__(self,f):
        super().__init__(f);self.calls=[];self.display=[];self.a.stubs[0x54E40]=lambda m:self.display.append(m.get('R1')) or 0
        from unicorn import UC_HOOK_CODE
        def observe(uc,address,size,user):
            if address==BASE+0x26EC34:self.calls.append(list(self.a.uc.mem_read(self.a.get('R1'),4)))
        self.a.uc.hook_add(UC_HOOK_CODE,observe)
        self.channels_base=self.channels
    def seed(self,seed,old66,flags=255,channel=7,mode=3,blocked=False):
        a=self.a;oldchannel=self.channel;self.channel=self.channels_base+436*channel
        if self.channel!=oldchannel:
            a.uc.mem_write(self.channel,bytes(a.uc.mem_read(oldchannel,436)))
        a.write(self.mode,mode);a.write(self.system+0x2C,int(blocked));self.byte(self.channel,channel|(128 if seed&1 else 0))
        for off,n in [(1,129),(0x82,120),(0x118,32),(0x13C,120)]:a.uc.mem_write(self.channel+off,bytes((seed*71+i*29+off)&255 for i in range(n)))
        self.byte(self.channel+0xC4,old66);self.byte(self.channel+0x114,flags);a.uc.mem_write(self.channel+0xFA,struct.pack('<h',-12345))
        for i in range(3):
            a.uc.mem_write(self.controls[i],bytes((seed*43+i*61+j*17)&255 for j in range(128)))
            a.uc.mem_write(self.timbres[i]+0x94,struct.pack('<h',1000+i));self.byte(self.timbres[i]+0x2A,91+i);self.byte(self.timbres[i]+0x2D,81+i)
        a.uc.mem_write(self.keys,bytes((seed+i*31)&255 for i in range(1536)))
        self.calls.clear();self.display.clear()
    def check(self,value,source=0,blocked=False):
        a=self.a;before=bytes(a.uc.mem_read(self.channel,436));parts=[bytes(a.uc.mem_read(p,64)) for p in self.parts]
        ctrl=[bytes(a.uc.mem_read(p,128)) for p in self.controls];bends=[bytes(a.uc.mem_read(t+0x94,2)) for t in self.timbres]
        caches=[bytes(a.uc.mem_read(t+0x2A,4)) for t in self.timbres];keys=bytes(a.uc.mem_read(self.keys,1536))
        status=0xB0+(before[0]&15);a.write(self.event,0,status+(121<<8)+(value<<16)+(source<<24),0);self.calls.clear();self.display.clear()
        a.call(0x271500,self.system,self.event);wanted=before if blocked else reset_channel(before)
        assert bytes(a.uc.mem_read(self.channel,436))==wanted,[(hex(i),x,y) for i,(x,y) in enumerate(zip(a.uc.mem_read(self.channel,436),wanted)) if x!=y][:12]
        for i in range(3):
            assert bytes(a.uc.mem_read(self.parts[i],64))==parts[i]
            assert bytes(a.uc.mem_read(self.controls[i],128))==(ctrl[i] if blocked else wanted[0x82:0xFA]+ctrl[i][120:])
            assert bytes(a.uc.mem_read(self.timbres[i]+0x94,2))==(bends[i] if blocked else bytes(2))
            assert bytes(a.uc.mem_read(self.timbres[i]+0x2A,4))==caches[i]
        assert bytes(a.uc.mem_read(self.keys,1536))==keys
        expected=[] if blocked else [[status,121,value,source],[status,64,0,0]]+([[status,66,0,0]] if before[0xC4]>63 else [])
        assert self.calls==expected,(self.calls,expected)
        assert self.display==([] if blocked else [0,1]*(2 if before[0xC4]>63 else 1)),self.display
        return dict(value=value,source=source,channel=before[0]&15,old66=before[0xC4],blocked=blocked,calls=list(self.calls),
            bank=[wanted[0x82],wanted[0xA2]],selector_flags=wanted[0x114],buffer_volume=wanted[0x89],cached_volume=[c[3] for c in caches],buffer_pan=wanted[0x8C],cached_pan=[c[0] for c in caches])

def live_reset(r,value,source,explicit=False):
    a=r.a;before=bytes(a.uc.mem_read(r.channel,436));parts=[bytes(a.uc.mem_read(p,64)) for p in r.ps]
    ctrl=[bytes(a.uc.mem_read(p,128)) for p in r.cs];caches=[bytes(a.uc.mem_read(t+0x2A,4)) for t in r.ts];keys=bytes(a.uc.mem_read(r.keycontrols,1536))
    pressed={v['slot']:v for v in r.snapshot() if v['flags']&128}
    if explicit:
        old66=before[0xC4];a.call(0x26DDC8,r.channel);r.cc(64,0)
        if old66>63:r.put8(r.channel+0xC4,old66);r.cc(66,0)
        a.call(0x2EE124,r.channel+0x13C,r.channel+0x82,120);a.call(0x26E97C,r.channel)
    else:r.cc(121,value,source)
    wanted=reset_channel(before);assert bytes(a.uc.mem_read(r.channel,436))==wanted
    for i in range(3):
        assert bytes(a.uc.mem_read(r.ps[i],64))==parts[i]
        assert bytes(a.uc.mem_read(r.cs[i],128))==wanted[0x82:0xFA]+ctrl[i][120:]
        assert bytes(a.uc.mem_read(r.ts[i]+0x94,2))==bytes(2)
        assert bytes(a.uc.mem_read(r.ts[i]+0x2A,4))==caches[i]
    assert bytes(a.uc.mem_read(r.keycontrols,1536))==keys
    after={v['slot']:v for v in r.snapshot()}
    for slot,v in pressed.items():
        assert slot in after and after[slot]['flags']&128
        for key in ['program','common','osc_parameters','sample']:assert after[slot][key]==v[key]
    return dict(old66=before[0xC4],source=source,value=value,channel_before=before.hex(),channel_after=wanted.hex(),
        buffer_volume=wanted[0x89],cached_volume=caches[0][3],buffer_pan=wanted[0x8C],cached_pan=caches[0][0],
        fine_tuning=sh(parts[0],8),bank=[wanted[0x82],wanted[0xA2]],pressed_slots_kept=sorted(pressed))

def live_matrix(f,smoke=False):
    assert sha(PRELOAD)=='71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b'
    raw=PRELOAD.read_bytes();gm=sources();a=LiveRig(f,raw,gm);b=LiveRig(f,raw,gm);traces=[]
    presets=[(0,0),(0,61),(5,42),(10,0),(20,0)]
    choices=[((0,0),3,127,5)] if smoke else itertools.product(presets,[0,3],[0,127],[0,5])
    for preset,mode,sost,source in choices:
        initial=a.setup(preset,8,mode,True);b.setup(preset,8,mode,True);compare_live(a,b);steps=[]
        for update in range(64):
            results=[]
            for r,explicit in [(a,False),(b,True)]:
                r.clear_capture();event={}
                if update==4:
                    # Native RPN fine tuning, then select a drum NRPN and edit a key.
                    for cc,value in [(101,0),(100,1),(6,70),(38,90),(99,20),(98,48),(6,99)]:r.cc(cc,value)
                    r.send(0xD7,92);r.send(0xA7,48,73)
                if update==8:
                    r.cc(7,99);r.cc(10,100);r.cc(11,73);r.send(0xE7,127,127)
                if update==12:r.cc(64,127);r.cc(66,sost)
                if update==16:event['note']=r.note_and_remember(64,100)
                if update==20:r.send(0x87,48,64)
                if update in [28,48]:event['reset']=live_reset(r,127,source,explicit)
                if update==32:r.send(0x87,64,64)
                results.append(event)
            compare_live(a,b);assert results[0]==results[1]
            for r in [a,b]:r.clear_capture();r.a.write(r.clock+4,123+20*update)
            elapsed=[0,1,3,20][update%4];a.a.call(0x1FD3CC,a.manager,elapsed);b.explicit_advance(elapsed);compare_live(a,b)
            a.clear_capture();b.clear_capture();a.a.call(0x1FE404,a.manager);b.explicit_poll();compare_live(a,b)
            steps.append(dict(update=update,event=results[0],state=a.voice_state(),commits=a.verify_commits()))
        assert steps[28]['event']['reset']['cached_volume']==99 and steps[28]['event']['reset']['buffer_volume']==127
        assert steps[28]['event']['reset']['cached_pan']==100 and steps[28]['event']['reset']['buffer_pan']==64
        assert steps[28]['state']['timbre_bend']==steps[28]['state']['channel_bend']==0
        assert steps[28]['state']['controllers']['11']==127
        traces.append(dict(preset=preset,mode=mode,sostenuto=sost,source=source,initial=initial,steps=steps))
        print(json.dumps(dict(live_trace=len(traces),preset=preset,mode=mode,sostenuto=sost,source=source)),flush=True)
    return traces

def main():
    p=argparse.ArgumentParser();p.add_argument('--verify-arm',action='store_true');p.add_argument('--smoke',action='store_true');args=p.parse_args();f=Firmware()
    for name,lo,hi in [('MIDI-reset-controllers',0x270078,0x270104),('MIDI-reset-channel-state',0x26DDC8,0x26DEBC),('MIDI-reset-timbre-copy',0x26E97C,0x26E9DC)]:
        s=io.StringIO()
        with contextlib.redirect_stdout(s):inspect(f.data,lo,hi)
        (OUT/(name+'.arm.txt')).write_text(s.getvalue())
    if not args.verify_arm:return
    r=Rig(f);r.seed(1,127);example=r.check(127,5)
    if args.smoke:
        traces=live_matrix(f,True);print(json.dumps(dict(passed=True,example=example,live_traces=len(traces),live_commits=sum(len(s['commits']) for t in traces for s in t['steps'])),indent=2));return
    counts={};digest=hashlib.sha256()
    def case(seed,old66,value,source=0,flags=255,channel=7,mode=3,blocked=False):
        r.seed(seed,old66,flags,channel,mode,blocked);row=r.check(value,source,blocked);digest.update(json.dumps(row,sort_keys=True).encode());return row
    n=0
    for seed,old66,value,source in itertools.product([0,1],[0,63,64,127],range(128),[0,1,5,8]):case(seed,old66,value,source);n+=1
    counts['value_matrix']=n;n=0
    for old66,value,source in itertools.product(range(128),[0,64,127],[0,1,5,8]):case(2,old66,value,source);n+=1
    counts['sostenuto_matrix']=n;n=0
    for flags,old66 in itertools.product(range(256),[0,127]):case(3,old66,0,flags=flags);n+=1
    counts['selector_flags']=n;n=0
    for channel,mode,source,old66 in itertools.product(range(16),range(5),[0,1,5,8],[0,127]):case(4,old66,64,source,channel=channel,mode=mode);n+=1
    counts['channels_modes']=n;n=0
    for channel,source,old66 in itertools.product(range(16),[0,5],[0,127]):case(5,old66,127,source,channel=channel,blocked=True);n+=1
    counts['blocked_system']=n
    traces=live_matrix(f);counts['live_traces']=len(traces);counts['live_updates']=sum(len(t['steps']) for t in traces);counts['live_commits']=sum(len(s['commits']) for t in traces for s in t['steps'])
    result=dict(passed=True,smoke_only=False,firmware_sha256=FW_SHA,device_access=False,tool_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'research/tools/program_firmware.py'),
        additional_helpers={name:sha(ROOT/'research/tools'/name) for name in ['firmware_midi_parameters.py','firmware_midi_voice_refresh.py','firmware_midi_voice_handoff.py','firmware_midi_program_load.py','firmware_gm_programs.py','firmware_drum_voice_chain.py','firmware_factory_voice_chain.py','firmware_midi_banks.py','firmware_voice_lfo.py','voice_math.py','firmware_voice_refresh.py']},counts=counts,matrix_sha256=digest.hexdigest(),example=example,live=traces,
        inputs=[dict(path=str(PRELOAD.relative_to(ROOT)),sha256=sha(PRELOAD)),dict(path=str(IMAGE.relative_to(ROOT)),sha256=IMAGE_SHA)],
        defaults=list(reset_channel(bytes(436))[0x82:0xFA]),
        boundaries=['Native271500/26EC34/270078 reset,26DDC8 channel state, nestedCC64/66,26E97C/27427C timbre copying execute',
            'No OSCs are allocated in the channel-state matrix; native primary release iteration has capacity0; display54E40 is recorded, existing parameter-notification stubs remain',
            'Independent model compares all436 channel bytes, three64-byte Part records, three128-byte controller buffers/bends/caches and all1536 drum-control bytes',
            'Complete value, sostenuto threshold, selector flags, mode/channel/source and blocked-system domains are represented; source5 also refreshes the shadow via native unconditional copy',
            'Live40 traces compare nativeCC121 against explicitly scheduled native reset/helpers, then compare original advance/poll against decoded kernel order; same32-slot pool retains notes, pedal and modulation state',
            'Live reset also compares the independent whole-channel/default model, all Part records, all timbre controller buffers/bends/caches and drum-key bytes; TG target/step words use prior independent integer verification',
            'Inherited live TG active/amplitude/score fixtures, two explicit auxiliary bindings, private scratch stack and notification/OS boundaries remain; no actual DSP audio',
            'All Notes Off/All Sound Off, exhaustive preset/voice exhaustion and full front-end parsing are outside this result'])
    (OUT/'midi-reset-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(passed=True,counts=counts),indent=2))
if __name__=='__main__':main()
