# KROSS 2 芯片与 DSP 传输证据

核对日期：2026-10-31。目标是取得重建音色所需的结构参数；不以完整芯片模拟为验收前提。

## 板卡与芯片识别

| 证据 | 可确认内容 | 边界 |
| --- | --- | --- |
| [Syntaur 的 KROSS 2 CPU 板资料](https://syntaur.com/parts/korg/kross-2-61/cpu-board-korg-kross-2) | CPU 板 KLM-3665，Korg 料号 510C94233665 | 板卡型号资料，无完整芯片规格 |
| [板卡卖家自己的实物照片](https://www.ebay.com/itm/156522112587) | 包装写 KROSS2-61 / KLM-3665 DATA；PCB 为 KLM-3665B；音源芯片可见 KORG / TGi，另有 TI 标识主控 | 仅该板卡版本；TI 芯片完整料号不够清晰，未据此宣称 AM1808 或 OMAP-L137 |
| 官方 v1.2.4 镜像字符串 | OmapL108SystemConfiguration.cpp、OmapL108Spi.cpp、OmapL137USB.cpp、OmapL137i2c.cpp、TG01.cpp | 确认软件驱动家族，不能将共享驱动名字直接当作实物料号 |

照片保存在 `research/external/hardware/`，来源与指纹在 `research/assets.json`。TGi 的实物证据补充了此前仅由 TG01 驱动名得到的线索；TGi、TG01 和老 M1 的 TGI 不应混为同一芯片。

[TI 的 OMAP-L1x 资料](https://www.ti.com/en/download/mcu/OMAP-L1x.pdf) 将 L108 列在 ARM-only 家族，L137/L138 则属于 ARM + C674x DSP 家族；L108 的初期资料列出 ARM9、约 300 MHz 工作点、1.0–1.2 V 内核以及 mDDR/DDR2 等接口。本地副本在 `research/downloads/TI_OMAP-L1x_overview.pdf`。这些是**候选主控家族的资料**，并非已经测得本琴的主频或配置。

同时查阅了 [TI AM1808 官方规格](https://www.ti.com/product/AM1808) 作为同类 ARM9 主控对照。尚未获得足够清晰的丝印或完整 KROSS 2 原理图，不将其 375/456 MHz 等额定规格写成本琴实测参数。TGi 的内部算术位宽、累加器、时钟及完整 ISA 仍无可核对的公开手册。

## 已由原固件确认的程序传输

此前将 8 字节存储单元简称为“64 位 DSP 程序”。本轮进一步执行真实上传函数后，确认需要细分：

- 镜像里每项保存 **8 字节**。
- 原函数 `0x12e9d8` 只读取该项的 u16 偏移 **0、6、4**。
- `0x12daac` 将它们依次写到 TG 基址 + `0x718`、`0x714`、`0x710`，每项实际程序载荷为 **48 位**。
- 偏移 2 的 16 位没有上传。实验将所有这些半字改为 `0x5aa5`，四种效果的上传序列仍完全相同。
- 常数通过 `0x12dbc4` 分成高、低 16 位写入 +`0x73c`、+`0x738`，每项传输 32 位。传输宽度不等同于音频乘法器或累加器精度。

验证只拦截底层 `write16` / `read16`，记录写入并返回 ready；其余上传原指令照常执行。没有映射物理硬件，也没有运行乐器操作系统。报告：`research/derived/verification/dsp-transport.json`。

每种效果新增 `dsp-upload.u16le.bin`，按上述三个寄存器的写入顺序保存，每项 6 字节。已有 `dsp-code.u64le.bin` 文件和目录名保留，继续表示原镜像的 8 字节存储布局。

## 重建时怎样使用这些资料

ARM 控制计算可以直接隔离执行：本轮已据此恢复目标 EQ 的系数，电脑端采用浮点双二阶滤波。Chorus/Hall 则从已知延迟、调制速率、混响时间和音色目标建立近似模型。后续 ISA 逆向可逐步校正模型，但当前实现不依赖完整 TGi 模拟器。
