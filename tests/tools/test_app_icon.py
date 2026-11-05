"""Reject stale or damaged precompiled icons before they enter an app bundle."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'app_icon', Path(__file__).resolve().parents[2] / 'tools/native-ui/compile_app_icon.py')
icon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(icon)


class PrecompiledIcon(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.source = root / 'Krose.icon'
        self.output = root / 'compiled'
        (self.source / 'Assets').mkdir(parents=True)
        self.output.mkdir()
        (self.source / 'icon.json').write_text('{"groups": []}')
        (self.source / 'Assets/K.png').write_bytes(b'foreground test fixture')
        # This exercises checksum validation, not Apple's catalog decoder.
        (self.output / 'Assets.car').write_bytes(b'compiled test fixture')
        self.manifest = {'format': 1, 'icon_name': 'Krose',
                         'source_sha256': icon.source_digest(self.source),
                         'assets_sha256': icon.digest(self.output / 'Assets.car')}
        self.write_manifest()

    def write_manifest(self):
        (self.output / 'manifest.json').write_text(json.dumps(self.manifest))

    def tearDown(self):
        self.temp.cleanup()

    def test_matching_data(self):
        icon.verify(self.source, self.output)

    def test_changed_artwork(self):
        (self.source / 'Assets/K.png').write_bytes(b'new artwork')
        with self.assertRaisesRegex(ValueError, 'changed'):
            icon.verify(self.source, self.output)

    def test_added_layer(self):
        (self.source / 'Assets/new.png').write_bytes(b'new layer')
        with self.assertRaisesRegex(ValueError, 'changed'):
            icon.verify(self.source, self.output)

    def test_corrupt_catalog(self):
        (self.output / 'Assets.car').write_bytes(b'damaged')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            icon.verify(self.source, self.output)

    def test_wrong_icon_name(self):
        self.manifest['icon_name'] = 'Other'
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            icon.verify(self.source, self.output)


if __name__ == '__main__':
    unittest.main()
