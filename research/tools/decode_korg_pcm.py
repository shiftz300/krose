#!/usr/bin/env python3
"""Export Concert SE Grand candidate multisamples as stereo PCM24 WAV.

Reconstruction follows the KROSS 2 1.2.4 encoder's own feedback path.
Exact TG01 arithmetic, playback-rate interpretation and the complete Program
remain subject to hardware comparison. No filter, FX or Program emulation.
Only the Python standard library and a C99 compiler are needed.
"""
import argparse
import array
import ctypes
import hashlib
import json
import math
import struct
import subprocess
import sys
from pathlib import Path

from layout import ROOT
SOURCE = ROOT / "output/kep-analysis"
FW = ROOT / "research/derived/firmware/KROSS2_V124/KROSSAPP.bin"
FW_SHA = "3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54"
LUT_OFFSET = 0x3FD180
LIMIT = 2147483647


def load_lut(path=FW):
    firmware = path.read_bytes()
    if hashlib.sha256(firmware).hexdigest() != FW_SHA:
        raise ValueError("Unsupported firmware: decoder offsets are version-specific")
    return struct.unpack_from("<256h", firmware, LUT_OFFSET)


def decode_reference(source, a1, a2, lut):
    """Slow, independent Python reference used for C/native validation."""
    previous = older = 0
    result = array.array("i")
    counts = [0, 0]
    for code in source:
        value = a1 * previous + a2 * older
        prediction = (abs(value) // 16384) * (-1 if value < 0 else 1)
        counts[0] += abs(prediction) > LIMIT
        prediction = max(-LIMIT, min(LIMIT, prediction))
        value = prediction + lut[(code + 128) & 255] * 65536
        counts[1] += abs(value) > LIMIT
        value = max(-LIMIT, min(LIMIT, value))
        result.append(value)
        older, previous = previous, value
    return result, counts


class Decoder:
    def __init__(self, lut, build_dir):
        build_dir.mkdir(parents=True, exist_ok=True)
        library = build_dir / ("korg_pcm_decode.dylib" if sys.platform == "darwin" else "korg_pcm_decode.so")
        subprocess.run(["cc", "-std=c99", "-O3", "-Wall", "-Wextra", "-Werror", "-shared",
                        "-fPIC", str(ROOT / "tools/korg_pcm_decode.c"), "-o", str(library)], check=True)
        self.library = ctypes.CDLL(str(library))
        self.function = self.library.korg_pcm_decode
        self.function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int16,
                                  ctypes.c_int16, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self.function.restype = None
        self.lut = (ctypes.c_int16 * 256)(*lut)

    def decode(self, source, a1, a2):
        result = array.array("i", [0]) * len(source)
        if result.itemsize != 4:
            raise RuntimeError("32-bit C int required")
        pointer = (ctypes.c_int32 * len(result)).from_buffer(result)
        counts = (ctypes.c_uint64 * 2)()
        self.function(source, len(source), a1, a2, self.lut, pointer, counts)
        return result, list(counts)


def write_wav(path, audio, channels, rate, root=None, loop=None):
    """PCM24, retaining the high 24 bits of reconstructed Q16 PCM16."""
    if len(audio) % channels:
        raise ValueError("Nonintegral frame count")
    if sys.byteorder != "little":
        audio = audio[:]
        audio.byteswap()
    raw = audio.tobytes()
    payload = bytearray(len(audio) * 3)
    payload[0::3], payload[1::3], payload[2::3] = raw[1::4], raw[2::4], raw[3::4]

    def chunk(tag, content):
        return tag + struct.pack("<I", len(content)) + content + (b"\0" if len(content) & 1 else b"")

    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * channels * 3, channels * 3, 24)
    chunks = chunk(b"fmt ", fmt)
    if root is not None:
        smpl = struct.pack("<9I", 0, 0, round(1e9 / rate), root, 0, 0, 0, int(loop is not None), 0)
        if loop is not None:
            if not 0 <= loop[0] <= loop[1] < len(audio) // channels:
                raise ValueError("Invalid WAV loop points")
            smpl += struct.pack("<6I", 0, 0, loop[0], loop[1], 0, 0)
        chunks += chunk(b"smpl", smpl)
    chunks += chunk(b"data", payload)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WAVE" + chunks)


def note_name(midi):
    return ("C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B")[midi % 12] + str(midi // 12 - 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=ROOT / "output/Concert_SE_Grand_WAV")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    lut = load_lut()
    decoder = Decoder(lut, ROOT / "build")
    samples = json.loads((args.input / "samples.json").read_text())
    multisamples = json.loads((args.input / "multisamples.json").read_text())
    target = json.loads((args.input / "Concert_SE_Grand/parameters.json").read_text())
    selected = set(target["candidate_sample_ids"])
    records = []
    for left_ms in multisamples[::2]:
        right_ms = multisamples[left_ms["id"] + 1]
        if not all(r["sample_id"] in selected for r in left_ms["regions"]):
            continue
        if len(left_ms["regions"]) != len(right_ms["regions"]):
            raise ValueError("Stereo region counts disagree")
        layer = ("mf", "f", "ff")[(left_ms["id"] - 2) // 2]
        folder = args.output / layer
        folder.mkdir(exist_ok=True)
        for left_region, right_region in zip(left_ms["regions"], right_ms["regions"]):
            pair = [samples[r["sample_id"]] for r in (left_region, right_region)]
            decoded, statistics = [], []
            pitches, coefficients = [], []
            for descriptor in pair:
                source = (args.input / descriptor["native_file"]).read_bytes()
                if hashlib.sha256(source).hexdigest() != descriptor["sha256"]:
                    raise ValueError("Native sample checksum changed")
                raw = bytes.fromhex(descriptor["descriptor_hex"])
                if struct.unpack_from("<I", raw, 4)[0] != 0x11000000:
                    raise ValueError("Unsupported native encoding flag")
                a1, a2 = struct.unpack_from("<2h", raw, 8)
                poles = ((a1 / 16384) ** 2 + 4 * a2 / 16384)
                radius = math.sqrt(-a2 / 16384) if poles < 0 else max(abs((a1 / 16384 + math.sqrt(poles)) / 2), abs((a1 / 16384 - math.sqrt(poles)) / 2))
                if radius >= 1:
                    raise ValueError("Unstable predictor")
                audio, counts = decoder.decode(source, a1, a2)
                decoded.append(audio)
                statistics.append({"prediction_saturations": counts[0], "output_saturations": counts[1],
                                   "peak_dbfs": 20 * math.log10(max(map(abs, audio), default=1) / 2**31)})
                pitches.append(struct.unpack_from("<h", raw)[0])
                coefficients.append([a1, a2])
            if pitches[0] != pitches[1] or len(decoded[0]) != len(decoded[1]) or pair[0]["loop_relative"] != pair[1]["loop_relative"]:
                raise ValueError("Stereo descriptors disagree")
            exact_rate = 48000 * 2 ** (pitches[0] / 1536)
            rate = round(exact_rate)
            root = left_region["root_key_candidate"]
            name = f"{layer}_midi{root:03d}_{note_name(root)}.wav"
            stereo = array.array("i", [0]) * (len(decoded[0]) * 2)
            stereo[0::2], stereo[1::2] = decoded
            loop = [pair[0]["loop_relative"], len(decoded[0]) - 1]
            write_wav(folder / name, stereo, 2, rate, root, loop)
            records.append({"file": f"{layer}/{name}", "layer": layer,
                            "native_ids": [p["id"] for p in pair], "root_key_candidate": root,
                            "top_key": left_region["top_key"], "region_raw": [left_region["raw_hex"], right_region["raw_hex"]],
                            "frames": len(decoded[0]), "wav_rate_hz": rate,
                            "playback_rate_candidate_hz": exact_rate, "pitch_field": pitches[0],
                            "loop_inclusive": loop, "coefficients_q14": coefficients, "statistics": statistics,
                            "sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest()})
        print(f"Exported {layer}: {len(left_ms['regions'])} stereo WAVs", flush=True)
    report = {"status": "Firmware-encoder-feedback reconstruction; TG01 output and complete Program not yet hardware-validated",
              "decoder_basis": {"firmware_sha256": FW_SHA, "lut_offset": hex(LUT_OFFSET),
                                "lut_sha256": hashlib.sha256(struct.pack("<256h", *lut)).hexdigest(),
                                "prediction_code": "0x1f5254..0x1f5304", "feedback_code": "0x1f55b0..0x1f5698",
                                "formula": "sat32(trunc0((a1*y[n-1]+a2*y[n-2])/16384)) + lut[signed8+128]*65536, then sat32",
                                "saturation_range": [-LIMIT, LIMIT], "initial_history": [0, 0]},
              "rate_status": "Inferred 1536 log2 units per octave relative to 48000 Hz; rounded to integral WAV rate",
              "rate_formula": "48000 * 2 ** (signed16_pitch / 1536)",
              "format": "stereo PCM24 WAV, no normalization, no FX; smpl root/loop metadata inferred from native descriptors",
              "scope": "84 candidate stereo samples (mf, f, ff), inferred Program selection; mp and Damper omitted",
              "stereo_wav_count": len(records), "mono_source_count": len(records) * 2, "samples": records}
    (args.output / "decode_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {len(records)} stereo files to {args.output}")


if __name__ == "__main__":
    main()
