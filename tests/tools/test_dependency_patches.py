"""Dependency preparation must preserve pinned inputs and fail on drift."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("dependency_patches", Path(__file__).resolve().parents[2] / "tools/prepare_plugin_dependencies.py")
dependencies = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dependencies)


class DependencyView(unittest.TestCase):
    def test_source_is_preserved_and_reconfigure_does_not_touch_outputs(self):
        with tempfile.TemporaryDirectory(prefix="krose dependency view ") as root:
            source, output = Path(root) / "pinned", Path(root) / "generated"
            name = "IPlug/IPlugStructs.h"
            header = source / name
            header.parent.mkdir(parents=True)
            header.write_text('// UTF-8: 音色\nstrcpy(utf8, _utf8);\n', encoding="utf-8")
            (source / "unmodified.txt").write_bytes(b"unchanged\r\n")
            script = source / "run.sh"
            script.write_text("#!/bin/sh\nexit 0\n")
            script.chmod(0o755)
            (source / ".git").mkdir()
            (source / ".git/config").write_text("local checkout metadata")
            original = header.read_bytes()
            with patch.object(dependencies, "PATCHED", {name}):
                dependencies.prepare(source, output)
                modified = (output / name).read_bytes()
                self.assertNotEqual(modified, original)
                self.assertIn("音色".encode("utf-8"), modified)
                self.assertEqual(header.read_bytes(), original)
                self.assertEqual((output / "unmodified.txt").read_bytes(), b"unchanged\r\n")
                self.assertFalse((output / ".git").exists())
                if os.name != "nt":
                    self.assertEqual((output / "run.sh").stat().st_mode & 0o777, 0o755)
                stamp = (output / name).stat().st_mtime_ns
                dependencies.prepare(source, output)
                self.assertEqual((output / name).stat().st_mtime_ns, stamp)

    def test_drift_fails_before_writing_partial_view(self):
        with tempfile.TemporaryDirectory() as root:
            source, output = Path(root) / "pinned", Path(root) / "generated"
            source.mkdir()
            with patch.object(dependencies, "PATCHED", {"IPlug/IPlugStructs.h"}):
                (source / "IPlug").mkdir()
                (source / "IPlug/IPlugStructs.h").write_text("upstream changed")
                with self.assertRaisesRegex(ValueError, "Pinned dependency changed"):
                    dependencies.prepare(source, output)
                self.assertFalse(output.exists())

    def test_view_cannot_overwrite_pinned_tree(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)
            for output in (source, source / "generated", source.parent):
                with self.assertRaisesRegex(ValueError, "separate"):
                    dependencies.prepare(source, output)


if __name__ == "__main__":
    unittest.main()
