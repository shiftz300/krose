"""Exercise guards against combining different resources, versions or slices."""
import importlib.util
import plistlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('merge_macos', Path(__file__).resolve().parents[2]/'tools/release/merge_macos.py')
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


class UniversalGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.arm = Path(self.temporary.name)/'arm64/Krose.app'
        self.intel = Path(self.temporary.name)/'x86_64/Krose.app'
        for bundle in (self.arm, self.intel):
            (bundle/'Contents/Resources').mkdir(parents=True)
            (bundle/'Contents/MacOS').mkdir()
            (bundle/'Contents/Resources/data').write_bytes(b'same frozen assets')
            (bundle/'Contents/MacOS/Krose').write_bytes(b'native executable')
            (bundle/'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='dev.LocalInstruments.Krose', CFBundleVersion='1')))

    def tearDown(self):
        self.temporary.cleanup()

    def test_matching_resources_and_native_slices(self):
        with patch.object(merge, 'output', side_effect=['arm64', 'x86_64']):
            merge.validate_pair(self.arm, self.intel)

    def test_changed_resource_is_rejected_before_lipo(self):
        (self.intel/'Contents/Resources/data').write_bytes(b'different bank')
        with patch.object(merge, 'output') as lipo, self.assertRaisesRegex(ValueError, 'resources differ'):
            merge.validate_pair(self.arm, self.intel)
        lipo.assert_not_called()

    def test_version_mismatch(self):
        (self.intel/'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='dev.LocalInstruments.Krose', CFBundleVersion='2')))
        with self.assertRaisesRegex(ValueError, 'metadata differs'):
            merge.validate_pair(self.arm, self.intel)

    def test_wrong_slice(self):
        with patch.object(merge, 'output', return_value='x86_64'), self.assertRaisesRegex(ValueError, 'Expected native arm64'):
            merge.validate_pair(self.arm, self.intel)


if __name__ == '__main__':
    unittest.main()
