# 研究状态与实验记录

更新：2026-10-31。入口：[项目说明](../README.md)。本记录区分可复现验证、结构推断和未完成事项。

当前边界：继续逆向和项目内验证，暂不复制、安装 VST3；此前的安装副本已撤回 `build/withdrawn-install/`。新控制模型已接入源码和项目内构建；旧 `output/SEGrand/` bundle 保留原样，最新滤波试听与清单在 `output/Concert_SE_Grand_Filter/`，前轮控制模型试听仍保留。

新增原机预置恢复：从官方编辑器随附 `PRELOAD.KRS2all` 拆出 A–F 共 768 条 2140 字节 Program；800256 个字段与 55695 个效果参数对照原 ARM 一致。官方名称与 OSC 模式逐项核对，原机 ROM PCM 尚未取得，新预置未接入播放器。用户已认可当前 Concert 听感并取消真琴 A/B 条件；当前重点是原机预置，详见 [FACTORY_SOUNDS.md](FACTORY_SOUNDS.md)。

## 已验证

| 事项 | 证据 | 验证边界 |
| --- | --- | --- |
| 官方 v1.2.4 CMP 解压 | LZSS 消耗完整输入，输出 6,291,456 字节，字节和 `32d233df` | 仅本版本镜像 |
| KEP 外层加密 | 原固件 ARM 隔离模拟、Python/C 两份实现 | 小端 Blowfish 变体，不等同标准库 Blowfish |
| KEP 数据区与提取 | 文件头和四个区块校验通过；272 条原生采样重新拼接后与 PCM1 相同 | 不代表所有参数含义已知 |
| 原厂 Program 块与字段 | Concert SE Grand，第 002 项，2144 字节；1042 个 Program 字段、95 个效果字段与原 ARM getter 一致 | 已解释关键参数；未解语义保留原值 |
| 残差重建运算 | 官方编码器中的逆量化表、两阶预测和反馈路径；C/Python/原 ARM 逐点比较 | 是编码器反馈重建路径，尚未直接验证 TG01 芯片运算 |
| WAV 导出 | 168 条候选单声道来源配成 84 个立体声 PCM24 WAV | 是干采样，不含 Program 音量、滤波、包络、叠层与 FX |
| 根音播放步进 | 原 ARM pitch 初始化、更新和指数函数得到 7171/8192 | 零额外调制、48 kHz 时钟基准；未测物理时钟或 TG 插值 |
| 效果实现资源 | EQ、Limiter、Chorus、Hall 的程序和常数经原加载器验证；进一步确认 8 字节项只上传 48 位 | 尚未执行专用 DSP 指令 |
| EQ 系数与电脑效果核心 | 原 ARM 生成八段系数、36 组中等增益用例；C99 浮点 EQ 和近似 Chorus/Hall 已运行 | 以相近听感验收，专用 DSP 音频运算仍未模拟 |
| iPlug2 VST3 与音符引擎 | 官方 validator 47 项通过，编译后插件三种采样率/音色发声与参数恢复通过；引擎 ASan/UBSan 通过 | 原包络/双 OSC/滤波仍有近似，Ableton 手工验收待完成 |
| 全效果资源目录 | 135 项定义、13 个启动构造函数、全部原缓冲加载器输出一致；2269 参数共 9076 次 getter 对照 | 未执行专用 DSP 音频程序，详见 FIRMWARE_MAP.md |
| 音量/包络数学移植 | 11 类曲线、6491 步 EG 状态、槽增益、键盘跟踪及 Mixer 类型 0/1/2 对照原 ARM | 原函数控制域；动态踏板、TG 内部音频和硬件时钟仍待验证 |
| Concert 控制扫描 | 两 OSC × 128 音高 × 127 力度，32512 个合成上下文；力度/槽缩放及两个 Mixer 与独立公式一致 | 外部 Tone Adjust/MIDI 覆盖关闭、静音门打开；不是全系统或真琴回放 |

新增：控制调度的名义周期 16 ms 与 TG 的 768 帧平滑窗口吻合；内核下一 tick 超时、25 项倒数表及 28 个 TG 命令已执行原 ARM 核对。播放器接入与验证见 [VOICE_TIMING.md](VOICE_TIMING.md)，包含 32512 个 C++ 上下文、243 个轨迹状态及四种采样率释放时长检查。机器报告另有 `voice-timing-arm-comparison.json` 和 `native-player-check.json`。

具体固件地址见 [FIRMWARE.md](FIRMWARE.md)。机器报告：

- `output/kep-analysis/extraction_report.json`：原件指纹、区块校验、提取结果。
- `research/derived/verification/pcm-arm-comparison.json`：15 组用例，共 28,928 个采样点，C = Python = 原 ARM 反馈重建代码。包括全部 256 个码值、静音、正负溢出、11 个低中高音与不同力度层的实际片段。
- `output/Concert_SE_Grand_WAV/decode_report.json`：逐文件输入编号、系数、峰值、饱和次数、循环点、采样率候选与输出 SHA-256。
- `research/derived/verification/wav-export-check.json`：84 个完整 WAV 的哈希、RIFF、PCM24、帧数、根音、循环元数据验证；重建预测与输出饱和次数均为 0。复现：`python3 tools/verify_wav_exports.py`。
- `research/derived/verification/program-arm-comparison.json`：字段、步进与四种效果加载的原 ARM 对照。
- `output/kep-analysis/Concert_SE_Grand/program-analysis.json`、`sample-rate-analysis.json`：本轮参数与速率结果；人可读解释见 [PROGRAM.md](PROGRAM.md) 和 [EFFECTS.md](EFFECTS.md)。
- `research/derived/verification/dsp-transport.json`：48 位程序载荷、忽略半字变异验证、32 位常数传输。
- `research/derived/firmware/KROSS2_V124/effects/007/concert-coefficients.json`：八段 EQ 的原始上传数值、工作系数、频响与稳定性检查。
- `research/derived/verification/effects-prototype-check.json`：电脑端频响、分块一致性、重置、尾音衰减、非法参数拒绝、内存检查及局部耗时。
- `output/Concert_SE_Grand_Effects/manifest.json`：同源 dry / Concert / Warm / Wide 试听、处理参数、指纹与共享增益。效果核心在 `src/dsp/`。

新增 Filter A/B 进展：32512 个原 ARM 上下文、4152 步连续状态、400 个参数变异、10 组 TG 命令通过，C++ 匹配 32512 个上下文和 552 个选取状态。已修正 Filter 字段标签并接入播放器；TG 内部 Hz/Q 仍未知，电脑端近似另列。详见 [FILTER_CONTROL.md](FILTER_CONTROL.md) 及 `concert-filter-arm-comparison.json / filter-player-check.json`。

## 结构推断，待验证

旧报告 OSC2 参数 namespace 步长错误（15→16）已修正并重生，原始字段值/字节不变。现在两个 OSC 的所有对应组均验证地址相差 380，公开分组另有 600 个字段回归；后续使用新的 `program-analysis.json`。

1. Program 的两个选择表位于块内 `0x564`、`0x6e0`，各四个槽。有效 bank/number 对应 ff、f、mf；并集是 sample 56..223。字段已对照固件 getter，层名称依据原生 bank 顺序与官方清单，尚未用真琴逐字段编辑验证。
2. 理想指数公式已由原 ARM 的整数查表步进细化：钢琴 -295 → 7171/8192 → 42017.578125 Hz。既有 42017 Hz WAV 和导出阶段报告不改写；新增精确速率证据单独保存，报告里的旧 candidate 公式是历史导出依据。
3. 根音、循环起点和结束点来自原生描述与键区结构。WAV `smpl` 已写入这些值，但尚未检验在 TG01 中循环边界、插值及反馈状态的所有细节。
4. Bottom Velocity 已确认为 `107 / 86 / 1`，三个 Xfade Width 均为 0；依手册语义得到 mf 1–85、f 86–106、ff 107–127。完整 note-on 边界、全局力度曲线和实时调制还需引擎/真琴验证。

## 研究过程与被排除的方案

### 外层提取

从官方更新包解出 ARM 镜像，定位 KEP 密钥选择、初始化、加解密与校验。先用隔离模拟确认，随后实现独立 Python/C 解密，最后解析 PRM1、PCM1、1KBP、1KBA。原 KEP 未更改。

### 采样编码

- 把原生负载直接当作线性 8 位 PCM：不成立，遗漏预测重建。
- 用两阶 Q14 预测器配线性或有符号平方残差：能出现钢琴谐波，但高音异常；只作为临时探针，没有作为完成结果导出。
- 在线检索 KEP、Krome 工具、KORG-Tools、Hacktribe、专利与 KORG Italy 论文。未找到可直接处理这份 KEP 的公开解码实现；相关资料的适用范围见 [SOURCES.md](SOURCES.md)。
- 扫描固件中的单调数表，在 `0x3fd180` 发现 256 项有符号 16 位表，追踪引用到 `0x1f55bc`，确认编码器用量化码查表并将重建值反馈到两阶预测状态。
- 按原指令的截断、饱和和索引方式实现解码，对原 ARM 计算逐点验证通过，然后导出 84 个候选立体声 WAV。试听副本只做固定 -3 dB、末端短淡出与采样率转换。

## 接下来的研究顺序

用户对已有干采样试听的反馈为“这个听起来完全没问题”；它是试听认可，尚未录制真琴 A/B。后续明确接受一个或多个类似音色，要求尽可能接近，完整芯片复刻和逐位一致不作为前提。验收规则以 [RECONSTRUCTION.md](RECONSTRUCTION.md) 为准。

1. 试听已完成的 EQ + Chorus/Hall 原型，选择喜欢的空间与亮度；需要时继续深入 DSP 指令以校正具体差异。
2. 用真琴校准 Filter A/B 的 Hz/Q、并联音量与系数过渡；继续研究外部 AMS、动态踏板及 TG 内部行为。已有力度/曲线/AMS/包络/滤波控制已接入。
3. 建立真琴干声/效果录音对照，确认插值、循环边界、力度切换和最终响应。
4. iPlug2 VST3 已实现，新控制模型的 64 复音引擎测量与构建指纹见 `output/Concert_SE_Grand_Filter/manifest.json`（前轮控制和旧原型清单仍保留）；继续 Ableton 演奏验收。引擎耗时不等于整个宿主性能。

## 文件管理规则

- 原件放 `EXPCM001/`、`research/downloads/`、`research/firmware/`，不写入派生内容。
- 逆向产物放 `research/derived/`，其他项目资料放 `research/external/`。
- 研究工具和测试放 `tools/`；可复用音频核心放 `src/dsp/`；编译和临时文件只放 `build/`。
- 可交付音频、参数和清单放 `output/`；当前状态以本文件和 WAV 报告为准，原始提取报告保留该阶段的未知字段。
- 新推断写明来源、固件版本、偏移坐标系、复现命令及验证状态。不得用另一个 Korg 型号的结果替代本机验证。
