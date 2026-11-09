"""Exercise safe dependency extraction on old and current Python tar APIs."""
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('bootstrap', Path(__file__).resolve().parents[2] / 'tools/bootstrap_plugin.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapArchive(unittest.TestCase):
    def archive(self, name, kind=tarfile.REGTYPE):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            item = tarfile.TarInfo(name)
            item.type, item.size = kind, 3 if kind == tarfile.REGTYPE else 0
            item.linkname = '../outside'
            archive.addfile(item, io.BytesIO(b'abc') if item.size else None)
        buffer.seek(0)
        return tarfile.open(fileobj=buffer)

    def test_verified_regular_payload_extracts(self):
        with tempfile.TemporaryDirectory() as root, self.archive('pin/subfolder/data.bin') as archive:
            members = bootstrap.archive_members(archive, 'pin/')
            bootstrap.extract_archive(archive, root, members)
            self.assertEqual((Path(root) / 'pin/subfolder/data.bin').read_bytes(), b'abc')

    def test_paths_must_stay_inside_expected_tree(self):
        for name in ('../outside', '/outside', 'pin/../outside', 'other/file'):
            with self.subTest(name=name), self.archive(name) as archive:
                with self.assertRaises(RuntimeError): bootstrap.archive_members(archive, 'pin/')

    def test_links_and_special_files_are_rejected_before_extracting(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind), self.archive('pin/file', kind) as archive:
                with self.assertRaises(RuntimeError): bootstrap.archive_members(archive, 'pin/')


if __name__ == '__main__':
    unittest.main()
