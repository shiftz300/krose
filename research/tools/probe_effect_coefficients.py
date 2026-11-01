#!/usr/bin/env python3
"""Recover peaking EQ coefficients with original ARM math, no OS or MMIO.
Host audio uses floating-point biquads; exact TG arithmetic is not required.
"""
import cmath
import json
import math
import struct

from program_firmware import Arm, Firmware, ROOT, FW_SHA


def response(c, frequency, sample_rate=48000):
    b0, b1, b2, f1, f2 = c
    z = cmath.exp(-2j * math.pi * frequency / sample_rate)
    return (b0 + b1*z + b2*z*z) / (1 - f1*z - f2*z*z)


class EqOracle:
    def __init__(self, firmware):
        self.arm = Arm(firmware)
        # Required original shared math and filter constant constructors.
        self.arm.call(0x57C1C, 1, 0xFFFF)
        self.arm.call(0x60F70, 1, 0xFFFF)
        self.context = 0x11008000

    def biquad(self, band, frequency_index, q_index, gain_index, precision=1):
        # Original buffered mode, no stubs; the original flush returns here.
        self.arm.uc.mem_write(self.context, b'\x01\x01' + bytes(30))
        self.arm.call(0x99714, self.context, 0, 2, frequency_index,
                      stack=(band, q_index + 5, gain_index, 1, precision))
        size = 10 if precision == 1 else 5
        words = struct.unpack('<' + 'I'*size, self.arm.uc.mem_read(0xC0FE9DC8 + 8, size*4))
        values = []
        if precision == 1:
            for high, low in zip(words[::2], words[1::2]):
                # 0x573e0 splits low 8 bits <<15 and remaining high 24 bits.
                # 0x99714 emits high then low; signed Q30 includes +/-2 range.
                value = ((high << 8) | (low >> 15)) & 0xFFFFFFFF
                if value & 0x80000000:
                    value -= 2**32
                values.append(value / 2**30)
        else:
            for value in words:
                if value & 0x800000:
                    value -= 2**24
                values.append(value / 2**22)
        return {'b0_b1_b2_feedback1_feedback2': values,
                'native_upload_words': list(words), 'precision_mode': precision}


def main():
    firmware = Firmware()
    oracle = EqOracle(firmware)
    folder = ROOT / 'output/kep-analysis/Concert_SE_Grand'
    program = json.loads((folder / 'program-analysis.json').read_text())
    slots = []
    for effect in program['effects'][:2]:
        assert effect['id'] == 7
        fields = effect['parameters']
        assert fields[1]['value'] == fields[2]['value'] == 0, 'Peaking mode only'
        bands = []
        for band, index in enumerate((5, 8, 11, 14)):
            frequency, q, gain = fields[index:index + 3]
            native = oracle.biquad(band, frequency['value'], q['value'], gain['value'],
                                    precision=1 if band < 2 else 0)
            working = oracle.biquad(band, frequency['value'], q['value'], gain['value'])
            c = working['b0_b1_b2_feedback1_feedback2']
            measured = 20*math.log10(abs(response(c, frequency['display']['value'])))
            assert abs(measured - gain['display']['value']) < 0.03, (effect['slot'], band, measured)
            f1, f2 = c[3:]
            poles = [(f1 + sign*cmath.sqrt(f1*f1 + 4*f2))/2 for sign in (1, -1)]
            assert max(map(abs, poles)) < 1
            grid = [frequency['display']['value']] + [20*1000**(i/100) for i in range(101)]
            quantization_error = max(abs(20*math.log10(abs(response(native['b0_b1_b2_feedback1_feedback2'], f)/response(c, f)))) for f in grid)
            assert quantization_error < 0.01
            bands.append({'band': band + 1, 'frequency_hz': frequency['display']['value'],
                          'q': q['display']['value'], 'gain_db': gain['display']['value'],
                          'native': native, 'host': working,
                          'gain_at_center_db': measured, 'maximum_pole_radius': max(map(abs, poles)),
                          'maximum_native_vs_working_response_difference_db': quantization_error})
        slots.append({'slot': effect['slot'], 'trim_raw': fields[0]['value'],
                      'trim_linear': int(fields[0]['value']*0x7FFFFF/100)/0x7FFFFF,
                      'trim_basis': '0x86e80 -> 0x94e24: trunc(raw * 0x7fffff / 100)', 'bands': bands})
    validation = []
    for band, frequency_index in enumerate((6, 155, 70, 129)):
        hz = (80, 1600, 7300, 13400)[band]
        for q_index in (0, 12, 95):
            # Keep the isolated helper inside its +/-2 coefficient range.
            # Large boost + broad Q needs caller-side headroom compensation;
            # this prototype only uses the factory patch's moderate gains.
            for gain_index in (-12, 0, 12):
                c = oracle.biquad(band, frequency_index, q_index, gain_index)['b0_b1_b2_feedback1_feedback2']
                measured = 20*math.log10(abs(response(c, hz)))
                assert abs(measured - gain_index/2) < 0.04, (band, q_index, gain_index, measured)
                if gain_index == 0:
                    errors = [abs(20*math.log10(abs(response(c, f)))) for f in (30,80,300,1000,10000,20000)]
                    assert max(errors) < 0.05, errors
                validation.append({'band': band + 1, 'q_index': q_index,
                                   'gain_index': gain_index, 'center_gain_db': measured})
    result = {'firmware_sha256': FW_SHA, 'sample_rate_hz': 48000,
              'original_functions': ['0x57c1c','0x60f70','0x99714','0x5f560','0x5e8fc','0x5ebe0','0x5a46c'],
              'stubs': [], 'execution_mode': 'Buffered context bytes [1,1]; original flush returns without MMIO',
              'host_equation': 'y = b0*x + b1*x1 + b2*x2 + feedback1*y1 + feedback2*y2',
              'scope': 'Factory patch coefficients plus moderate +/-6 dB probes. Large-boost caller-side headroom compensation is not reconstructed. Host realization is floating point.',
              'slots': slots, 'validation': validation}
    destination = ROOT / 'research/derived/firmware/KROSS2_V124/effects/007/concert-coefficients.json'
    destination.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS eight Concert EQ bands and 36 positive/negative/zero-gain cases')
    for slot in slots:
        print(slot['slot'], [(b['frequency_hz'], round(b['gain_at_center_db'],4)) for b in slot['bands']])
    print('Wrote', destination)


if __name__ == '__main__':
    main()
