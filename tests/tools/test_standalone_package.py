"""Standalone archives must carry their own verified banks and only app payloads."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('standalone', Path(__file__).resolve().parents[2] / 'tools/release/package_standalone.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class StandalonePackage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'out'
        resources = self.source / 'Resources'
        resources.mkdir(parents=True)
        (self.source / 'Krose.exe').write_bytes(b'MZ executable')
        (self.source / 'Krose.vst3').mkdir()
        (self.source / 'Krose.vst3/private-plugin-file').write_bytes(b'not part of standalone')
        (resources / 'native-base@2x.png').write_bytes(b'image')
        for name, folder in package.BANKS.items():
            data = b'frozen samples: ' + name.encode()
            (resources / name).write_bytes(data)
            manifest = self.root / 'assets' / folder / 'manifest.json'
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'files': [{'file': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}]}))

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        return package.package(self.source, self.root / 'dist', 'windows-x64', '0.1.0', self.root)

    def test_complete_portable_without_plugin(self):
        archive = self.build()
        with zipfile.ZipFile(archive) as zipped:
            names = zipped.namelist()
            self.assertIn('Krose/Krose.exe', names)
            self.assertIn('Krose/Resources/Factory.samples', names)
            self.assertIn('Krose/Resources/SEGrand.samples', names)
            self.assertIn('Krose/README.txt', names)
            self.assertFalse(any('vst3' in name for name in names))
            for name in package.BANKS:
                self.assertEqual(zipped.read('Krose/Resources/' + name), (self.source / 'Resources' / name).read_bytes())

    def test_bad_bank_is_rejected_before_publishing(self):
        (self.source / 'Resources/Factory.samples').write_bytes(b'wrong bank')
        with self.assertRaisesRegex(ValueError, 'bank mismatch'):
            self.build()
        self.assertFalse((self.root / 'dist').exists())

    def test_missing_bank_is_rejected(self):
        (self.source / 'Resources/SEGrand.samples').unlink()
        with self.assertRaises(FileNotFoundError):
            self.build()

    def test_missing_editor_is_rejected(self):
        (self.source / 'Resources/native-base@2x.png').unlink()
        with self.assertRaisesRegex(ValueError, 'editor resources'):
            self.build()

    def test_wrong_executable_is_rejected(self):
        (self.source / 'Krose.exe').write_bytes(b'not a PE')
        with self.assertRaisesRegex(ValueError, 'executable'):
            self.build()


if __name__ == '__main__':
    unittest.main()
