> 阶段记录：本页保留当时的逆向过程。后续已取得 TG 下 64 MiB 并完成板载采样解码；现状见 [当前逆向进度](PROGRESS.md) 与 [资源索引](../RESOURCES.md)。

# 原机 ROM 恢复：公开资料、导出原型与实机边界

2026-11-01 更新：**已从自有KROSS2实机取得完整下64MiB TG ROM，256块传输校验及原厂诊断算法核对通过，用户确认采集后发声正常。** 最终镜像、原始来源及尚未解码波形的边界见[完整采集记录](ROM_ACQUISITION.md)。下方保留此前仅有离线原型时的研究记录，不代表当前仍未取得负载。

此页记录此前尚未获得写入授权时的离线导出原型。后续用户接受风险并要求代为执行；v2修正FIFO边界后实机回复身份02，再通过[第二阶段读取器](ROM_SINGLE_BLOCK.md)取得完整目标区域。插件和原始备份保持原样。下方未部署/未取得ROM的说明仅描述当时阶段。

## 公开资料核查

| 一手来源 | 实际取得的证据 | 对本机恢复的作用 |
| --- | --- | --- |
| [KORG官方更新页](https://www.korg.com/us/support/download/software/0/754/3833/) | 下载并检查旧版1.2.2 ZIP；同1.2.4一样只有主应用CMP、PPAT和说明PDF | 未获得BOOTSYS或KROSSPCM；不把更新包当成整库 |
| [Hacktribe作者的PCM讨论](https://github.com/bangcorrupt/hacktribe/discussions/77) | 作者报告在Electribe中截取PCM至CPU RAM后，经SysEx导出；讨论中也有Mac成功报告 | 是实际先例，机型和改动条件不同 |
| [作者的SysEx源码](https://github.com/bangcorrupt/hacktribe/blob/94c8e608e6918c432cac90b2c19042b2d65ae626/scripts/e2sysex.py) | RAM读取opcode52、Flash读取55、执行RAM代码57 | 已做KROSS2原解析器离线对照，不能直接复用 |
| [作者的启动备份脚本](https://github.com/bangcorrupt/hacktribe/blob/94c8e608e6918c432cac90b2c19042b2d65ae626/scripts/e2-backup-bootloader.py) | 通过Electribe接口读运行时SBL，地址80000000、长度1c000 | 不是现成启动镜像，也不是KROSS2导出脚本 |
| [机主的USB维修记录](https://www.ifixit.com/Answers/View/886888/Korg+Kross+2+-+Pitches+reversed+or+not+sounding) | 替换系统文件修复系统存储损坏，但不能据此恢复音高故障 | 与我们取得系统卷、未取得TG ROM的边界一致 |

另检索KROSSPCM.BIN、BOOTSYS.BIN、KROSS2 ROM dump、维修镜像、俄文“дамп прошивка”、旧版更新和完整MIDI实现说明。检查过的来源中未找到可验证的KROSS2原机PCM映像或现成整库导出器；这不是证明所有私人维修资料都不存在。

作者文件只保存用于检查，未导入或执行。源代码按Git blob校验，保留GPL许可证；快照与来源指纹位于 `research/external/rom-recovery-20261101/`，没有混入产品代码。旧版官方原件保存于 `research/downloads/KROSS2_V122.zip` 与 `research/firmware/KROSS2_V122/`，派生ARM镜像另存 `research/derived/firmware/KROSS2_V122/`。

## 跨机型命令不能直接照搬

新工具 `tools/compare_recovery_protocols.py` 只解析第三方源码的AST，不运行其MIDI代码。

6组原ARM字节解析覆盖3个公开命令及原Electribe model24／替换后的KROSS2 model49：

- model24被KROSS2的model检查拒绝；
- 即使改为model49，RAM读取52和执行57也没有产生有效读取事件；
- Electribe Flash读取55的完整参数报文，在KROSS2中产生无效报文事件05，未进入Flash读函数；
- 另执行KROSS2内部55事件的分发，目标是 `0x2be8bc`，静态对应Exclusive配置处理，不能当作读Flash。

因此不能靠修改设备ID就把现成脚本变成KROSS2 ROM工具。没有给琴试发这些报文。

## 启动代码的新定位线索

原1.2.2和1.2.4各有一个小getter返回 `0x8001b000`，均已执行原ARM验证：

| 版本 | 解压固件SHA-256 | getter文件偏移 |
| --- | --- | --- |
| 1.2.2 | `959e585abd71f7986ff73c6861e4b518d26c253269b2b33fd9d1b962ecf905e8` | `0x2c7ec8` |
| 1.2.4 | `3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54` | `0x2c7f9c` |

1.2.4的版本界面调用该getter后读取四字节版本。这表明应用仍引用独立的片上RAM启动信息，而非把这段启动程序保存进应用镜像。与Electribe脚本所读SBL范围的位置吻合，是值得继续检查的线索；不能推出两机启动代码或USB协议相同。

两份6291456字节应用原件的最后u16均等于前面所有字节累加的低16位。这里只记录已验证的原件校验关系，没有因此生成或安装修改固件，也没有证明修改后的程序一定能启动。

## 已实现的离线导出器

研究源文件 `tools/rom_recovery_core.c`，未接入产品CMake。它接受外部提供的只读块函数、输出回调和256KiB scratch，不分配内存，不包含Flash写入、擦除、MIDI设备发现或固件安装逻辑。

一次请求只允许块号0..255，对应候选原机下64MiB。每块输出64字节头与262144字节负载；头记录块号、长度、CRC32、固件profile SHA-256和来源标签。

编译得到972字节ARMv5TE代码，执行时加载在模拟器的测试地址。它不是完整固件，不应复制到琴上；没有确定安全加载地址、任务上下文、scratch所有权或实机发送通道。代码仅证明导出计算和原读取函数可以连接。

`tools/probe_rom_recovery.py` 已验证：

1. 原生C导出全部256个合成块，导入端逐块比较全部67108864个负载字节；
2. 新ARM代码直接调用原 `0x11c90c`，执行首块0和末块255，每块131072次合成TG u16读取；CRC及每个输出字节一致；
3. 越界块、容量不足、未对齐buffer和输出失败会返回错误；
4. 导入端拒绝坏CRC、截断、缺块及冲突重传，相同块重传可接受。

所有完整测试流只在电脑内存中使用，没有保存为ROM镜像。合成记录带synthetic标签，导入CLI明确拒绝它们。

## 真实采集后的导入端

`tools/recover_rom_stream.py` 目前是离线导入器，**不会自行采集数据**。只有取得符合上述格式的真实记录后，它才有输入。

它要求256块全部存在、CRC匹配、固件profile一致，并检查末16字节中的KORG标记；输出必须位于 `research/derived/`。条件不全时不写完整镜像。即使通过，也命名为 `TG-ROM-candidate.img`：CRC和profile证明数据一致，不能证明物理来源、型号真实性或全部采样编码已经解开。

## 尚未越过的实机边界

当前短板是**运行入口和传输入口**。原厂已有的银行／名称请求不输出PCM；固定诊断只输出校验状态；125MiB USB系统镜像也不包含已确认的原机TG负载。新增导出器不能靠电脑模拟补出不存在的真实字节。

继续仅USB软件路线，可查启动维护模式与尚未恢复的间接分发；在没有新入口前，不能声称能够实机只读导出。修改应用或接入硬件调试都属于另外的实机步骤，尚未执行。

现有USB镜像可保留已暴露系统卷的原始数据，但不包含完整启动Flash及TG PCM，**不是可以保证任何刷写／硬件错误都能恢复的整机救援备份**。当前不根据它承诺修改固件没有变砖风险。

## 复现与输出

```sh
python3 tools/compare_recovery_protocols.py --verify-arm
python3 tools/probe_rom_recovery.py
python3 tools/probe_rom_recovery.py --verify-arm
python3 tools/verify_firmware_research.py
```

ARM执行需要允许Unicorn JIT；外部读写仍全部是合成桩或内存回调。结果位于 `research/derived/firmware/KROSS2_V124/rom/recovery/`，包括协议对照、导出器验证和独立ARM代码节。没有制作安装包，没有更改原固件或备份，没有复制／安装VST3。
