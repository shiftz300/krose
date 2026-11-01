#!/usr/bin/env python3
"""Research-only ctypes bridge. Future audio hosts can call the C API directly."""
import array
import ctypes
import json
import subprocess
import sys

from decode_korg_pcm import ROOT


def load_library():
    build = ROOT / "build/effects"
    build.mkdir(parents=True, exist_ok=True)
    destination = build / ("concert_effects.dylib" if sys.platform == "darwin" else "concert_effects.so")
    source = ROOT / "src/dsp/concert_effects.c"
    header = ROOT / "src/dsp/concert_effects.h"
    if not destination.exists() or destination.stat().st_mtime < max(source.stat().st_mtime, header.stat().st_mtime):
        subprocess.run(["cc", "-std=c99", "-O3", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                        str(source), "-o", str(destination), "-lm"], check=True)
    library = ctypes.CDLL(str(destination))
    library.concert_effects_create.argtypes = [ctypes.c_double, ctypes.POINTER(ctypes.c_double)] + [ctypes.c_double]*5
    library.concert_effects_create.restype = ctypes.c_void_p
    library.concert_effects_process.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_size_t]
    library.concert_effects_process.restype = None
    library.concert_effects_reset.argtypes = [ctypes.c_void_p]
    library.concert_effects_reset.restype = None
    library.concert_effects_destroy.argtypes = [ctypes.c_void_p]
    library.concert_effects_destroy.restype = None
    library.concert_effects_memory_bytes.restype = ctypes.c_size_t
    return library


def concert_coefficients():
    path = ROOT / "research/derived/firmware/KROSS2_V124/effects/007/concert-coefficients.json"
    if not path.exists():
        raise FileNotFoundError("Run tools/probe_effect_coefficients.py first")
    report = json.loads(path.read_text())
    coefficients = [value for slot in report["slots"] for band in slot["bands"]
                    for value in band["host"]["b0_b1_b2_feedback1_feedback2"]]
    trim = report["slots"][0]["trim_linear"] * report["slots"][1]["trim_linear"]
    return coefficients, trim


PRESETS = {
    "concert": {"reverb_seconds": 1.8, "reverb_wet": 0.15, "chorus_wet": 0.0, "tone_lowpass_hz": 0.0},
    "warm": {"reverb_seconds": 1.5, "reverb_wet": 0.12, "chorus_wet": 0.0, "tone_lowpass_hz": 8500.0},
    "wide": {"reverb_seconds": 2.6, "reverb_wet": 0.23, "chorus_wet": 0.18, "tone_lowpass_hz": 0.0},
}


class Effects:
    def __init__(self, coefficients=None, trim=None, preset="concert", **controls):
        self.library = load_library()
        self.handle = None
        if coefficients is None:
            coefficients, default_trim = concert_coefficients()
            if trim is None:
                trim = default_trim
        elif trim is None:
            trim = 1.0
        if len(coefficients) != 40:
            raise ValueError("Expected eight biquads")
        config = {**PRESETS[preset], **controls}
        unknown = set(config) - set(PRESETS["concert"])
        if unknown:
            raise ValueError(f"Unknown controls: {unknown}")
        self.handle = self.library.concert_effects_create(48000, (ctypes.c_double*40)(*coefficients), trim,
            config["reverb_seconds"], config["reverb_wet"], config["chorus_wet"], config["tone_lowpass_hz"])
        if not self.handle:
            raise ValueError("Invalid or unstable effect configuration")

    def process(self, audio, start=0, frames=None):
        if not self.handle or not isinstance(audio, array.array) or audio.typecode != "f" or len(audio) % 2:
            raise ValueError("Expected an open effect and interleaved stereo array('f')")
        if frames is None:
            frames = len(audio)//2 - start
        if start < 0 or frames < 0 or (start+frames)*2 > len(audio):
            raise ValueError("Audio range outside buffer")
        if frames:
            buffer = (ctypes.c_float*(frames*2)).from_buffer(audio, start*8)
            self.library.concert_effects_process(self.handle, buffer, frames)

    def reset(self):
        if not self.handle:
            raise ValueError("Effect is closed")
        self.library.concert_effects_reset(self.handle)

    def close(self):
        if self.handle:
            self.library.concert_effects_destroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
