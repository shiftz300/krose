# 可复用固件索引与完整效果目录

研究版本：KROSS 2 v1.2.4，SHA-256 沿用 [FIRMWARE.md](FIRMWARE.md)。所有地址均为解压后 `KROSSAPP.bin` 的文件偏移；虚拟地址另加 `0xc0000000`。本轮没有启动固件操作系统、连接琴或刷写设备。

当前工作边界：继续逆向与项目内验证；暂不生成新的发布副本或安装 VST3。已有插件是验证架构的原型，研究数据不会未经声音调校就自动接入播放器。

## 完整效果资源

`tools/probe_effect_catalog.py` 已枚举 **135 项定义：No Effect + 134 种效果**，解析 **2269 个参数描述符**，并得到 **117 组不同代码指纹**。后者只是代码字节去重，不表示只有 117 种声音或算法。

此前直接读取文件只能取得大部分效果：13 项的 DSP 代码指针、长度在镜像中为零，由 C++ 启动初始化填入。它们不是空效果或另一种 DSP 编码。

| ID | 效果 | 原始初始化入口 | 恢复的 8 字节代码项数 |
| --- | --- | --- | --- |
| 31 | Orange PHASE | `0x0a2da8` | 96 |
| 32 | Black PHASE | `0x0a3000` | 96 |
| 33 | U-VIBE | `0x0a2b50` | 96 |
| 65 | Vintage Chorus | `0x0a32f0` | 108 |
| 73 | Vintage Flanger | `0x0a35b8` | 108 |
| 109 | Reverb2 Spring | `0x0a4170` | 107 |
| 110 | Reverb2 Hall | `0x0a50f0` | 107 |
| 111 | Reverb2 Plate | `0x0a469c` | 107 |
| 112 | Reverb2 Room | `0x0a4bc4` | 107 |
| 124–127 | 四种 G.Amp 模型 | 见机器报告，逐项恢复 | 各 232 |

初始化只执行对应的小函数及其原始 getter，没有替换函数。随后对全部 135 项执行原缓冲加载器 `0x5a51c`，代码、常数与恢复数据逐字节一致。2269 个参数分别用 `00/ff/55/aa` 四种原始字节模式对照原 getter，合计 **9076 次**，验证字段编码与符号处理；不表示参数所有物理语义均已恢复。

产物保持原有层级：

```text
research/derived/firmware/KROSS2_V124/
  effects/000..134/
    dsp-code.u64le.bin             原 8 字节存储项
    dsp-upload.u16le.bin           每项 0、6、4 半字的 48 位上传载荷
    initial-constants.u32le.bin    初始常数，未应用任意 Program
  catalog/effects.json             全部名称、参数、回调、地址、初始化及指纹
research/derived/verification/
  effects-catalog-arm-comparison.json
```

先前 003/007/064/105 的额外分析文件保留。共享代码对应不同参数和常数，不能把一个效果的控制映射套到其他效果。

这批数据为后续选择压缩器、延迟、混响、合唱或放大器研究提供入口。专用 DSP ISA 和音频运算仍未解码；资源完整不等于这些效果已经能在电脑上执行。

## ARM 入口、表与源码线索

`tools/index_firmware.py` 生成 `catalog/index.json`：

- 464 个带名称或效果回调角色的入口，包括已有确认函数、全部效果回调和 13 个初始化入口；每项保留独立证据状态。
- 14 张已识别表的地址、长度、指纹和原始切片，包括 EG 时间/曲线、指数、力度及参数指针表。未知长度的表只保留地址，不任意截断导出。
- 114 条固件内源码路径字符串及其指针引用，可按 `pcmvoice`、`soundsys` 等模块查找。
- `symbols.csv` 导出名称、文件偏移、虚拟地址及证据状态，便于后续导入分析工具；共享回调的各效果使用者也保留在 JSON。
- `arm-candidates.json` 保存 67045 条直接 BL 候选边及 PC 相对指针引用。线性扫描可能把数据认成指令，故全部标为候选，不据此宣称恢复完整调用图或函数边界。

例如：

```sh
python3 tools/probe_effect_catalog.py
python3 tools/index_firmware.py
python3 tools/index_firmware.py --entry 0x1fa1a0 --bytes 0x100
```

最后一条显示该入口的已知解释、直接调用候选和有界反汇编。初始索引是静态线索；后续用原 ARM 对照确认行为，再提升条目的证据等级。

主要新入口：

| 偏移 | 已恢复内容 |
| --- | --- |
| `0x200fb4` | 有符号调制乘积、缩放和饱和 |
| `0x20102c` | Q16 指数到 Q16 倍率 |
| `0x1fb02c` | EG 时间受调制后的整数缩放 |
| `0x1fab3c` | 11 类包络曲线系数，分段查表与插值 |
| `0x1faf3c` / `0x1fb0ac` / `0x1fac24` | 包络目标、准备和单步推进 |
| `0x201674` | multisample 槽增益初始化 |
| `0x2913ec` / `0x2915a8` | 一般/音量键盘跟踪，两者负斜率算法不同 |
| `0x201434` / `0x20119c` | AMS Mixer 初始化/更新；类型 0/1/2 已独立移植 |
| `0x1fa1a0` / `0x1f9dd4` | 音量初始化/更新，已建立 Concert 合成上下文扫描 |

音符控制的公式、适用上下文和后续缺口见 [VOICE_CONTROL.md](VOICE_CONTROL.md)。

离线完整性检查：`python3 tools/verify_firmware_research.py`。它核对 15 个既有输入资产指纹、所有效果导出、控制扫描表头/长度/哈希、LUT 切片和报告对应的工具指纹。结果在 `research/derived/verification/firmware-research-check.json`；当前全部通过，原 84 个 WAV 的另行校验也通过。

原机预置研究另见 [FACTORY_SOUNDS.md](FACTORY_SOUNDS.md)：恢复官方 PRELOAD 的 768 个 Program，新增原机银行选择器片段及 ROM 波形元数据表。
