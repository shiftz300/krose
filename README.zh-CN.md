# Krose

[English](README.md)

基于 iPlug2 的 KROSS 2 采样乐器，提供 macOS arm64 VST3 和独立程序。当前接入 1,161 个出厂／GM／扩展 Program，另保留 Concert 兼容入口；原厂分类顺序与固定尺寸界面共用同一套目录和源码。

原生界面使用 IGraphics／NanoVG。采样按当前音色在后台加载，近期缓存与仍在发声的旧音符共享采样；切换期间保留播放。机制、内存实测和效果优化见 [采样加载](docs/SAMPLE_LOADING.md)。

## 构建

需要 CMake 3.25+、Ninja、macOS Command Line Tools 和本地冻结采样包。固件及大型采样包不随 Git 仓库提供。

```sh
python3 tools/bootstrap_plugin.py
cmake --preset plugin
cmake --build --preset plugin
ctest --preset plugin
```

不构建 GUI 时使用 `engine` preset；内存检查使用 `sanitize` preset。产物位于 `build/plugin/out/`。原生窗口检查：

```sh
build/plugin/test-vst3-host build/plugin/out/Krose.vst3 --editor
```

[目录与模块边界](docs/PROJECT_LAYOUT.md) · [音频架构与已知限制](docs/NATIVE_ARCHITECTURE.md) · [实现进度](docs/IMPLEMENTATION.md) · [设计参考](docs/design/README.md) · [剩余资源复核](research/docs/architecture/RESOURCE_GAPS.md) · [研究交接](research/docs/REVERSE_HANDOFF.md)
