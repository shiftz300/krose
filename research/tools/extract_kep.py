#!/usr/bin/env python3
"""Decode and inspect the supplied EXPCM001 KEP, preserving native sample bytes.

This is an EXPCM001/KROSS 2 1.2.4 research extractor, not a general Korg
converter. Native sample compression is deliberately not mislabelled as WAV.
All variable layout counts and section checksums are validated before export.
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

from firmware_inspect import decompress_cmp
from probe_blowfish import KorgBlowfish

from layout import ROOT
EXPECTED_FIRMWARE_SHA256 = "3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54"
PCG_SOURCE = "https://github.com/DaBlick/PCG-Tools/blob/master/KorgKronosTools/Model/Kross2Specific/Synth/Kross2Program.cs"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def word_sum(data):
    if len(data) % 4:
        raise ValueError("Checksum input not word aligned")
    return sum(value[0] for value in struct.iter_unpack("<I", data)) & 0xFFFFFFFF


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def prepare_context(firmware):
    # This format uses a little-endian Blowfish variant, including its F().
    # The factory key material is decoded and interleaved at firmware 1ef190.
    initial = KorgBlowfish(firmware, b"KORG0002ABCDEFGHIJKLMNOP")

    def runtime_constant(offset):
        plain = initial.decrypt(firmware[offset:offset + 16])
        return bytes(plain[i // 2 + (8 if i & 1 else 0)] for i in range(16))

    suffix = runtime_constant(0x48EE54)
    salt = runtime_constant(0x48EE2C)
    codec = KorgBlowfish(firmware, b"KORG0002" + suffix)
    context = struct.pack("<18I", *codec.p) + struct.pack("<1024I", *codec.s)
    return codec, context, salt


def parse_sections(data, salt):
    if data[:4] != b"KORG":
        raise ValueError("KEP did not decode to KORG magic")
    header_expected = u32(data, 4)
    header_actual = (word_sum(data[8:64]) + word_sum(salt)) & 0xFFFFFFFF
    if header_expected != header_actual:
        raise ValueError("KEP header checksum mismatch")
    if data[64:68] != b"EXP1" or u32(data, 68) != 128:
        raise ValueError("Unsupported EXP1 header")
    sections = []
    pos = 192
    expected_tags = (b"PRM1", b"PCM1", b"1KBP", b"1KBA")
    for expected in expected_tags:
        tag = data[pos:pos + 4]
        if tag != expected:
            raise ValueError(f"Expected {expected!r} at {pos:#x}, found {tag!r}")
        if tag in (b"PRM1", b"PCM1"):
            header_size, size, checksum = struct.unpack_from("<III", data, pos + 4)
            if header_size != 16:
                raise ValueError("Unsupported PCM/PRM header length")
            count = stride = None
        else:
            header_size = 32
            size, checksum, count, stride = struct.unpack_from("<4I", data, pos + 4)
            if size != count * stride:
                raise ValueError("Invalid native resource bank count")
        payload_start = pos + header_size
        end = payload_start + size
        if end > len(data):
            raise ValueError("Truncated section")
        actual = word_sum(data[payload_start:end])
        if checksum != actual:
            raise ValueError(f"Section {tag!r} checksum mismatch")
        sections.append({"tag": tag.decode(), "offset": pos, "header_bytes": header_size,
                         "payload_offset": payload_start, "payload_bytes": size,
                         "checksum_expected": f"{checksum:08x}", "checksum_actual": f"{actual:08x}",
                         "checksum_pass": True, "count": count, "record_bytes": stride})
        pos = end
    if pos != len(data):
        raise ValueError("Unexpected trailing sections or bytes")
    return {"expected": f"{header_expected:08x}", "actual": f"{header_actual:08x}", "pass": True}, sections


def parse_library(data, sections, output):
    prm, pcm, prg, arp = sections
    prm_data = data[prm["payload_offset"]:prm["payload_offset"] + prm["payload_bytes"]]
    pcm_data = data[pcm["payload_offset"]:pcm["payload_offset"] + pcm["payload_bytes"]]
    sample_count, region_count, ms_count = struct.unpack_from("<3I", data, 0x9C)
    if sample_count * 64 + region_count * 20 + ms_count * 28 != len(prm_data):
        raise ValueError("Parameter table lengths do not match EXP1 counts")
    samples = []
    next_start = 0
    for i in range(sample_count):
        off = i * 64
        words = list(struct.unpack_from("<16I", prm_data, off))
        start, start2, loop, end = words[3:7]
        if not (start == next_start and start <= start2 <= end and start <= loop <= end < len(pcm_data)):
            raise ValueError(f"Invalid sample addresses in record {i}")
        native = pcm_data[start:end + 1]
        filename = f"native_samples/{i:03d}.kpcm"
        (output / filename).write_bytes(native)
        samples.append({"id": i, "native_file": filename, "native_bytes": len(native),
                        "sha256": digest(native), "descriptor_offset": prm["payload_offset"] + off,
                        "descriptor_hex": prm_data[off:off + 64].hex(), "descriptor_u32_le": words,
                        "start": start, "start2": start2, "loop_start": loop,
                        "end_inclusive": end, "loop_relative": loop - start,
                        "encoding": "Korg native format; PCM conversion unverified",
                        "sample_rate_hz": None})
        next_start = end + 1
    padding = pcm_data[next_start:]
    if len(padding) > 7:
        raise ValueError("Unexpected unreferenced PCM payload")
    region_offset = sample_count * 64
    regions = []
    for i in range(region_count):
        off = region_offset + i * 20
        raw = prm_data[off:off + 20]
        sample_id = struct.unpack_from("<H", raw)[0]
        if sample_id >= sample_count:
            raise ValueError("Region references nonexistent sample")
        regions.append({"index": i, "sample_id": sample_id, "raw_hex": raw.hex(),
                        "flags_raw": raw[2], "top_key": raw[3], "root_key_candidate": raw[4],
                        "tune_raw": struct.unpack_from("<b", raw, 5)[0],
                        "level_raw": struct.unpack_from("<b", raw, 6)[0],
                        "pan_raw": struct.unpack_from("<b", raw, 7)[0],
                        "remaining_u32_le": list(struct.unpack_from("<3I", raw, 8)),
                        "field_status": "Krome 20-byte mapping correspondence; audio behavior unverified"})
    ms_offset = region_offset + region_count * 20
    multisamples = []
    for i in range(ms_count):
        off = ms_offset + i * 28
        first, count = struct.unpack_from("<HH", prm_data, off)
        name = prm_data[off + 4:off + 28].decode("ascii").rstrip(" \0")
        if first + count > region_count:
            raise ValueError("Multisample region range invalid")
        entries = regions[first:first + count]
        if any(a["top_key"] > b["top_key"] for a, b in zip(entries, entries[1:])):
            raise ValueError("Multisample keys not ordered")
        multisamples.append({"id": i, "name": name, "region_first": first,
                             "region_count": count, "regions": entries})
    programs = []
    for i in range(prg["count"]):
        off = prg["payload_offset"] + prg["record_bytes"] * i
        raw = data[off:off + prg["record_bytes"]]
        name = raw[:24].decode("ascii").rstrip(" \0")
        file = f"programs/{i:03d}_{safe_name(name)}.bin"
        (output / file).write_bytes(raw)
        programs.append({"index": i, "name": name, "offset": off, "bytes": len(raw),
                         "sha256": digest(raw), "file": file})
    target = next(p for p in programs if p["name"] == "Concert SE Grand")
    raw = data[target["offset"]:target["offset"] + target["bytes"]]
    oscillators = []
    selected = set()
    # The two 380-byte OSC structures contain four 8-byte MS selections.
    # These offsets are supported by cross-preset comparisons; remain marked
    # as inferred until measured against a hardware edit or a complete spec.
    for osc, off in enumerate((0x564, 0x6E0), 1):
        slots = []
        for slot in range(4):
            pos = off + 8 * slot
            enable, bank, number, level = struct.unpack_from("<BBHB", raw, pos)
            item = {"slot": slot + 1, "program_offset": pos, "raw_hex": raw[pos:pos + 8].hex(),
                    "enabled_candidate": bool(enable & 1), "bank_raw": bank,
                    "number_raw": number, "level_candidate": level,
                    "interpretation_status": "inferred from manual bank ordering and cross-preset comparisons"}
            if enable & 1 and bank == 5:
                left = 2 * number
                pair = multisamples[left:left + 2]
                if len(pair) != 2:
                    raise ValueError("Invalid stereo optional bank selection")
                item["multisample_pair_candidate"] = [ms["name"] for ms in pair]
                item["multisample_ids_candidate"] = [ms["id"] for ms in pair]
                for ms in pair:
                    selected.update(r["sample_id"] for r in ms["regions"])
            slots.append(item)
        threshold_off = off + 32
        oscillators.append({"oscillator": osc, "multisamples": slots,
                            "bottom_velocity_candidates": [u32(raw, threshold_off + 4 * j) for j in range(3)],
                            "velocity_and_crossfade_raw_hex": raw[threshold_off:threshold_off + 20].hex()})
    target_dir = output / "Concert_SE_Grand"
    target_dir.mkdir(exist_ok=True)
    (target_dir / "program.bin").write_bytes(raw)
    (target_dir / "program.hex.txt").write_text("\n".join(
        f"{off:04x}: {raw[off:off + 16].hex(' ')}" for off in range(0, len(raw), 16)) + "\n")
    fields = {"name": target["name"], "program_index": target["index"],
              "native_program_bytes": len(raw), "native_program_sha256": digest(raw),
              "confirmed_parameters": {"oscillator_mode": {"value": "Double", "raw": raw[1288] & 7,
                                        "offset": 1288, "bits": "2:0", "source": PCG_SOURCE},
                  "category": {"value": 0, "offset": 1298, "bits": "4:0", "raw": raw[1298] & 31},
                  "subcategory": {"value": 0, "offset": 1298, "bits": "7:5", "raw": raw[1298] >> 5}},
              "oscillator_selection_candidates": oscillators,
              "candidate_sample_ids": sorted(selected), "candidate_native_sample_count": len(selected),
              "candidate_native_sample_bytes": sum(samples[i]["native_bytes"] for i in selected),
              "unresolved": ["Native compressed sample decoding and exact rate",
                             "Hardware confirmation of inferred OSC selection and velocity fields",
                             "Remaining filter, envelope, modulation and FX parameter semantics",
                             "A/B validation against the user's instrument"]}
    if fields["confirmed_parameters"]["oscillator_mode"]["raw"] != 1:
        raise ValueError("Unexpected target oscillator mode")
    write_json(target_dir / "parameters.json", fields)
    write_json(target_dir / "sample_manifest.json", {
        "status": "Candidate subset from inferred stereo bank mapping; bytes are checksum-validated native originals",
        "samples": [{**samples[i], "native_file": "../" + samples[i]["native_file"]} for i in sorted(selected)]})
    (output / "sections" / "PRM1.bin").write_bytes(prm_data)
    write_json(output / "programs.json", programs)
    write_json(output / "multisamples.json", multisamples)
    write_json(output / "samples.json", samples)
    return {"sample_count": sample_count, "region_count": region_count, "multisample_count": ms_count,
            "program_count": len(programs), "arpeggio_count": arp["count"],
            "pcm_padding_bytes": len(padding), "pcm_padding_hex": padding.hex(),
            "concert_se_grand": fields}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kep", type=Path, default=ROOT / "EXPCM001/EXPCM001.KEP")
    parser.add_argument("--firmware-cmp", type=Path, default=ROOT / "research/firmware/KROSS2_V124/KROSS2SY/KROSSAPP.CMP")
    parser.add_argument("--output", type=Path, default=ROOT / "output/kep-analysis")
    args = parser.parse_args()
    original = args.kep.read_bytes()
    original_hash = digest(original)
    firmware = decompress_cmp(args.firmware_cmp)
    if EXPECTED_FIRMWARE_SHA256 and digest(firmware) != EXPECTED_FIRMWARE_SHA256:
        raise ValueError("Firmware layout only verified for official KROSS2 1.2.4")
    output = args.output.resolve()
    if args.kep.resolve().is_relative_to(output):
        raise ValueError("Output directory must not contain the source KEP")
    for name in ("native_samples", "programs", "sections"):
        (output / name).mkdir(parents=True, exist_ok=True)
    codec, context, salt = prepare_context(firmware)
    head = codec.decrypt(original[:64])
    if head[:4] != b"KORG":
        raise ValueError("Unsupported KEP factory key")
    context_file = output / "sections/expanded_context.bin"
    context_file.write_bytes(context)
    executable = ROOT / "build/kep_blowfish"
    executable.parent.mkdir(parents=True, exist_ok=True)
    source = ROOT / "tools/kep_blowfish.c"
    if not executable.exists() or source.stat().st_mtime > executable.stat().st_mtime:
        subprocess.run(["cc", "-O3", "-Wall", "-Wextra", "-o", str(executable), str(source)], check=True)
    decoded_path = output / "EXPCM001.dec.bin"
    subprocess.run([str(executable), str(context_file), str(args.kep.resolve()), str(decoded_path)], check=True)
    data = decoded_path.read_bytes()
    if data[:64] != head:
        raise ValueError("C decoder differs from Python/firmware-validated implementation")
    header_check, sections = parse_sections(data, salt)
    result = parse_library(data, sections, output)
    if digest(args.kep.read_bytes()) != original_hash:
        raise ValueError("Source KEP changed during extraction")
    report = {"source": str(args.kep.resolve()), "source_bytes": len(original),
              "source_sha256_before": original_hash, "source_sha256_after": digest(args.kep.read_bytes()),
              "source_unchanged": True, "firmware_sha256": digest(firmware),
              "firmware_byte_sum_pass": True, "decoded_sha256": digest(data),
              "header_checksum": header_check, "sections": sections, **result}
    write_json(output / "extraction_report.json", report)
    print(json.dumps({"output": str(output), "source_unchanged": True,
                      "checksums_passed": 5, "sample_count": result["sample_count"],
                      "multisample_count": result["multisample_count"],
                      "candidate_target_samples": result["concert_se_grand"]["candidate_native_sample_count"],
                      "wav_conversion_verified": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
