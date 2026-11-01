#!/usr/bin/env python3
"""Integer ports of version-locked voice-control helpers; not a whole synth.

All arithmetic uses the firmware's tables and truncation. Envelope time units
remain internal units; caller cadence must be independently established.
"""
import struct


def signed32(value):
    return (value + 2**31) % 2**32 - 2**31


def clamp(value, low, high):
    return min(high, max(low, value))


class VoiceMath:
    def __init__(self, firmware):
        self.firmware = firmware

    def exp2_q16(self, exponent):
        """0x20102c: Q16 exponent -> unsigned Q16 scale."""
        exponent = signed32(exponent)
        whole = exponent >> 16
        if whole < -16:
            return 0
        if whole > 15:
            return 0xFFFFFFFF
        fraction = exponent & 0xFFFF
        index, residue = fraction >> 8, fraction & 255
        table = self.firmware.data
        a = struct.unpack_from('<H', table, 0x4076E4 + index * 2)[0]
        b = 65536 if index == 255 else struct.unpack_from('<H', table, 0x4076E4 + (index+1) * 2)[0]
        factor = 65536 + a + ((b-a)*residue >> 8)
        return min(0xFFFFFFFF, ((1 << (whole+16))*factor) >> 16)

    def modulation_product(self, intensity, source):
        """0x200fb4: signed product *331 >>15, saturated to signed16."""
        return clamp((signed32(intensity)*signed32(source)*331) >> 15, -32768, 32767)

    def eg_duration(self, base, modulation):
        """0x1fb02c: base time units scaled by 2**(modulation/4096)."""
        if modulation > 0 and base <= 7:
            base = 8
        scale = self.exp2_q16(modulation << 4)
        return min(0x7FFFFFFF, (base*scale) >> 16)

    def eg_curve_coefficient(self, curve, steps):
        """0x1fab3c: eleven curves, piecewise table interpolation."""
        if not 0 <= curve <= 10 or steps < 0:
            raise ValueError('Invalid EG curve or step count')
        f = self.firmware
        if steps <= 640:
            row = max(0, steps-1)
            return f.u32(0x3FD734 + 4*(row*11+curve))
        if steps < 6400:
            row, fraction = divmod(steps-640, 64)
            a = f.u32(0x404534 + 4*(row*11+curve))
            b = f.u32(0x404534 + 4*((row+1)*11+curve))
            return a + ((b-a)*fraction >> 6)
        a = f.u32(0x4054D8+curve*4)
        b = f.u32(0x4054D8+(curve+11)*4)
        if steps >= 230400:
            return b
        # ARM's signed division truncates toward zero, including negative slope.
        numerator = (b-a)*(steps-6400)
        return a + (abs(numerator)//224000)*(1 if numerator >= 0 else -1)

    def eg_level(self, level, intensity=0, source=0, minimum=0):
        """0x1faed0 / 0x1fae60: 0..99 level with optional AMS."""
        extra = 12*self.modulation_product(intensity, source) if intensity else 0
        return clamp(level*330+extra, minimum, 32767)

    def velocity_gain(self, velocity, intensity):
        """Gain-table portion of 0x1fa1a0, before other amp modulation."""
        centered=velocity-127 if intensity>0 else velocity
        index=max(0,255+((centered*intensity*667) >> 15))
        return struct.unpack_from('<H',self.firmware.data,0x4064EA+index*2)[0]

    def multisample_gain(self, level, modulation_a=0, modulation_b=0):
        """0x201674: slot level and two signed modulation offsets -> Q15."""
        a=32768+modulation_a*331
        b=32768+modulation_b*331
        product=(a*b) >> 15
        scaled=signed32(signed32(product*level)*129) >> 14
        return clamp(scaled,0,65535)

    def keyboard_tracking(self, parameters, note, amp=False):
        """0x2913ec (general) / 0x2915a8 (amp), including ramp infinities."""
        low,center,high,*ramps=struct.unpack('<3B4b',parameters[:7])
        ll,lc,hc,hh=ramps
        if note<low:terms=[(low-note,ll),(center-low,lc)]
        elif note>high:terms=[(note-high,hh),(high-center,hc)]
        elif note<center:terms=[(center-note,lc)]
        elif note>center:terms=[(note-center,hc)]
        else:return 0
        if any(r<=-100 for _,r in terms):return -4096
        if any(r>=100 for _,r in terms):return 4096
        def ramp(r):
            if not amp or r>=0:return r
            if r>=-95:return (r*134) >> 7
            return {-99:-118,-98:-169,-97:-297,-96:-594}[r]
        total=sum(distance*ramp(r) for distance,r in terms)
        limit,scale=(1188,225985) if amp else (5940,45197)
        if total>limit:return 4096
        if total < -limit:return -4096
        return (total*scale) >> 16

    def basic_mixer(self, parameters, sources):
        """Stateless AMS mixer types 0/1/2: A+B, Amt A×B, Offset."""
        kind=parameters[0]&7
        source_a,source_b=parameters[1],parameters[3]
        intensity_a=struct.unpack_from('<b',parameters,2)[0]
        intensity_b=struct.unpack_from('<b',parameters,4)[0]
        def scaled(intensity,source):return signed32(intensity*sources.get(source,0)*331) >> 15
        if kind==0:
            value=scaled(intensity_a,source_a)+scaled(intensity_b,source_b)
        elif kind==1:
            intensity=intensity_a+((scaled(intensity_b,source_b)*99) >> 12)
            value=scaled(intensity,source_a)
        elif kind==2:
            intensity,offset=struct.unpack_from('<2h',parameters,6)
            value=scaled(intensity,source_a)+((offset*165) >> 2)
        else:raise ValueError('Only stateless AMS mixer types 0,1,2 are ported')
        return clamp(value,-24576,24576)


class EnvelopeSegment:
    """0x1faf3c + 0x1fb0ac + 0x1fac24, with dynamic pedal scaling disabled.

    Fields mirror the packed ARM envelope state. Outputs are control levels;
    this does not model the downstream TG interpolation/audio gain stage.
    """
    def __init__(self, math, current, target, index, modulation, curve, stage=0):
        self.math = math
        self.level = current
        self.stage = stage
        if current >= target:
            self.stage += 1
        self.low = min(current, target)
        self.delta = abs(current-target)
        self.curve = curve
        self.total = math.eg_duration(math.firmware.u32(0x3FD5A4+index*4), modulation)
        self.remaining = self.total
        self.progress = 0
        self.asymptote = math.firmware.u32(0x405830+curve*4)
        self.coefficient = math.eg_curve_coefficient(curve, self.total//24)

    def step(self):
        self.progress = (self.progress + ((self.coefficient*(self.asymptote-(self.progress >> 2))) >> 29)) & 0xFFFFFFFF
        self.remaining -= 24
        progress = min(self.progress, 0x80000000)
        if 0 <= self.stage <= 9:
            if self.stage & 1:
                progress = 0x80000000-progress
            self.level = self.low + ((progress*self.delta) >> 31)
        return self.level, self.remaining <= 0
