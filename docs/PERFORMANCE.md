# 单音、连奏与滑音

2026-11-04。Concert 与完整 Program 引擎共用 `Performance.h` 的按键记录和滑音累加器；页面只发送参数及 MIDI，关掉编辑器后继续演奏。

## 操作

| 控件 | 行为 |
| --- | --- |
| POLY | 保留既有复音路径，Glide 不参与 |
| MONO | 每个 MIDI 通道只保留一个当前音符组，换音重建采样与包络，旧声部短淡出 |
| LEGATO | 重叠按键保留原采样、力度、播放位置、振幅／滤波包络，更新音高与键盘跟踪；全部松开后下一音重新起奏 |
| GLIDE | 0 关闭，1–127 逐渐变慢；在 Mono／Legato 的重叠按键和松键回退间滑音 |

Program 的多层和双 OSC 仍可占用多个采样声部。鼓组保持单次采样语义，Mono／Legato 选中新音时重新触发，Glide 不改变鼓采样音高。

Glide 数值在下一次换音时读取，当前滑音沿用启动时的速度。模式和 Glide 为保存于工程的全局覆盖，切换音色时保持。切换模式会清空按键记录并淡出旧声部；需要重新按键。单音模式切换 Program 同样清空旧按键，防止松键后重新触发旧音。

## 按键与连续演奏

每个 MIDI 通道有十条记录。同音高可重复占用记录，Note Off 删除当前排序中的第一条匹配项；满表后先淘汰尾项。Factory／GM／扩展 Program 使用原 `+509` 的优先级：Low、High、Last。保留的 Concert 入口使用 Last。未定义的编码 3 按 Last 处理。

松开当前音后回到等待音。回退使用最后一次成为当前音的力度缓存；Normal Legato 复用声部时继续保持其起始力度。延音踏板在最后松键后保持声音，新的非重叠按键重新起奏。CC120、CC123 清空该通道的按键表，CC121 释放踏板并保留仍按住的键。Panic 同时清理声部、事件队列、控制器和按键记录。

声部、尾音、按键与事件队列均为固定容量。音频处理不分配堆内存。

## 来源与实现边界

按键模型依据 [原按键链检查](https://github.com/shiftz300/krose-source/blob/main/research/docs/architecture/MONO_KEYS.md)，连奏依据 [原声部复用](https://github.com/shiftz300/krose-source/blob/main/research/docs/architecture/VOICE_REUSE.md) 和 [真实采样连续轨迹](https://github.com/shiftz300/krose-source/blob/main/research/docs/architecture/MONO_LIVE.md)。Normal Legato 保留原包络进度；重算键盘跟踪时只替换控制来源和基准增益，滤波器内部延迟状态继续使用。

Glide 系数来自 v1.2.4 的 `0x3FD380`，128 项全部进入 `PerformanceData.h`。整数累加器使用 Time 模式的音程缩放和终点夹紧。当前主机模型以 62.5 Hz 调度控制访问，在访问之间连续插值音高；这些秒数与音频插值尚无实机校准。Mono 重建时，在前音与目标音中取较高的查询键位；Normal Legato 继续使用原采样。

当前滑音统一作用于 MIDI 键位，并使用当前可听音高作为下一滑音起点。原 OSC 独立的移调／Slope 后选区、Rate／Time、Fingered、控制器覆盖，以及 Offset Legato、Unison 的完整装配仍待接入。由此产生的选样和时长差异继续作为实现限制记录。

原观察文件 SHA-256：

- `mono-keys-check.json`：见 `tests/fixtures/performance/manifest.json`。
- `voice-reuse-check.json`：`9968092e04c058e3da1a810f73ac11d0427bb6b2787bfc9c55d11a0d71319301`。

`python3 research/tools/export_performance_checks.py` 显式更新原表和测试夹具，普通构建不执行研究代码。

## 参数与验证

新增参数 `Voice Mode=17`、`Glide=18`，已有 ID 0–16 保持。支持旧 6 参数、17 参数工程以及新 19 参数状态，附带的 VST3 bypass 字段保持原位置语义。

测试对照冻结的 72 条按键记录（含场景复位）、66 条原滑音访问和全部 128 项系数。音频回归检查两套引擎的重复音、力度与包络保留、松键回退、分通道踏板、模式／音色切换、三种采样率、跨块一致和零实时分配。真实 WKWebView 测试验证按钮、旋钮、宿主回写与重开回读。实际 DAW 长时演奏仍待手工验收。

其后琶音增量追加参数至 29 项，旧 19 参数状态继续迁移；详见 [琶音器](ARPEGGIATOR.md)。
