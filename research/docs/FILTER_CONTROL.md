# Filter A/B：控制字、调制与播放器接入

更新：2026-11-01。只针对本项目锁定的 v1.2.4 固件和 Concert SE Grand Program。地址均为解压镜像文件偏移，虚拟基址 `0xc0000000`。本轮没有复制、安装或重新打包输出目录中的 VST3。

## 修正早期字段标签

旧报告把几个字段按错误的界面顺序命名，**数值读取没错，语义标签错位**。原截止频率函数 `0x1fb2b0` 读取每分支参数块 +`0x13`，共振函数 `0x1fb3a4` 读取 +`0x14`，Trim/Output 读取 +`0x11/+0x12`。A 参数块起于 OSC+`0x90`，B 起于 OSC+`0xb4`。

| 字段 | Filter A | Filter B |
| --- | --- | --- |
| 类型 / 路由 | Low Pass / Parallel | Band Pass / Parallel |
| Trim / Output | 99 / 99 | 99 / 0 |
| Frequency / Resonance 基础索引 | **9 / 0** | **30 / 9** |
| Cutoff AMS1 | Velocity +15 | Velocity +61 |
| Cutoff AMS2 | M.Wheel +21 | Velocity +13 |
| Resonance AMS | Velocity +2 | Velocity 0 |
| Output AMS | Velocity 0 | **AMS Mixer2 +99** |
| Filter EG 强度 / Velocity 强度 | +64 / +4 | 0 / -6 |
| Filter 键盘跟踪强度 | 0 | 0 |

因此，先前“B 的基础 Frequency=0，Mixer2 调制 B 截止频率”的解释需撤销：**B 基础 Output=0，Mixer2 调制的是 B 输出量**。B 截止频率主要受基础值、两路 Velocity AMS 和速度相关的 Filter EG 贡献影响。`analyze_concert_program.py` 与 `program-analysis.json` 已修正标签，原 Program 字节不变。

400 次独立参数变异覆盖 A/B 各 100 个 Frequency 和 Resonance 索引，运行原控制函数核对输出。完整 getter 回归仍通过 1042 个 Program 字段和 95 个效果字段；getter 数值一致本身不能证明语义，这次由消费者代码和变异试验补上语义证据。

## 已恢复的控制计算

令 `M(intensity,source)=clamp((intensity*source*331)>>15,-32768,32767)`。右移使用 ARM 有符号算术右移，以下变量不是音频电压或 Hz。

```text
tracking = (FilterKTrk * keyboardIntensity) >> 5
egDepth = egIntensity*63 + ((velocity*egVelocityIntensity) >> 1)
rawCutoff = frequencyIndex*32767
          + ((egDepth*FilterEGlevel) >> 6)
          + tracking*256
          + 8*cutoffDepth1*AMS1 + 8*cutoffDepth2*AMS2
cutoffWord = min(31744, ((max(rawCutoff,0)>>2)*317)>>13)
resonanceWord = clamp(resonanceIndex*321 + 8*M(resDepth,resSource),0,31744)
trimWord = trimIndex==99 ? 32767 : trimIndex*331
outputWord = clamp((outputIndex>=99 ? 32767 : outputIndex*331)
                   + 8*M(outputDepth,outputSource),0,32767)
```

这是原音色、外部控制器/LFO/额外采样偏移为零的独立移植；外部 KnobMod1、调制轮、Ribbon、额外 pitch/控制量不在当前播放器连接范围。公式中存在这些入口，不能据此称已实现所有 AMS 源。两个 Mixer 保留前轮原整数实现。

Filter EG 沿用已验证的公共曲线/时间表，独立恢复初始化、Attack/Decay/Slope/Release、速度和键盘跟踪的时间调制，以及有符号电平。它的 Release 目标可以非零，结束保持状态 6，不能复用音量包络“释放到零并销毁”的规则。滤波两路各自使用其 EG 强度。控制周期沿用 [VOICE_TIMING.md](VOICE_TIMING.md) 的名义 16 ms。

MIDI60 的部分原始输出如下（每路顺序为 Cutoff / Resonance / Output；Trim 均 32767）：

| 力度 | A 控制字 | B 控制字 |
| --- | --- | --- |
| 1 | 3324 / 0 / 32767 | 9692 / 2889 / 0 |
| 40 | 14172 / 208 / 32767 | 16610 / 2889 / 0 |
| 85 | 26836 / 440 / 32767 | 23945 / 2889 / 4728 |
| 100 | 27557 / 520 / 32767 | 26493 / 2889 / 4864 |
| 127 | 28836 / 656 / 32767 | 31080 / 2889 / 0 |

这说明 B 输出并非随力度单调增加，不能用恒定混音量代替。原控制字也不能直接标成 Hz、Q 或 dB。

## TG 写入与尚未恢复的传递函数

控制结构每路保存 4 个 u16：Trim、Cutoff、Resonance、Output。A 在 voice+`0xec`，B 在 voice+`0x100`；Filter EG 在 voice+`0x120`。初始化 `0x1fb79c`，更新 `0x1fb4b0`，EG 初始化/推进/释放分别为 `0x1fb8c4 / 0x1fbbe0 / 0x1fbaa0`。

`0x12d088` 为平滑更新：A 截止频率目标写 TG+`0x388`，共振目标写 +`0x390`，均左移 8 位；对应步长写 +`0x38c/+0x394`。Trim 写 +`0x39c`，Output 写 +`0x3a0`，高 16 位有符号步长、低 16 位目标。B 各寄存器地址再加 `0x20`。时长沿用 0–24 单位倒数表。**滤波打包器对零差值仍生成 +1 步长，与 Amp 更新“相同目标跳过写入”不同。** 10 组原 ARM 命令已核对，包括 A/B、0/1/5/24/100 单位（100 钳到 24）。

原 ARM 到这里传递的是控制字，尚未发现 TG 内部的截止频率查表、共振到极点的映射或滤波音频指令。在线检索也没有找到可直接代替这部分的公开 TG 实现。[KORG 参数手册](https://cdn.korg.com/us/support/download/files/96dbde75752a88b2daf897262d199b80.pdf)支持双模滤波和调制的功能语义，不能补足芯片内部数值映射。物理琴的扫频/脉冲/相同 MIDI 录音仍是下一步校准依据。

## 当前播放器的近似部分

`src/instrument/NativeFilter.cpp` 将**经验证的控制模型**与**可校准的音频解释**放在明确分开的函数中。每音符、每 OSC 各有 Filter A/B 立体声状态，先滤波再按原 Amp 控制混合，保留原型均值和 0.4 余量。两路按 Parallel 相加；不加额外自动响度归一化。

电脑端采用 [W3C / Robert Bristow-Johnson 的 biquad 公式](https://www.w3.org/TR/audio-eq-cookbook/)，A 为二阶低通，B 为峰值 0 dB 的带通。**以下均为工程假设，未经真琴证明：**

```text
Hz = 20000 * 2^((cutoffWord/317 - 99)/10)
Q  = (1/sqrt(2)) * 2^(6*resonanceWord/31744)
branchGain = (trimWord/32768) * (outputWord/32768)
```

截止频率限制在宿主采样率的 0.45 倍以下。每 16 ms 根据原控制模型重新算目标系数，在宿主音频帧上做 16 ms 线性系数过渡。它与 TG 逐帧控制字斜坡不相同，也不复刻 TG 固定点舍入、饱和、非线性和带通电平补偿。32–192 kHz 可运行，测试覆盖 32/44.1/48/96/192 kHz。

现有界面无需新增控件；`Controls.filterEnabled` 默认开启，仅给离线对照和回归提供旁路。Release 旋钮继续只调整 Amp EG 基础释放值，Filter EG 使用原 Program 的释放参数。CC1/Ribbon/KnobMod、LFO、动态半踏板均没有在本轮额外接入。

## 验证、文件与复现

- Python 独立控制模型 vs 原 ARM：32512 个初始化上下文、4152 个连续阶段状态、400 个原参数变异、7 个明确标注的 Mixer2 边界注入、10 组原 TG 命令。
- C++ vs 原 ARM fixtures：32512 个上下文、552 个选取的跨阶段状态；并非对全音域每个持续时间都穷举。
- 电脑近似滤波：五种采样率下的高频抑制、脉冲/尾音稳定性、左右声道独立；引擎内旁路对照确认滤波实际生效。
- 全 CTest 4/4、ASan/UBSan 3/3、官方 VST3 validator 47/47；不同缓冲分块结果一致、处理期间零 C++ `new`。不等于 Live 或真琴验收。

```text
tools/filter_firmware.py                  原 ARM 合成上下文
tools/filter_math.py                      独立 Python 整数参考
tools/probe_concert_filter.py             原 ARM 对照与 fixtures 导出
tests/test_native_filter.cpp              C++ 控制/音频解释测试（tools/ 旧路径为符号链接）
tools/verify_filter_player.py             指纹、日志、试听与未部署核验
src/instrument/NativeFilter.h/.cpp        产品端控制与电脑近似滤波
research/derived/firmware/KROSS2_V124/voice/
  concert-filter-map.bin                 32512 条原控制输出
  concert-filter-traces.bin              552 个原轨迹选取状态
  concert-filters.json                   参数、轨迹、来源与范围
  filter-control.arm.txt                 原指令片段
research/derived/verification/
  concert-filter-arm-comparison.json
  filter-player-check.json
output/Concert_SE_Grand_Filter/           带空间、无空间、滤波旁路试听与清单
```

```sh
python3 tools/probe_concert_filter.py
python3 tools/analyze_concert_program.py
python3 tools/test_program_firmware.py
python3 tools/index_firmware.py
python3 tools/verify_firmware_research.py
cmake --build build/plugin --target test-native-filter test-piano-engine SEGrand-vst3 test-vst3-host render-piano benchmark-piano -j 6
ctest --test-dir build/plugin --output-on-failure
python3 tools/verify_filter_player.py
```

原 ARM 探针需要 Unicorn 及相应可执行内存权限。构建和音频处理不执行固件、不依赖 Python/Unicorn。旧 `output/Concert_SE_Grand_Control/` 和 `output/SEGrand/` 保留历史字节与清单；旧 `verify_native_player.py` 对应之前的无滤波构建，不能拿旧日志为当前构建作验证。
