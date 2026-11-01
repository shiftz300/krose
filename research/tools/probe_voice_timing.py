#!/usr/bin/env python3
"""Verify nominal scheduler arithmetic and TG amplitude command generation.

All mapped timer registers are Unicorn memory, never host/device MMIO.
TG arithmetic/packing is original ARM; internal TG stepping is not executed.
"""
import contextlib
import hashlib
import json
import struct
from program_firmware import Arm, Firmware, ROOT, BASE, FW_SHA
from firmware_inspect import inspect


def main():
    firmware=Firmware();arm=Arm(firmware)
    manager=0x11010000;frame=0x111EF000;stack=0x111EE000
    arm.set('FP',frame);arm.set('SP',stack);arm.set('R0',manager)
    boot=[]
    def capture(machine):
        boot.append([machine.get('R'+str(i)) for i in range(4)]+list(struct.unpack('<3I',machine.uc.mem_read(machine.get('SP'),12))))
        return manager
    arm.stubs={0x1FD1C8:capture}
    arm.uc.emu_start(BASE+0x2B7474,BASE+0x2B74A4,count=10000)
    assert boot==[[manager,120,120,16,2,0x60000000,0x60000000]],boot
    arm.stubs={};arm.set('FP',frame);arm.set('SP',stack)
    arm.write(frame-0x60,manager);arm.write(frame-0x64,120)
    arm.write(frame-0x6C,16);arm.write(frame+4,2)
    arm.uc.emu_start(BASE+0x1FD278,BASE+0x1FD2C0,count=10000)
    assert struct.unpack('<I',arm.uc.mem_read(manager+0xE4,4))[0]==120
    batch=bytes(arm.uc.mem_read(manager+0xE8,1))[0];assert batch==15
    voices=0x11020000;list_head=0x11008000
    arm.write(manager+4,voices);arm.write(manager+0xCC,list_head)
    arm.uc.mem_write(list_head,bytes(16));visited=[]
    arm.stubs={0x1F8140:lambda machine:visited.append((machine.get('R0')-voices)//0x24C) or 0}
    for _ in range(8):arm.call(0x1FD3CC,manager,2)
    assert visited==list(range(120)),visited
    # Kernel sleep queues its timeout relative to the *next* clock tick.
    task=0x11009000;error=0x1100A000;timer_event=0x1100B000
    arm.write(0xC1B7A3A0,task);arm.write(0xC1B7A3B0,101)
    sleep_deadlines=[]
    arm.stubs={0x2FCF44:lambda _:0,
               0x2FD58C:lambda machine:sleep_deadlines.append(machine.get('R1')) or 0}
    arm.call(0x2FD18C,error,timer_event,1)
    assert sleep_deadlines==[102]
    # Original empty timer-queue signal advances the kernel by one clock tick.
    arm.stubs={};arm.write(0xC1B7A2DC,1);arm.write(0xC1B7A3B8,0)
    arm.write(0xC1B7A3AC,100);arm.set('CPSR',0x10)
    arm.call(0x2FBD5C)
    assert struct.unpack('<I',arm.uc.mem_read(0xC1B7A3AC,4))[0]==101
    timer=0x01C20000;arm.uc.mem_map(timer,0x1000)
    arm.call(0x130620,timer)
    timer_period=struct.unpack('<I',arm.uc.mem_read(timer+0x18,4))[0]
    assert timer_period==24000
    coefficients=list(struct.unpack_from('<25H',firmware.data,0x3A8D40))
    assert coefficients==[65535]+[65535//(32*i) for i in range(1,25)]
    writes=[]
    arm.stubs={0x132690:lambda m:writes.append((m.get('R0'),m.get('R1'))) or 0,
               0x1326B4:lambda _:0}
    cases=[]
    for duration in (0,1,2,5,15,24,100):
        for current,target in [(0,32767),(32767,0),(1000,2000),(2000,1000),(12345,12345)]:
            writes.clear();arm.call(0x12D288,0x60000000,current,target,duration)
            actual=[value for address,value in writes if address==0x60000418]
            if current==target:assert actual==[];continue
            product=(coefficients[min(duration,24)]*(target-current)) >> 16
            step=product+(1 if product>=0 else -1)
            expected=((step&65535)<<16)|target
            assert actual==[expected],(duration,current,target,actual,expected)
            cases.append({'duration_units':duration,'previous_target':current,'target':target,
                          'step':step,'register_word':expected})
    folder=ROOT/'research/derived/firmware/KROSS2_V124/voice'
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'timing-control.arm.txt').open('w') as stream:
        with contextlib.redirect_stdout(stream):
            for start,end in [(0x2B7474,0x2B74A4),(0x1FD278,0x1FD2C0),(0x1FD3CC,0x1FD45C),
                              (0x2B5560,0x2B5588),(0x2CD6D0,0x2CD744),(0x2FD18C,0x2FD1F8),
                              (0x130620,0x130650),(0x11710C,0x117144),(0x12CC10,0x12CC44),(0x12D288,0x12D2D8)]:
                print(f'\n# bounded excerpt {start:#x}..{end:#x}')
                inspect(firmware.data,start,end)
    result={'firmware_sha256':FW_SHA,'boot_voice_count':120,'boot_frame_period_argument':16,
            'boot_slice_period_argument':2,'voices_per_slice':batch,'slices_per_round':8,
            'all_voices_visited_once':True,'kernel_sleep_at_clock_100_wait_1_deadline':sleep_deadlines[0],
            'timer_base':hex(timer),'timer_PRD12':timer_period,
            'nominal_clock_tick_seconds':0.001,'nominal_voice_control_period_seconds':0.016,
            'nominal_EG_internal_units_per_second':1500,'EG_units_per_control_step':24,
            'nominal_audio_rate_hz':48000,'TG_reciprocal_table_offset':0x3A8D40,
            'TG_reciprocal_table':coefficients,'TG_register': 'base+0x418: signed step in high16, target in low16',
            'TG_command_cases':cases,'nominal_TG_audio_frames_per_time_unit':32,
            'scope':['Nominal 16 ms combines boot 16/2 slice setup, original n+1 kernel timeout and 8-slice voice round',
                     'Timer PRD12=24000 and TI Timer0 AUXCLK reference support nominal 1 ms; physical oscillator not measured',
                     'EG time table/manual and TG reciprocal table independently agree with 1500 internal units/s at 48 kHz',
                     'TG command generation is ARM-verified. Host per-sample signed-step/clamp interpretation remains a model; silicon is not executed',
                     'Overload/jitter and phase of hardware voice allocation are outside this test'],
            'boundary_stubs':['boot manager constructor capture','voice advance records index','kernel ready-list removal and timeout insertion capture','TG read/write bus'],
            'tool_sha256':{name:hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in ('program_firmware.py','probe_voice_timing.py')}}
    (ROOT/'research/derived/verification/voice-timing-arm-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS nominal 120/15/8 scheduler, kernel next-tick deadline, timer setup, 25 reciprocals and 28 TG amplitude commands')


if __name__=='__main__':main()
