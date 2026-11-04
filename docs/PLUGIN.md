> PRESET 现按原厂大类打开二级音色菜单；爱心可加入 Favorites，重开插件后保留。内存与动画修订见 [优化记录](UI_OPTIMIZATION.md)。

> 采样已改为按当前音色后台加载，保留完整键区与力度层；首次加载时显示 `LOADING`，期间原音色继续播放。采样缓存、尾音保留、实际内存和效果 CPU 对照见 [采样与效果优化](SAMPLE_LOADING.md)。

> 最新界面优化保持像素和动画，开窗实测约 238–302 MB；另提供同宿主下的 Analog Lab、Auburn 与 Grand Piano 对照，见 [插件内存测量](PLUGIN_MEMORY_COMPARISON.md)。

> 2026-11-04 原生 UI：默认编辑器已切换为 C++ IGraphics / NanoVG，保留定稿面板和现有参数。网页源码仅供设计参考与资源导出。当前验收与平台范围见 [原生界面移植](NATIVE_UI_MIGRATION.md)。下文早期 WebKit 描述为历史记录。

> 琶音增量：ARP、Latch、五种内置 Pattern、Resolution、Gate、Octave、Sort、Key Sync 和内部／宿主时钟已接入。编辑位置为 LCD 的 ARP 页，操作与剩余 Pattern 范围见 [琶音器](ARPEGGIATOR.md)。

> 当前演奏增量：POLY、MONO、LEGATO 和 GLIDE 已接入。Mono 使用按键优先级及松键回退；Legato 保留已有采样与包络；Glide 作用于重叠按键，0 关闭。新参数支持自动化及工程恢复。具体范围见 [演奏实现](PERFORMANCE.md)。构建使用 `cmake --preset plugin`、`cmake --build --preset plugin`；最新交付位于 `output/Krose/`。以下保留各阶段的历史声音与验证记录。

> 2026-11-04：完整目录已接入，共 1,162 项（含 Concert 兼容入口）。通过 PRESET 或 BROWSE 搜索、筛选。当前资源与限制见 [原生引擎结构](NATIVE_ARCHITECTURE.md)，界面与功能进度见 [实现计划](IMPLEMENTATION.md)。以下 Concert 声音基线记录保留。

> 2026-11-01 目录迁移：当前根目录为 `krose`。下文历史验证记录保留；旧编译与旧插件二进制已清理，按构建步骤重新生成。

# Krose 0.1.0 · iPlug2 VST3

产品名已定为 **Krose**，当前构建产物为 `build/plugin/out/Krose.vst3` 与 `Krose.app`。VST3 类 ID、参数 ID 和原 bundle 标识保留，内部 `SEGrand` 类名与采样包名也保持兼容；这次改名不改变声音或状态格式。尚未在 Live 手工验证旧工程加载。

本文描述当前源码和 `build/plugin/` 内的新构建。已接入原力度、双 OSC 键盘跟踪、AMS、多段 Amp EG 与 TG 平滑解释，见 [VOICE_TIMING.md](../research/docs/VOICE_TIMING.md)。**暂不复制或安装 VST3。** `research/output/SEGrand/` 保留旧原型，尚未重新打包；最新音频在 `research/output/Concert_SE_Grand_Filter/`。现已接入原 Filter A/B 控制与 Filter EG；电脑滤波传递函数仍为近似，字段标签修正与证据见 [FILTER_CONTROL.md](../research/docs/FILTER_CONTROL.md)。

本地制作的 Concert SE Grand 近似钢琴：84 个已解码立体声采样、三层力度、Concert / Warm / Wide 三种变体。运行时采样已装进插件，不需要连接 KROSS 2、Python 或固件。当前构建为 **Apple Silicon arm64，macOS 13+**。

## 控件与后续宿主验收

后续目标是原生 Apple Silicon Ableton Live 的 VST3；尚未构建 Intel/Rosetta 版本。本轮只在项目内编译并使用无界面测试宿主加载，没有进行安装或 Live 手工验收。

`Krose.app` 是可选的独立试听程序。菜单 Krose → Audio and MIDI Settings 可选择声卡、缓冲、采样率与 MIDI 输入。VST3 使用 Live 的音频设置。

| 控件 | 含义 |
| --- | --- |
| Concert / Warm / Wide | 基准、较柔和、较宽空间；后两者是本项目变体 |
| Output | 输出增益，默认 -6 dB；密集和弦过响时调低 |
| Space | 混响量，0% 可听近干声；Wide 还包含合唱 |
| Release | 释放基础时间，默认 288 ms；随后施加原音高/力度 AMS，实际结束时刻随音符变化 |
| Velocity | 原力度模型之后的额外指数调整，默认 1 为中性；越大弱奏越轻 |

支持 64 复音，另有短淡出缓冲用于抢占；CC64 延音、CC7 音量、CC11 表情、CC67 柔音、±2 半音弯音、CC120/121/123。屏幕键盘用于鼠标试音。力度分层为 1–85、86–106、107–127，按恢复值切换，不做层间交叉淡化。

## 声音依据与近似

- 原始 PCM24 数据逐字节保留在 `SEGrand.samples`；加载后转换为共享的只读 float 采样，约 131 MiB。采样包约 98 MiB。
- 根音播放速度采用固件步进换算的 42017.578125 Hz，随宿主采样率换算；三次插值，循环边界短交叉淡化。
- 两级 EQ 使用原 ARM 控制程序计算出的八段系数；48 kHz 直接使用，其他速率用预扭曲双线性映射近似迁移。
- 力度、槽增益、双 OSC 键盘跟踪、AMS Mixer、音量 AMS 和多段 Amp EG 使用原整数行为；62.5 Hz 控制和 48 kHz TG 平滑解释独立于宿主分块。旧 1.5 ms 淡入和指数释音已移除。
- 两 OSC 共用立体声采样读取，取控制增益均值并保留 0.4 余量；原 TG 的绝对增益/声像、全局语音分配相位、滤波内部 Hz/Q、键区微调、半踏板与共鸣仍未完整重建。
- 每 OSC 的 Filter A/B 现按原控制字和 Filter EG 运算，再由 RBJ 低通/带通处理音频；Hz/Q 标定与 16 ms 系数过渡为本项目近似，外部 M.Wheel/KnobMod/Ribbon/LFO 尚未连接。
- Hall/Chorus、循环交叉淡化、CC7/CC11 线性响应和柔音处理仍是本项目方案；不模拟专用 DSP 定点音频行为。
- 支持 32–192 kHz；实际引擎回归覆盖 44.1/48/96/192 kHz，编译后的 VST3 发声测试覆盖 44.1/48/96 kHz。参数自动化按处理块读取并平滑，MIDI 有样本偏移；不宣称参数逐采样自动化。

用户于 2026-11-01 明确认可当前听感，作为可用基线，不再要求真琴 A/B。后续重点转向原机预置音色选择，见 [FACTORY_SOUNDS.md](../research/docs/FACTORY_SOUNDS.md)。Live 内的交互、项目重开和长时间演奏仍未手工验证；本轮继续不复制或安装 VST3。

## 已完成验证

- 本轮新构建的官方 VST3 SDK 验证器：47 项通过，0 项失败。
- 新滤波 C++：32512 个原 ARM 上下文与 552 个轨迹状态匹配；五种采样率下的抑制/稳定性检查及引擎内滤波开关差异通过。完整 CTest 4/4、ASan/UBSan 3/3。
- 新 C++ 音量控制模型：32512 个原 ARM 初始/释放上下文、243 个选取的轨迹状态、28 个 TG 命令全部匹配；四种采样率下指定测试音释放约 0.38000–0.38001 秒。
- 编译后插件的无界面宿主测试：自带采样加载、立体声输出、MIDI 偏移、三种采样率/音色、自动化后序列化、参数保存恢复、踏板映射、编辑器对象创建。
- 引擎回归：力度边界、踏板/重复音、事件跨块、循环、复音抢占、队列溢出恢复；不同块划分产生相同音频；处理期间零 C++ `new`。
- AddressSanitizer / UndefinedBehaviorSanitizer 引擎检查通过。C 效果核心另有同类检查。
- 历史原型独立程序曾完成界面和菜单检查；本轮新控制模型只做无界面验证，未重复界面验收。
- 原 84 个 WAV 的全部哈希仍一致。来源与新模型构建/测试指纹见 `research/output/Concert_SE_Grand_Filter/manifest.json`。

本机 release 引擎测量：64 个持续音符、三组效果同时运算、128 帧、1000 次调用，48 kHz 中位约 222 µs，P99 约 251 µs，单块时间预算 2667 µs。测量排除 Live、GUI、声卡与调度，不替代宿主实时性能结果。完整结果见 `research/archive/migration-2026-11-01/build-evidence/filter-piano-benchmark.json` 和新试听清单。

最新 `research/output/Concert_SE_Grand_Filter/instrument-filter.wav`、`instrument-filter-dry.wav` 和 `instrument-bypass-dry.wav` 均为 14 秒，包含力度变化、琶音和踏板和弦；后两者 Space=0，仍保留 EQ，其中 bypass 关闭滤波且与上轮无滤波干声逐字节相同。三个文件共用单位导出增益，不作独立响度匹配。旧 `research/output/SEGrand/instrument-preview.wav` 仍使用旧包络。

## 从源码构建

需要 CMake 3.25+、Ninja、macOS Command Line Tools，以及完整的 `assets/concert-se-grand/` 资源包。首次用下载辅助工具准备依赖时另需 Git、Python 3.9+；产品 CMake 不再用 Python 提取固件数据。源码根目录执行：

```sh
python3 tools/bootstrap_plugin.py
cmake -S . -B build/plugin -G Ninja -DCMAKE_BUILD_TYPE=Release -DIPLUG_DEPLOY_PLUGINS=OFF
cmake --build build/plugin --target Krose-vst3 Krose-app validator test-vst3-host test-piano-engine test-native-voice test-native-filter render-piano benchmark-piano -j 6
ctest --test-dir build/plugin --output-on-failure
cmake -S . -B build/sanitize -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DSEGRAND_BUILD_PLUGIN=OFF -DSEGRAND_SANITIZE=ON
cmake --build build/sanitize --target test-piano-engine test-native-voice test-native-filter -j 6
ctest --test-dir build/sanitize --output-on-failure
build/plugin/benchmark-piano build/plugin/generated/SEGrand.samples > build/filter-piano-benchmark.json
python3 tools/check_project_boundary.py
```

日常构建只使用 `assets/` 的冻结运行资源与 `tests/fixtures/` 的独立回归数据，配置时逐文件核验 SHA-256。固件、84 个 WAV、研究报告只在显式执行 `python3 research/tools/export_runtime_assets.py` 更新资源时需要。大型采样包是本地资源，不随纯源码副本自动取得。目录职责和更新方式见 [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md)。

依赖版本锁在 `cmake/dependencies.json`：iPlug2 `d82b2e99`，VST3 SDK `v3.8.0_build_66`。工具核验下载指纹和已有依赖，不覆盖未知修改。源码的官方 validator 由项目 CMake 直接构建，可使用 Command Line Tools，无需改写 SDK 或伪装完整 Xcode。`verify_filter_player.py` 保留原滤波接入阶段的验证用途；目录调整后的结构检查另记于 `build/project-structure-check.json`，不改写历史声音清单。

目录：`src/dsp/` 效果；`src/instrument/` 音符引擎；`src/plugin/` iPlug2 与界面；`assets/` 运行数据；`tests/` 测试；`cmake/` 构建支持；`research/` 逆向资料；`build/` 可重建缓存；`research/output/` 试听与历史成品。研究原件已整体迁入 research，内容保持不变。

构建后的插件与独立程序使用本机 ad-hoc 签名，尚未进行 Developer ID 签名、公证或跨机发行测试。第三方框架/字体声明随 bundle 放在 `Contents/Resources/`；[Roboto 官方许可证](https://github.com/googlefonts/roboto/blob/main/LICENSE) 另附全文。采样来自用户提供的 EXPCM001，本地成品没有上传发布；框架许可不代表采样素材的发行许可。
