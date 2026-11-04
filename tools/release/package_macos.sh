#!/bin/bash
set -euo pipefail
build_dir="$1"
version="$2"
app_archs=$(lipo -archs "$build_dir/out/Krose.app/Contents/MacOS/Krose")
plugin_archs=$(lipo -archs "$build_dir/out/Krose.vst3/Contents/MacOS/Krose")
[[ "$app_archs" == "$plugin_archs" ]]
case "$app_archs" in
  *arm64*x86_64*|*x86_64*arm64*) platform=macos-universal ;;
  arm64) platform=macos-arm64 ;;
  x86_64) platform=macos-x86_64 ;;
  *) echo "Unsupported architectures: $app_archs" >&2; exit 1 ;;
esac
stage="$build_dir/installer-root"
mkdir -p "$stage/Applications" "$stage/Library/Audio/Plug-Ins/VST3" dist
/usr/bin/ditto "$build_dir/out/Krose.app" "$stage/Applications/Krose.app"
/usr/bin/ditto "$build_dir/out/Krose.vst3" "$stage/Library/Audio/Plug-Ins/VST3/Krose.vst3"
for bundle in "$stage/Applications/Krose.app" "$stage/Library/Audio/Plug-Ins/VST3/Krose.vst3"; do
  codesign --force --sign - "$bundle"
  codesign --verify --deep --strict "$bundle"
done
pkgbuild --analyze --root "$stage" "$build_dir/installer-components.plist"
python3 - "$build_dir/installer-components.plist" <<'PYCODE'
import plistlib, sys
from pathlib import Path
p = Path(sys.argv[1])
components = plistlib.loads(p.read_bytes())
for component in components:
    component['BundleIsRelocatable'] = False
    component['BundleOverwriteAction'] = 'upgrade'
p.write_bytes(plistlib.dumps(components))
PYCODE
pkgbuild --component-plist "$build_dir/installer-components.plist" --root "$stage" --identifier dev.LocalInstruments.Krose.installer \
  --version "$version" --install-location / "dist/Krose-$version-$platform.pkg"
pkgutil --payload-files "dist/Krose-$version-$platform.pkg" > dist/macos-payload.txt
