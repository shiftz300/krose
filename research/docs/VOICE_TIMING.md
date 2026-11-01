# 控制调度与 TG 音量平滑

固件版本 v1.2.4；下述地址均为解压镜像文件偏移，虚拟基址 `0xc0000000`。可复现探针为 `tools/probe_voice_timing.py`，原 ARM 输出存于 `research/derived/verification/voice-timing-arm-comparison.json`，反汇编在 `research/derived/firmware/KROSS2_V124/voice/timing-control.arm.txt`。

## 调度的证据链

| 环节 | 原代码证据 | 结果 |
| --- | --- | --- |
| 启动构造 | `0x2b7474..0x2b74a4` | 管理器参数为 120、120、16，栈上传入 2 等参数 |
| 分批计算 | `0x1fd278..0x1fd2c0` | 每批 `120 / (16 / 2) = 15` 个语音 |
| 管理器推进 | `0x1fd3cc` | 连续 8 次覆盖全部 120 个语音各一次；探针只在语音推进边界记录索引 |
| 控制线程 | `0x2b5440` 经 `0x271324` 调度；尾部 `0x2b5578` | 读取时钟、计算等待、调用 `0x2cd704` |
| 内核超时 | `0x2fd18c` | 超时基点是下一 tick；clock=100、wait=1 实际排到 102，因此正常两 tick 一批 |
| Timer0 | `0x12f0cc` / `0x130620` | 地址 `0x01c20000`，PRD12=24000，TGCR=5，TCR=0x80，INTCTL=3 |
| 中断至内核 | `0x117064`、尾部 `0x11711c` → `0x2cd764` → `0x2fbd5c` | 空等待队列测试中一次中断推进内核时钟 1 |

[TI 官方 Timer64 表](https://downloads.ti.com/dsps/dsps_public_sw/sdo_sb/targetcontent/tirtos/1_21_00_09/exports/docs/products/bios_6_37_00_20/docs/cdoc/ti/sysbios/timers/timer64/doc-files/TimerTables.html)列出候选 AM1808 家族 Timer0 地址和默认 24 MHz 时钟；本地保留 HTML 与真正包含表数据的 `TimerTables.js`。这支持 **名义 1 ms/tick → 每批 2 ms → 单语音完整周期 16 ms（62.5 Hz）**。没有测量琴内晶振，不凭此确定主控完整型号。这里也不模拟线程抢占、负载抖动及所有启动阶段。

Amp EG 每次推进扣减 24 内部单位，因此名义换算为 `24 / 0.016 = 1500 单位/秒`。[KORG 参数手册](https://cdn.korg.com/us/support/download/files/96dbde75752a88b2daf897262d199b80.pdf)的 EG 时长表与此比例相符。不能把 1500 单位/秒误作 EG 调用频率。

## TG 平滑的命令格式

`0x12d288` 接收上一目标、新目标和时长。`0x12cc10` 从 `0x3a8d40` 选取系数，时长限制为 0–24：

```text
C(0) = 65535
C(n) = floor(65535 / (32*n)), n=1..24
p = arithmetic_shift_right(C(n) * (newTarget-oldTarget), 16)
step = p + (p >= 0 ? 1 : -1)
```

目标相同则跳过写入。`0x12cc30` 计算上述有符号步长；`0x12ccf8` 将 **有符号 step 放高 16 位、target 放低 16 位**，写入 TG 基址 + `0x418`。底层 `0x132690` 把 32 位字拆成高、低两个 16 位总线写入，不能把一次回调的 R1 截成 16 位。

原 ARM 已核对全部 25 项系数、28 组上下行命令及目标不变时无写入。32 帧/单位意味着 24 单位对应 768 帧，在名义 48 kHz 下恰为 16 ms，与语音控制周期吻合。整数舍入和 ±1 步长修正会让某些斜坡提前到达目标；并非所有斜坡都严格花满窗口。

**验证边界：** 已执行的是 ARM 命令生成和寄存器传输；没有执行 TG 芯片内部逻辑。电脑端选择每个原生音频帧累加 step、到达 target 时钳位的解释。这一解释与系数关系一致，仍须真琴录音或芯片资料进一步校验。

## 播放器接入

`src/instrument/NativeVoice.cpp` 独立实现已验证的 Concert 力度表、槽增益、两个 OSC 的键盘跟踪、两个 AMS Mixer、音量 AMS 和多段 Amp EG。最初由 `tools/prepare_voice_assets.py` 在构建时提取固件表及 Program；目录分离后改由 `tools/export_runtime_assets.py` 显式导出到 `assets/concert-se-grand/`，普通构建只复制冻结的 `NativeVoiceData.h` 到 `build/*/generated/`。输入/输出指纹保留；构建资源提取与音频运行均不再依赖固件执行，见 [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md)。

`PianoEngine` 以每语音 62.5 Hz 更新控制，以独立 48 kHz 相位推进 TG 平滑解释；宿主可用 32–192 kHz。移除了旧固定 1.5 ms 起音和指数释音。每音符从 note-on 建立控制相位，尚未还原全局分配器给每个硬件语音安排的相位。

两个 OSC 各自算控制量，但共享一次立体声采样读取，增益取均值并保留原型 0.4 余量。后续 Filter A/B 控制与 Filter EG 已接入，见 [FILTER_CONTROL.md](FILTER_CONTROL.md)；真实 TG 混合、声像、绝对响度、插值、滤波内部 Hz/Q、动态半踏板及专用效果 DSP 运算仍未恢复。CC7/CC11 等现有宿主控制保留电脑端线性处理；原始数值回归的上下文中它们为全量。

Release 现在默认 **288 ms 基础时间**（原索引 43 → 432 单位），随后施加已恢复的音高/力度 AMS，故实际释放不固定为 288 ms。Velocity 默认 1，表示不增加额外曲线；其他设置在原力度响应后作音量调整，层边界不变。旧项目保存的这些参数仍会按旧数值恢复，默认值变化仅影响新实例/新预置。

## 已执行验证与试听

- C++ 模型对照原 ARM：32512 个初始/释放上下文、243 个多阶段轨迹状态、28 个 TG 命令全部一致。轨迹只是选取的原始状态，不表示所有音符的完整持续轨迹都已穷举。
- 引擎回归：不同处理块划分音频一致；回调零 C++ `new`；力度边界、踏板、循环、复音抢占和事件恢复通过。
- MIDI60、力度100、按住0.5秒后松键，44.1/48/96/192 kHz 下语音结束约 0.38000–0.38001 秒。这是该测试上下文的电脑模型结果，不是全音域统一时长或真琴实测。
- CTest 3/3（含编译后 VST3 无界面宿主）、ASan/UBSan 2/2、官方 VST3 validator 47/47。仅项目内构建，部署选项关闭，未复制或安装 VST3。

新试听和清单在 `output/Concert_SE_Grand_Control/`。旧 `output/SEGrand/` bundle 和旧试听保留原样，不能用它们试听新控制模型。本阶段历史核验清单为 `research/derived/verification/native-player-check.json`；最新滤波接入清单为 `filter-player-check.json`。旧日志保留阶段证据，当前构建使用 `verify_filter_player.py`。

```sh
python3 tools/probe_voice_timing.py
cmake --build build/plugin --target test-native-voice test-piano-engine render-piano SEGrand-vst3 test-vst3-host -j 6
ctest --test-dir build/plugin --output-on-failure
python3 tools/verify_firmware_research.py
python3 tools/verify_filter_player.py
```

探针需 Unicorn；本机受限沙箱的可执行内存权限可能阻止 JIT，对照需在获准的研究执行环境运行。构建和播放器本身不使用 JIT。
