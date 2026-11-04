# Krose

[中文](README.zh-CN.md)

An iPlug2 sample instrument reconstructing KROSS 2 sounds, with macOS arm64 VST3 and standalone builds. The catalog contains 1,161 factory, GM and expansion Programs plus the compatible Concert entry. The fixed-size editor and preset browser share the product catalog and original category order.

The native editor uses IGraphics/NanoVG. Samples load per selected Program on a background thread, with a shared recent cache and pinned samples for existing voices. Playback continues during loading. See [sample loading and effects optimization](docs/SAMPLE_LOADING.md) for measured memory use and switching behavior.

Research resources are published in [krose-source](https://github.com/shiftz300/krose-source). The complete local repository is preserved in `../krose-source-2026-11-05.tar.zst`; its expanded directory and compatibility symlink have been removed. Frozen runtime assets, test fixtures and editor resources remain in this product workspace; normal builds do not require the archive.

## Build

Requires CMake 3.25+, Ninja, macOS Command Line Tools and the local frozen sample bundles. Firmware and large sample packs are not included in Git.

The plugin runtime does not use Python. Python 3 remains a development dependency for SDK preparation, UI asset tools, validation and packaging; CI also uses these scripts. Once dependencies and frozen assets are available, ordinary CMake builds do not invoke the research tools.

```sh
python3 tools/bootstrap_plugin.py
cmake --preset plugin
cmake --build --preset plugin
ctest --preset plugin
```

Use the `engine` preset for headless engine/tools builds and `sanitize` for ASan/UBSan. Bundles are written to `build/plugin/out/`. Run the native editor check with:

```sh
build/plugin/test-vst3-host build/plugin/out/Krose.vst3 --editor
```

[CI and installers](docs/RELEASE.md) · [Project structure](docs/PROJECT_LAYOUT.md) · [Audio architecture and limits](docs/NATIVE_ARCHITECTURE.md) · [Implementation status](docs/IMPLEMENTATION.md) · [Design reference](docs/design/README.md) · [Resource gaps](https://github.com/shiftz300/krose-source/blob/main/research/docs/architecture/RESOURCE_GAPS.md) · [Research handoff](https://github.com/shiftz300/krose-source/blob/main/research/docs/REVERSE_HANDOFF.md)
