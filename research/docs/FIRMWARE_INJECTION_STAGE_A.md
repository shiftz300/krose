# KROSS 2 v1.2.4：第一阶段身份探针注入与回退

2026-11-01。用户明确接受实验风险，先要求具体步骤，随后要求执行并已进入USB存储模式。仍不拆机、不复制或安装VST3。

**此页保留第一版的历史步骤。v1正常启动发声，但三次探针无回复；随后发现并复现了读取8字节事件之外数据的缺陷。修正版v2已写入，正常启动发声，并实际收到版本02身份回复，第一阶段通过。当前操作请使用[v2说明](FIRMWARE_INJECTION_STAGE_A_V2.md)，不要回装本页旧候选。** v1操作记录为`research/derived/firmware/KROSS2_V124/rom/injection/operations/20261031T211046598168Z/`；v2操作记录为`.../operations/20261031T213044007847Z/`（目录时间为UTC）。

**这份包只验证新增代码能否在琴上运行，不包含ROM导出。** 启动及身份回复通过后，才具备继续验证TG读取、任务上下文和长数据传输的实机基础。不要把身份回复成功当成64MiB采样已经取得。

## 实验的确切内容

输入是已备份且与官方1.2.4一致的6291456字节`KROSSAPP.BIN`：

```text
原件/回退 SHA-256:
3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54

第一阶段候选 SHA-256:
ea7d1453a79a84f192eb060c386fa647f2495157e9eb98ea7ea6de183c874d03
```

候选只修改三个范围（均为文件偏移，不是虚拟地址）：

| 位置 | 修改 |
| --- | --- |
| `0x2bf288`，4字节 | 原72/18请求的错误分支指针改为`0xc0500000` |
| `0x500000`，232字节 | 原FF填充改为身份探针；没有开机自动调用 |
| `0x5ffffe`，2字节 | 按两份原厂应用观察到的累加关系重算u16LE校验 |

启动后，只有收到USB端口、正确通道、72/18、模式0、索引0的请求，才回复`KROSE`与版本1标记。探针不分配堆内存、不调用TG读写、不访问文件、不写启动Flash；使用原厂6字节头构造函数与MIDI发送器，最终送入USB队列。

这里的“没有写Flash函数”描述新增代码。**手工替换应用文件本身仍然是对琴内部存储的写入**，也不能排除程序错误导致异常。

## 证据和仍未确认的风险

`verification-arm.json`验证了修改后的完整应用中的局部路径：

- 16个通道：原字节解析器 → 来源端口交接 → 原命令分发 → 新代码 → 原头构造与发送器 → 模拟USB队列，回复匹配；
- 另执行原USB接收函数`0x2cc9ec`，由其真实指令写入来源8，经模拟事件队列交给原`0x2c1a6c`后得到回复；
- 拒绝895组非零模式/索引、DIN来源、Exclusive关闭、错误通道及两个受阻模式；
- 5组端口输入保留R4–R11和SP，另外254组原有分发与未修改应用一致；
- 触及已知TG、Flash、身份写入、堆分配入口即测试失败，实际未触及。

这些不是完整开机仿真：OS上下文、队列和特殊传输状态有模拟桩；真实USB输出队列未执行。未验证启动器是否接受修改应用、是否加载填充区、该地址的实机执行权限/运行时占用，以及真实任务栈和发送锁。即使小探针也可能不开机、卡死或破坏运行状态。

已有本机125MiB系统卷备份，不含完整启动Flash或TG采样ROM。坏应用后能否重新进入USB存储模式，**本机尚未实测，无法保证**。[一位机主的第一手维修记录](https://www.ifixit.com/Answers/View/886888/Korg+Kross+2+-+Pitches+reversed+or+not+sounding)报告，按住GLOBAL/MEDIA与FUNCTION开机可进入USB存储模式，且在出现“Loading application failed”后仍通过替换文件恢复过；这只是个案。

## 一、准备并检查本地包

包的固定位置：

```text
research/derived/firmware/KROSS2_V124/rom/injection/stage-a/
  candidate/KROSSAPP.BIN         第一阶段实验应用
  restore/KROSSAPP.BIN           与原件逐字节一致的回退应用
  probe-arm.text.bin            232字节新增代码
  probe-channel-1.syx           通道1身份请求；仅保存，不自动发送
  manifest.json                 修改范围、指纹与未知条件
  SHA256SUMS
  verification-arm.json         离线ARM结果
```

先用正常功能保存PCG/SNG；有Pad录音再另存KSC及关联文件或WAV，见[PCG备份说明](PCG_BACKUP_SCOPE.md)。PCG有助于恢复参数，不替代固件救援。

在Mac终端从包目录核对应用，再回项目目录检查客户端：

```sh
cd /Users/shiftz/dev/kross2/research/derived/firmware/KROSS2_V124/rom/injection/stage-a
shasum -a 256 -c SHA256SUMS
cd /Users/shiftz/dev/kross2
build/kross-probe-midi self-test
```

两份应用均应显示`OK`，客户端自检应显示`PASS`。当前本机已经完成这些检查；不需要为了安装重新运行耗时的其他研究。

## 二、进入USB存储模式并只读核对目标

1. 关闭Ableton及其他MIDI工具。使用稳定供电，接好Mac与琴的USB线。
2. 琴关机，按住`GLOBAL/MEDIA + FUNCTION`再开机，等内部系统卷出现在Mac上。这是之前取得完整备份时使用的存储模式；不是正常演奏模式。
3. 找出新出现的卷名，不沿用旧的`disk4`编号。可执行下面只读命令：

```sh
ls /Volumes
diskutil list external physical
```

把下方变量中的中文替换为实际卷名，保留引号；它应是含`KROSSAPP.BIN`、`SYSINFO.BIN`等文件的**内部系统卷**，不是SD卡：

```sh
KROSE_VOLUME='/Volumes/替换为实际系统卷名'
python3 tools/kross_app_file.py check --volume "$KROSE_VOLUME"
```

应显示`current_kind: official-1.2.4`、6291456字节对应的原件SHA。工具要求外接USB、MS-DOS文件系统、确切挂载根和既有系统文件；任一不符会停止。`check`不会写入。如果是未知版本、文件缺失或尺寸异常，先检查原因，不格式化、不自动修复卷。

## 三、实际替换应用——这是第一次写琴

先查看操作计划，仍不写琴：

```sh
python3 tools/kross_app_file.py install --volume "$KROSE_VOLUME"
```

确认计划中的卷和哈希正确后，**下面这条才会覆盖琴上的应用文件**：

```sh
python3 tools/kross_app_file.py install --volume "$KROSE_VOLUME" --write
```

它先在Mac的`research/derived/.../rom/injection/operations/时间戳/`保存当前应用及日志，再原位写入同尺寸候选，fsync并逐字节读回。不打开原始设备节点，不格式化、不删除其他文件，不修改`PPAT.BIN`、`HWINFO.BIN`或参数银行。只有成功显示`Application file read-back verified`后才继续。

```sh
python3 tools/kross_app_file.py check --volume "$KROSE_VOLUME"
diskutil eject "$KROSE_VOLUME"
```

应显示`stage-a-candidate`，并确认弹出成功。**写入或弹出未完成时不要断电拔线。** 然后关琴，再不按任何键正常开机。观察能否正常进入Program模式、原有音色能否发声；出现异常直接走下方回退，不发送更多命令。

不要把这份原始BIN当CMP经“Update System Software”安装。[KORG官方更新包](https://www.korg.com/us/support/download/software/0/754/3833/)走SD卡与其附带的更新文件/说明；本实验采用之前已读出的系统卷文件路径，未重打包官方更新容器，也不是官方升级方式。

## 四、验证身份回复

琴需正常演奏模式，经USB MIDI连接；**USB存储模式不做此测试**。在`G–MIDI > FILTER`临时勾选`Enable Exclusive`，记下全局MIDI通道。客户端的`--channel`必须与之相同，范围1–16。此阶段不需要把Global设置写入内部存储。

```sh
cd /Users/shiftz/dev/kross2
build/kross-probe-midi list
```

找出KROSS对应的`source UID`（琴→Mac）和`destination UID`（Mac→琴）。使用**UID，不是行号**，负数UID也应保留。将以下两处中文替换为实际数字；通道不是1时也要改：

```sh
build/kross-probe-midi probe --source 源UID --destination 目标UID --channel 1 --experimental-stage-a
```

它只发一次固定身份请求，最多等待5秒，不读ROM、不上传固件。通道1请求和预期回复：

```text
TX: F0 42 30 00 01 49 72 18 00 00 00 F7
RX: F0 42 30 00 01 49 7D 4B 52 4F 53 45 01 F7
```

成功应显示`PASS: KROSE stage-A identity reply received`。仅这一步通过，才说明这台实机的应用加载、执行地址、命令路径和小消息回复已经得到验证。超时先检查UID、通道、Exclusive与是否退出存储模式；它不能单独证明注入失败，更不能判断ROM是否可读。

把正常开机、发声、该命令输出这三项结果带回当前研究，再实现和验证第二阶段。当前没有让琴读取TG ROM的有效请求，不试发其他诊断、写入或跨机型命令。

## 五、回退原应用

无论探针成功与否，都可先尝试回到原应用：关琴，按住`GLOBAL/MEDIA + FUNCTION`开机，重新核对实际卷名；设备号可能改变。若USB卷能出现：

```sh
cd /Users/shiftz/dev/kross2
KROSE_VOLUME='/Volumes/替换为重新出现的实际系统卷名'
python3 tools/kross_app_file.py restore --volume "$KROSE_VOLUME"
python3 tools/kross_app_file.py restore --volume "$KROSE_VOLUME" --write
python3 tools/kross_app_file.py check --volume "$KROSE_VOLUME"
diskutil eject "$KROSE_VOLUME"
```

应恢复为`official-1.2.4`和原件SHA。弹出成功后关机，正常开机。如果写入中断造成同尺寸文件哈希未知，先核对目标与日志；工具只在显式添加`restore --allow-damaged-app --write`时允许这种回退。

若卷不出现、文件缺失、尺寸改变、文件系统异常或读回失败，当前脚本不处理这些情况。**没有已验证的不拆机兜底方案；不要整盘dd回写125MiB镜像、格式化或循环刷写。** 保留现象和日志，进一步判断或交由维修。软件路线在这种故障下可能无法完成恢复，这是本次实验接受的剩余风险。

## 离线复现

```sh
cd /Users/shiftz/dev/kross2
python3 tools/build_probe_injection.py
python3 tools/verify_probe_injection.py
clang -std=c11 -O2 -Wall -Wextra -Werror -Wno-deprecated-declarations tools/kross_probe_midi.c -framework CoreMIDI -framework CoreFoundation -o build/kross-probe-midi
build/kross-probe-midi self-test
```

ARM验证需允许Unicorn JIT；这些复现命令不调用`kross_app_file.py install/restore --write`，不发送MIDI。汇编、构建、验证与Mac端工具都在`tools/`；候选、回退副本、报告和采集操作日志在`research/derived/`；原件、125MiB备份和产品`src/assets`不改动。
