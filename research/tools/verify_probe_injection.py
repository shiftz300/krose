#!/usr/bin/env python3
"""Offline ARM execution of the exact stage-A application candidate.

Does not boot an operating system or contact any keyboard. The final MIDI queue
is intercepted; no physical USB/MIDI, flash or TG access takes place.
"""
import hashlib
import json
import struct
from pathlib import Path

from build_probe_injection import OUT, SLOT, TABLE, build, sum16
from program_firmware import Arm, BASE, FW_SHA, Firmware, ROOT

PACKET, CONTEXT = 0x11010000, 0x11011000
GLOBAL = BASE + 0x1DCC2D8
FORBIDDEN = (0x11C888, 0x11C8CC, 0x11C90C, 0x11C994, 0x11C9E0, 0x11CA44,
             0x12E1C0, 0x12E210, 0x12E264, 0x12E494, 0x12E5EC,
             0x117F08, 0x117E6C, 0x14DECC, 0x14E730, 0x14E760)
TERMINALS = (0x2BEEA0, 0x2BEF74, 0x136454, 0x2BF000, 0x2BF074,
             0x13280C, 0x132950, 0x132C30, 0x135DAC, 0x2BF18C,
             0x2BF130, 0x2BF0F4, 0x2BF1E8, 0x134040, 0x13423C,
             0x134B5C, 0x138D0C)


def reject(a):
    raise AssertionError(f'Forbidden TG/flash/allocation function {a.get("PC"):#x}')


def setup(fw):
    machine = Arm(fw)
    machine.stubs = {t: reject for t in FORBIDDEN}
    machine.stubs.update({t: lambda a: 0 for t in (0x2B955C, 0x2B931C, 0x2B95A0,
                                                 0x2B947C, 0x2B95C0, 0x40C10)})
    machine.stubs.update({0x2BCC50: lambda a: 0x11015000, 0x2BCCD4: lambda a: 1,
                         0x243DB0: lambda a: 0, 0x276090: lambda a: 1})
    return machine


def capture_queue(captured):
    def callback(a):
        assert a.get('R0') == BASE + 0x1B5AE1C, 'Response reached non-USB queue'
        assert a.get('R2') == 14
        captured.append(bytes(a.uc.mem_read(a.get('R1'), a.get('R2'))))
        return 0
    return callback


def decode(machine, wire, source=8, channel=0, enabled=True):
    machine.uc.mem_write(PACKET, bytes(0x100))
    machine.write(PACKET+0x18, 0xFFFFFFFF)
    machine.uc.mem_write(BASE+0x1B571C0, bytes(0x40))
    machine.uc.mem_write(GLOBAL+0x1350, bytes([channel]))
    machine.uc.mem_write(GLOBAL+0x1353, bytes([0x20 if enabled else 0]))
    packets = []
    for byte in wire:
        ready = machine.call(0x2C2E90, PACKET, byte, source, count=10000)
        if ready:
            packets.append(bytes(machine.uc.mem_read(PACKET, 16)))
    return packets


def wire_case(machine, wire, source=8, channel=0, enabled=True, mode=0):
    captured = []
    machine.stubs[0x2B7E80] = capture_queue(captured)
    machine.stubs[0x40C10] = lambda a: mode
    packets = decode(machine, wire, source, channel, enabled)
    for packet in packets:
        machine.uc.mem_write(PACKET, packet)
        # The real DIN/USB receivers write [packet+3] AFTER parsing, at
        # 0x116bcc/0x2ccb18 respectively. This shim models that queue handoff;
        # a separate case below executes the actual USB receiver instructions.
        machine.uc.mem_write(PACKET+3, bytes([source]))
        machine.uc.mem_write(CONTEXT, bytes(0x100))
        machine.call(0x2C11A0, PACKET, CONTEXT, 0x72, count=10000)
        assert machine.get('SP') == machine.stack
    return packets, captured


def usb_receiver_case(fw):
    machine = setup(fw)
    receiver_packet = BASE+0x1B5ADE4
    queued, output = [], []
    machine.uc.mem_write(receiver_packet, bytes(0x100))
    machine.write(receiver_packet+0x18, 0xFFFFFFFF)
    machine.uc.mem_write(GLOBAL+0x1350, b'\0')
    machine.uc.mem_write(GLOBAL+0x1353, b'\x20')
    machine.stubs[0x2C1EC0] = lambda a: 0  # OS special-transfer mode disabled
    def enqueue(a):
        assert a.get('R0') == BASE+0x1B554F8
        assert a.get('R1') == receiver_packet
        queued.append(bytes(a.uc.mem_read(receiver_packet, 16)))
        return 1  # queue accepted immediately
    machine.stubs[0x2B7BFC] = enqueue
    machine.stubs[0x2B7E80] = capture_queue(output)
    for byte in request():
        machine.call(0x2CC9EC, 0, byte, count=10000)
    assert len(queued) == 1 and queued[0][3] == 8, queued
    machine.stubs[0x14D744] = lambda a: 1  # registered OS message context
    machine.uc.mem_write(PACKET, queued[0])
    machine.call(0x2C1A6C, PACKET, CONTEXT, count=10000)
    assert output == [bytes.fromhex('f0 42 30 00 01 49 7d 4b 52 4f 53 45 01 f7')]
    return dict(original_byte_receiver='0x2cc9ec', source_port_assigned_by_original=8,
                original_event_wrapper='0x2c1a6c', OS_queue_and_context_mocked=True,
                special_transfer_mode_mocked_disabled=True, output_hex=output[0].hex())


def request(channel=0, flag=0, index=0):
    return bytes([0xF0, 0x42, 0x30+channel, 0, 1, 0x49, 0x72, 0x18,
                  flag, index & 127, index >> 7, 0xF7])


def main():
    manifest = build()
    original, patched = Firmware(), Firmware()
    patched.data = (OUT/'candidate/KROSSAPP.BIN').read_bytes()
    assert hashlib.sha256(original.data).hexdigest() == FW_SHA
    assert len(patched.data) == len(original.data) == 0x600000
    assert struct.unpack_from('<H', patched.data, 0x5FFFFE)[0] == sum16(patched.data)
    assert patched.u32(TABLE) == BASE+SLOT
    assert (OUT/'restore/KROSSAPP.BIN').read_bytes() == original.data
    arm = setup(patched)
    positives = []
    for channel in range(16):
        packets, output = wire_case(arm, request(channel), channel=channel)
        expected = bytes([0xF0, 0x42, 0x30+channel, 0, 1, 0x49, 0x7D,
                          0x4B, 0x52, 0x4F, 0x53, 0x45, 1, 0xF7])
        assert len(packets) == 1 and output == [expected], (channel, packets, output)
        positives.append(dict(channel=channel+1, request_hex=request(channel).hex(), reply_hex=expected.hex()))
    # The original parser is exercised on every wire request, including all
    # reserved mode values and indices whose upper bits are stored separately.
    rejected = 0
    for flag in range(128):
        for index in (0, 1, 127, 128, 255, 256, 16383):
            if flag == index == 0: continue
            packets, output = wire_case(arm, request(flag=flag, index=index))
            assert len(packets) == 1 and not output, (flag, index, packets, output)
            rejected += 1
    gates = []
    cases = [('DIN_port', dict(source=7)), ('exclusive_disabled', dict(enabled=False)),
             ('wrong_channel', dict(channel=1)), ('blocked_mode_8', dict(mode=8)),
             ('blocked_mode_9', dict(mode=9))]
    for name, args in cases:
        packets, output = wire_case(arm, request(), **args)
        assert not output, (name, output)
        gates.append(name)
    # Direct dispatch with nonzero callee-saved canaries tests the injected tail
    # trampoline, original frame restoration and the new handler's ABI.
    canaries = {f'R{i}': 0x16000000+i for i in range(4, 12)}
    for port in (0, 1, 2, 3, 0xffffffff):
        captured = []
        arm.stubs[0x2B7E80] = capture_queue(captured)
        arm.uc.mem_write(PACKET, bytes([0x72, 0x18])+bytes(254))
        for i in range(13): arm.set('R'+str(i), 0)
        for reg, value in canaries.items(): arm.set(reg, value)
        for reg, value in [('R0', PACKET), ('R1', CONTEXT), ('R2', 0x18),
                           ('R3', port), ('SP', arm.stack), ('LR', 0x10000000)]:
            arm.set(reg, value)
        arm.uc.emu_start(BASE+0x2BF1F4, 0x10000000, count=10000)
        assert arm.get('PC') == 0x10000000 and arm.get('SP') == arm.stack
        assert all(arm.get(reg) == value for reg, value in canaries.items())
        assert len(captured) == int(port == 2)
    # Both images must retain the same original semantic leaves for every other
    # subcommand. No leaf body is executed here (some would write parameters).
    traces = []
    for fw in (original, patched):
        machine = setup(fw)
        trace = []
        for flag in (0, 0x40):
            for sub in range(128):
                if sub == 0x18: continue
                leaves = []
                def capture(target):
                    def callback(a):
                        leaves.append((target, [a.get('R'+str(i)) for i in range(4)],
                                       bytes(a.uc.mem_read(a.get('SP'), 12)).hex()))
                        return 0
                    return callback
                machine.stubs.update({target: capture(target) for target in TERMINALS})
                machine.uc.mem_write(PACKET, bytes([0x72, sub, 0, 8, flag, 0])+bytes(250))
                machine.uc.mem_write(CONTEXT, bytes(0x100))
                machine.write(BASE+0x1747538+8, 1)
                machine.call(0x2C11A0, PACKET, CONTEXT, 0x72, count=10000)
                assert len(leaves) == 1
                trace.append((flag, sub, leaves))
        traces.append(trace)
    assert traces[0] == traces[1]
    report = dict(scope='Offline mocked ARM only; no keyboard boot/transport/recovery test',
                  candidate_sha256=manifest['candidate_sha256'], firmware_sha256=FW_SHA,
                  tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  positive_wire_cases=positives, rejected_mode_index_requests=rejected,
                  negative_gates=gates, ABI_callee_saved_registers=canaries,
                  ABI_port_cases=5, unchanged_dispatch_cases=len(traces[0]),
                  USB_receiver=usb_receiver_case(patched),
                  forbidden_TG_flash_allocator_entries=list(map(hex, FORBIDDEN)),
                  original_header_and_sender_executed=True,
                  final_MIDI_queue_mocked=True, hardware_tested=False,
                  ROM_bytes_recovered=0, original_and_restore_match=True)
    (OUT/'verification-arm.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'positive_wire_cases'}, indent=2))


if __name__ == '__main__':
    main()
