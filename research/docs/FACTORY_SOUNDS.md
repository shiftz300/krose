# 原机出厂预置：银行数据恢复与选择

更新：2026-11-01。用户明确要普通 KROSS2 原机出厂预置，扩展包不是本轮选择的重点；当前 Concert 的听感已获认可，不再要求真琴 A/B 作为完成条件。播放器代码、本次之前的音频和 VST3 bundle 均未改动，也未安装任何插件或官方编辑器。

## 已真正恢复的原机数据

从 Korg 官方巴西站的 `KROSS2Editor_mac_100_en.zip` 中，以只读方式检查随附 DMG，找到独立的数据文件 **PRELOAD.KRS2all**。未运行 Installer；保存该数据文件后已卸载镜像。

- 原下载入口：[Korg Brasil 官方软件页面](https://www.korg.com.br/sistemas-operacionais)；它标为旧版软件，实际链接到编辑器归档，不能当成 v1.0 完整系统 ROM。
- 下载原件：`research/downloads/KROSS2Editor_mac_100_en.zip`。
- 预置数据原件：`research/libraries/KROSS2_Editor_100/PRELOAD.KRS2all`，5,993,354 字节，SHA-256 `71bf82f1183e36422f31fb253be8a3010435f46d6fb7f3bd35d432116adb557b`。
- 外层 `tra `，大端长度字段等于文件大小减 8，机型标记 `KRS2`。
- 原机 Program 表从文件偏移 **0x1ef220** 开始，每条 **2140 字节**；顺序 A000–A127、B000–B127，直到 F127，共 **768 条**。
- 后面另有 512 条 `InitProg` 用户银行记录，不作为原机出厂音色加入候选表。

所有 768 个名称与官方 2018-03-23 Voice Name List 一致（仅三处连续空格在目录显示时折叠），OSC Single/Double/Drums 模式也全部吻合。原始名称和原始 2140 字节切片另外保留，未改写来源。

Editor 的 2140 字节记录容纳所有已索引参数，最大已读取字段跨度为 2137；参考 KEP 的 2144 字节记录多出四个末尾零字节。当前索引的内部字段偏移保持一致。研究工具直接保存 2140 字节，不凭空补成另一个原件格式。

## 参数和原 ARM 验证

沿用 v1.2.4 `0x407bd0` 参数组表及原 getter `0x20af84`：

| 项目 | 本轮结果 |
| --- | --- |
| 每个 Program 的通用/双 OSC 字段 | 1042 项 |
| 768 个 Program 的数值比较 | **800256 项全部一致** |
| 各 Program 实际效果类型对应的参数 | **55695 项与原 getter 一致** |
| 原始资料 | 768 条原始 Program，SHA-256 单独记录 |
| 可读字段 | 双 OSC、采样槽与力度边界、音量/包络、滤波/AMS、声像/发送、IFX/MFX 类型及参数 |

数值读取一致不等于所有调制、效果拓扑已经在电脑上运行。许多 Program 用到当前 Concert 引擎尚未支持的 LFO、调制源、效果、八层力度、单音/滑音、鼓组等。**本轮只恢复数据供选择，没有把 768 个音色自动装进现有插件。**

`parameter-schema.json` 保存共享字段顺序/固件描述符，`parameter-values.json` 按该顺序保存每个原机 Program 的全部值。`programs.json` 附可读的主要分组、效果原参数和原件切片路径。

## 固件中的银行文件与波形目录

固件文件名表从 `0x457bb8` 开始。索引 7–12 指向 `PPROGIA.BIN` 到 `PPROGIF.BIN`。本轮原样执行 `0x2c5720..0x2c572c` 和 `0x17f610..0x17f620` 两段选择逻辑，六个银行共 **12 个捕获**均正确。后续代码涉及内部逻辑卷 `A:/` 的文件读写/传输；没有启动 OS、访问琴或执行完整文件加载。

v1.2.4 官方更新 ZIP 确实不附带这六个银行文件。因此，最初只检查更新包无法恢复原机完整 Program；本轮通过官方编辑器随附 PRELOAD 补到了参数数据。不能把“更新包没有”扩展为“官方资料里绝对没有”。

原 `0x20cf34 / 0x20cf40` 返回的 ROM 波形目录地址/数量也已执行核对：`0x48f5cc`，**497 条**，包括最后的诊断 `Sine 1kHz`。这是波形名称、区域数等元数据，不是 497 个 Program，也不是压缩 PCM 音频。

普通音色的 mono bank0 直接引用这张表；stereo bank1 的关联按顺序匹配相邻同名 `-L/-R` 项，共 7 对，所有原机 stereo 引用均在范围内。这一关联是结构对应推断，完整 note-on 分配器未运行。鼓组模式保留原字段，未强行当普通 multisample 解读。

部分已恢复的实际配置如下：

| 原机编号 | 名称 | 波形引用／主要效果依据 |
| --- | --- | --- |
| A000 | Kross Grand Piano 1 | KROSS Piano mp/mf/f 及 Piano Damper；EQ、Mastering Limiter、Hall 等 |
| A034 | M1 Piano | mono15 `M1 Piano`；Stereo Exciter、Hall |
| A064 | E.P.Suit R&B SW1/2 | EP-Suit Pure/Dark 不同力度波形；EQ、Limiter、Hall |
| B019 | E.Organ Jazz Perc.1 | E.Organ Perc/F.Click；Rotary Speaker、Graphic EQ、Wah、Hall 等 |
| C001 | Stereo Strings 1 | Str.Ensemble 2 L/R、Str.Ensemble 1、3Violins-MK II；两级 EQ、Hall 等 |
| D010 | DW8000 Lead 1 | Saw-MG3、Square-mMG；Tube PreAmp、Harmonic Chorus、BPM Delay 等 |
| D103 | Sine Pad | Sine、Sine-JP；EQ、Chorus、Hall |
| E054 | Nylon Guitar 1 | Nylon Guitar 2、E.Gtr.Fret Noise；两级 EQ、Chorus、Hall |
| E098 | E.Bass Finger 1 | E.Bass Finger 1；Compressor、Bass Amp/Cabinet、Decimator 等 |

表中列举效果配置不代表这些效果全部位于主信号串联路径；完整开启状态、链路标志、输出总线和发送值保留在机器数据中。

## 选择范围与还缺的内容

[选择目录](../output/Factory_Sound_Selection/README.md)按 11 类整理全部 768 个 A–F 原机预置，附完整 CSV。可按原机编号选，例如 `A034 M1 Piano` 或 `D103 Sine Pad`。普通 KROSS2 与 SE/88MB 额外预置分开，本轮没有用 EXPCM 包名冒充原机 Program。

另从官方表记录 265 条 GM 条目，但 PRELOAD 的 A–F 表未提供其 Program 字节，所以 GM 不标成参数已恢复。官方表中 G016 同时标给 Tubular Bells 和 Santur，是来源中的冲突，本轮保留并标注，不猜改其编号。

**尚缺原机 ROM PCM 的实际音频负载。** PRELOAD 是 Program/组合/设置数据，不能把其中的采样编号当成已导出的 WAV。因而本轮没有生成冒充原机预置的试听。后续选定后，可研究 ROM 资源取得方式，或在用户接受近似的边界内选择可用的合成/采样实现；不要求先录真琴 A/B。

后续已定位 `A:/KROSSPCM.BIN` 镜像编程路径及 TG 存储读取协议，6 组原 ARM 读取命令通过模拟寄存器核对；实际 ROM 字节仍未取得，见 [ROM_SAMPLES.md](ROM_SAMPLES.md)。原机非鼓 Program 的波形引用共享统计与当前 Concert 压缩实验见 [RESOURCE_DESIGN.md](RESOURCE_DESIGN.md)，不改变这里的原件与历史验证清单。

## 文件与复现

```text
research/downloads/                         官方原始 ZIP、Voice Name List PDF
research/libraries/KROSS2_Editor_100/        PRELOAD.KRS2all 原件副本
research/derived/factory/KROSS2_Editor_100/
  programs/                                768 条原始 2140 字节 Program
research/derived/firmware/KROSS2_V124/sounds/factory/
  programs.json / programs.csv              原机目录、参数摘要及来源
  parameter-schema.json                     共享的 1042 项字段描述
  parameter-values.json                     768 份完整原值
  GM-programs.csv                           GM 名录，未称已提取参数
  factory-load.arm.txt                      银行选择/文件 I/O 的原指令节选
research/derived/verification/
  factory-sound-catalog-check.json           来源与输出指纹、验证范围
output/Factory_Sound_Selection/              给用户选择的分类目录和 CSV
```

`tools/catalog_factory_presets.py --verify-arm` 使用 pdfplumber 读取两列表格，并以原 ARM 验证参数/效果字段和银行选择器；可用 Codex 自带 Python 环境运行。原 ARM 探针需要可执行内存权限。已有离线研究核验脚本另外验证这些固定输出和指纹，无需重新运行 JIT。

本轮旁支分析过的 EXPCM002/004 原件及派生数据保留在原有研究分区，标为辅助资料；`output/Sound_Selection/` 的音频仅是扩展波形试听，**不是本目录中的原机预置试听**，不作为本轮选择入口。
