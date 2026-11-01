# Krose

基于 iPlug2 的独立采样乐器，目标宿主为 Ableton Live / VST3。当前包含原 Concert SE Grand 及其三种变体，并新增由共享采样库和 Program 参数驱动的板载钢琴、Celesta、DWGS Bells、弦乐及 Basic/Jazz 鼓组。

## 开发目录

- `src/`：音频引擎、DSP、插件界面。
- `assets/`：冻结的运行采样与控制参数，构建时校验 SHA-256。
- `tests/`：原生回归测试与独立原 ARM 期望数据。
- `cmake/`、`tools/`：产品构建支持；iPlug2 / VST3 SDK 的版本锁位于 `cmake/dependencies.json`。
- `research/`：全部原始资料、固件、完整 ROM、WAV、分析脚本和历史验证记录。
- `build/`：产品的依赖及可再生成构建结果。
- 相邻 `../krose-website/`：独立网页工程，已与插件构建分离。

## 构建与检查

普通引擎开发不需要研究依赖，也不读取固件：

```sh
cmake -S . -B build/engine -G Ninja -DCMAKE_BUILD_TYPE=Release -DSEGRAND_BUILD_PLUGIN=OFF
cmake --build build/engine -j 6
ctest --test-dir build/engine --output-on-failure
```

插件构建依赖已保留；重新获取时运行 `python3 tools/bootstrap_plugin.py`。完整步骤见 [插件文档](docs/PLUGIN.md)。**当前仍不复制或安装 VST3。**

[原生引擎结构与首批音色](docs/NATIVE_ARCHITECTURE.md) · [当前逆向进度](research/docs/PROGRESS.md) · [资源总索引](research/RESOURCES.md) · [目录职责](docs/PROJECT_LAYOUT.md) · [研究入口](research/README.md) · [网站仓库](https://github.com/shiftz300/krose-website)
