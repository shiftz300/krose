# Concert SE Grand：效果通路和实现位置

更新：2026-10-31。结论来自 EXPCM001 Program、官方 v1.2.4 固件和 [KORG 参数指南](https://cdn.korg.com/us/support/download/files/96dbde75752a88b2daf897262d199b80.pdf)。固件偏移坐标和版本指纹见 [FIRMWARE.md](FIRMWARE.md)。

## 实际通路

```text
OSC1 + OSC2 → IFX1：四段参数 EQ → IFX2：四段参数 EQ → L/R
                                      ├─ Send1 → MFX1：Stereo Chorus → Return1
                                      └─ Send2 → MFX2：Reverb Hall   → Return2
```

Program 输出 Bus `0x50f` 为 1（IFX1）。IFX1 开启并串接 IFX2；IFX2 输出 L/R，Send1/2 均为 127；MFX Return1/2 均为 101。以上 Send / Return 数字保留为原值，尚未作为线性百分比使用。

IFX3/4 关闭。IFX5 存储并开启 Stereo Limiter，但不在上述钢琴主通路中，复刻时不应直接把它插在主输出上。尚未确定其他部分是否使用 IFX5。

MFX 输出仅包含湿声，手册明确排除干声分量。MFX1 虽开启，基础 Wet/Dry 为 Dry，因此在无 Dmod 偏移时合唱湿声返回为零；旋钮调制可以把它打开。最终状态还受实时控制器及全局效果开关影响。

## 两级 EQ

频率、Q 和 Gain 已按固件显示换算函数解释。全部参数、原值和显示函数地址保存在 `output/kep-analysis/Concert_SE_Grand/program-analysis.json`。

| 槽 / Trim | 频段 | 频率 | Q | Gain |
| --- | --- | --- | --- | --- |
| IFX1 / 89 | 1，Peaking | 80 Hz | 1.7 | +3.5 dB |
| | 2 | 1600 Hz | 0.5 | +3.5 dB |
| | 3 | 7300 Hz | 0.6 | +2.5 dB |
| | 4，Peaking | 13400 Hz | 3.1 | +2 dB |
| IFX2 / 98 | 1，Peaking | 60 Hz | 10 | 0 dB |
| | 2 | 70 Hz | 10 | 0 dB |
| | 3 | 300 Hz | 0.5 | +2.5 dB |
| | 4，Peaking | 20000 Hz | 10 | +4.5 dB |

两级均为 Wet。本轮已执行原 ARM 取得八段双二阶系数，并恢复 Trim 的线性缩放，电脑端频响验证通过。实现采用浮点运算；TG 定点舍入不作为当前验收目标。详见 [重建与验收](RECONSTRUCTION.md)。

## 合唱与混响

| 参数 | MFX1：Stereo Chorus |
| --- | --- |
| LFO | Triangle，0.50 Hz，左右相位差 180° |
| Pre Delay L / R | 24 ms / 13 ms |
| Depth / Trim | 70 / 100，原值 |
| Low / High EQ | 0 / 0 dB |
| Wet/Dry | Dry |
| Wet/Dry Dmod | K.M3 #20，强度 +50 |

| 参数 | MFX2：Reverb Hall |
| --- | --- |
| Reverb Time | 1.8 s |
| High Damp | 62，百分比控制值 |
| Pre Delay / Pre Delay Thru | 0（该 UI 项禁用）/ 6，原值 |
| Trim | 98，原值 |
| Low / High EQ | -3 / +2 dB |
| Low / High EQ Fc | Mid-Lo / High |
| Wet/Dry | 16:84 |
| Wet/Dry Dmod | K.M4 #21，强度 +22 |

IFX5 Limiter 的保存值为 Ratio 4:1、Threshold -15 dB、Attack 60、Release 50、Gain +4 dB、Wet；Attack / Release 暂保留索引。

## 找到的实现

效果定义表位于固件 `0x336d6c`，每项指向 40 字节定义，包含名称、DSP 程序、初始常数、三个 ARM 控制入口、参数表和长度。现已补齐全部 135 项，详见 [完整目录](FIRMWARE_MAP.md)；以下四种是当前钢琴重点分析对象。程序每项在镜像中存储 8 字节，实际上传 48 位载荷，详见 [硬件记录](HARDWARE.md)：

| ID | 固件名称 | 定义偏移 | DSP 程序偏移 / 8 字节项数 | 常数偏移 / 32 位字数 |
| --- | --- | --- | --- | --- |
| 3 | Stereo Limiter | `0x35f228` | `0x35f2d0` / 119 | `0x35f250` / 32 |
| 7 | St.Parametric4EQ | `0x36ccb8` | `0x36cda8` / 118 | `0x36cce0` / 50 |
| 64 | Stereo Chorus | `0x3464f0` | `0x346584` / 106 | `0x346518` / 27 |
| 105 | Reverb Hall | `0x35daac` | `0x3568dc` / 121 | `0x35dad4` / 61 |

每种效果的产物位于 `research/derived/firmware/KROSS2_V124/effects/{003,007,064,105}/`：

- `definition.json`：参数、回调地址、长度、二进制 SHA-256。
- `dsp-code.u64le.bin` 与 `dsp-code.words.txt`：完整程序字节和原始字对，尚未解码指令集。
- `initial-constants.u32le.bin`：初始系数，不等同于应用本 Program 后的最终系数。
- `dsp-upload.u16le.bin`：本轮恢复的程序总线上传顺序，每项 3 个 u16；原 8 字节容器保留。
- `arm-control.arm.txt`：三个 ARM 控制入口附近的反汇编节选，每处 0x300 字节；不是函数的完整边界。

原固件加载函数 `0x5a51c` 按上述长度拷贝程序和常数；本项目已执行它的缓冲模式，四组输出与提取数据逐字节一致。硬件写入路径分别为 `0x12daac`（程序）与 `0x12dbc4`（常数），驱动中存在 TG01 命名。没有据此认定具体芯片型号。

音频算法位于专用 DSP 程序中，ARM 函数负责初始化、参数/调制和系数更新。效果实现已提取，完整指令集解释器尚未完成。用户已明确以相近听感验收，因此本轮直接使用恢复出的 EQ 系数，另行实现近似 Chorus/Hall，生成了可运行 C 核心和 [三种试听](../output/Concert_SE_Grand_Effects/README.md)。

## 下一步实现研究

1. 当前目标的 EQ 参数→系数已完成；后续需要时补充极端增益的余量补偿。Chorus/Hall 原型已可运行，可按试听调节空间和调制量。
2. 效果核心已接入 iPlug2 VST3 的音符引擎、力度、近似包络和踏板；接下来优先解决演奏时可听见的差异，见 [PLUGIN.md](PLUGIN.md)。
3. 可继续对照简单程序解析 48 位载荷的寄存器、乘加和地址编码，用于校正模型；完整 ISA 不作为交付门槛。
4. 已测量 64 复音引擎及三组效果的处理耗时；Ableton 内的宿主回调表现仍待实测。

本轮也检索了 KROSS 2 / TG01 DSP 实现和指令集资料，未找到可直接运行这些程序的公开解释器或匹配的公开指令手册。检索结论有范围限制；其他 Korg 型号和 logue SDK 不作为这台琴算法的替代证据。
