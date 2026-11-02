# Krose 研究资料

**本轮逆向已于 2026-11-02 按用户要求结束。** 成果供后续插件实现使用，未解的音频问题继续保留。产品源码位于仓库的 `src/`，研究文件均位于本目录。

## 先看这里

- [研究交接与保留缺口](docs/REVERSE_HANDOFF.md)
- [图文报告 PDF：10 页、7 幅图](output/pdf/KROSS2-v1.2.4-plugin-report.pdf) · [可编辑正文](docs/architecture/PLUGIN_REPORT.md)
- [按主题排列的全部文档](docs/architecture/INDEX.md) · [研究工具索引](tools/README.md)
- [资源总索引](RESOURCES.md) · [历史进度](docs/PROGRESS.md)

## 插件主要证据

| 主题 | 阅读入口 |
| --- | --- |
| 采样与资源 | [PCM 解码](docs/ROM_DECODING.md) · [扩展采样](docs/architecture/EXPANSION_PCM.md) · [GM](docs/architecture/GM_PROGRAMS.md) |
| 选样与鼓组 | [原厂声部](docs/architecture/FACTORY_VOICE_CHAIN.md) · [鼓组发声](docs/architecture/DRUM_VOICE_CHAIN.md) |
| MIDI 与声部 | [MIDI 控制](docs/architecture/MIDI_PARAMETERS.md) · [单音/滑音](docs/architecture/MONO_LIVE.md) · [复音压力](docs/architecture/VOICE_PRESSURE.md) |
| 调制与刷新 | [EG](docs/architecture/ENVELOPES.md) · [LFO](docs/architecture/VOICE_LFO.md) · [AMS Mixer](docs/architecture/AMS_MIXERS.md) · [正常刷新](docs/architecture/VOICE_REFRESH.md) |
| 音乐发生器 | [琶音](docs/architecture/ARPEGGIATOR.md) · [步进](docs/architecture/STEP_SEQUENCER.md) · [鼓轨到声部](docs/architecture/DRUM_VOICE_PLAYBACK.md) |
| 滤波与效果 | [滤波控制](docs/FILTER_CONTROL.md) · [EQ](docs/architecture/EFFECT_EQ.md) · [效果路由](docs/architecture/EFFECT_ROUTING.md) · [加载状态](docs/architecture/EFFECT_LOAD_STATE.md) |
| 导入与引用 | [资源导入](docs/architecture/RESOURCE_IMPORT.md) · [引用重编号](docs/architecture/PROGRAM_RELOCATION.md) |
| 历史整机研究 | [阶段 01 架构](docs/architecture/README.md) · [归档范围与状态](docs/architecture/REVERSE_STATUS.md) |

## 目录

| 路径 | 内容 |
| --- | --- |
| `docs/` | 章节、正文、交接说明与图 |
| `tools/` | 脚本、模型、绘图与复核工具 |
| `derived/` | 解析结果、CSV、原指令及证据指纹 |
| `output/` | 当前 PDF、源 WAV 和研究试听 |
| `firmware/`、`libraries/`、`downloads/` | 既有固件、设备备份、扩展库和手册 |
| `archive/` | 历史快照与整理前版本 |
| `build/`、`tmp/` | 工作产物；有证据引用的文件保留 |

## 复核

```sh
python3 research/tools/firmware_runtime_verify.py
```

现有核验覆盖 86 份原 ARM 模块结果，并检查 54 份保护文件、当前报告与相关证据。具体边界见各章；主机候选和原机音频验收分别记录。

研究使用既有离线材料，产品实现与冻结资源保持原值。仓库发布文档、脚本、图表和最终 PDF；固件、采样、设备备份、派生证据与归档保留本地，相关链接供完整离线工作区使用。旧命令中的 `tools/`、`output/` 由兼容路径承接，见[工具索引](tools/README.md)。
