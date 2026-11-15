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
        manifests = {}
        for name, manifest_path in package.BANKS.items():
            data = b'frozen samples: ' + name.encode()
            directory = self.source if name == package.OASYS else resources
            (directory / name).write_bytes(data)
            manifests.setdefault(manifest_path, []).append(
                {'file': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        for manifest_path, entries in manifests.items():
            manifest = self.root / 'assets' / manifest_path
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({'files': entries}))

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
            self.assertIn('Krose/EXPCM001.pcm', names)
            self.assertNotIn('Krose/Resources/EXPCM001.pcm', names)
            self.assertIn('Krose/README.txt', names)
            self.assertFalse(any('vst3' in name for name in names))
            for name in package.BANKS:
                relative = Path(name) if name == package.OASYS else Path('Resources') / name
                self.assertEqual(zipped.read('Krose/' + relative.as_posix()),
                                 (self.source / relative).read_bytes())

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
