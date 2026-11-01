# Krose · KROSS 2 音色研究与插件

**最新原机 ROM 结果**：已导出 4,068 个完整原机采样、恢复 42 套鼓组，并制作可部署到 Cloudflare Pages 的极简试弹网站。[网页部署说明](output/Krose_Web_README.md) · [网站目录](output/Krose_Web/) · [ROM 解码与验证](docs/ROM_DECODING.md)。网页使用有损试听资源；原始 PCM24 WAV 保留，插件未安装。

目标：从用户提供的 EXPCM001 中研究 Concert SE Grand，重建听感尽可能接近、可扩展出相似变体的钢琴，最终在 Ableton Live 中以 VST3 脱离硬件运行。用户已明确：不要求完整复刻乐器或逐位模拟芯片，以实际听感和宿主可用性验收。

当前阶段：已用 **iPlug2 做成 Krose 0.1.0 VST3 与独立程序**，整合 84 个立体声采样、三层力度、64 复音、延音踏板、恢复出的八段 EQ 与近似 Chorus/Hall，提供 Concert / Warm / Wide 三种变体。官方 VST3 验证器 47 项、无界面插件宿主发声/状态测试及引擎内存检查通过；用户于 2026-11-01 认可当前听感，不要求真琴 A/B；Ableton 的实际界面与项目使用尚未手工验收。

**当前继续固件研究，暂不复制、安装 VST3。** 已补齐全部 135 项效果资源、2269 个参数，新增可复用固件索引；音量/包络数学移植已对照原 ARM，并扫描 32512 组 Concert 控制上下文。控制调度与 TG 命令时序已继续核对，已验证的力度、双 OSC 键盘跟踪、AMS 和多段包络现已接入播放器。新一轮已接入经原 ARM 核对的 Filter A/B 控制和 Filter EG，音频滤波的 Hz/Q 映射仍为可校准近似。最新试听在 `output/Concert_SE_Grand_Filter/`，此前 `output/Concert_SE_Grand_Control/` 和 `output/SEGrand/` 保留原样。

- [原机 A–F 768 个预置音色选择](output/Factory_Sound_Selection/README.md)
- [原机 PRELOAD 恢复、参数和波形引用](docs/FACTORY_SOUNDS.md)
- [原机 ROM 采样取得路径与本轮读取协议研究](docs/ROM_SAMPLES.md)
- [整库描述符、候选64MiB范围与USB备份入口](docs/ROM_LIBRARY_LAYOUT.md)
- [完整USB备份分析、16组Pad WAV与启动Flash读取线索](docs/USB_BACKUP_ANALYSIS.md)
- [诊断与MIDI命令追踪、TG校验读取的离线验证](docs/ROM_MIDI_DISPATCH.md)
- [ROM恢复进展、公开方案对照与离线导出原型](docs/ROM_RECOVERY_PROGRESS.md)
- [PCG备份的用途与当前刷写边界](docs/PCG_BACKUP_SCOPE.md)
- [第一阶段固件注入：身份探针、Mac步骤及回退](docs/FIRMWARE_INJECTION_STAGE_A.md)
- [身份探针v2：真实8字节队列边界修正与当前进展](docs/FIRMWARE_INJECTION_STAGE_A_V2.md)
- [第二阶段：ROM小窗口、RAM检查与单块传输](docs/ROM_SINGLE_BLOCK.md)
- [原机64MiB TG ROM实机采集完成：镜像与校验记录](docs/ROM_ACQUISITION.md)
- [Krose 紧凑音色库、共享波形与压缩实测](docs/RESOURCE_DESIGN.md)
- [可复用固件索引与完整效果目录](docs/FIRMWARE_MAP.md)
- [力度、键盘跟踪、AMS 与包络控制](docs/VOICE_CONTROL.md)
- [控制调度、TG 平滑与新播放器验证](docs/VOICE_TIMING.md)
- [Filter A/B、AMS 与字段标签修正](docs/FILTER_CONTROL.md)
- [最新滤波播放器开关对照试听](output/Concert_SE_Grand_Filter/README.md)
- [此前无滤波控制模型试听](output/Concert_SE_Grand_Control/README.md)

- [插件使用、构建与已知近似](docs/PLUGIN.md)
- 既有原型：[VST3](output/SEGrand/SEGrand.vst3)、[独立程序](output/SEGrand/SEGrand.app)、[音符引擎试听](output/SEGrand/instrument-preview.wav)

- [研究记录与结论状态](docs/RESEARCH.md)
- [官方固件地址与算法](docs/FIRMWARE.md)
- [播放速率、力度层、滤波和包络参数](docs/PROGRAM.md)
- [效果通路、具体设置与 DSP 实现位置](docs/EFFECTS.md)
- [芯片证据与实际上传格式](docs/HARDWARE.md)
- [重建目标、近似边界和验收方法](docs/RECONSTRUCTION.md)
- [第一版效果试听](output/Concert_SE_Grand_Effects/README.md)
- [来源及适用范围](docs/SOURCES.md)
- [WAV 与试听说明](output/Concert_SE_Grand_WAV/README.md)
- [原生容器提取记录](output/kep-analysis/README.md)

## 目录约定

产品代码与研究数据现已在构建依赖上分离：普通编译只读 `src/`、冻结的 `assets/` 和测试数据，不读固件、研究报告或 `output/`。详见 [研究与产品边界、资源更新流程](docs/PROJECT_LAYOUT.md)。

```text
EXPCM001/                         用户原件，保持原文件名与内容
docs/                             人可读研究记录、证据与未解问题
tools/                            构建辅助、离线工具、显式导出及既有研究脚本
src/dsp/                          可复用的电脑端 DSP 核心，C API
src/instrument/                   采样库、MIDI、复音与包络，独立 C++17 引擎
src/plugin/                       iPlug2 包装、界面与平台资源
assets/concert-se-grand/           冻结的产品采样、控制表和 EQ；独立于研究环境
tests/                            C/C++ 回归源码及 fixtures/ 原 ARM 期望数据
cmake/                            依赖版本锁与 SDK 验证器构建
licenses/                         第三方框架及字体声明
research/
  downloads/                      官方下载原件：ZIP、PDF
  firmware/KROSS2_V124/            官方 ZIP 原样解包的文件
  libraries/                      官方库/编辑器附带的未修改数据，与派生分析隔离
  external/                       其他项目的研究资料，与官方原件隔离
  derived/firmware/KROSS2_V124/    解压后的 ARM 镜像、反汇编片段、量化表
  derived/kep/                    早期解密探针的派生输出
  derived/manuals/                PDF 的文本提取
  derived/verification/           与原固件逐点对照的验证报告
  python-deps/                    可选研究依赖；不是产品运行依赖
  assets.json                     研究输入与派生固件的来源、大小、SHA-256
build/                            编译产物、验证临时文件，可重新生成
output/
  kep-analysis/                   解密容器、原生采样与 Program 参数
  Concert_SE_Grand_WAV/           PCM24 WAV、导出报告及 previews/
  Concert_SE_Grand_Effects/       效果原型试听与来源/参数/增益清单
  Factory_Sound_Selection/         原机 768 个预置的分类选择目录和 CSV
  Concert_SE_Grand_Filter/         最新滤波模型试听、旁路对照与清单
  Concert_SE_Grand_Control/        保留的前轮无滤波试听与清单
  SEGrand/                        保留的旧 VST3、独立程序及旧试听
```

新增研究必须保留输入来源与指纹；地址以 **解压后的 v1.2.4 镜像文件偏移** 表示，不能和 ARM 虚拟地址或 KEP 偏移混用。推断和实测分开记录，不把可播放 WAV 当作完整音色复刻完成。原件不改动，研究默认离线；实机文件替换仅在明确调用专用工具并添加`--write`时发生，采集也须显式运行。第二阶段已实机读完目标下64MiB TG ROM，256块传输校验与原厂诊断算法核对通过，用户确认读取后发声正常。镜像与原始消息已冻结保存，原机采样现已逐条导出，鼓组和网页试听见上方最新结果；尚未将这些新音色接入桌面插件。

## 复现

Python 3.9+、C99 编译器即可完成解包与 WAV 导出。先有官方 CMP，再运行：

```sh
python3 tools/firmware_inspect.py --decompress research/firmware/KROSS2_V124/KROSS2SY/KROSSAPP.CMP --output research/derived/firmware/KROSS2_V124/KROSSAPP.bin
python3 tools/extract_kep.py
python3 tools/test_kep_extraction.py
python3 tools/decode_korg_pcm.py
python3 tools/test_korg_pcm.py
python3 tools/verify_wav_exports.py
```

官方 ARM 指令对照另需 `requirements-research.txt` 中的 Unicorn；反汇编需 Capstone：

```sh
python3 tools/test_korg_pcm.py --firmware
python3 tools/analyze_concert_program.py
python3 tools/test_program_firmware.py
python3 tools/probe_effect_coefficients.py
python3 tools/probe_dsp_transport.py
python3 tools/probe_effect_catalog.py
python3 tools/index_firmware.py
python3 tools/probe_voice_math.py
python3 tools/probe_concert_voice.py
python3 tools/probe_voice_timing.py
python3 tools/probe_concert_filter.py
python3 tools/make_previews.py
```

`make_previews.py` 使用 macOS 的 `afconvert` 制作 48 kHz / PCM16 干声试听副本。既有 PCM24 WAV 保留先前的 42017 Hz 整数头和全部字节，新速率证据单独保存；与原固件步进换算值相差约 0.024 音分。所有完整导出保留自己的清单和校验值，不用试听文件替代研究原件。

效果核心及试听仅需 Python 标准库与 C99 编译器；原 ARM 系数提取完成后无需 Unicorn 参与音频处理：

```sh
python3 tools/test_concert_effects.py --sanitize
python3 tools/render_effects_prototype.py
```
