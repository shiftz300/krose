#!/usr/bin/env python3
"""Compare independent integer voice helpers/EG segments with original ARM."""
import hashlib
import json
import random
import struct

from program_firmware import Arm, Firmware, ROOT, FW_SHA
from voice_math import VoiceMath, EnvelopeSegment


def main():
    firmware = Firmware()
    math = VoiceMath(firmware)
    arm = Arm(firmware)
    counts = {}
    rng = random.Random(0x124)
    exponents = [-0x110000, -0x100000, -1, 0, 1, 0xFFFF, 0x10000, 0xFFFFF, 0x100000]
    exponents += [rng.randrange(-0x110000, 0x110000) for _ in range(300)]
    for value in exponents:
        assert math.exp2_q16(value) == arm.call(0x20102C, value) & 0xFFFFFFFF, value
    counts['exp2_q16'] = len(exponents)
    for _ in range(400):
        intensity, source = rng.randint(-99,99), rng.randint(-32768,32767)
        assert math.modulation_product(intensity,source)==arm.call(0x200FB4,intensity,source)
    counts['modulation_product'] = 400
    for index in range(100):
        for modulation in (-32768,-4096,-1,0,1,4096,32767):
            base=firmware.u32(0x3FD5A4+index*4)
            assert math.eg_duration(base,modulation)==arm.call(0x1FB02C,base,modulation),(index,modulation)
    counts['eg_duration'] = 700
    steps = [0,1,2,19,639,640,641,703,704,6399,6400,6401,230399,230400,300000]
    for curve in range(11):
        for step in steps:
            assert math.eg_curve_coefficient(curve,step)==arm.call(0x1FAB3C,curve,step),(curve,step)
    counts['eg_curve_coefficient'] = 11*len(steps)
    for level in range(100):
        for intensity in (-24,0,24):
            source=12345
            # The original optional AMS source is injected at the boundary;
            # level arithmetic itself is unmodified firmware instructions.
            arm.stubs={0x1F8608: lambda _: source}
            assert math.eg_level(level,intensity,source)==arm.call(0x1FAED0,0,0,0,intensity,stack=(level,))
    arm.stubs={}
    counts['eg_level_with_ams_boundary_injection'] = 300
    state=0x11008000
    for level in (0,1,50,119,127):
        for a in (-24,0,24):
            for b in (-24,0,24):
                arm.call(0x201674,state,level,a,b)
                assert math.multisample_gain(level,a,b)==struct.unpack('<H',arm.uc.mem_read(state,2))[0]
    counts['multisample_gain']=45
    program=(ROOT/'output/kep-analysis/Concert_SE_Grand/program.bin').read_bytes()
    sets=[(program[0x564+380*osc+offset:][:7],amp) for osc in (0,1) for offset,amp in [(0xFC,False),(0x13C,True)]]
    sets += [(program[offset:offset+7],False) for offset in (0x554,0x55C)]
    for parameters,amp in sets:
        arm.uc.mem_write(state,parameters)
        for note in range(128):
            assert math.keyboard_tracking(parameters,note,amp)==arm.call(0x2915A8 if amp else 0x2913EC,state,note),(parameters.hex(),note,amp)
    counts['keyboard_tracking']=len(sets)*128
    edge_checks=0
    for amp in (False,True):
        for ramp in (-100,-99,-98,-97,-96,-95,-1,0,1,99,100):
            parameters=struct.pack('<3B4b',36,60,84,*([ramp]*4))
            arm.uc.mem_write(state,parameters)
            for note in (0,24,36,48,60,72,84,96,127):
                assert math.keyboard_tracking(parameters,note,amp)==arm.call(0x2915A8 if amp else 0x2913EC,state,note),(amp,ramp,note)
                edge_checks+=1
    counts['keyboard_tracking_ramp_edges']=edge_checks
    sources={9:-2048,10:3072}
    for kind in (0,1,2):
        for _ in range(100):
            parameters=bytearray(24)
            parameters[:5]=bytes([kind,9,rng.randint(-99,99)&255,10,rng.randint(-99,99)&255])
            struct.pack_into('<2h',parameters,6,rng.randint(-199,199),rng.randint(-199,199))
            arm.uc.mem_write(state,bytes(parameters))
            arm.write(state+0x40,state)
            arm.stubs={0x1F8608:lambda machine:sources.get(machine.get('R1'),0)}
            arm.call(0x20119C,state+0x40,0,1)
            actual=struct.unpack('<h',arm.uc.mem_read(state+0x46,2))[0]
            assert math.basic_mixer(parameters,sources)==actual,(kind,parameters.hex(),actual)
    arm.stubs={}
    counts['AMS_mixer_types_0_1_2_with_source_injection']=300
    segment_cases=[]
    ticks=0
    state=0x11008000
    for index,curve,start,target in [(0,0,0,32767),(1,10,32767,0),(10,0,0,32767),
                                   (43,10,32767,0),(43,5,20000,1000),(77,1,0,24000),
                                   (91,0,32670,32670),(99,10,32767,0)]:
        model=EnvelopeSegment(math,start,target,index,0,curve)
        arm.uc.mem_write(state,bytes(0x80))
        arm.uc.mem_write(state,struct.pack('<h',start))
        arm.call(0x1FAF3C,state,target)
        arm.call(0x1FB0AC,state,index,0,curve)
        count=0
        while True:
            expected,done=model.step()
            actual_done=arm.call(0x1FAC24,state,0,curve)
            actual=struct.unpack('<h',arm.uc.mem_read(state,2))[0]
            assert (expected,done)==(actual,bool(actual_done)),(index,curve,count,expected,actual,done,actual_done)
            count+=1
            if done: break
            assert count<10000
        ticks+=count
        segment_cases.append({'time_index':index,'curve':curve,'start':start,'target':target,'matched_ticks':count,
                              'internal_duration_units':model.total,'final_control_level':expected})
    counts['eg_segment_ticks']=ticks
    result={'firmware_sha256':FW_SHA,'counts':counts,'segments':segment_cases,
            'tool_sha256':{name:hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in
                           ('program_firmware.py','voice_math.py','probe_voice_math.py')},
            'stubs':{'exp2_duration_curve_segment':'none',
                     'level_ams':'0x1f8608 injects source=12345 to test level arithmetic',
                     'AMS_mixer':'0x1f8608 injects sources 9=-2048 and 10=3072; mixer arithmetic unmodified'},
            'scope':'Original ARM helper/control state comparison; no TG audio gain/interpolation, scheduler or physical time validation'}
    output=ROOT/'research/derived/verification/voice-math-arm-comparison.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS',counts)


if __name__=='__main__':main()
