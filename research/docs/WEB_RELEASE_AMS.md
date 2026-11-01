# 网页释音时间 AMS

网页按原厂 Program / 当前所选波形，取第一个匹配活跃 OSC 的三路 Amp EG Release Time AMS。保留原始 source、intensity、基础时间、曲线及键盘跟踪参数；不改动原件、PCM、冻结的原生插件资源。

- 进入释放阶段时读取当前 AMS 值，计算 `12 * sum(sat16((intensity * source * 331) >> 15))`，再用原 Q16 指数表换算基础时间。释放中的连续控制器变化不重新启动尾音。
- 音高、力度、Exp. Velocity、Filter/Amp/Common Keyboard Tracking、AMS Mixer 0/1/2 使用原整数计算和查表。
- MIDI 控制器以输入端口和通道隔离，支持原始来源对应的 CC、弯音、通道触后、多音触后。双极旋钮以 64 为中心；未收到控制器时其贡献为零。切换音色清空控制器状态。
- E043 的两路释音使用 Common LFO：按原参数实现未变形的三角波，32 个四分音符为一周期。网页默认 120 BPM，接收到 MIDI Clock 后更新速度；相位以选择音色为起点。这不是原琴全局时钟相位同步。
- 录音捕获初始控制器状态和后续 CC/弯音/触后，MIDI 导入、回放、下载保留通道和这些事件。回放不依赖上一段遗留的控制器值。
- 重算调制后的曲线系数，而非只伸缩原基础尾音。最长 8192 个控制步（约 131 s）使用整数递推；极端更长尾音使用相同系数的闭式近似并限制采样点数量，避免松键时阻塞主线程。曲线缓存最多 128 项。

## 原函数依据与验证

`0x1f8608` 为语音 AMS 分派，`0x273ee0` 为公共/控制器分派，`0x273e30` / `0x273e7c` 为单极/双极 CC，`0x1fa4b4` / `0x1faabc` 为释放阶段的三路时间调制，`0x1fb02c` 为时间指数换算；Common LFO 波形使用 `0x200a3c`，节奏单位表来自 `0x2c4de0`。

`tools/probe_web_release_ams.py` 仅在本机模拟内存中执行原 ARM。共 1200 个原厂 OSC、3600 组音高/力度/控制器案例，来源值和最终释音内部时长与浏览器独立实现逐项一致；另外核对 143 个曲线系数边界。Common LFO 原波形在显式输入相位下核对；Tone Adjust 为零，MIDI 使能边界由探针提供。

`tools/test_web_release_ams.cjs` 另外检查 157 种基础曲线、实时 CC 对尾音的影响、通道隔离、MIDI 控制器往返与覆盖录音的踏板闭合。此次未试弹、未做硬件或浏览器音频验收。

数据与实现：

- `tools/prepare_web_releases.py`：提取来源、参数、曲线表，拒绝实际依赖中未实现的来源。
- `research/derived/firmware/KROSS2_V124/rom/decoding/web-releases.json`：派生参数、映射、来源指纹。
- `research/derived/verification/web-release-ams-arm.json`：原 ARM 结果。
- `tools/templates/krose-web/release-ams.js`：无固件运行依赖的网页实现。

范围是**释音时间 AMS**。完整 Attack/Decay/Slope、电平 AMS、滤波调制和原机效果链仍未移植到网页。一个波形只用其匹配 OSC 的参数，不叠加整个 Program；Web Audio 增益插值仍是电脑端近似。
