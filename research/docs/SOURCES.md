# 外部资料与适用范围

检索与核对日期：2026-10-31。没有找到直接支持本 EXPCM001.KEP 采样解码的现成公开实现；这是本次检索结果，不代表从未有人完成过。

插件采用 [iPlug2 官方源码](https://github.com/iPlug2/iPlug2) 的固定提交 `d82b2e99b17c8f723d3f6e2a88ffd8b656f28e5d`，参考其 [CMake 文档](https://iplug2.github.io/docs/md_cmake.html)；[Steinberg 官方 VST3 SDK](https://github.com/steinbergmedia/vst3sdk) 锁定 `v3.8.0_build_66`。版本和归档哈希在 `cmake/dependencies.json`，许可在 `licenses/`。这些依赖负责宿主接口、GUI 和验证，不作为 Korg 算法证据。

本轮补充检索 GitHub 上的 KROSS/KROSS2 firmware、DSP、envelope 公开资料，未找到能直接替代当前控制函数或 TGi ISA 分析的实现；此结论仅限本次检索。官方产品页列出的 [134 种效果](https://www.korg.com/us/products/synthesizers/kross2/index.php/1000/) 与固件 No Effect + 134 项目录一致；原始表和构造函数仍是本项目资源恢复的直接证据。官方参数手册的 EG 时长表提供时间单位标定线索，不单独作为调度周期的证据；新增内核/定时器探针及 TI 家族时钟参考共同支持名义周期，见 [VOICE_TIMING.md](VOICE_TIMING.md)。

| 一手来源 | 有用信息 | 本项目适用边界 |
| --- | --- | --- |
| [KORG 官方 KROSS 2 v1.2.4](https://www.korg.com/us/support/download/software/0/754/3833/) | 官方 ARM 程序、KEP 加解密与采样编码器反馈计算 | 当前核心算法证据，版本指纹锁定 |
| [KORG 参数指南](https://cdn.korg.com/us/support/download/files/96dbde75752a88b2daf897262d199b80.pdf) | Program、multisample bank、力度与交叉淡化的语义 | 不是二进制字段地址或采样编码规范 |
| [KORG KROSS 2 官方规格](https://www.korg.com/de/products/synthesizers/kross2/specifications.php) | 48 kHz 录音/采样系统、双滤波、五 IFX / 两 MFX 架构 | 钢琴的有效根音速率仍由样本 pitch 与固件整数步进决定 |
| [KROSS 2 官方下载目录](https://www.korg.com/us/support/download/product/0/754/) | 核对手册和固件入口；HTML 存于 `research/downloads/KROSS2_downloads.html` | 本次目录未发现可替代当前固件解析的完整二进制参数规范 |
| [KROSS 2 CPU 板实物照片](https://www.ebay.com/itm/156522112587) 与 [板卡型号](https://syntaur.com/parts/korg/kross-2-61/cpu-board-korg-kross-2) | 卖家的 KLM-3665B 实物、Korg TGi 丝印、板卡料号 | 实物版本特定，TI 主控完整型号未读清 |
| [TI OMAP-L1x 官方资料](https://www.ti.com/en/download/mcu/OMAP-L1x.pdf) 和 [AM1808 官方规格](https://www.ti.com/product/AM1808) | 区分 ARM-only 与 ARM+DSP，核对固件中主控家族线索 | 候选家族资料，不作为本琴主频/容量的确定值 |
| [TI Timer64 官方时钟表](https://downloads.ti.com/dsps/dsps_public_sw/sdo_sb/targetcontent/tirtos/1_21_00_09/exports/docs/products/bios_6_37_00_20/docs/cdoc/ti/sysbios/timers/timer64/doc-files/TimerTables.html) | AM1808 Timer0 地址 0x1c20000、默认 24 MHz；本地保留 HTML 和实际数据 JS | 候选家族参考，支持名义 1 ms tick，不证明主控型号或实测晶振 |
| [W3C Audio EQ Cookbook](https://www.w3.org/TR/2021/NOTE-audio-eq-cookbook-20210608/) | 电脑端 RBJ biquad 系数公式，HTML 与指纹已归档 | 只作近似滤波音频实现依据，不证明 Korg 的 Hz/Q 或 TG 内部拓扑 |
| [Julius O. Smith 的 FDN/Householder 教材](https://dsprelated.com/freebooks/pasp/Householder_Feedback_Matrix.html) | 电脑端近似混响所用数学构造 | 独立实现的近似 Hall，不作为 Korg 原算法证据 |
| [PCG Tools Kross2Program.cs](https://github.com/DaBlick/PCG-Tools/blob/master/KorgKronosTools/Model/Kross2Specific/Synth/Kross2Program.cs) | 部分 KROSS 2 Program 字段 | 用于 OSC Mode 与类别位的独立结构对照 |
| [Krome-Sample-Tool](https://github.com/Newstyl3/Krome-Sample-Tool) | 近似波形描述、20 字节键区布局 | Krome 用户采样结构不能代替 KROSS 2 原厂压缩解码 |
| [KORG-Tools](https://github.com/aczwink/KORG-Tools) | SET/OC31 等其他 Korg 文件格式的研究代码 | 未发现可用于本 KEP 的解码器 |
| [Hacktribe #77](https://github.com/bangcorrupt/hacktribe/discussions/77) 与 [synth-pcm-dump 分支](https://github.com/bangcorrupt/hacktribe/tree/synth-pcm-dump) | 作者实际利用 Electribe 固件加载/解压路径导出 PCM 的先例 | 另一机型、依赖其固件与硬件，不能直接用作 KROSS 2 解码器；下载的补丁是 BSDIFF40 二进制 |
| [KORG 专利 JP2000293178A](https://patents.google.com/patent/JP2000293178A/en) | 分块 ADPCM 与最小步长的设计 | 没有证据证明本 KEP 使用该专利的具体实现，未照搬为解码公式 |
| [Kawai 专利 US5693901A](https://patents.google.com/patent/US5693901A/en) | 每个波形配预测系数、循环反馈的设计 | 作者与型号均不同，仅作概念对照，不作为 Korg 格式证据 |
| [KORG Italy 实习论文元数据](https://tesi.univpm.it/handle/20.500.12075/9279) | 讨论其专有编码研究、IMA 与 G.726 预测器改进 | 摘要可读，PDF 访问返回 403；未拿到完整算法，不把摘要当作本机解码规范 |
| [Reuben 本人发布的 Pa 钢琴讨论](https://korgforums.com/forum/phpBB3/viewtopic.php?t=118639) | 另一机型存在压缩和解压采样，可考虑成对样本研究 | 未下载该大型音色包，未作为本次验证样本 |

[ConvertWithMoss](https://www.mossgrabers.de/Software/ConvertWithMoss/ConvertWithMoss.html) 与 [Awave](https://www.fmjsoft.com/awfmts.html) 的公开支持列表未发现 KEP。支持 KMP/KSF 不等于支持原厂 KEP。

本项目没有通过拷贝其他项目的解码实现获得当前 PCM 公式；公式来自本地官方镜像的查表与反馈指令追踪。

效果层检索包含 KROSS 2 固件、TG01 / MB87M4080 指令集与效果模拟器。未找到可直接解释本次提取程序的公开 ISA 手册或现成运行器；其他型号服务手册的芯片信息不用于断言 KROSS 2 的具体硬件。当前效果实现证据来自本地官方固件定义表、ARM 控制函数和经原加载器验证的程序。本轮又确认了 8 字节存储项对应的 48 位上传载荷，并恢复目标 EQ 系数；详见 [EFFECTS.md](EFFECTS.md) 和 [HARDWARE.md](HARDWARE.md)。

原机出厂预置来源：Korg Brasil 官方站的 KROSS2 Editor 1.0.0 归档随附 `PRELOAD.KRS2all`，与 Korg 官方 2018-03-23 Voice Name List 的 A–F 名称和模式核对。原件与指纹已登记；未执行安装程序。具体字段验证及 ROM PCM 缺项见 [FACTORY_SOUNDS.md](FACTORY_SOUNDS.md)。
