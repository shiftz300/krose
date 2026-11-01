# 官方固件证据与重建算法

研究输入为 [KORG 官方 KROSS 2 v1.2.4 更新包](https://www.korg.com/us/support/download/software/0/754/3833/)，不是第三方修改固件。来源指纹详见 `research/assets.json`。

新增的完整效果目录、运行时初始化恢复和可查询 ARM 索引见 [FIRMWARE_MAP.md](FIRMWARE_MAP.md)；幅度、键盘跟踪、AMS 与包络单步移植见 [VOICE_CONTROL.md](VOICE_CONTROL.md)；控制线程、内核定时器及 TG 平滑寄存器见 [VOICE_TIMING.md](VOICE_TIMING.md)；Filter A/B 与 Filter EG 的新增原 ARM 探针和字段修正见 [FILTER_CONTROL.md](FILTER_CONTROL.md)。

## 坐标与输入

- 官方原件：`research/downloads/KROSS2_V124.zip`。
- 原样解包：`research/firmware/KROSS2_V124/KROSS2SY/KROSSAPP.CMP`，以及同包其他文件。
- 派生 ARM 镜像：`research/derived/firmware/KROSS2_V124/KROSSAPP.bin`。
- 镜像长度 `0x600000`，SHA-256：`3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54`。
- 本文地址统一为该镜像的**文件偏移**。ARM 装载基址为 `0xc0000000`；例如偏移 `0x1f55bc` 对应虚拟地址 `0xc01f55bc`。KEP 文件偏移是另一坐标系。
- ARM 整数和表项是小端；该固件软浮点 double 常量使用高 32 位字在前的字序，不能一概用普通 `<d` 扫描常量。

## CMP 容器

前 4 字节为小端输出长度，接着 4 字节为解压结果的字节和。其后为 4096 字节环形字典的 LZSS：初始字典置零，写指针 `0xfee`；标志最低位优先，1 为字面量，0 为双字节引用。引用位置为 `low | ((high & 0xf0) << 4)`，长度 `(high & 15) + 3`。

验证：恰好消耗完整 CMP，结果字节和 `32d233df` 与头一致，并由 SHA-256 锁定版本。

## KEP 加密地址索引

| 文件偏移 | 作用 |
| --- | --- |
| `0x061574` / `0x061a64` | 单块加密 / 解密 |
| `0x061f54` | 密钥展开 |
| `0x0620f0` / `0x062178` | 缓冲区加密 / 解密 |
| `0x1ec65c` | 依据类型选择密钥 |
| `0x1ef190` | 生成运行时工厂密钥及校验 salt |
| `0x33f958` / `0x340958` | 初始 S / P 常量 |

Blowfish 的 key word 与 F 函数字节次序采用小端变体。实现及隔离 ARM 对照见 `tools/probe_blowfish.py`，完整提取见 `tools/extract_kep.py`。

## 采样重建地址索引

| 文件偏移 | 已观察到的行为 |
| --- | --- |
| `0x1f5194` | 编码函数入口，含两阶重建反馈 |
| `0x1f5254..0x1f5304` | 读取两个有符号 16 位系数，乘以两项 32 位历史值，缩放、截断与饱和 |
| `0x1f55b0..0x1f55d0` | 取量化码高字节，转为有符号索引，查表 |
| `0x1f55dc..0x1f5698` | 表值左移 16，叠加预测值，饱和后写入历史 |
| `0x3fd180..0x3fd37f` | 256 项有符号 16 位逆量化表，零值位于索引 128 |

反汇编节选和原始 LUT 二进制保存在 `research/derived/firmware/KROSS2_V124/`；它们必须与当前镜像指纹一起使用。

设 `q` 是负载字节按 int8 解释后的值，`a1, a2` 是样本描述偏移 8、10 的两个 int16，`T` 为上述表。初始历史为零，以 32 位整数保存：

```text
prediction = sat32(trunc_towards_zero((a1*y[n-1] + a2*y[n-2]) / 16384))
y[n]       = sat32(prediction + T[q + 128] * 65536)
sat32(x)   = min(2147483647, max(-2147483647, x))
```

乘加采用 64 位整数，负数除法向零截断。负饱和值为 `-2147483647`。输出 WAV24 取 `y[n]` 的高 24 位；24 位容器用于保留重建精度，不宣称原始录音为 24 位。

实现：`tools/korg_pcm_decode.c`；独立 Python 对照与原指令执行：`tools/test_korg_pcm.py`。

该实验执行的是**编码器内部反馈重建**的原始指令。它为重建公式提供直接证据，但 TG01 的硬件位宽、舍入、插值、循环和后续处理仍需另行验证，不能据此宣称已经复刻整个音源。

## Program、音高与效果地址索引

| 文件偏移 / 明确注明的 RAM 地址 | 作用 |
| --- | --- |
| `0x407bd0` | Program 参数 namespace 指针表 |
| RAM `0xc1666c88` | 当前 Program 的运行时字段基址 |
| `0x20af84` | 原始参数 getter，处理类型、有符号位域和位移 |
| `0x1ff764` / `0x1ff38c` | 单音音高初始化 / 更新 |
| `0x1ff348` | 整数指数→步进，3072 内部单位/八度 |
| `0x405984` / `0x405b88` | 步进小数表 / 整数表 |
| `0x12ce5c` | 步进传入 TG 寄存器路径 |
| `0x1fa300` / `0x1fb8c4` | Amp EG / Filter EG 初始化 |
| `0x1fa6c0` / `0x1fbaf8` | 两种包络的阶段处理 |
| `0x1fac24` / `0x1fb0ac` / `0x3fd5a4` | 公共包络推进 / 时间参数设置 / 时间表 |
| `0x3d9b10` / `0x336cd0` | 47 项合成器 AMS 源 / 38 项效果 Dmod 源 |
| `0x336d6c` | 效果定义指针表 |
| `0x5a51c` | 效果 DSP 程序与常数加载，可选择缓冲模式 |
| `0x12daac` / `0x12dbc4` | DSP 程序 / 常数写入硬件的路径 |

参数描述符长 20 字节：type、display format、shift、width 各 1 字节，随后是 flags、min、max、callback 各 4 字节。display format 不是字段存储偏移。参数单元另存数据指针与描述符指针；`tools/program_firmware.py` 按这些元数据读取。1042 个 Program 字段和 95 个效果字段与原 ARM getter 逐项一致。

步进函数先将输入上限限制为 `0x5fff`，加 `0x8000` 后按高位读取 32 位整数表、低 8 位读取 16 位小数表。返回 `base + (((base * fraction) & 0xffffffff) >> 16)`，乘法保留低 32 位。单独的 Python 实现已对照原 ARM 的跨表输入；完整 pitch 初始化/更新也在根音、零额外调制上下文中验证。详见 [PROGRAM.md](PROGRAM.md)。

效果定义 40 字节，字段依次为 full-name、short-name、DSP-code、constants、三个 ARM 回调指针；随后四个 u16（参数数、8 字节代码项数、32 位常数字数、未解数量），末尾参数指针表。现已扩展至全部 135 项，代码/常数与原加载器缓冲输出一致。13 项的代码指针/长度需先执行原始启动初始化函数，不能将镜像中的零解释成无程序。

进一步执行总线上传路径后确认：每个 8 字节代码项只上传偏移 0、6、4 的三个半字，偏移 2 被忽略，实际可见程序载荷为 48 位。修改忽略半字不影响上传；常数则分两次 16 位写入。证据在 `dsp-transport.json`，详见 [HARDWARE.md](HARDWARE.md)。

EQ 数学常数初始化 `0x57c1c`、`0x60f70`；双二阶生成 `0x99714 → 0x5f560 → 0x5e8fc / 0x5ebe0`；拆分系数助手 `0x573e0`。本轮用原缓冲模式取得八段参数对应的实际系数。原程序 ISA 仍未完整解释，电脑端采用浮点 EQ 和近似空间效果，详见 [RECONSTRUCTION.md](RECONSTRUCTION.md)。
