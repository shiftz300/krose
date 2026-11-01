# Concert SE Grand：播放速率与 Program 参数

更新：2026-10-31。输入为 EXPCM001 的第 002 项、2144 字节 Program。固件版本、坐标和指纹见 [FIRMWARE.md](FIRMWARE.md)。下文 `0x...` 均为 Program 内偏移，明确标为固件地址的除外。

机器可读结果：`output/kep-analysis/Concert_SE_Grand/program-analysis.json`、`sample-rate-analysis.json`。每个字段保留偏移、原始固件描述符、数值和语义标注状态；未知语义保留为 `field_N`。

修正记录：OSC2 参数 namespace 步长由 15 改为 16，旧 OSC2 的分组名称已纠正；两个块的字节数据未改。新增地址/编码对齐检查及 600 个已分组字段回归。完整解释与新控制函数实验见 [VOICE_CONTROL.md](VOICE_CONTROL.md)。

## 播放速率

已执行官方固件的 pitch setup `0x1ff764`、pitch update `0x1ff38c` 和查表函数 `0x1ff348`，在根音且其他音高调制为零的隔离上下文中得到：

| 样本 pitch 字段 | 固件步进，单位 1/8192 | 按 48 kHz 时钟换算的有效速率 |
| --- | --- | --- |
| 0 | 8192 | 48000 Hz |
| -295，钢琴三层 | 7171 | **42017.578125 Hz** |
| -898，Damper 对照 | 5462 | 32003.90625 Hz |
| -1536 | 4096 | 24000 Hz |
| +1536 | 16384 | 96000 Hz |

48 kHz 是本项目的引擎时钟基准；官方规格也列出录音及采样系统为 48 kHz。这里验证的是固件生成的整数步进，没有测量硬件晶振，也没有执行 TG 插值器。播放速率不能据此反推压缩前录音工程的采样率。

之前采用的理想公式 `48000 * 2**(pitch/1536)` 忽略了固件查表的整数舍入。已有 WAV 头为 42017 Hz，与上表相差约 -0.024 音分。用户已认可这些试听；本轮保持全部 WAV 字节不变，另存精确步进报告。未来采样器应使用固件步进或等价重采样比。

## 力度层与双振荡器

OSC1 的 multisample 表从 `0x564` 开始，OSC2 从 `0x6e0` 开始。两个振荡器配置相同的三个有效采样槽，第四槽关闭：

| 引擎收到的力度 | 层 | 槽 | Bank / Number | Level 原值 | 交叉淡化宽度 |
| --- | --- | --- | --- | --- | --- |
| 1–85 | mf | 3 | 5 / 1 | 119 | 0 |
| 86–106 | f | 2 | 5 / 2 | 119 | 0 |
| 107–127 | ff | 1 | 5 / 3 | 127 | 0 |

范围由固件字段读取结果与手册的 Bottom Velocity / Xfade 语义共同得到；尚未运行完整 note-on 分配器做全部边界遍历。实体键盘的全局力度曲线可能先改变输入力度。Level 是原始控制值；本轮已执行 `0x201674` 并移植槽增益计算，但从控制量到 TG 音频的完整响度映射仍待验证。

每个 OSC 的主参数块长 `0x17c`（380）字节。两个块只有三处不同，全部在 Amp 键盘跟踪：High Key 为 94 / 81，High-Center Ramp 为 -6 / +1，High-High Ramp 为 +3 / -3。OSC 基础设置还有块外字段，不能据此认定两个振荡器整体完全相同。

## 滤波和调制

两个 OSC 的滤波配置相同，路由为 **Parallel**：

| 字段 | Filter A | Filter B |
| --- | --- | --- |
| 类型 | Low Pass | Band Pass |
| Trim / Output | 99 / 99 | 99 / 0 |
| Frequency 索引 | 9 | 30 |
| Resonance | 0 | 9 |
| Cutoff AMS1 | Velocity +15 | Velocity +61 |
| Cutoff AMS2 | M.Wheel +21 | Velocity +13 |
| Resonance AMS | Velocity +2 | Velocity 0 |
| Output AMS | Velocity 0 | AMS Mixer 2 +99 |

**2026-11-01 修正：** 早期报告按错误顺序标注 Output、Frequency、Resonance 及部分 AMS 字段；1042 个原字段的读取值和 Program 字节均未变化。现在依据原 `0x1fb2b0 / 0x1fb3a4` 的实际消费者、400 次字段变异和 TG 寄存器路径确认标签。B 的基础零值是 Output，Mixer2 调制的是 B 输出，不能继续沿用“B 截止频率=0”的旧解释。

原 Filter EG、截止频率、共振与输出控制已对照 32512 个原 ARM 上下文和 4152 步轨迹，并接入播放器。TG 控制字到真实 Hz/Q 的内部映射仍未恢复，当前音频传递函数为明确的电脑端近似。详见 [FILTER_CONTROL.md](FILTER_CONTROL.md)。

Amp Level 为 106；Velocity Intensity 为 70；Amp AMS 为 Exp. Velocity，强度 +17。Pan 原值 64，两个 Send 原值均为 127。

合成器 AMS 使用固件 `0x3d9b10` 的 47 项源表；效果器 Dmod 使用 `0x336cd0` 的 38 项源表。二者编号不同，机器报告分开解释。

## 多段包络

以下是两个 OSC 共同的基础值。时间是 0–99 原厂索引，电平为原厂控制单位；不将这些数字直接当成毫秒或线性振幅。

| 包络字段 | Amp EG | Filter EG |
| --- | --- | --- |
| Start Level | 99 | +1 |
| Attack Time / Level | 91 / 99 | 89 / -1 |
| Decay Time / Break Level | 77 / 74 | 86 / +6 |
| Slope Time / Sustain Level | 97 / 0 | 86 / +8 |
| Release Time / Level | 43 / 固定终点 | 77 / +18 |
| Attack、Decay、Slope、Release Curve | 0、0、10、10 | 0、1、0、0 |

Curve 索引范围 0–10，手册描述从线性到指数曲线。Amp EG 还保存 Velocity 对 Attack 的 -13、对 Break 的 +24 调制；完整字段见 JSON。只复制基础时间无法恢复全部演奏响应。

固件侧已定位 Amp EG 初始化 `0x1fa300`、Filter EG 初始化 `0x1fb8c4`、阶段切换 `0x1fa6c0` / `0x1fbaf8`、公共推进 `0x1fac24`、时间换算 `0x1fb0ac` 及时间表 `0x3fd5a4`。时间表取值如 43→432、77→4608、91→19176；推进代码每次扣减 24 个内部时间单位。名义控制周期现已串到 16 ms，与内部 1500 单位/秒及 TG 平滑表相符；物理晶振、动态踏板和 TG 内部执行未实测。见 [VOICE_TIMING.md](VOICE_TIMING.md)。

新增验证：11 类曲线的系数查表/插值及无动态踏板缩放的包络单步已独立移植，6491 步与原 ARM 状态一致；原 Amp 初始化、阶段推进和释放也已在合成上下文执行。时间和电平确实受音高、力度及 AMS 调制。32512 个上下文的控制量存于 `research/derived/firmware/KROSS2_V124/voice/`，不等同完整硬件音频回放。

## 验证边界与复现

`tools/test_program_firmware.py` 将独立解析器的字段值与固件原始 getter `0x20af84` 逐项比较，并执行原始速率和效果加载函数。结果在 `research/derived/verification/program-arm-comparison.json`。字段数值一致不等于所有语义和完整音色行为已经验证；真琴录音 A/B、滤波系数和硬件时序实测仍未完成；原 ARM 控制时序与 C++ 接入已另行验证。

```sh
python3 tools/analyze_concert_program.py
python3 tools/test_program_firmware.py
```

第一条需要 Capstone 生成 ARM 节选，第二条需要 Unicorn。资源输出位置沿用现有目录约定，不改写原 KEP、官方固件或 WAV。
