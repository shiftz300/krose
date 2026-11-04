"""Check real CMake generation and error paths without training or private PCM."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform in ('darwin', 'win32'), 'Supported release toolchains')
class PGOConfiguration(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='krose-pgo-config-')
        self.root = Path(self.temporary.name)
        self.assets = self.root/'assets'
        for name in ('concert-se-grand', 'program-library'):
            target = self.assets/name
            shutil.copytree(ROOT/'assets'/name, target, ignore=shutil.ignore_patterns('*.samples'))
            manifest = json.loads((target/'manifest.json').read_text())
            for item in manifest['files']:
                if item['file'].endswith('.samples'):
                    data = b'CONFIGURATION CHECK ONLY'
                    (target/item['file']).write_bytes(data)
                    item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            (target/'manifest.json').write_text(json.dumps(manifest))

    def tearDown(self):
        self.temporary.cleanup()

    def configure(self, *options, error=None, generator='Ninja'):
        command = ['cmake', '-S', str(ROOT), '-B', str(self.root/'build'), '-G', generator,
                   '-DCMAKE_BUILD_TYPE=Release', '-DSEGRAND_BUILD_PLUGIN=OFF',
                   '-DSEGRAND_BUILD_TOOLS=OFF', '-DBUILD_TESTING=OFF',
                   '-DSEGRAND_ASSET_DIR='+str(self.assets/'concert-se-grand'),
                   '-DKROSE_FACTORY_ASSET_DIR='+str(self.assets/'program-library')]
        if os.name == 'nt':
            command += ['-DCMAKE_C_COMPILER=clang-cl', '-DCMAKE_CXX_COMPILER=clang-cl', '-DCMAKE_LINKER=lld-link']
        result = subprocess.run(command+list(options), capture_output=True, text=True)
        if error:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error, result.stdout+result.stderr)
            return []
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return json.loads((self.root/'build/compile_commands.json').read_text())

    def test_release_uses_automatically_generated_profile(self):
        commands = self.configure()
        flags = '\n'.join(item['command'] for item in commands)
        self.assertIn('-fprofile-use=', flags)
        self.assertIn('-fprofile-generate=', flags)
        self.assertIn('-fprofile-update=atomic', flags)
        self.assertIn('profile-instr-out-of-date', flags)
        self.assertIn('ProfileStamp.h', flags)
        self.assertIn('/FI' if os.name == 'nt' else '-include', flags)

    def test_opt_out(self):
        commands = self.configure('-DKROSE_ENABLE_PGO=OFF')
        self.assertFalse(any('-fprofile-' in item['command'] for item in commands))

    def test_debug_has_no_training_or_profile_flags(self):
        commands = self.configure('-DCMAKE_BUILD_TYPE=Debug')
        self.assertFalse(any('-fprofile-' in item['command'] for item in commands))

    def test_multi_config_debug_build_never_runs_trainer(self):
        self.configure(generator='Ninja Multi-Config')
        result = subprocess.run(['cmake', '--build', str(self.root/'build'),
                                 '--config', 'Debug', '--target', 'krose-core', '--parallel', '2'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertNotIn('Trained 36', result.stdout)
        self.assertFalse(list((self.root/'build').rglob('*.profraw')))
        executable = 'krose-pgo-train.exe' if os.name == 'nt' else 'krose-pgo-train'
        self.assertFalse([p for p in (self.root/'build').rglob(executable) if p.is_file()])

    def test_sanitizer_has_no_profile_flags(self):
        if os.name == 'nt':
            self.skipTest('ASan/UBSan preset uses the macOS toolchain')
        commands = self.configure('-DSEGRAND_SANITIZE=ON')
        self.assertFalse(any('-fprofile-' in item['command'] for item in commands))

    def test_missing_profile_merger_fails_explicitly(self):
        self.configure('-DKROSE_LLVM_PROFDATA='+str(self.root/'absent'), error='PGO requires llvm-profdata')

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS architecture guard')
    def test_universal_requires_native_training_per_slice(self):
        self.configure('-DCMAKE_OSX_ARCHITECTURES=arm64;x86_64', error='PGO requires a native build per architecture')


if __name__ == '__main__':
    unittest.main()
