# Krose

[中文](README.zh-CN.md)

An iPlug2 sample instrument reconstructing KROSS 2 sounds, with macOS arm64 VST3 and standalone builds. The catalog contains 1,161 factory, GM and expansion Programs plus the compatible Concert entry. The fixed-size editor and preset browser share the product catalog and original category order.

## Build

Requires CMake 3.25+, Ninja, macOS Command Line Tools and the local frozen sample bundles. Firmware and large sample packs are not included in Git.

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

[Project structure](docs/PROJECT_LAYOUT.md) · [Audio architecture and limits](docs/NATIVE_ARCHITECTURE.md) · [Implementation status](docs/IMPLEMENTATION.md) · [Design reference](docs/design/README.md) · [Resource gaps](research/docs/architecture/RESOURCE_GAPS.md) · [Research handoff](research/docs/REVERSE_HANDOFF.md)
