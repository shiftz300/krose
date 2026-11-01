#!/usr/bin/env python3
"""Isolated original-ARM checks of boot SerialFlash read paths.

Every peripheral call is replaced by synthetic memory-only hooks. The image
is neither booted nor connected to a keyboard. No writer/eraser is executed.
"""
import contextlib
import io
import json
from pathlib import Path

from analyze_kross_backup import OUT, ROOT, sha, store
from firmware_inspect import inspect
from index_firmware import scan
from program_firmware import Arm, Firmware, FW_SHA


def main():
    firmware = Firmware()
    folder = OUT / 'interfaces'
    folder.mkdir(parents=True, exist_ok=True)
    excerpts = [(0x12EA0C, 0x12EA68), (0x12EEC0, 0x12F028),
                (0x117D1C, 0x11803C), (0x17F36C, 0x17F428),
                (0x287C5C, 0x287D7C), (0x1EF3D8, 0x1EF410)]
    for start, end in excerpts:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer): inspect(firmware.data, start, end)
        store(folder / f'{start:06x}-{end:06x}.asm.txt', buffer.getvalue().encode())
    arm = Arm(firmware)
    obj, output = 0x11010000, 0x11020000
    cases = []
    for entry, block, length, block_mode in [
            (0x12EEC0, 0, 1, False), (0x12EEC0, 1, 257, False),
            (0x12EEC0, 0x3F, 32, False),
            (0x12EF64, 0, 65536, True), (0x12EF64, 0x3F, 65536, True),
            (0x118000, 0x3F, 32, False)]:
        expected = bytes(((block*65536+i)*37+19) & 255 for i in range(length))
        sent = []
        reads = []
        phases = []
        arm.write(obj, 0x11008000, 0x11009000)
        arm.uc.mem_write(output, b'\xcc'*(length+16))
        def constructor(a):
            a.write(a.get('R0'), 0x11008000, 0x11009000)
            return 0
        def send(a):
            assert a.get('R0') == 0x11008000
            sent.append(a.get('R1'))
            return 0
        def receive(a):
            i = len(reads)
            assert a.get('R0') == 0x11008000 and a.get('R1') == 0
            assert a.get('R2') == output+i and i < length
            a.uc.mem_write(output+i, expected[i:i+1])
            reads.append(output+i)
            return 0
        def phase(name):
            def callback(a): phases.append(name); return 0
            return callback
        def reject(a): raise AssertionError('Unexpected firmware assertion')
        arm.stubs = {0x12EA98: constructor, 0x12EC38: phase('busy_check'),
                     0x12EB18: phase('select'), 0x12EA68: phase('deselect'),
                     0x130880: send, 0x1307EC: receive, 0x2C5220: reject}
        if entry == 0x118000:
            arm.call(entry, obj, output, count=10000)
        else:
            arm.call(entry, obj, block, length//65536 if block_mode else length,
                     output, count=1000000)
        assert sent == [3, block, 0, 0]
        assert len(reads) == length
        assert phases == ['busy_check', 'select', 'deselect']
        assert bytes(arm.uc.mem_read(output, length)) == expected
        assert bytes(arm.uc.mem_read(output+length, 16)) == b'\xcc'*16
        cases.append(dict(entry=hex(entry), block=block, bytes=length,
                          SPI_transmit=sent, receive_count=len(reads),
                          synthetic_output_sha256=sha(expected), all_bytes_match=True,
                          guard_bytes_unchanged=True))
    arm.stubs = {}
    boot_size = arm.call(0x117E64, obj)
    assert boot_size == 0x20000
    calls, _ = scan(firmware.data)
    targets = [0x12EF64, 0x12EEC0, 0x118000, 0x117D1C, 0x117E64]
    report = dict(firmware_sha256=FW_SHA, tool_sha256=sha(Path(__file__).read_bytes()),
                  mode='Offline original ARM with synthetic peripherals only',
                  boot_ROM_logical_bytes=boot_size, read_cases=cases,
                  direct_BL_callers={hex(t): [hex(s) for s, d in calls if d == t] for t in targets},
                  address_limit=0x400000, sector_bytes=65536,
                  interpretation=dict(SerialFlash='Separate boot/identity flash; not TG PCM ROM',
                                      USB_host_read_entry='Not established',
                                      BOOTSYS_handler='0x17f36c loads file then calls boot writer 0x117e6c; not an export'),
                  real_device_bytes_read=0,
                  limitations=['Synthetic outputs prove protocol and copy logic, not actual flash contents',
                               'Direct BL scan does not resolve all indirect or diagnostic dispatch paths'])
    (folder / 'read-check-arm.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
