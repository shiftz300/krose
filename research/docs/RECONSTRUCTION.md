# 重建目标、当前实现与验收

用户于 2026-10-31 明确调整边界：**尽可能接近喜欢的 Concert SE Grand，允许合理近似；一个或多个相似且好用的音色即可。** 完整 KROSS 2、全部效果、芯片逐位执行和“原厂”身份均不是交付目标。

继续复刻的优先顺序：力度/增益 → 包络 → 双 OSC/键盘跟踪 → 滤波/AMS → 效果调校。固件研究同时沉淀为通用目录与参考函数。本轮已将 [控制域进展](VOICE_CONTROL.md) 接入播放器，时序证据见 [VOICE_TIMING.md](VOICE_TIMING.md)；按用户要求暂不复制、安装 VST3。

2026-11-01 用户确认：“不需要对照了，差不多就得了，我觉得很像”。据此将当前 Concert 听感作为已接受基线，真琴录音 A/B 不再是完成条件。接下来研究原机 A–F 预置，排除把扩展包当作主要选择，见 [FACTORY_SOUNDS.md](FACTORY_SOUNDS.md)。

## 当前实现

`src/dsp/concert_effects.c` / `.h` 为可复用的 C99 效果核心。为宿主多采样率扩大延迟缓冲后，每组状态为 689,072 字节，支持 32–192 kHz。处理函数使用固定缓冲，不分配内存、不加锁、不进行文件访问。48 kHz 保留原系数，其他速率以预扭曲双线性映射近似迁移；Python 桥接仍用于 48 kHz 研究试听。

现已接入 `src/instrument/` 的 64 复音 MIDI 引擎和 `src/plugin/` 的 iPlug2 VST3，详情、实际测试与边界见 [PLUGIN.md](PLUGIN.md)。引擎使用经原 ARM 对照的力度/AMS/多段包络、TG 平滑解释及近似循环交叉淡化；每实例保持三组效果运行，以平滑切换并保留尾音。框架不承担原琴音色算法的重建。

| 部分 | 实现依据 | 当前近似边界 |
| --- | --- | --- |
| 两级四段 EQ | 执行官方 ARM 系数生成、共享数学初始化和原系数写入路径；按实际 Program 取八段频率/Q/增益 | 电脑端浮点实现，使用工作精度；不模拟 TG 定点音频舍入 |
| EQ Trim | 原 `0x86e80 → 0x94e24` 的 `trunc(raw*0x7fffff/100)` | 两个固定 Trim 合并为整体线性乘数，适用于当前线性 EQ 通路 |
| Chorus | 24/13 ms 左右延迟、0.5 Hz Triangle、反相 LFO | Depth70→±3.5 ms、线性插值为本项目近似；Concert 基础版本关闭湿声 |
| Hall | 1.8 s 时间目标，-3/+2 dB 发送着色，HiDamp62 启发高频衰减 | 本项目独立的 8 路 Householder FDN、扩散和早期反射；不是从原 DSP 还原的 Hall 拓扑 |
| 空间量 | 基础 0.15、可调整 | Send/Return 原值到电脑湿声增益的完整映射尚未恢复，听感验收优先 |
| Warm / Wide | 以同一基准 EQ 为基础调整亮度、空间和合唱 | 本项目变体，非 KEP 中原有的另两个 Program |

FDN 原理参考作者的公开教材 [Julius O. Smith：Householder Feedback Matrix](https://dsprelated.com/freebooks/pasp/Householder_Feedback_Matrix.html)。只使用数学构造，C 实现独立编写，没有引入第三方混响实现依赖。

## EQ 逆向的具体进展

工具：`tools/probe_effect_coefficients.py`。必须先执行数学静态初始化 `0x57c1c`、`0x60f70`；只映射镜像而不初始化会产生错误系数。随后执行 `0x99714 → 0x5f560 → 0x5e8fc / 0x5ebe0`，使用原缓冲模式，无函数替换和 MMIO。

工作系数解包为：`y = b0*x + b1*x1 + b2*x2 + f1*y1 + f2*y2`。双字模式重组有符号 Q30；单字模式按有符号 24 位、22 个小数位解释。目标低两段保留双字格式，高两段的原上传模式与工作格式同时存档。

八段中心增益与 Program 显示值相符；另外验证 36 组 ±6 dB/零增益、不同 Q 用例。目标原上传精度与工作精度在检查网格上的最大频响差小于 0.004 dB。系数和全部验证原值见 `research/derived/firmware/KROSS2_V124/effects/007/concert-coefficients.json`。

隔离助手在大提升、宽 Q 时可能需要外围余量补偿；探索 +12 dB 用例暴露了此边界。当前只采用此音色的中等增益和已经通过的范围，不宣称通用 EQ 所有参数都已恢复。

## 可试听产物

`output/Concert_SE_Grand_Effects/` 中包括 dry、concert、warm、wide 和依次串联的 comparison。四份采用同一源、同一最终增益，保留各自响度差；额外的 comparison_level_matched 对比较片段匹配 RMS，减少响度偏差。manifest 记录输入/实现指纹、参数、峰值、RMS、匹配增益和播放顺序。原 84 个完整 WAV 不改写。

这一阶段试听只比较**效果层**：输入是此前已认可的干采样预览，尚未模拟完整双 OSC、音符力度响应、包络、滤波、踏板或 MIDI。因此本轮的接受结论可以是“效果方向可用”，而非完整插件验收。

## 验收方式

1. **效果听感**：用相同干声切换 Concert / Warm / Wide，关注击弦亮度、低频厚度、立体声和尾音；用户认可一个基准与喜欢的变体即可进入音符引擎阶段。无需逐位一致。
2. **后续音色响应**：固定 MIDI 乐句与速度，覆盖低中高音、弱中强力度、85/86 与 106/107 边界、短音、长音和踏板；记录偏亮、偏闷、力度跳变或释放不自然的具体位置。真实录音可用于调校，有差异并不自动判失败。
3. **数值与状态**：无非有限值、无导出削波；同一输入的不同处理块大小结果一致；重置后可重复；混响有尾音并衰减。EQ 实现按恢复系数检验频响。
4. **宿主实用性**：VST3 官方验证器及无界面宿主的发声/参数保存测试已通过；仍需在 Ableton 中检查演奏、项目重开、踏板、复音、切换听感与缓冲大小。自动测试不替代这项验收。
5. **性能**：以目标复音和整个插件的回调时间判断是否有余量；效果核心的历史局部测量与当前完整引擎测量分别保留；新引擎 64 个持续音符、三组效果同时运行，48 kHz/128 帧中位约 222 µs、P99 约 251 µs，不代替宿主测量。

复现：

```sh
python3 tools/probe_effect_coefficients.py
python3 tools/probe_dsp_transport.py
python3 tools/test_concert_effects.py --sanitize
python3 tools/render_effects_prototype.py
```

前两条需 Unicorn；后两条不运行固件。测试报告保存在 `research/derived/verification/effects-prototype-check.json`。音符引擎与 VST3 已接入，最新滤波试听在 `output/Concert_SE_Grand_Filter/`，控制与 Filter EG 已原 ARM 验证，音频映射另保留近似。后续按实际演奏调校 TG 增益/Hz/Q 解释、循环与效果，见 [FILTER_CONTROL.md](FILTER_CONTROL.md)。

本轮导出的六个效果 WAV 还逐项检查了格式、指纹、无削波、输入/实现来源和 RMS 匹配，报告在 `research/derived/verification/effects-export-check.json`。本机 arm64 的 256 帧效果处理耗时中位约 8 µs（包含 ctypes），这是离线局部测量，不是完整插件或 Ableton 性能结论。
