"""Integrity checks against the actual supplied bank, not synthetic audio."""
import hashlib
import json
import unittest
from pathlib import Path

from extract_kep import ROOT, parse_sections, prepare_context


class ExtractionIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = ROOT / "output/kep-analysis"
        cls.report = json.loads((cls.out / "extraction_report.json").read_text())
        cls.data = (cls.out / "EXPCM001.dec.bin").read_bytes()
        fw = (ROOT / "research/derived/firmware/KROSS2_V124/KROSSAPP.bin").read_bytes()
        cls.codec, _, cls.salt = prepare_context(fw)

    def test_original_file_unchanged(self):
        source = Path(self.report["source"]).read_bytes()
        actual = hashlib.sha256(source).hexdigest()
        self.assertEqual(actual, "ca8e77bac45e731a09b50a4e9446ec72d8fad81a423e243cac34c9ae3e75be8c")
        self.assertEqual(actual, self.report["source_sha256_before"])
        self.assertEqual(actual, self.report["source_sha256_after"])

    def test_all_five_kep_checksums(self):
        header, sections = parse_sections(self.data, self.salt)
        self.assertTrue(header["pass"])
        self.assertEqual([s["tag"] for s in sections], ["PRM1", "PCM1", "1KBP", "1KBA"])
        self.assertTrue(all(s["checksum_pass"] for s in sections))

    def test_python_and_c_decoder_agree(self):
        source = Path(self.report["source"]).read_bytes()
        positions = [0, 192, 0x5BF0, 0x100000, 0x2D33360, 0x2D43F80]
        for start in positions:
            with self.subTest(offset=start):
                self.assertEqual(self.codec.decrypt(source[start:start + 64]), self.data[start:start + 64])

    def test_corrupt_pcm_is_rejected(self):
        modified = bytearray(self.data)
        modified[0x5C00 + 4096] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            parse_sections(modified, self.salt)

    def test_truncated_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Truncated"):
            parse_sections(self.data[:-8], self.salt)

    def test_all_samples_reassemble_exact_pcm_payload(self):
        samples = json.loads((self.out / "samples.json").read_text())
        self.assertEqual(len(samples), 272)
        pcm = self.report["sections"][1]
        combined = bytearray()
        for sample in samples:
            native = (self.out / sample["native_file"]).read_bytes()
            self.assertEqual(hashlib.sha256(native).hexdigest(), sample["sha256"])
            self.assertEqual(len(native), sample["native_bytes"])
            combined.extend(native)
        combined.extend(bytes.fromhex(self.report["pcm_padding_hex"]))
        self.assertEqual(combined, self.data[pcm["payload_offset"]:pcm["payload_offset"] + pcm["payload_bytes"]])

    def test_target_program_is_exact_bank_record(self):
        target = self.report["concert_se_grand"]
        raw = (self.out / "Concert_SE_Grand/program.bin").read_bytes()
        self.assertEqual(len(raw), 2144)
        self.assertEqual(raw[:24].decode().strip(), "Concert SE Grand")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), target["native_program_sha256"])
        pg = self.report["sections"][2]
        offset = pg["payload_offset"] + 2 * pg["record_bytes"]
        self.assertEqual(raw, self.data[offset:offset + len(raw)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
