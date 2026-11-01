# 原机64MiB TG ROM：实机采集完成

2026-11-01。用户自有KROSS2，经已安装的第二阶段读取器和USB MIDI完成下64MiB的256块采集。没有使用SD导出、拆机、压缩或安装VST3。整库采集约360秒；此前末块额外独立读取一次，两次全部262144字节一致。用户确认窗口、单块及整库读取后均发声正常。

## 交付文件

完整镜像（只读）：

```text
research/derived/acquisitions/KROSS2_ROM_stage_b_20261031T215150691039Z/complete/TG-ROM-candidate.img
67108864 bytes
SHA-256 c9d4c9b4dd0f915b45a553e6b66d2cab7e51b80f4b2189fb6db4d91b1ccc94a5
```

同目录`acquisition-verification.json`是最终核对报告，`import-report.json`记录完整记录流的导入；`SHA256SUMS`可独立校验镜像。父目录`complete-records.bin`包含256份64字节头+256KiB负载记录，可重新导入。单块记录、每次报告及进度保留在同一会话目录。

未处理的原始消息位于：

```text
research/libraries/KROSS2_ROM_stage_b_20261031T215150691039Z/
```

共有259个原始`.syx`：257次块采集（包括末块的额外一次）、一次RAM检查和一次尾部窗口。原始消息总计85824465字节，另附`manifest.json`和`SHA256SUMS`。文件设为0400，原始目录设为0500；继续采集应创建新会话，避免修改已冻结来源。目录名使用UTC，实际操作日期为北京时间2026-11-01。

## 已通过的验证

| 检查 | 结果 |
| --- | --- |
| 块号0..255 | 全部存在，无缺块 |
| 每块传输 | 1024个数据帧的长度、偏移、CRC32及整块CRC32通过 |
| 拼接后镜像 | 每块SHA-256与独立记录一致，总长64MiB |
| 地址变化 | 256个块的负载SHA-256各不相同 |
| 独立尾部读取 | 与完整镜像末16字节逐字节一致：`4b4f52470100000d000000003a73ec56` |
| 原厂诊断算法 | 两个u16计算值分别为`0x733a`、`0x56ec`，与尾部存储值一致 |
| 原厂ARM诊断 | 在电脑用已采集字节执行原`0x11cc88`，返回0，通过；没有为此再访问琴 |
| 采样目录范围 | 已恢复的4070个描述符候选地址全部落在镜像中，最大终点67108842 |
| 读取后乐器状态 | 用户确认发声正常 |

原厂诊断只覆盖原算法指定的稀疏读取位置，不是对每一个ROM字节的原厂校验。逐帧/逐块CRC覆盖实际传回负载，证明传输自洽；物理来源以本次安装、身份03、端口和原始消息记录为证，不是设备的密码学签名。

目录中有496个音乐multisample、1014个drumsample及相关区域/描述符。完整地址范围已取得，**采集阶段当时尚未解码；随后已完成全部 4068 个音乐采样的 WAV 导出和波形试听目录，见 [当前进度](PROGRESS.md) 与 [解码记录](ROM_DECODING.md)**，也没有因此把所有原机音色接入Krose。本镜像是TG下64MiB采样区域，不是启动Flash、整机存储或扩展区的完整备份。

## 琴和产品的当前状态

全部读取进程已结束。用户随后要求移除读取器，现已将琴上的应用恢复为与最初实机备份逐字节一致的原厂1.2.4，独立读回SHA-256为`3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54`，系统卷已安全弹出；用户已确认正常重启、发声正常。读取器移除完成，ROM及研究数据保留。

恢复日志位于`research/derived/firmware/KROSS2_V124/rom/injection/operations/20261031T221645693766Z/`；最新部署状态为同级`current-deployment.json`。

替换前v2应用和操作日志在`research/derived/firmware/KROSS2_V124/rom/injection/operations/20261031T215417814104Z/`；原厂恢复副本在第二阶段包`restore/KROSSAPP.BIN`。原始125MiB USB备份及官方固件保留，产品`src/`、冻结`assets/`未改动，也未复制或安装VST3。

## 重做离线核对

```sh
cd /Users/shiftz/dev/krose
python3 research/tools/verify_acquired_rom.py --session research/derived/acquisitions/KROSS2_ROM_stage_b_20261031T215150691039Z --verify-arm
```

此命令只读电脑上的采集数据并运行模拟器；不发送MIDI。采集工具为`tools/acquire_rom_library.py`，底层仍是已验证的逐块`tools/acquire_rom_block.py`。用户已明确取消SD方案研究。
