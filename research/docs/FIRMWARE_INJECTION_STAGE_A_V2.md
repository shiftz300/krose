# 第一阶段身份探针 v2：修正真实 MIDI 事件边界

2026-11-01。第一版已实机写入；用户确认正常启动、发声正常，但身份探针未回复。原厂身份查询返回`F0 7E 00 06 02 42 49 01 05 00 01 02 04 00 F7`，原厂当前模式查询返回`F0 42 30 00 01 49 42 02 00 02 00 00 F7`。因此USB MIDI往返、通道01、原厂1.2.4查询路径已实测可用。

Exclusive已由用户勾选，回到PROG主界面后第一版仍无回复。原厂72/15名称查询也无回复，原因尚未确认；不能把整个72系列的实机路由视作已经打通。

## 已复现的问题

原固件`0x2b8540`初始化USB事件FIFO时，传给`0x2b79c4`的元素大小为8字节。原入队`0x2b7bfc`和出队`0x2b7d74`均只复制两个u32。

第一版却读取`packet+8`处的u16，试图检查解析器中的索引高位。该位置不属于队列事件。此前离线测试直接把16字节解析缓冲交给分发函数，跳过了真实8字节复制，所以没有发现这个错误。

新增`tools/verify_probe_injection_v2.py`实际执行原USB接收、FIFO构造、入队、出队和分发，并在接收事件后填入非零数据：第一版会越过事件末尾读取，后方为A5或FF时静默拒绝请求；后方为0时才回复。该缺陷已在电脑复现，但未直接读取实机栈，因此不声称它已经解释了全部实机现象。

v2去掉越界检查，仍只使用事件内的命令、子命令、模式和低8位索引。回复版本标记由01改为02，用于分辨实际运行版本。没有加入TG读取、分配或Flash操作。

另确认原解析器索引按**高7位在前、低7位在后**组合，事件字节5仅保留低8位。第一阶段只返回身份，索引256等别名等同0无读取副作用；不能把此编码直接用于需要严格14位边界的后续协议。

## 候选与验证

新包独立放在`research/derived/firmware/KROSS2_V124/rom/injection/stage-a-v2/`。旧`stage-a/`候选、汇编和ARM报告保留，官方原件不改。

```text
v1（当前已安装）:
ea7d1453a79a84f192eb060c386fa647f2495157e9eb98ea7ea6de183c874d03
v2（已实机验证身份回复）:
8dd166c6d4650f3b060c1f5129f9fa02bd1710672e565041ef034b82ab0b0944
官方回退:
3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54
```

v2代码220字节，仍只修改原先声明的分发表指针、FF填充和校验值。离线验证48组通道/事件后方数据、131组无效模式/索引，均未读取事件之外；另验证3组无读取副作用的索引别名。OS、中断、内存分配和最终MIDI发送仍有模拟，不是实机通过。

## 替换与回退

按[第一版说明](FIRMWARE_INJECTION_STAGE_A.md)重新进入USB存储模式并核对卷名。工具只有显式`--revision 2`才选择v2；允许输入为原版或已验证的v1，其他未知应用会停止。先计划再写入：

```sh
cd /Users/shiftz/dev/kross2
KROSE_VOLUME='/Volumes/替换为实际系统卷名'
python3 tools/kross_app_file.py install --revision 2 --volume "$KROSE_VOLUME"
python3 tools/kross_app_file.py install --revision 2 --volume "$KROSE_VOLUME" --write
python3 tools/kross_app_file.py check --revision 2 --volume "$KROSE_VOLUME"
diskutil eject "$KROSE_VOLUME"
```

工具会先在Mac保存当前v1应用及操作日志，再替换并读回核对。成功弹出后关机正常开机；确认正常发声、Exclusive勾选、通道01、处于PROG主界面后：

```sh
build/kross-probe-midi probe --source 1225107962 --destination -399364021 --channel 1 --revision 2 --experimental-stage-a
```

这些UID是当前这台Mac本轮枚举结果；设备重连后应重新运行`build/kross-probe-midi list`核对。v2预期回复：`F0 42 30 00 01 49 7D 4B 52 4F 53 45 02 F7`。

如需回退原厂应用，重新进入存储模式并核对卷名，执行`python3 tools/kross_app_file.py restore --revision 2 --volume "$KROSE_VOLUME" --write`，读回核对后安全弹出，再正常开机。仍不保证坏应用后USB模式一定可用；不做整盘回写、格式化或拆机。

**当前v2实机验证通过。** 写入、独立读回核对及安全弹出后，用户确认正常启动、发声正常、Exclusive开启、通道01、PROG主界面。Mac端实际收到：

```text
F0 42 30 00 01 49 7D 4B 52 4F 53 45 02 F7
PASS: KROSE stage-A identity reply received.
```

这确认了修改应用能启动、新增代码在所选地址实际执行、8字节事件经原厂分发进入新处理器、14字节回复经真实USB MIDI返回Mac。修正后的v2已在实机解决第一版无身份回复的问题；不能因此断言原厂72/15名称查询也已恢复，尚未重测。

操作日志、替换前v1副本和`installation-result.json`在`research/derived/firmware/KROSS2_V124/rom/injection/operations/20261031T213044007847Z/`。包内`hardware-result.json`保存实机记录；构建时`manifest.json`及离线ARM报告中的`hardware_tested: false`保留其当时测试范围，当前部署状态以独立实机记录为准。

第一阶段完成；尚未验证真实TG读块、堆缓冲区、长数据发送或64MiB完整导出，也未取得真实ROM。下一阶段从一个受限块开始，读取后恢复TG发声状态，再做带校验的传输；不能直接把短身份报文成功等同于导出器已可用。
