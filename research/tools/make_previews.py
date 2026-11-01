#!/usr/bin/env python3
"""Make short 48 kHz / PCM16 listening copies on macOS using afconvert.

These are dry samples, attenuated by 3 dB with a short ending fade.
Full PCM24 exports and their loop metadata are never modified.
"""
import array
import json
import subprocess
import wave
from pathlib import Path

from decode_korg_pcm import ROOT, write_wav


def read_pcm24(path):
    with wave.open(str(path), "rb") as reader:
        assert reader.getnchannels() == 2 and reader.getsampwidth() == 3
        rate = reader.getframerate()
        raw = reader.readframes(reader.getnframes())
    values = array.array("i", (int.from_bytes(raw[i:i + 3], "little", signed=True) * 256
                               for i in range(0, len(raw), 3)))
    return values, rate


def fragment(audio, rate, seconds):
    count = min(len(audio) // 2, round(rate * seconds))
    fade = min(round(rate * 0.08), count)
    result = array.array("i", [0]) * (count * 2)
    gain = 10 ** (-3 / 20)
    for frame in range(count):
        level = gain * min(1, (count - 1 - frame) / max(1, fade))
        result[frame * 2] = round(audio[frame * 2] * level)
        result[frame * 2 + 1] = round(audio[frame * 2 + 1] * level)
    return result


def main():
    folder = ROOT / "output/Concert_SE_Grand_WAV"
    report = json.loads((folder / "decode_report.json").read_text())
    output = folder / "previews"
    scratch = ROOT / "build/previews"
    output.mkdir(exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    records = []

    def save(name, audio, rate, sources, sequence=None):
        temporary = scratch / name
        destination = output / name
        write_wav(temporary, audio, 2, rate)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@48000", "-r", "127",
                        str(temporary), str(destination)], check=True)
        records.append({"file": name, "sources": sources, "sequence": sequence,
                        "processing": "-3 dB, 80 ms ending fade, CoreAudio resampling to 48000 Hz and PCM16"})

    for layer in ("mf", "f", "ff"):
        source = next(x for x in report["samples"] if x["layer"] == layer and x["root_key_candidate"] == 62)
        audio, rate = read_pcm24(folder / source["file"])
        save(f"preview_{layer}_midi062_D4.wav", fragment(audio, rate, 4), rate, [source["file"]])
    sequence, sources, combined = [], [], array.array("i")
    for note in (24, 48, 62, 77, 96):
        source = next(x for x in report["samples"] if x["layer"] == "ff" and x["root_key_candidate"] == note)
        audio, rate = read_pcm24(folder / source["file"])
        sequence.append({"midi": note, "start_seconds": len(combined) / 2 / rate})
        combined.extend(fragment(audio, rate, 1.5))
        combined.extend(array.array("i", [0]) * (round(rate * 0.3) * 2))
        sources.append(source["file"])
    save("preview_ff_range.wav", combined, rate, sources, sequence)
    (output / "manifest.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} listening previews to {output}")


if __name__ == "__main__":
    main()
