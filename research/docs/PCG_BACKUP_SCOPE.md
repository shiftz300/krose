# PCG 的用途与当前刷写边界

2026-11-01。用户明确不拆机。此前仅在保证不伤琴时接受刷写，无法满足；**后续已明确接受实验风险，先要求具体注入步骤，再要求代为执行**。第一版正常启动、发声正常，但探针无回复；已离线复现队列边界缺陷并替换为v2，正常重启发声且实际收到版本02身份回复，见[v2注入说明](FIRMWARE_INJECTION_STAGE_A_V2.md)。执行入口验证通过不等于已经验证完整故障恢复路径。

## PCG 确实有用，但不含原机采样

已核对本地官方《KROSS2 Parameter Guide》印刷页184，及官方《Operation Guide》印刷页120–122、125。

| 文件／备份 | 内容与作用 | 不能代替的内容 |
| --- | --- | --- |
| `.PCG` | Program、Combination、Drum Kit、Arpeggio、Global等参数；用于保护用户编辑，并与已恢复的官方／内部银行比较 | 原机ROM的PCM波形、启动程序、整机固件恢复 |
| `.SNG` | Sequencer歌曲数据 | PCM及固件 |
| `.KSC`及其关联`.KMP/.KSF`文件，或`.WAV` | 通过Pad sampler导出自己录制的采样；关联目录应一起保留 | 整套出厂ROM |
| 已取得的125MiB USB系统镜像 | 已暴露系统卷的文件和文件系统原始内容 | 尚未取得的独立启动Flash及TG采样ROM |

官方 `Save All (PCG & SEQ)` 保存参数到PCG，并另外保存歌曲到SNG；名称中的“All”不表示整个机器的存储器或ROM全部镜像化。用户采样另走Pad导出功能。

PCG对本项目尤其有用：它可提供该机器当前的音色参数、组合和波形编号引用，核对用户修改与现有出厂银行的差异。读取PCG无需在琴上运行自制固件。文件里的波形编号是引用，不是对应采样字节。

## 正常导出步骤

1. 在琴的 `MEDIA > FILE` 选择SD卡上的保存目录。
2. 用FUNCTION菜单执行 `Save All (PCG & SEQ)`，取一个未使用的新文件名，例如 `KRBACK01`。
3. 保存结束后，在Mac上复制生成的 `.PCG` 和 `.SNG`。若只需要参数，也可使用 `Save PCG`。
4. 若要保留Pad录音，再在SAMPLER SETUP使用 `Export to KSC` 或 `Export to WAV`；KSC关联文件和目录一起复制。

这些是琴的正常保存功能，不是安装导出器。当前项目中尚未发现用户导出的`.PCG`文件，因此没有声称已经解析这台琴的PCG。收到后原件放在 `research/libraries/` 的独立采集目录，解析结果放 `research/derived/`；不回写琴或覆盖现有产品资源。

## 为什么目前不能承诺刷写无风险

现有导出器仅在电脑上，以合成TG数据验证了读块和输出。尚未验证琴上的启动加载、任务上下文、缓冲区所有权、真实传输及修改应用损坏时的完整恢复路径。

PCG只能帮助恢复对应的音乐数据。即使保存PCG并保留USB镜像，也不能推出自制程序刷入后一定可启动、启动维护模式一定仍可用，或所有损坏均能恢复。不会用“仅修改应用”“不改启动区”等设计意图替代这种证据。

当前状态：不拆机；第二阶段读取器已实机取得完整下64MiB TG ROM，校验通过，用户确认发声正常，见[完整采集记录](ROM_ACQUISITION.md)。这不改变PCG只保存参数/引用、不含ROM波形的结论，也不代表已取得启动Flash整机恢复镜像。

## 来源

- [KORG Parameter Guide](https://cdn.korg.com/us/support/download/files/96dbde75752a88b2daf897262d199b80.pdf)，本地原件 `research/downloads/KROSS2_Parameter_Guide.pdf`，SHA-256 `da60cf9461c5721e7c0c89373a5c005f83207d563f161a82e5642347edc85c5a`；`Save All (PCG & SEQ)`／`Save PCG`：印刷页184。
- [KORG KROSS2 Operation Guide E3](https://cdn.korg.com/us/support/download/files/74d78cf41317a372895b4a76af10548e.pdf)，文件结构及Pad导出范围：印刷页120–122；SD保存：印刷页125。
- [当前导出原型与缺失环节](ROM_RECOVERY_PROGRESS.md)。原型结果和原件指纹保持原样。
