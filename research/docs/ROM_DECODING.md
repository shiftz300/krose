> 目录迁移及后续进度：当前网页源文件位于相邻 `krose-website/public/`，旧 `tools/templates/krose-web/`、网页导出目录和 ZIP 已清理；文中旧命令为阶段记录。当前资源、OASYS 和网页能力见 [进度](PROGRESS.md) 与 [资源索引](../RESOURCES.md)。

# 原机 ROM 波形解码与网页试听

2026-11-01。本轮仅离线处理已取得的 TG 下 64 MiB 镜像，不再安装读取器或发送 MIDI。琴已恢复原厂应用，用户确认启动、发声正常。

## 输入与边界

- 镜像：`research/derived/acquisitions/KROSS2_ROM_stage_b_20261031T215150691039Z/complete/TG-ROM-candidate.img`。
- SHA-256：`c9d4c9b4dd0f915b45a553e6b66d2cab7e51b80f4b2189fb6db4d91b1ccc94a5`。保持只读。
- 固件：v1.2.4，SHA-256 `3005f0eca3f3772bcb810c526ceebb15562747d3cdcdf5d20faae4a539520c54`。
- 原始描述符仍位于 `research/derived/firmware/KROSS2_V124/rom/catalog/`，历史报告不覆盖；本轮报告放在同级 `decoding/`。
- 这份镜像覆盖全部已恢复的原机采样描述符，不代表整机启动 Flash、扩展区或所有存储的备份。

## 编码与速率

描述符 bit0=1 的 3,335 项采用已恢复的二阶预测/残差 LUT 解码；bit0=0 的 733 项原机采样为小端有符号 PCM16，另有 2 个诊断描述符。地址分别按 1 字节或 2 字节缩放。所有 4,068 项原机数据均已导出成未归一化 PCM24 WAV；PCM16 输入不会因此增加原始精度。

速率使用 `48000 * phase_increment(2 * descriptor_pitch) / 8192`，而不是理想指数函数。48 个不同的描述符 pitch 已逐一对照原 ARM；WAV 整数采样率仅在文件头四舍五入。分区根音及有符号 fine 字段也经过原 `0x1ff764` / `0x1ff38c` 核对，fine 修正为带符号截断的 `abs(fine)*1311 >> 10`，单位对应每半音 256 格。键盘跟踪禁用位和原相位增量上限均保留。

验证：4 类预测编码的 4,096 个真实 ROM 帧逐点与 C、Python 和原 ARM 编码器反馈一致；另核对了真实采样 855 和 980 的两处饱和边界。23 个分区音高上下文与原 ARM 一致。所有 WAV 导出均逐帧读回核对 PCM24 高位、声道、帧数及文件头。原始导出保留候选末端 guard，不把尚未完全解释的反向、重启历史字与循环模式当作已完整模拟的 TG 行为。

## 鼓组

官方编辑器 PRELOAD 的 Program 表之后，从 `0x48be20` 开始为 58 个 8,728 字节鼓组记录：24 字节名称加 128 个 68 字节键位。前 42 项为原厂鼓组，后 16 项为 InitDrumkit。固件参数 namespace `0x61` 的 67 个键位字段确定了 4 层采样选择、3 个力度阈值、调音、反向、声像、Assign 位及独占组等位置。

共恢复 3,594 个有效键位、5,239 个采样槽，497,408 次字段范围检查通过，36,582 次原 ARM getter 比较一致。Basic Kit 1 的底鼓、军鼓、闭镲和开镲引用也与官方 Voice Name List 第 21 页一致。42 个 Drum Program 分别关联其原始鼓组；不再把一个 Program 当作单个鼓采样。网页实现按键位/力度选样、左右声道、粗细调音、反向、声像和独占组止音；交叉淡化曲线、原机鼓包络/滤波/效果仍属于后续范围，试听响度采用近似换算。

## 输出和产品隔离

- `output/Factory_ROM_WAV/`：4,068 个完整原机 PCM24 WAV、2 个单列诊断 WAV、逐采样 CSV 和清单。
- `output/Factory_Sound_Selection/`：489 项旋律波形与 965 项单鼓试听、768 项 Program 来源关联表。旧 README/CSV 保留原历史版本；最新交互界面使用下面的网页包。
- `tools/templates/krose-web/`：独立静态网站的 HTML、CSS、JS 模板，不参与插件构建。
- `output/Krose_Web/`：部署目录；`output/Krose_Web_CF_Pages.zip`：根目录直接含 index.html 的部署压缩包。
- `build/web-opus/`：有损试听编码缓存；原始 PCM24 WAV 不变。此前 FLAC 比较缓存仅留在 build/，不放入部署包。

网页版采用 48 kHz、64 kbps VBR 单声道 Ogg Opus，立体声保持独立左右采样。原始音频约 195 MB，试听约 35.6 MB。极短循环先按原周期延展并移动到稳定循环段；极短单次声音只补静音到可编码长度。所有 Ogg granule 帧数及打包条目哈希逐项校验。有损试听不作逐位一致性声明。

每次选择波形或鼓组，先完整下载、解码其全部键位/力度资源并固定在当前内存集合，再开放试弹。下载与解码进度独立计入进度条；失败时保持阻塞并允许重试。琴键发声路径不再临时 fetch 或解码。网页仍使用通用门控和 CPU 音高模型，未接入完整 Program DSP。

试听曲目为 Debussy · Clair de lune、Chopin · Nocturne Op.9 No.2、Satie · Gymnopédie No.1，均使用 Mutopia 完整版本的全部 MIDI 音符；补充按和声/原谱伴奏组编配的自动踏板和不同释音时间，不声称为作曲家原始演奏。曲目来源、改编说明及 CC BY-SA 署名在部署包的 `music-credits.html`。

网页分为「试听」和「录音」两个工作区，共享键盘和音色。录音保留音符、力度及 CC64 踏板，支持浏览器本地保存、回放和 MIDI 下载，也可导入 SMF 0/1（含变速与 SMPTE 时基）。导入多轨文件按当前选中音色合并试听，不复原多音色编排。钢琴窗支持音符位置/音高拖动、右边缘时值编辑、撤销、空白平移和总览边界缩放。简单立体声卷积混响可调；这些网页效果不代表原机 DSP。编解码和原始 Mutopia 文件往返检查使用 `node tools/test_web_midi.cjs`。

## 复现

```sh
python3 tools/decode_factory_rom.py --verify-arm
python3 tools/build_factory_rom_selection.py
python3 tools/catalog_factory_drumkits.py --verify-arm
python3 tools/prepare_web_music.py
python3 tools/compress_web_samples.py --codec opus
python3 tools/build_krose_web.py
```

研究依赖见 `requirements-research.txt`、`requirements-rom-audio.txt`。网页音频编码使用本机 FFmpeg/libopus；浏览器运行不需要这些工具、后端或外部 CDN。Unicorn JIT 在 macOS 沙箱外仅用于离线模拟，不访问硬件。

公开资料复核：[KromeHeaven 的 META V2 研究](https://kromeheaven.com/home/blog/364-korg-kross-meta-v2-img-decoded)讨论了文件组织，但没有给出本库可直接复用的完整 PCM 解码器。本次以已取得的真实 ROM 和原固件算术验证为依据。网页格式依据 [MDN 音频编码说明](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Audio_codecs)；部署限制见 [Cloudflare Pages 限制](https://developers.cloudflare.com/pages/platform/limits/)及 [Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)。

本轮未改动 `src/`、冻结 `assets/`、已接受的 Concert WAV 或原机固件，也未复制、安装 VST3。


### 网页释音参数

`tools/prepare_web_releases.py` 从原厂 A–F Program 读取每个活跃 OSC 的 Amp EG Release Time 和 Release Curve，并核对原 Program 二进制及固件 SHA256。输出位于 `research/derived/firmware/KROSS2_V124/rom/decoding/web-releases.json`；网页打包仅携带时间、曲线和当前波形对应关系，不包含固件或 Program 原始二进制。

网页松键现按当前 Program / 波形应用对应释音，替代 Bell、Strings 分类的统一时长。曲线使用既有 `VoiceMath` / `EnvelopeSegment` 整数算法和原固件时间表，以 16 ms 控制周期生成，再由 Web Audio 平滑插值。768 个 Program 共使用 157 种基础释音配置。示例：DWGS Bells 1 的两路基础值为 1.776 / 1.440 s、曲线 9 / 8；Tubular Bells 为 4.448 s、曲线 7；Music Box 为 0.944 s、曲线 6。

边界：这是原参数驱动的基础释音，并非完整原机包络。释音时间 AMS 已按原参数接入，见 [WEB_RELEASE_AMS.md](WEB_RELEASE_AMS.md)；之前的 Attack/Decay/Slope、电平 AMS 和 TG 控制量到音频增益转换尚未接入网页；同一波形对应多个 OSC 时使用第一个活跃匹配项，不声称实现双 OSC 叠层。采样本身先结束时自然终止，不人为延长无循环采样。鼓组仍按 one-shot 播放；现有混响单独保留。
