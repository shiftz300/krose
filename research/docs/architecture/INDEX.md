# 研究文档索引

本轮研究已结束。章节保留原路径；先读[交接说明](../REVERSE_HANDOFF.md)或[统一报告](PLUGIN_REPORT.md)。历史章节中的后续计划仅作为记录。

## 报告与归档

- [KROSS 2 音源逆向报告](PLUGIN_REPORT.md)
- [KROSS 2 音源与系统研究](README.md)
- [KROSS 2 固件逆向报告](REPORT.md)
- [插件逆向归档状态](REVERSE_STATUS.md)

## 采样和资源

- [扩展采样、银行寻址与鼓组依赖](EXPANSION_PCM.md)
- [扩展音色的声部启动](EXPANSION_VOICES.md)
- [GM 音色映射与真实采样](GM_PROGRAMS.md)
- [压缩采样循环：已知算术与未定状态](PCM_LOOP_BOUNDARY.md)
- [导入音色的引用重编号](PROGRAM_RELOCATION.md)
- [扩展资源的实际放置与导入边界](RESOURCE_IMPORT.md)

## MIDI 与声部

- [鼓组逐键控制与参数生效时机](DRUM_CONTROLS.md)
- [MIDI NRPN 到鼓组控制与包络](DRUM_NRPN_LIVE.md)
- [鼓组的选样、增益与截音](DRUM_VOICE_CHAIN.md)
- [鼓轨到真实声部](DRUM_VOICE_PLAYBACK.md)
- [原厂素材如何组成左右声道与键区](FACTORY_REGIONS.md)
- [原厂音色从选样到声部启动](FACTORY_VOICE_CHAIN.md)
- [CC120 / CC123：关音、回收与复用缺口](MIDI_ALL_OFF.md)
- [MIDI 银行编码与音色转换](MIDI_BANKS.md)
- [MIDI 调音、弯音与 RPN/NRPN](MIDI_PARAMETERS.md)
- [MIDI 换音与 OSC 装载](MIDI_PROGRAM_LOAD.md)
- [CC121：控制器重置与发声延续](MIDI_RESET.md)
- [停止后的成对声部复用与主机适配](MIDI_STOP_REUSE.md)
- [关音后继续演奏：主机适配的连续验证](MIDI_STOP_REUSE_LIVE.md)
- [MIDI 传输命令与定位请求](MIDI_TRANSPORT.md)
- [换音前后的连续声部](MIDI_VOICE_HANDOFF.md)
- [换音后的持续控制与 TG 提交](MIDI_VOICE_REFRESH.md)
- [单音优先级与松键回退](MONO_KEYS.md)
- [单音、连奏、Unison 与滑音选样](MONO_LIVE.md)
- [从 MIDI 音符到 PCM 声部](RUNTIME_FLOW.md)
- [Unison 叠加与音高分散](UNISON.md)
- [正常刷新中可省略的两段附加计算](VOICE_AUXILIARY.md)
- [声部构造失败后如何收尾](VOICE_FAILURES.md)
- [PCM 声部参数如何建立](VOICE_PARAMETERS.md)
- [密集起音、声部耗尽与立体声抢占](VOICE_PRESSURE.md)
- [正常演奏中的声部刷新](VOICE_REFRESH.md)
- [音符释放、踏板保持与声部回收](VOICE_RELEASE.md)
- [声部复用、立体声抢占与滑音](VOICE_REUSE.md)
- [从声部控制到 TG 启动与回收](VOICE_TG.md)

## 调制和控制

- [AMS Mixer：七种调制运算与状态更新](AMS_MIXERS.md)
- [鼓组包络：演奏中编辑与自然阶段切换](DRUM_ENVELOPE_LIVE.md)
- [鼓组逐键 Attack / Decay 的时间修正](DRUM_ENVELOPE_TIMES.md)
- [三类 EG：阶段、时间调制与重触发](ENVELOPES.md)
- [LFO 怎样改变音高、滤波与音量](LFO_TARGETS.md)
- [踏板对释放时间与辅助包络的影响](PEDAL_ENVELOPES.md)
- [松踏板如何进入释音](PEDAL_RELEASE_FLOW.md)
- [音源 LFO：波形、时间推进与调制输出](VOICE_LFO.md)
- [LFO 频率调制与声部调用](VOICE_LFO_INPUTS.md)

## 音乐时钟与发生器

- [琶音 Pattern、触键与播放时序](ARPEGGIATOR.md)
- [鼓轨 Pattern 库的存储与整理](DRUM_PATTERNS.md)
- [外部 MIDI 时钟与来源切换](EXTERNAL_CLOCK.md)
- [外部时钟的周期估算与速度读回](EXTERNAL_TEMPO.md)
- [音乐时钟与节拍同步延迟](MUSIC_CLOCK.md)
- [序列器录制：事件入口与歌曲音符](RECORDING.md)
- [序列器控制事件与通道状态](SEQUENCE_CONTROLS.md)
- [轨道循环、前奏与跨圈关音](SEQUENCE_LOOPS.md)
- [序列器音符、时长与 MIDI 输出](SEQUENCE_NOTES.md)
- [序列器 SysEx 记录与参数消息](SEQUENCE_SYSEX.md)
- [歌曲位置、拍号与速度轨](SEQUENCE_TIME.md)
- [步进序列器的数据与播放逻辑](STEP_SEQUENCER.md)

## 滤波和效果

- [合唱局部程序：控制引用与 MFX 修正](CHORUS_PROGRAM.md)
- [立体声合唱：延迟、LFO、混合与前置 EQ](EFFECT_CHORUS.md)
- [四段参数均衡器：系数、缩放与调制](EFFECT_EQ.md)
- [四段 EQ 的整链音频参考与试听](EFFECT_EQ_AUDIO.md)
- [Hall 混响：延迟区间、衰减与阻尼](EFFECT_HALL.md)
- [限制器：压缩比、时间、电平与侧链 EQ](EFFECT_LIMITERS.md)
- [效果加载：常数清零与初始上传](EFFECT_LOAD_STATE.md)
- [效果路由：串接、发送、返回与电平](EFFECT_ROUTING.md)
- [四段 EQ：B2 双端点引用与动态算法缺口](EQ_B2_PROGRAM.md)
- [Hall 局部字段与地址引用](HALL_LOCAL_OPERANDS.md)
- [母带限制器：25 项窗与地址区间](MASTER_LIMITER_KERNEL.md)

## 参数与界面逻辑

- [参数消息交接与同步回复](MESSAGE_REPLIES.md)
- [MMI 参数更新与延后处理](MMI_PARAMETERS.md)
- [歌曲参数缓存与应用队列](PARAMETER_CACHE.md)
- [参数出队、内存写入与变更通知](PARAMETER_DISPATCH.md)
- [参数变更通知与歌曲缓冲同步](PARAMETER_NOTIFICATIONS.md)
- [从矩形刷新到显示缓冲](UI_BITMAP.md)
- [窗口遮挡与可绘制区域](UI_OCCLUSION.md)
- [界面裁剪与刷新分派](UI_REFRESH.md)
- [参数怎样找到界面控件](UI_TREE.md)

## 较早研究与资源资料

- [Concert SE Grand：效果通路和实现位置](../EFFECTS.md)
- [原机出厂预置：银行数据恢复与选择](../FACTORY_SOUNDS.md)
- [Filter A/B：控制字、调制与播放器接入](../FILTER_CONTROL.md)
- [官方固件证据与重建算法](../FIRMWARE.md)
- [KROSS 2 v1.2.4：第一阶段身份探针注入与回退](../FIRMWARE_INJECTION_STAGE_A.md)
- [第一阶段身份探针 v2：修正真实 MIDI 事件边界](../FIRMWARE_INJECTION_STAGE_A_V2.md)
- [可复用固件索引与完整效果目录](../FIRMWARE_MAP.md)
- [KROSS 2 芯片与 DSP 传输证据](../HARDWARE.md)
- [PCG 的用途与当前刷写边界](../PCG_BACKUP_SCOPE.md)
- [Concert SE Grand：播放速率与 Program 参数](../PROGRAM.md)
- [逆向研究阶段记录](../PROGRESS.md)
- [重建目标、当前实现与验收](../RECONSTRUCTION.md)
- [研究状态与实验记录](../RESEARCH.md)
- [Krose：紧凑音色库的组织建议](../RESOURCE_DESIGN.md)
- [原机64MiB TG ROM：实机采集完成](../ROM_ACQUISITION.md)
- [原机 ROM 波形解码与网页试听](../ROM_DECODING.md)
- [原机整库恢复：目录、存储范围与读出入口](../ROM_LIBRARY_LAYOUT.md)
- [TG 采样读取：诊断与 MIDI 分发的离线追踪](../ROM_MIDI_DISPATCH.md)
- [原机 ROM 恢复：公开资料、导出原型与实机边界](../ROM_RECOVERY_PROGRESS.md)
- [原机 ROM 采样：取得路径研究](../ROM_SAMPLES.md)
- [第二阶段：ROM 小窗口、RAM 检查和单块传输](../ROM_SINGLE_BLOCK.md)
- [外部资料与适用范围](../SOURCES.md)
- [完整 USB 备份：隐藏区域、Pad 音频与启动 Flash](../USB_BACKUP_ANALYSIS.md)
- [音量、AMS 与包络控制逆向](../VOICE_CONTROL.md)
- [控制调度与 TG 音量平滑](../VOICE_TIMING.md)
- [网页释音时间 AMS](../WEB_RELEASE_AMS.md)
