# 第二阶段：ROM 小窗口、RAM 检查和单块传输

2026-11-01。**第二阶段实机采集已完成：256块、64MiB、全部传输校验通过，原厂ARM诊断离线返回0，用户确认整库读取后发声正常。** 最终镜像、指纹及范围见[完整采集记录](ROM_ACQUISITION.md)。未使用SD导出，仍不拆机、不复制或安装VST3，不做资源压缩。下方保留单块验证和采集流程。

实机安装日志与替换前v2副本：`research/derived/firmware/KROSS2_V124/rom/injection/operations/20261031T215417814104Z/`。采集会话为`research/derived/acquisitions/KROSS2_ROM_stage_b_20261031T215150691039Z/`，原始采集目录在`research/libraries/`同名目录。

采集完成后，用户要求移除读取器。原厂1.2.4应用现已恢复并读回核对，系统卷安全弹出，用户确认正常启动、发声正常；下文安装/采集命令保留用于研究复现，读取器已不在琴上。

## 本阶段做什么

候选位于`research/derived/firmware/KROSS2_V124/rom/injection/stage-b/`，新增4028字节ARM代码，沿用实测的`0xc0500000`入口。固件原件、第一阶段候选及回退副本保留。

```text
Stage B SHA-256:
1564ab16dece5eed3ac2a8af27ef6b1d49ddccf39f89daa27dac1970fe1bfdfa
原版回退:
3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54
```

一次72/18请求仍只使用原厂FIFO传递的8字节事件：

| 模式（事件字节4） | 作用 |
| --- | --- |
| 0，索引0 | 返回身份版本03，不访问TG或预留RAM |
| 3，索引0 | 检查独立RAM区域为FF，逐字写入/读回测试图样并恢复FF |
| 1，索引0 | 调用原`0x11cd00`读取下64MiB末16字节的ROM身份信息 |
| 2，索引0..255 | 调用原`0x11c90c`读取一个256KiB块，然后分帧传回 |

索引线上高7位在前，事件只保留低8位，所以无论线上高位如何，都只可能选择0..255，不开放任意地址或写入命令。未接入开机自动读取或整库循环。

## 内存、门控和传输

原厂常规分配器在失败时也会调用断言，故新增代码不调用堆分配器。使用应用镜像FF填充区对应的RAM `0xc0520000..0xc05601ff`，共262656字节，包含256KiB块缓冲和512字节传输缓冲。官方原镜像这段全部FF，且未扫描到指向它的对齐u32常量；这不能证明所有运行时用途，**实机可用性仍须RAM检查**。缓冲区不占用原厂ROM管理器的共享256KiB工作区。

读块前要求整段RAM仍为FF；否则回复错误2，不读TG、不覆盖未知内容。原读函数负责进入/退出TG读模式，返回后才计算CRC和发送MIDI，发完后将预留RAM恢复为FF。原门控的声音暂停/恢复逻辑保持原样；每帧发送采用原厂发送互斥，不在TG读模式中持锁。

每块包含一帧64字节记录头、1024帧256字节数据及结束帧，总线上约333947字节。每帧使用MSB掩码7位打包；数据帧含偏移、长度和CRC32，整块另有CRC32。导入端验证完整偏移集合、固件profile、全部CRC及结束记录，拒绝缺帧、截断或冲突数据。只有通过后才生成独立`.record`，不拼出缺数据的ROM。

新增代码不含Flash擦写函数，但实际TG读门控、这段RAM及长传输尚未实测。原厂轮询和发送队列本身没有新增超时，异常时可能卡住。v2启动成功不能代替这些验证，也不保证任何故障都能通过USB恢复。

## 离线验证范围

`tools/verify_rom_stage_b.py`实际执行了修改后的ARM、原USB接收、8字节FIFO、原读门控和寄存器轮询。硬件寄存器、声音管理器回调、内核互斥和最终USB队列由桩代替。

- 16个通道的身份03；RAM检查及脏RAM拒绝；16字节窗口。
- 首块0、末块255，每块131072次合成u16读取，全部262144字节匹配。
- 原门控成对调用暂停/恢复；发送均发生在TG已回到正常模式之后。
- 两块各1026帧，CRC/偏移/长度通过；坏CRC、缺帧和截断被拒绝。
- 合成负载只留在测试内存，未写成实机采集文件或ROM镜像。

Mac采集器通过常规及AddressSanitizer/UndefinedBehaviorSanitizer自检，覆盖分片回调、实时字节过滤和长度上限。临时普通文件上验证了v2→Stage B→原版的替换/回退。既有31个研究输入、12个产品源码基线及5份冻结资源保持一致。

## 实机步骤

按此前方法进入USB存储模式，重新核对实际卷名。以下`--revision 3`才选择本阶段，默认参数仍不会选中ROM读取器：

```sh
cd /Users/shiftz/dev/kross2
KROSE_VOLUME='/Volumes/替换为实际系统卷名'
python3 tools/kross_app_file.py install --revision 3 --volume "$KROSE_VOLUME"
python3 tools/kross_app_file.py install --revision 3 --volume "$KROSE_VOLUME" --write
python3 tools/kross_app_file.py check --revision 3 --volume "$KROSE_VOLUME"
diskutil eject "$KROSE_VOLUME"
```

工具先保存当前应用再替换，逐字节读回核对。弹出后正常重启，确认正常发声、Exclusive勾选、通道01，并回到PROG主界面。采集期间先不要弹奏，结束后再检查声音。

重新运行`build/kross-probe-midi list`核对UID，然后创建独立采集会话；此命令本身不访问设备：

```sh
python3 tools/acquire_rom_block.py init --source 1225107962 --destination -399364021 --channel 1
```

保存输出的session路径，按顺序执行（每步都会先确认实机回复版本03）：

```sh
KROSE_SESSION='替换为init输出的session绝对路径'
python3 tools/acquire_rom_block.py scratch --session "$KROSE_SESSION" --experimental-stage-b
python3 tools/acquire_rom_block.py tail --session "$KROSE_SESSION" --experimental-stage-b
python3 tools/acquire_rom_block.py block --block 255 --session "$KROSE_SESSION" --experimental-stage-b
```

尾16字节必须CRC匹配且有KORG标记，才允许块采集。末块的最后16字节还须与独立窗口读取相同。重复读取同一块时要求SHA-256一致；失败保留原始数据并停止该会话后续块采集。首次单块通过并确认发声恢复后，再安排更多块。

原始`.syx`保存在`research/libraries/KROSS2_ROM_stage_b_UTC时间/`，捕获后设为只读；解码记录、尾部数据、日志和会话状态在同名的`research/derived/acquisitions/`目录。二者不混进产品资源。

若需回退，重新进入USB模式并核对卷名，执行`python3 tools/kross_app_file.py restore --revision 3 --volume "$KROSE_VOLUME" --write`，读回通过并安全弹出后正常重启。无法进入USB模式时，当前不提供未经验证的整盘回写、格式化或拆机步骤。

## 工具

读取器`tools/kross_rom_stage_b.c`；严格ARM ELF链接器`tools/arm_research_link.py`；构建/验证`tools/build_rom_stage_b.py`、`tools/verify_rom_stage_b.py`；原始采集`tools/kross_rom_midi.c`；协议验证`tools/parse_rom_midi.py`；顺序采集器`tools/acquire_rom_block.py`。`build/`仅放编译产物和综合报告。
