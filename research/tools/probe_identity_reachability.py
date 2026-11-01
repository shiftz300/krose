#!/usr/bin/env python3
"""Offline identity-handler reachability with nonzero reused packet storage.

No keyboard APIs. Executes the original parser, an empty observer list and the
patched dispatcher. OS mode/monitor and final USB queue remain mocked.
"""
import hashlib
import json
import struct

from program_firmware import BASE, Firmware
from verify_probe_injection import GLOBAL, PACKET, CONTEXT, setup, capture_queue, request
from build_probe_injection import OUT


def main():
    fw = Firmware()
    fw.data = (OUT/'candidate/KROSSAPP.BIN').read_bytes()
    cases = []
    for fill in (0, 0xa5, 0xff):
        arm = setup(fw)
        # Run real observer getters/filter with an empty registered list, real
        # MIDI clock predicate (internal clock), and real special-mode flag.
        for offset in (0x2BCC50, 0x2BCCD4, 0x276090): arm.stubs.pop(offset, None)
        arm.uc.mem_write(GLOBAL+0x1350, b'\0\0\x01\x3f')
        arm.uc.mem_write(PACKET, bytes([fill])*0x100)
        arm.write(PACKET+0x10, 0)
        arm.write(PACKET+0x18, 0xffffffff)
        output, events = [], []
        arm.stubs[0x2B7E80] = capture_queue(output)
        trace = []
        for byte in request():
            ready = arm.call(0x2C2E90, PACKET, byte, 8, count=10000)
            trace.append(dict(byte=byte, ready=ready))
            if ready: events.append(bytes(arm.uc.mem_read(PACKET, 16)))
        assert len(events) == 1
        arm.uc.mem_write(PACKET, events[0])
        arm.uc.mem_write(PACKET+3, b'\x08')
        arm.uc.mem_write(CONTEXT, bytes(0x100))
        arm.call(0x2C11A0, PACKET, CONTEXT, 0x72, count=10000)
        cases.append(dict(initial_fill=hex(fill), decoded_packet_hex=events[0].hex(),
                          response_hex=[message.hex() for message in output], trace=trace))
    report = dict(scope='Offline with empty observer list; no hardware access',
                  candidate_sha256=hashlib.sha256(fw.data).hexdigest(), cases=cases)
    (OUT/'reachability-arm.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
