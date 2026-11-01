#!/usr/bin/env python3
"""Render matched-source dry/concert/warm/wide previews without editing sources."""
from layout import PRODUCT_ROOT
import array
import hashlib
import json
import math
import sys
import wave

from effects_runtime import Effects, PRESETS
from decode_korg_pcm import ROOT


def read_preview(path):
    with wave.open(str(path), "rb") as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (2, 2, 48000)
        raw = array.array("h", reader.readframes(reader.getnframes()))
    if sys.byteorder != "little":
        raw.byteswap()
    return array.array("f", (v/32768 for v in raw))


def write_pcm16(path, audio, gain):
    integers = array.array("h", (round(max(-1, min(32767/32768, v*gain))*32768) for v in audio))
    if sys.byteorder != "little":
        integers.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        out.writeframes(integers.tobytes())


def main():
    output = ROOT / "output/Concert_SE_Grand_Effects"
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "output/Concert_SE_Grand_WAV/previews/preview_ff_range.wav"
    dry = read_preview(source)
    dry.extend(array.array("f", [0])*(48000*2*4))
    versions = {"dry": array.array("f", dry)}
    for preset in PRESETS:
        audio = array.array("f", dry)
        with Effects(preset=preset) as effect:
            for start in range(0, len(audio)//2, 256):
                effect.process(audio, start, min(256, len(audio)//2-start))
        assert all(math.isfinite(v) for v in audio)
        versions[preset] = audio
    peak = max(max(map(abs, audio)) for audio in versions.values())
    gain = min(1, 10**(-1/20)/max(peak, 1e-20))
    records = []
    for name, audio in versions.items():
        path = output / (name + ".wav")
        write_pcm16(path, audio, gain)
        records.append({"name": name, "file": path.name, "controls": PRESETS.get(name),
                        "frames": len(audio)//2, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "peak_dbfs": 20*math.log10(max(map(abs, audio))*gain),
                        "rms_dbfs": 20*math.log10(math.sqrt(sum(v*v for v in audio)/len(audio))*gain)})
    comparison = array.array("f")
    for audio in versions.values():
        comparison.extend(audio)
        comparison.extend(array.array("f", [0])*(48000*2))
    write_pcm16(output / "comparison.wav", comparison, gain)
    # Additional listening aid: equalize RMS only in this explicitly labelled
    # comparison, so a brighter/louder EQ is not automatically preferred.
    rms = {name: math.sqrt(sum(v*v for v in audio)/len(audio)) for name,audio in versions.items()}
    target_rms = min(rms.values())
    matched = array.array('f')
    matched_gains = {}
    for name,audio in versions.items():
        level = target_rms / rms[name]
        matched_gains[name] = 20*math.log10(level)
        matched.extend(array.array('f',(v*level for v in audio)))
        matched.extend(array.array('f',[0])*(48000*2))
    write_pcm16(output / 'comparison_level_matched.wav', matched, gain)
    report = {"source": str(source.relative_to(PRODUCT_ROOT)), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "sample_rate_hz": 48000, "format": "stereo PCM16 listening copies",
              "added_tail_seconds": 4, "shared_gain_db": 20*math.log10(gain),
              "comparison_order": list(versions), "comparison_separator_seconds": 1,
              "comparison_sha256": hashlib.sha256((output / 'comparison.wav').read_bytes()).hexdigest(),
              "level_matched_comparison": {"file": 'comparison_level_matched.wav',
                  "additional_gain_db": matched_gains,
                  "sha256": hashlib.sha256((output / 'comparison_level_matched.wav').read_bytes()).hexdigest(),
                  "scope": 'RMS-matched comparison only; individual versions retain their shared gain'},
              "implementation_sources": {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (
                  'src/dsp/concert_effects.c', 'src/dsp/concert_effects.h',
                  'research/derived/firmware/KROSS2_V124/effects/007/concert-coefficients.json')},
              "scope": "Effects-only audition using already accepted dry sample previews; not a complete Program, envelope/filter or VST3 render",
              "eq_basis": "Original ARM-generated eight-band coefficients and recovered trim mapping",
              "reverb_basis": "Original independent 8-line Householder FDN approximation, 1.8 s reference target",
              "chorus_basis": "Approximate modulated delay, recovered 24/13 ms bases and 0.5 Hz opposite-phase triangle",
              "records": records}
    (output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"folder": str(output), "shared_gain_db": report["shared_gain_db"], "records": records}, indent=2))


if __name__ == "__main__":
    main()
