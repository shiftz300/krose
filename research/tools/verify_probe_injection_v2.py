#!/usr/bin/env python3
"""Execute original USB receiver, real 8-byte FIFO push/pop, then application.

All kernel, allocation and final MIDI output effects are mocked. No device I/O.
The old v1 failure is reproduced with nonzero consumer stack bytes at event+8.
"""
import hashlib
import json
import struct
from pathlib import Path

from build_probe_injection import OUT as OLD_OUT
from build_probe_injection_v2 import OUT, build
from program_firmware import BASE, FW_SHA, Firmware
from verify_probe_injection import GLOBAL, CONTEXT, setup, capture_queue

FIFO = BASE+0x1B554F8
PARSER = BASE+0x1B5ADE4
CONSUMER = 0x11018000
BUFFER = 0x11020000


def case(fw, poison, channel=0, flag=0, index=0):
    arm = setup(fw)
    from unicorn import UC_HOOK_MEM_READ
    for address in (0x2BCC50, 0x2BCCD4, 0x276090): arm.stubs.pop(address, None)
    arm.stubs.update({0x2E2F9C: lambda a: BUFFER, 0x132660: lambda a: 0,
                      0x132670: lambda a: 0, 0x2FC618: lambda a: 0})
    # Real constructor uses element_bytes=8, capacity=1024, two u32 per event.
    arm.call(0x2B79C4, FIFO, 8, 0x400, 2, stack=(1,))
    element, words = struct.unpack('<HH', arm.uc.mem_read(FIFO+0xC, 4))
    assert element == 8 and words == 2
    arm.uc.mem_write(PARSER, bytes(0x100))
    arm.write(PARSER+0x18, 0xffffffff)
    arm.uc.mem_write(GLOBAL+0x1350, bytes([channel, 0, 1, 0x3f]))
    output = []
    arm.stubs[0x2B7E80] = capture_queue(output)
    # Original parser 0x2c38d8 shifts the FIRST index byte by seven;
    # 0x2c3904 combines the SECOND and stores only its low eight bits.
    wire = bytes([0xf0,0x42,0x30+channel,0,1,0x49,0x72,0x18,
                  flag,(index>>7)&127,index&127,0xf7])
    for byte in wire:
        arm.call(0x2CC9EC, 0, byte, count=10000)
    assert struct.unpack('<H', arm.uc.mem_read(FIFO+0x14, 2))[0] == 1
    arm.uc.mem_write(CONSUMER, bytes([poison])*16)
    assert arm.call(0x2B7D74, FIFO, CONSUMER) == 1
    event = bytes(arm.uc.mem_read(CONSUMER, 8))
    assert event[:2] == b'\x72\x18' and event[3] == 8
    assert bytes(arm.uc.mem_read(CONSUMER+8, 8)) == bytes([poison])*8
    # Actual readiness getter, with an explicitly ready synthetic app context.
    arm.uc.mem_write(BASE+0x104795C, b'\x01')
    overreads = []
    arm.uc.hook_add(UC_HOOK_MEM_READ,
                   lambda uc, access, address, size, value, user: overreads.append(dict(address=hex(address), bytes=size)),
                   begin=CONSUMER+8, end=CONSUMER+15)
    arm.call(0x2C1A6C, CONSUMER, CONTEXT, count=20000)
    assert arm.get('SP') == arm.stack
    return dict(poison=poison, channel=channel+1, flag=flag, wire_index=index,
                event_hex=event.hex(), reply_hex=[b.hex() for b in output],
                reads_beyond_event=overreads)


def main():
    manifest = build()
    old, new = Firmware(), Firmware()
    old.data = (OLD_OUT/'candidate/KROSSAPP.BIN').read_bytes()
    new.data = (OUT/'candidate/KROSSAPP.BIN').read_bytes()
    regression = [case(old, fill) for fill in (0, 0xa5, 0xff)]
    assert len(regression[0]['reply_hex']) == 1
    for result in regression:
        assert result['reads_beyond_event']
        if result['poison']: assert result['reply_hex'] == []
    positives = [case(new, fill, channel) for channel in range(16) for fill in (0, 0xa5, 0xff)]
    for result in positives:
        expected = bytes.fromhex('f042300001497d4b524f534502f7')
        expected = expected[:2]+bytes([0x30+result['channel']-1])+expected[3:]
        assert result['reply_hex'] == [expected.hex()] and not result['reads_beyond_event']
    negatives = [case(new, 0xa5, flag=flag) for flag in range(1,128)]
    negatives += [case(new, 0xa5, index=index) for index in (1,127,128,255)]
    for result in negatives: assert not result['reply_hex'] and not result['reads_beyond_event']
    aliases = [case(new, 0xa5, index=index) for index in (256,512,16128)]
    for result in aliases: assert len(result['reply_hex']) == 1 and not result['reads_beyond_event'], result
    report = dict(scope='Offline original FIFO/USB/application path; kernel/allocation/output mocked',
                  firmware_sha256=FW_SHA, candidate_sha256=manifest['candidate_sha256'],
                  test_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  FIFO_element_bytes=8, FIFO_u32_per_event=2,
                  original_functions_executed=list(map(hex, (0x2b79c4,0x2cc9ec,0x2b7bfc,0x2b7d74,0x2c1a6c,0x2bccd4))),
                  v1_regression=regression, v2_positive_cases=len(positives),
                  v2_negative_cases=len(negatives), harmless_wire_index_aliases=aliases,
                  v2_no_event_overread=True, hardware_tested=False, ROM_bytes_recovered=0)
    (OUT/'verification-arm.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
