# 原机 ROM 采样：取得路径研究

最新进展（2026-11-01）：已通过实机TG读取器和USB MIDI取得目标下64MiB，完整校验和读取后发声检查通过，见[采集结果](ROM_ACQUISITION.md)。下方是此前取得路径研究的历史范围；采样波形仍待逐项解码。

日期：2026-11-01；固件 v1.2.4，所有地址均为解压镜像文件偏移。本轮不改播放器，不连接键盘，不刷写硬件，不复制或安装 VST3。

后续进展：已恢复4070条样本描述符、5570条键区和1014条鼓采样目录，目标原机区域缩小到候选下64MiB，并执行了整块读取和尾标验证。新增USB内部存储备份线索及其边界见 [ROM_LIBRARY_LAYOUT.md](ROM_LIBRARY_LAYOUT.md)。按用户要求，压缩和资源格式改造暂停。

## 检索结论

本轮检索 KROSS2/KROSS 2、PCM/ROM dump、KROSSPCM.BIN、固件提取及 GitHub 实现，未找到可直接导出 KROSS 2 原机 ROM PCM 的、可核对的现成工具或完整格式规范。这个结论限定于本轮已查来源，不代表无人完成过。

| 一手资料 | 已有工作 | 对 KROSS 2 的适用边界 |
| --- | --- | --- |
| [Hacktribe 作者讨论 #77](https://github.com/bangcorrupt/hacktribe/discussions/77) | Electribe 固件解压 Flash PCM 后，在传入 DSP 前截取并经 SysEx 导出；作者和使用者报告成功 | 可借鉴数据截取位置；不同机型，不能照搬其固件或地址 |
| [Kromeheaven 作者的 META V2 研究](https://kromeheaven.com/home/blog/364-korg-kross-meta-v2-img-decoded) | 作者研究旧 Kross 的 META.IMG V2，并说明当时未公开相应实现 | 用户/扩展采样描述格式线索，不是 KROSS 2 出厂 ROM dump |
| [Krome-Sample-Tool 作者仓库](https://github.com/Newstyl3/Krome-Sample-Tool) | Krome 采样转换工具 | 不能证明支持 KROSS 2 原机 ROM |
| [KORG 官方规格](https://www.korg.com/us/products/synthesizers/kross2/specifications.php) | 约 128 MB 预置 PCM（48 kHz/16-bit 线性等效）、496 multisamples、1014 drumsamples | 等效容量不是物理 Flash 型号、压缩镜像大小或下载文件 |
| [官方 v1.2.4 更新](https://www.korg.com/us/support/download/software/0/754/3833/) | 可分析 ARM 程序 | 本地 ZIP 逐项检查仍无 KROSSPCM.BIN |

公开旧 Kross 的 IMG 加载经验和 KROSS 2 的 pad sampler 导出功能，均不能直接当作原机 ROM 导出能力。PRELOAD.KRS2all 已给出 Program 参数，也未包含 ROM 音频负载。

## 本轮新定位

工具：`tools/probe_rom_storage.py`。静态报告与带桩执行报告分别存于 `research/derived/firmware/KROSS2_V124/rom/storage-probe.json`、`storage-probe-arm.json`；原指令节选为同目录 `storage-path.arm.txt`。

| 偏移 | 证据 | 当前结论 |
| --- | --- | --- |
| `0x462d7c` | 字符串 `KROSSPCM.BIN`；`0x1e9b40` 的 PC 相对引用 | 找到了 PCM 镜像文件名，尚未取得文件 |
| `0x1e9aac` | 从卷名表取得 `A:`，拼接 `/KROSSPCM.BIN`，以最多 `0x40000` 字节读取，递增块号调用 `0x11c9e0` | 镜像编程路径；这是写入，不是导出，未执行 |
| `0x11c90c` | 以 `0x10000` 次循环读取，每次两路 u16 写入目标缓冲 | 一次输出 262144 字节的存储块读函数；未完整执行 |
| `0x11c994` | 包装上述读函数，检查块号为 `0x100..0x1ff` | 现有调用方用于特定区域；这个检查不证明出厂 PCM 的地址范围 |
| `0x12e1c0` | 向 `TG+0x330` 传地址、向 `TG+0x338` 传 `0xfe`，轮询 bit1，读取 `TG+0x334` 的低16位 | TG 寄存器间接访问存储的读接口 |
| `0x12e494` | 写路径包含 `0x555/0x2aa` 地址、`0xaa/0x55` 解锁及 `0x25/0x29` 命令 | NOR 风格协议线索，不能据此确定物理芯片型号；未执行 |

已在 Unicorn 执行 **6 组原 ARM 读取命令**，只替换底层寄存器 I/O 为内存桩。核对地址 `(index<<1)+half`、命令值、busy→ready 轮询和返回低16位。没有取得真实存储字节，没有执行 OS、写入路径或访问真实 TG。探针在本机需要获准的 JIT 可执行内存环境。

`NANDRomManager.cpp` 的存在不能自动证明音频就在 NAND；附近已有 KROSSAPP.BIN 校验用途。本轮 PCM 协议线索应与主控程序存储分别记录。

## 后续取得顺序

1. 优先查官方/维修来源的完整 PCM 恢复镜像，目标文件名现已具体化为 KROSSPCM.BIN；当前公开更新包不含它。仍需验证该镜像布局、适用机型与版本。
2. 继续追踪原机启动和读取路径，确认出厂 PCM 区域、描述符及地址单位；查清是否存在原固件可用的只读导出/调试入口。现有读寄存器函数不等于电脑已能通过 USB 调用。
3. 若只有用户实机有数据，再评估只读硬件备份或受控读出方案，需要真实板卡/存储器识别。这不是当前已完成的步骤。

拿到字节后，先恢复样本描述符、键区、循环、音高及解码系数，再测试能否复用 EXPCM 的预测解码；不能仅因同属 KORG 就假定编码完全相同。录制成品音色可作为近似素材的另一路，但属于重新采样，不称原始 ROM 提取。

## 复现

```sh
python3 tools/probe_rom_storage.py
python3 tools/probe_rom_storage.py --verify-arm
```

静态分析需本地 Capstone；第二条另需 Unicorn 和可执行内存。原件 SHA-256、工具指纹和更新包成员已写入报告。网络来源摘要存于 `research/external/rom-research/sources.json`。
