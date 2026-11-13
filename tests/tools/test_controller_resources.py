"""Exercise bundled adapters and extension boundaries without MIDI hardware/Live."""
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_ableton_controller import ROOT, installer, module

builder = module('controller_resources', ROOT / 'tools/build_controller_resources.py')
catalog = module('controller_catalog', ROOT / 'controllers/shared/keylab-essential-mk3/catalog.py')


class Resources(unittest.TestCase):
    def test_bundle_contains_ready_to_copy_adapter_and_templates(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'Controllers'
            builder.build(target)
            builder.verify(target)
            script = target / 'ableton/Remote Scripts/Krose_KeyLab_Essential'
            order, programs = catalog.load_catalog(script)
            self.assertEqual(len(order), len(programs))
            self.assertEqual(programs[1][:2], ['A000', 'Kross Grand Piano 1'])
            self.assertTrue((target / 'templates/standalone/generic-keyboard.json').is_file())
            self.assertTrue((target / 'templates/ableton/Krose_Generic_Template/surface.py').is_file())
            self.assertTrue((target / 'schema.json').is_file())
            # The bundled installer must work without a repository or sample assets.
            bundled = module('bundled_controller_installer', target / 'install_ableton_controller.py')
            library = Path(root) / 'User Library 音色'
            installed = bundled.install(library)
            self.assertEqual(catalog.load_catalog(installed), (order, programs))
            stamp = (target / 'manifest.json').stat().st_mtime_ns
            builder.build(target)
            self.assertEqual((target / 'manifest.json').stat().st_mtime_ns, stamp)

    def test_kit_verification_rejects_modified_files_and_escape_paths(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'Controllers'
            builder.build(target)
            manifest = target / 'manifest.json'
            data = json.loads(manifest.read_text())
            (target / 'README.md').write_text('modified')
            with self.assertRaises(ValueError): builder.verify(target)
            builder.build(target)
            data['files'][0]['path'] = '../outside'
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError): builder.verify(target)
            builder.build(target)
            (target / 'old-script.py').write_text('# stale executable code')
            with self.assertRaises(ValueError): builder.verify(target)

    def test_catalog_rejects_duplicate_indices_and_malformed_records(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            def write(order, programs):
                (folder / 'program_order.json').write_text(json.dumps(order))
                (folder / 'programs.json').write_text(json.dumps(programs))
            for order, programs in [([0, 0], [['A', 'Name', 'PIANO']] * 2),
                                     ([True], [['A', 'Name', 'PIANO']]),
                                     ([0], [['Name']]), ([0], [['A', 'X' * 257, 'PIANO']])]:
                write(order, programs)
                with self.assertRaises(ValueError): catalog.load_catalog(folder)
            write([0], [['A', 'Name', 'PIANO']])
            self.assertEqual(catalog.load_catalog(folder)[0], [0])
            (folder / 'program_order.json').write_bytes(b' ' * (4 * 1024 * 1024 + 1))
            with self.assertRaises(ValueError): catalog.load_catalog(folder)

    def test_failed_source_copy_preserves_installed_script_and_configuration(self):
        with tempfile.TemporaryDirectory() as root:
            library = Path(root)
            target = installer.install(library)
            marker = target / 'custom.py'
            marker.write_text('# preserve this customization')
            original = (library / installer.CONFIG_PATH).read_bytes()
            with patch.object(installer, 'copy_script', side_effect=OSError('copy failed')):
                with self.assertRaises(OSError): installer.install(library)
            self.assertEqual(marker.read_text(), '# preserve this customization')
            self.assertEqual((library / installer.CONFIG_PATH).read_bytes(), original)

    def test_invalid_configuration_does_not_remove_installed_script(self):
        with tempfile.TemporaryDirectory() as root:
            library = Path(root)
            target = installer.install(library)
            marker = target / 'custom.py'
            marker.write_text('# user code')
            config = library / installer.CONFIG_PATH
            config.write_text(' ' * (2 * 1024 * 1024 + 1))
            with self.assertRaises(ValueError): installer.install(library)
            self.assertEqual(marker.read_text(), '# user code')

    def test_configuration_entry_types_are_validated_before_writes(self):
        with tempfile.TemporaryDirectory() as root:
            path = installer.install_parameter_configuration(Path(root))
            data = json.loads(path.read_text())
            for entry in [None, {'id': True}, {'id': -1}, {'id': 1, 'x-slot': 'invalid'}]:
                data['groups'][0]['parameters'] = [entry]
                path.write_text(json.dumps(data))
                before = path.read_bytes()
                with self.assertRaises(ValueError): installer.install_parameter_configuration(Path(root))
                self.assertEqual(path.read_bytes(), before)

    @unittest.skipUnless(os.name == 'nt', 'Windows directory junction regression')
    def test_windows_junction_cannot_redirect_installation(self):
        with tempfile.TemporaryDirectory() as root:
            library, outside = Path(root) / 'library', Path(root) / 'outside'
            library.mkdir(); outside.mkdir()
            marker = outside / 'keep.txt'; marker.write_text('preserved')
            link = library / 'Remote Scripts'
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], check=True, capture_output=True)
            try:
                with self.assertRaises(ValueError): installer.install(library)
                self.assertEqual(list(outside.iterdir()), [marker])
            finally:
                os.rmdir(link)  # Remove only the junction itself, never its target.

    @unittest.skipIf(os.name == 'nt', 'Symlink creation requires additional Windows permissions')
    def test_symlink_destinations_cannot_redirect_installation(self):
        with tempfile.TemporaryDirectory() as root:
            library, outside = Path(root) / 'library', Path(root) / 'outside'
            library.mkdir(); outside.mkdir()
            marker = outside / 'keep.txt'; marker.write_text('preserved')
            (library / 'Remote Scripts').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): installer.install(library)
            self.assertEqual(list(outside.iterdir()), [marker])
            (library / 'Remote Scripts').unlink()
            (library / 'Defaults').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): installer.install_parameter_configuration(library)
            self.assertEqual(list(outside.iterdir()), [marker])


if __name__ == '__main__': unittest.main()
