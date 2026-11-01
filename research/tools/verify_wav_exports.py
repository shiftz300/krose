#!/usr/bin/env python3
"""Check every full WAV against its export manifest, including smpl loops."""
import hashlib
import json
import struct
import wave

from decode_korg_pcm import ROOT


def main():
    folder = ROOT / "output/Concert_SE_Grand_WAV"
    report = json.loads((folder / "decode_report.json").read_text())
    verified = []
    for record in report["samples"]:
        path = folder / record["file"]
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == record["sha256"], path
        assert data[:4] == b"RIFF" and len(data) == struct.unpack_from("<I", data, 4)[0] + 8, path
        with wave.open(str(path), "rb") as reader:
            assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate(), reader.getnframes()) == (
                2, 3, record["wav_rate_hz"], record["frames"]), path
            assert len(reader.readframes(reader.getnframes())) == record["frames"] * 6, path
        pos, sampler = 12, None
        while pos < len(data):
            tag, size = struct.unpack_from("<4sI", data, pos)
            if tag == b"smpl":
                sampler = data[pos + 8:pos + 8 + size]
            pos += 8 + size + (size & 1)
        assert pos == len(data) and sampler is not None, path
        assert struct.unpack_from("<I", sampler, 12)[0] == record["root_key_candidate"], path
        assert list(struct.unpack_from("<2I", sampler, 44)) == record["loop_inclusive"], path
        verified.append(record["file"])
    assert len(verified) == 84 and len(set(verified)) == 84
    assert {i for r in report["samples"] for i in r["native_ids"]} == set(range(56, 224))
    result = {"wav_count": len(verified), "sha256_and_riff_and_pcm24_pass": True,
              "root_and_loop_metadata_pass": True, "all_files_checked": verified,
              "prediction_saturations": sum(x["prediction_saturations"] for r in report["samples"] for x in r["statistics"]),
              "output_saturations": sum(x["output_saturations"] for r in report["samples"] for x in r["statistics"]),
              "total_file_bytes": sum((folder / r["file"]).stat().st_size for r in report["samples"])}
    path = ROOT / "research/derived/verification/wav-export-check.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS {len(verified)} stereo WAVs: source coverage, hashes, RIFF, PCM24, frame counts, root notes and loop metadata")
    print(f"Reconstruction saturations: prediction={result['prediction_saturations']}, output={result['output_saturations']}")


if __name__ == "__main__":
    main()
