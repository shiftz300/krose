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
CONFIG_PATH = Path("Defaults/Plug-In Configurations/VST3s/maincore/Krose/Default.appc")
LEGACY_CONFIG_PATH = Path("Defaults/Plug-In Configurations/VST3s/Local Instruments/Krose/Default.appc")


def install_parameter_configuration(library):
    """Add only missing Krose parameter IDs, preserving existing customization."""
    template = json.loads((ROOT / "integrations/ableton" / CONFIG_PATH).read_text())
    target = library / CONFIG_PATH
    # Preserve layouts installed before the public manufacturer name changed.
    source = target if target.exists() else library / LEGACY_CONFIG_PATH
    original = source.read_bytes() if source.exists() else None
    data = json.loads(original) if original is not None else template
    if (data.get("id") != template["id"] or data.get("version") != "1.0" or
            data.get("device-id", "").split("?")[0] != template["device-id"].split("?")[0]):
        raise ValueError("Existing Krose parameter configuration has an incompatible identity; left unchanged")
    groups = data.get("groups")
    if not isinstance(groups, list) or not all(isinstance(g, dict) and isinstance(g.get("parameters"), list) for g in groups):
        raise ValueError("Invalid Krose parameter groups; left unchanged")
    existing = {p["id"] for g in groups for p in g["parameters"]}
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
        backup = library / "Krose Controller Backups" / ("configuration-" + str(time.time_ns()) + ".appc")
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
    install_parameter_configuration(library)
    source = ROOT / "integrations/ableton/Krose_KeyLab_Essential"
    target = library / "Remote Scripts/Krose_KeyLab_Essential"
    if target.exists():
        backup = library / "Krose Controller Backups" / (time.strftime("%Y%m%d-%H%M%S") + "-" + str(time.time_ns()))
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, backup)
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    order = json.loads((ROOT / "assets/program-library/FactoryBrowser.json").read_text())["order"]
    (target / "program_order.json").write_text(json.dumps(order) + "\n")
    catalog = json.loads((ROOT / "assets/program-library/FactoryPrograms.json").read_text())
    (target / "programs.json").write_text(json.dumps([row[:3] for row in catalog]) + "\n")
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
                archive.write(ROOT / "docs/CONTROLLERS.md", "CONTROLLERS.md")
                archive.write(ROOT / "LICENSE", "LICENSE")
        print(args.archive)
    else:
        print(install(args.user_library))
