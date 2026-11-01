# 音量、AMS 与包络控制逆向

版本及坐标沿用 [FIRMWARE.md](FIRMWARE.md)。控制计算已成为播放器基线，TG 音频内部执行仍使用解释模型。研究仍在继续，VST3 不复制、不安装。

## 修正 OSC2 参数分组

原报告的 `namespace + oscillator*15` 不正确。OSC1 从 `0x41` 开始，OSC2 从 `0x51` 开始，中间另有 `0x50` 公共键盘跟踪组，故步长为 **16**。音色内存块大小仍为 **380 字节**，两者是不同维度。

`analyze_concert_program.py` 已修正并重生报告；两个 OSC 的对应字段须满足地址差 380、编码/范围一致。回调可按 OSC 不同，不能要求其指针相同。原 getter 回归另对公开的 600 个分组字段检查语义归属。原始 1042 个字段的数值读取没有因此改变；受影响的是 OSC2 的旧分组和名称。原 KEP、固件和 WAV 保持不变。

## 可独立运行的整数公式

`tools/voice_math.py` 从固件读取锁定版本的表，移植以下算法，不依赖 Unicorn 执行：

| 算法 | 已核对的性质 |
| --- | --- |
| `exp2_q16` | 有符号 Q16 指数，小数表插值、范围处理 |
| `modulation_product` | `sat16((intensity * source * 331) >> 15)` |
| `eg_duration` | 时间乘以 Q16 指数倍率；正调制时极短基础值先升至 8 单位 |
| `eg_curve_coefficient` | 0–10 共 11 类曲线；短表、中表插值、长时间插值及上限 |
| `eg_level` | `level*330` 加 AMS，原整数截断与电平限制 |
| `EnvelopeSegment` | 目标方向、内部进度递推、曲线、电平和 24 单位倒计时 |
| `multisample_gain` | 槽 Level 与两路调制，保留原缩放，非直接除以 127 |
| `velocity_gain` | 原力度表与 Velocity Intensity 映射，非简单幂函数 |
| `keyboard_tracking` | 一般/音量两种算法，四段斜率、±Inf、音量负斜率特殊编码 |
| `basic_mixer` | 类型 0 A+B、类型 1 Amt A×B、类型 2 Offset；限幅 ±24576 |

独立实现与原 ARM 对照：309 个指数用例、400 个调制乘积、700 个时间调制、165 个曲线查表、300 个电平调制、45 个槽增益、768 个 Concert 键盘跟踪及 198 个斜率边界用例、300 个 Mixer 用例，以及 **6491 个包络单步状态**。

电平/Mixer 的隔离测试在 AMS 源边界注入已知值；实际运算执行原函数。指数、时间、曲线、槽增益、键盘跟踪及无踏板的包络单步测试不替换函数。`voice-math-arm-comparison.json` 分开记录这两种情形。

## Concert 的原始声音上下文

`tools/voice_firmware.py` 构造显式的语音、Program、OSC、控制器和全局指针；运行原键盘跟踪、两个 Mixer、Amp 初始化、完整 Amp EG 阶段推进及释放。替换的外部入口只有：Tone Adjust 返回零、MIDI 覆盖使能返回关闭、轨道静音查询返回未静音。

`tools/probe_concert_voice.py` 遍历两个 OSC、128 个音高、力度 1–127，合计 **32512 个合成上下文**，按实际层边界使用 Level119/119/127：

- 所有上下文的力度因子，与独立力度 LUT + 槽增益公式一致。
- 所有上下文的两个 Mixer，与独立类型 1/2 公式一致。
- 保留初始音量/EG 控制量、有效 Attack 与 Release 内部时间。
- 额外导出三条带松键的包络轨迹，均进入结束状态。

上下文保留原 Program 的 Mixer 值 103、Amp Level106、Velocity Intensity70 和 Exp. Velocity 强度17；另设 part volume127、CC7/CC11 全量、LFO 音频贡献为零、额外样本/音量偏移为零。未运行完整 note-on 调度、全局力度曲线、Filter EG 或 TG 插值/增益运算。表中增益是控制量，不直接标成线性音频倍率或 dB。

部分结果如下，均为力度 100 的初始原始 Amp 控制值：

| MIDI 音高 | OSC1 | OSC2 | 说明 |
| --- | --- | --- | --- |
| 60 | 13029 | 13029 | 此上下文中心附近一致 |
| 84 | 11180 | 13126 | 高音跟踪分歧已影响实际控制结果 |
| 108 | 10874 | 12071 | 差异继续存在 |

因此未来两个 OSC 的幅度分布需分别计算；直接把同一采样复制两次并等增益相加不能恢复这些行为。

## 时间、起音与尚未确认的部分

Concert 的 Start 和 Attack 基础电平同为 99。Amp EG 从高电平开始，力度的 Attack 电平调制 -13 又使有效目标发生变化。因此它并非“从零做一个固定 1.5 ms 淡入”；播放器现已移除这段旧淡入。

本轮已继续验证启动构造、分批调度、内核下一 tick 超时、Timer0 设置及 TG 音量命令。名义链路为每批 2 ms、8 批一轮，即单语音每 16 ms 更新；EG 每次减 24 单位，得到 1500 单位/秒。TG 倒数表对应 24 单位 × 32 原生音频帧 = 768 帧，名义 48 kHz 下同为 16 ms。绝对晶振和 TG 内部逐帧行为尚未实测，详见 [VOICE_TIMING.md](VOICE_TIMING.md)。

`src/instrument/NativeVoice.cpp` 已将上述力度、双 OSC 跟踪、AMS 与多段 EG 接入播放器，移除原固定起音/指数释音。C++ 对照 32512 个原 ARM 上下文、243 个轨迹状态和 28 个 TG 命令全部通过；新试听在 `output/Concert_SE_Grand_Control/`。TG 音频增益映射及双 OSC 混合仍包含明确的电脑端近似。

接下来优先解决：

1. 用真琴验证 TG 逐帧平滑和全局语音相位；当前调度和命令生成已验证并接入。
2. Filter A/B 控制与 Filter EG 已验证并接入；Mixer2 实际调制 B 输出，早期标签已修正，详见 [FILTER_CONTROL.md](FILTER_CONTROL.md)。接下来需校准 TG 控制字到真实 Hz/Q 的音频映射。
3. 半踏板与释放时长动态缩放；本轮默认踏板关闭，单步移植未覆盖动态缩放。
4. 真琴同 MIDI 录音 A/B，校准最终响度、击键、长音与松键听感。

## 文件与复现

```text
tools/voice_math.py                       独立整数实现
tools/voice_firmware.py                   原函数合成上下文
tools/probe_voice_math.py                 单函数和逐步对照
tools/probe_concert_voice.py              全音高/力度扫描
research/derived/firmware/KROSS2_V124/
  voice/concert-controls.json             上下文、示例、轨迹与限制
  voice/concert-control-map.bin           32512 条控制记录，格式在 JSON
  catalog/                               LUT 原始切片与地址索引
research/derived/verification/
  voice-math-arm-comparison.json
  concert-voice-arm-comparison.json
```

```sh
python3 tools/analyze_concert_program.py
python3 tools/test_program_firmware.py
python3 tools/probe_voice_math.py
python3 tools/probe_concert_voice.py
python3 tools/verify_firmware_research.py
```

独立数学移植读取本地固件表；对照/扫描脚本另外需要 Unicorn。所有输出均在项目目录内，不触碰系统插件目录。
