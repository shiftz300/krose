#!/usr/bin/env python3
"""Verify host EQ response, state continuity, decay and measured compute cost."""
import array
import argparse
import cmath
import json
import math
import platform
import random
import statistics
import subprocess
import time

from effects_runtime import Effects, concert_coefficients, load_library
from probe_effect_coefficients import response
from decode_korg_pcm import ROOT


def impulse(seconds=4):
    audio = array.array("f", [0])*(48000*2*seconds)
    audio[0] = 0.5
    return audio


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sanitize', action='store_true')
    args=parser.parse_args()
    identity = [1.0, 0.0, 0.0, 0.0, 0.0]*8
    random_source = random.Random(3101)
    signal = array.array("f", (random_source.uniform(-0.2,0.2) for _ in range(40000)))
    bypass = array.array("f", signal)
    with Effects(identity, reverb_wet=0, chorus_wet=0) as effects:
        effects.process(bypass)
    assert bypass.tobytes() == signal.tobytes()
    whole, partitioned = array.array("f", signal), array.array("f", signal)
    with Effects(preset="wide") as effect:
        effect.process(whole)
        effect.reset()
        sizes = (1, 7, 16, 63, 128, 257)
        start = 0
        i = 0
        while start < len(partitioned)//2:
            frames = min(sizes[i % len(sizes)],len(partitioned)//2-start)
            effect.process(partitioned,start,frames)
            start += frames
            i += 1
    assert whole.tobytes() == partitioned.tobytes()
    assert all(math.isfinite(x) for x in whole)
    coefficients, trim = concert_coefficients()
    dry_impulse = impulse(2)
    with Effects(reverb_wet=0, chorus_wet=0) as effect:
        effect.process(dry_impulse)
    assert max(map(abs,dry_impulse[1::2])) == 0
    response_checks = []
    for frequency in (30,60,80,300,1600,7300,13400,20000):
        z = cmath.exp(-2j*math.pi*frequency/48000)
        power = 1+0j
        actual = 0j
        for x in dry_impulse[::2]:
            actual += 2*x*power
            power *= z
        expected = complex(trim)
        for offset in range(0,40,5):
            expected *= response(coefficients[offset:offset+5], frequency)
        error_db = 20*math.log10(abs(actual/expected))
        assert abs(error_db) < 0.002, (frequency,error_db)
        response_checks.append({"frequency_hz":frequency,"error_db":error_db})
    decay = impulse(5)
    with Effects(identity, reverb_wet=0.5, chorus_wet=0) as effect:
        effect.process(decay)
    assert all(math.isfinite(x) for x in decay)
    assert max(map(abs,decay)) <= 1
    early_energy = sum(x*x for x in decay[4800:48000])
    late_energy = sum(x*x for x in decay[48000*2*3:48000*2*4])
    assert early_energy > 1e-4
    assert late_energy / early_energy < 1e-7
    # Continuous stereo input exercises multiple complete LFO and ring cycles.
    wide = array.array('f', (0.1*math.sin(2*math.pi*(220 if ch == 0 else 331)*n/48000)
                            for n in range(48000*5) for ch in range(2)))
    with Effects(preset="wide") as effect:
        effect.process(wide)
        assert all(math.isfinite(x) for x in wide)
        assert max(map(abs,wide)) < 2
    for controls in ({"reverb_seconds":float("nan")},{"chorus_wet":1},{"tone_lowpass_hz":-1}):
        try:
            Effects(**controls)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid control accepted")
    # Report compute time, not a claim about Ableton scheduling or plugin latency.
    block = array.array("f", (random_source.uniform(-0.1,0.1) for _ in range(512)))
    timings=[]
    with Effects(preset="wide") as effect:
        for i in range(400):
            start = time.perf_counter()
            effect.process(block)
            timings.append(time.perf_counter()-start)
            # Do not feed the effect its previous output during the next run.
            for j in range(len(block)):
                block[j] = 0.01 if j % 2 == 0 else -0.01
    timings.sort()
    if args.sanitize:
        binary=ROOT/'build/effects/test-sanitize'
        subprocess.run(['cc','-std=c99','-O1','-g','-fsanitize=address,undefined',
            '-fno-omit-frame-pointer','-I',str(ROOT/'src/dsp'),str(ROOT/'src/dsp/concert_effects.c'),
            str(ROOT/'tools/test_concert_effects_sanitize.c'),'-o',str(binary),'-lm'],check=True)
        subprocess.run([str(binary)],check=True)
    result={"status":"PASS", "sample_rate_hz":48000,
            "identity_bypass_exact":True,"block_partition_and_reset_exact":True,
            "eq_channel_isolation":True,"eq_response_checks":response_checks,
            "reverb_late_to_early_energy_ratio":late_energy/early_energy,
            "finite_outputs_and_invalid_control_rejection":True,
            "address_and_undefined_behavior_sanitizers":args.sanitize,
            "memory_bytes":load_library().concert_effects_memory_bytes(),
            "compute":{"architecture":platform.machine(),"block_frames":256,
                "block_duration_us":256/48000*1e6,
                "median_us_including_ctypes":statistics.median(timings)*1e6,
                "p99_us_including_ctypes":timings[math.ceil(len(timings)*0.99)-1]*1e6,
                "scope":"Local release C core + ctypes only; no DAW, voice engine, oversampling or realtime scheduling test"}}
    path=ROOT/'research/derived/verification/effects-prototype-check.json'
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
