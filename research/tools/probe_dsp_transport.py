#!/usr/bin/env python3
"""Verify original TG program/constant transport with mocked 16-bit I/O only."""
import hashlib
import json
import struct

from program_firmware import Arm, BASE, Firmware, ROOT, FW_SHA


def main():
    firmware = Firmware()
    arm = Arm(firmware)
    writes = []

    def write16(machine):
        writes.append((machine.get('R0'), machine.get('R1') & 0xFFFF))
        return 0

    arm.stubs = {0x132690: write16, 0x1326B4: lambda _: 0}
    hardware = 0x60000000
    bundles = []
    for effect_id in (3,7,64,105):
        d = firmware.effect(effect_id)
        data = firmware.data[d['code_offset']:d['code_offset']+d['code_words_64']*8]
        expected = [(h0,h3,h2) for h0,pad,h2,h3 in struct.iter_unpack('<4H',data)]
        arm.call(0x12DAAC, hardware, 32, d['code_words_64'], BASE+d['code_offset'])
        parts = [(address-hardware, value) for address,value in writes if address-hardware in (0x718,0x714,0x710)]
        actual = []
        for i in range(0,len(parts),3):
            row=parts[i:i+3]
            assert [a for a,v in row] == [0x718,0x714,0x710]
            actual.append(tuple(v for a,v in row))
        assert actual == expected
        writes.clear()
        altered = bytearray(data)
        for i in range(0,len(altered),8):
            altered[i+2:i+4] = b'\xa5\x5a'
        scratch = 0x11010000
        arm.uc.mem_write(scratch,bytes(altered))
        arm.call(0x12DAAC,hardware,32,d['code_words_64'],scratch)
        altered_parts = [(a-hardware,v) for a,v in writes if a-hardware in (0x718,0x714,0x710)]
        assert altered_parts == parts
        writes.clear()
        arm.call(0x12DBC4,hardware,0,d['constant_words_32'],BASE+d['constants_offset'])
        constants=[]
        for a,v in writes:
            if a-hardware in (0x73C,0x738): constants.append(v)
        expected_constants=[]
        for value, in struct.iter_unpack('<I',firmware.data[d['constants_offset']:d['constants_offset']+d['constant_words_32']*4]):
            expected_constants.extend([value>>16,value & 0xFFFF])
        assert constants == expected_constants
        writes.clear()
        output=ROOT/f'research/derived/firmware/KROSS2_V124/effects/{effect_id:03d}/dsp-upload.u16le.bin'
        payload=b''.join(struct.pack('<3H',*row) for row in actual)
        output.write_bytes(payload)
        bundles.append({'effect_id':effect_id,'instructions':len(actual),'stored_bytes':len(data),
                        'uploaded_payload_bytes':len(payload),'payload_sha256':hashlib.sha256(payload).hexdigest(),
                        'padding_mutation_does_not_change_upload':True,'constant_words_verified':d['constant_words_32']})
    report={'firmware_sha256':FW_SHA,'program_loader':'0x12daac','word_reader':'0x12e9d8',
            'constant_loader':'0x12dbc4','mocked_io':['0x132690 write16 records value','0x1326b4 read16 returns ready (0)'],
            'program_container_bytes':8,'program_visible_payload_bits':48,
            'program_store_halfword_offsets_in_bus_write_order':[0,6,4],
            'ignored_store_halfword_offset':2,'program_data_registers':['TG+0x718','TG+0x714','TG+0x710'],
            'constant_transport_bits_per_word':32,'constant_data_registers':['TG+0x73c high16','TG+0x738 low16'],
            'scope':'Actual bus payload layout, not an instruction-set decode or accumulator precision determination',
            'bundles':bundles}
    output=ROOT/'research/derived/verification/dsp-transport.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
