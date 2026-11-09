#!/usr/bin/env python3
"""Install the project-owned script in Live's User Library, never its app bundle."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
import zipfile
import os
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "controllers" if (ROOT / "controllers").is_dir() else Path(__file__).resolve().parent
CONFIG_PATH = Path("Defaults/Plug-In Configurations/VST3s/maincore/Krose/Default.appc")
LEGACY_CONFIG_PATH = Path("Defaults/Plug-In Configurations/VST3s/Local Instruments/Krose/Default.appc")


def managed_path(library, relative):
    """Reject redirection inside the explicitly selected User Library."""
    root = Path(library).resolve()
    path = root
    for part in Path(relative).parts:
        if part in ("..", "/"):
            raise ValueError("Invalid managed path")
        path = path / part
        if path.is_symlink():
            raise ValueError("Managed controller path is a symlink; left unchanged")
    return path


def read_configuration(path, with_bytes=False):
    with path.open('rb') as stream:
        data = stream.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Ableton configuration exceeds size limit")
    try:
        value = json.loads(data)
        if not isinstance(value, dict): raise ValueError("Configuration must be an object")
        return (value, data) if with_bytes else value
    except (ValueError, RecursionError) as error:
        raise ValueError("Invalid Ableton configuration; left unchanged") from error


def copy_script(source, target):
    for file in source.rglob('*'):
        if '__pycache__' in file.parts or file.suffix == '.pyc': continue
        if file.is_symlink(): raise ValueError("Controller source symlinks are not supported")
        if file.is_file():
            destination = target / file.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, destination)


def install_parameter_configuration(library):
    """Add only missing Krose parameter IDs, preserving existing customization."""
    template = read_configuration(SUPPORT / "ableton" / CONFIG_PATH)
    target = managed_path(library, CONFIG_PATH)
    # Preserve layouts installed before the public manufacturer name changed.
    source = target if target.exists() else managed_path(library, LEGACY_CONFIG_PATH)
    data, original = read_configuration(source, True) if source.exists() else (template, None)
    if (data.get("id") != template["id"] or data.get("version") != "1.0" or
            not isinstance(data.get("device-id"), str) or
            data.get("device-id", "").split("?")[0] != template["device-id"].split("?")[0]):
        raise ValueError("Existing Krose parameter configuration has an incompatible identity; left unchanged")
    groups = data.get("groups")
    if not isinstance(groups, list) or not all(isinstance(g, dict) and isinstance(g.get("parameters"), list) for g in groups):
        raise ValueError("Invalid Krose parameter groups; left unchanged")
    parameters = [p for g in groups for p in g["parameters"]]
    if len(parameters) > 128 or any(not isinstance(p, dict) or type(p.get("id")) is not int or
            not 0 <= p["id"] <= 0x7fffffff or type(p.get("x-slot", 0)) is not int or
            not 0 <= p.get("x-slot", 0) <= 4096 for p in parameters):
        raise ValueError("Invalid Krose parameter entries; left unchanged")
    existing = {p["id"] for p in parameters}
    missing = [p.copy() for p in template["groups"][0]["parameters"] if p["id"] not in existing]
    if len(existing) + len(missing) > 128:
        raise ValueError("Krose configuration would exceed Live's 128-parameter limit; left unchanged")
    if missing:
        if not groups:
            groups.append({"name": "Default", "parameters": []})
        group = next((g for g in groups if g.get("name") == "Default"), groups[0])
        first_column = max((p.get("x-slot", 0) for p in group["parameters"]), default=-1) + 1
        for i, p in enumerate(missing):
            p.update({"x-slot": first_column + i // 4, "y-slot": i % 4})
        group["parameters"].extend(missing)
    content = (json.dumps(data, indent=2) + "\n").encode()
    if target.exists() and original is not None and data == json.loads(original):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if original is not None:
        backup = managed_path(library, Path("Krose Controller Backups") / ("configuration-" + str(time.time_ns()) + ".appc"))
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(original)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".krose-config-", delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def install(library):
    target = managed_path(library, "Remote Scripts/Krose_KeyLab_Essential")
    source = SUPPORT / "ableton/Remote Scripts/Krose_KeyLab_Essential"
    # Build the replacement completely before touching an installed script.
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".krose-stage-") as folder:
        stage = Path(folder) / target.name
        stage.mkdir()
        copy_script(source, stage)
        if not (stage / "program_order.json").exists():
            order = json.loads((ROOT / "assets/program-library/FactoryBrowser.json").read_text())["order"]
            (stage / "program_order.json").write_text(json.dumps(order) + "\n", encoding="utf-8")
            catalog = json.loads((ROOT / "assets/program-library/FactoryPrograms.json").read_text())
            (stage / "programs.json").write_text(json.dumps([row[:3] for row in catalog]) + "\n", encoding="utf-8")
        install_parameter_configuration(library)
        backup = None
        if target.exists():
            backup = managed_path(library, Path("Krose Controller Backups") / ("script-" + str(time.time_ns())))
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.rename(backup)
        try:
            stage.rename(target)
        except BaseException:
            if backup is not None and not target.exists(): backup.rename(target)
            raise
    return target


if __name__ == "__main__":
    default = Path.home() / ("Music" if sys.platform == "darwin" else "Documents") / "Ableton/User Library"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-library", type=Path, default=default)
    parser.add_argument("--archive", type=Path, help="Build a drag-and-drop ZIP instead of installing")
    args = parser.parse_args()
    if args.archive:
        with tempfile.TemporaryDirectory(prefix="krose-controller-package-") as root:
            target = install(Path(root))
            args.archive.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(args.archive, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(target.rglob("*")):
                    if file.is_file():
                        archive.write(file, str(file.relative_to(target.parent)))
                archive.write(Path(root) / CONFIG_PATH, str(CONFIG_PATH))
                archive.write(ROOT / "docs/CONTROLLERS.md" if (ROOT / "docs/CONTROLLERS.md").exists() else SUPPORT / "CONTROLLERS.md", "CONTROLLERS.md")
                archive.write(ROOT / "LICENSE" if (ROOT / "LICENSE").exists() else SUPPORT / "LICENSE", "LICENSE")
        print(args.archive)
    else:
        print(install(args.user_library))
