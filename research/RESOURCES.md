# 资源总索引

2026-11-01。本表由 `python3 research/tools/index_resources.py` 生成。旧报告不覆盖，当前状态以本索引和 [逆向进度](docs/PROGRESS.md) 为入口。

2026-11-02 GM 后续：[265 条完整参数、银行映射及真实采样](docs/architecture/GM_PROGRAMS.md)已核实。当前 GM 条目见[新参数索引 CSV](derived/firmware/KROSS2_V124/architecture/stage04/gm-programs.csv)；下方清单与旧 CSV 保留 2026-11-01 快照的统计口径。

2026-11-02 扩展后续：[E.P./Future Synth 完整源采样与原区域寻址](docs/architecture/EXPANSION_PCM.md)已核实。新增 797 个 WAV 及[采样清单](derived/firmware/KROSS2_V124/architecture/stage04/expansion-samples.csv)，位于 `research/output/Expansion_PCM_WAV/`；原网页代表试听和旧统计继续保留。

| 层级 | 资源 | 目录 | 文件数 | 大小 MiB | 用途 |
| --- | --- | --- | ---: | ---: | --- |
| 原始资料 | [EXPCM001 原件](EXPCM001) | `research/EXPCM001` | 2 | 45.30 | 未修改 KEP 与原始附带资料 |
| 原始资料 | [设备备份与原始采集消息](libraries) | `research/libraries` | 282 | 260.85 | USB 存储备份、TG 采集消息、官方扩展包原件 |
| 原始资料 | [官方固件与手册下载](downloads) | `research/downloads` | 22 | 46.42 | 来源存档；不作为产品运行依赖 |
| 原始资料 | [固件解包原件](firmware) | `research/firmware` | 8 | 9.50 | 与分析后的 ARM 镜像分开保存 |
| 已解码采样 | [板载完整 WAV](output/Factory_ROM_WAV) | `research/output/Factory_ROM_WAV` | 4072 | 191.00 | 4068 个音乐采样 + 2 个诊断样本；PCM24 容器 |
| 已解码采样 | [Concert SE Grand WAV](output/Concert_SE_Grand_WAV) | `research/output/Concert_SE_Grand_WAV` | 91 | 101.88 | 84 个立体声分区、3 个力度层；插件来源 |
| 已解码采样 | [OASYS Piano 全部 WAV](output/OASYS_Piano_WAV) | `research/output/OASYS_Piano_WAV` | 275 | 135.78 | 272 个单声道采样，10 个 multisample 条目；含导出/Opus清单 |
| 研究试听 | [原机分类波形试听](output/Factory_Sound_Selection) | `research/output/Factory_Sound_Selection` | 1463 | 245.79 | 489 个旋律波形试听、965 个单鼓试听；不是 1454 个完整预置 |
| 研究试听 | [扩展包代表波形试听](output/Sound_Selection) | `research/output/Sound_Selection` | 10 | 8.81 | E.P./Future Synth 的 8 个代表波形；不是整库导出 |
| 产品输入 | [板载共享库](../assets/factory-starter) | `assets/factory-starter` | 3 | 54.55 | 357 个共享单声道采样、418 个区域、6 个 Program；首批数据驱动播放器 |
| 产品输入 | [冻结插件资源](../assets/concert-se-grand) | `assets/concert-se-grand` | 6 | 98.02 | 5 个运行输入，当前仍为 Concert 专用采样/控制表 |
| 测试输入 | [原 ARM 期望数据](../tests/fixtures/concert-se-grand) | `tests/fixtures/concert-se-grand` | 6 | 1.53 | 5 个独立二进制回归输入，不链接到插件 |
| 研究缓存 | [Opus 编码缓存](build/web-opus) | `research/build/web-opus` | 8680 | 45.18 | 原始 WAV 的有损派生物，供网页重新导出 |
| 历史证据 | [迁移前源码与构建凭据](archive) | `research/archive` | 115 | 5.23 | 旧记录保留；不代表本轮重建或新 ARM 验证 |

[完整机器清单](derived/catalog/resources.json) · [音色状态表 CSV](derived/catalog/programs.csv) · [本轮完整性检查](derived/catalog/integrity.json)

旧音色状态表含 768 条板载 A–F、265 条 GM 名称目录、128 条扩展包预置，共 1161 行。其中 GM 行保留当时状态；现已补齐完整记录和受控采样映射，完整复刻与插件接入仍未完成。

原始 `programs.json` 仍保留当时的 `ROM_PCM_available=false` 或扩展依赖不全标记；现已取得 ROM。本索引提供当前状态覆盖，不改写旧证据的字节。

原生播放器现有 Concert 兼容路径及 6 个板载首批 Program，见 [原生结构](../docs/NATIVE_ARCHITECTURE.md)。这些首批音色采用原参数驱动，但完整 FX/调制仍未重建。

32 个 OASYS 预置是不同的参数和波形引用，不是 32 套互不重复的录音。网页单波形试听、完整 Program 复刻和桌面插件预置接入是不同阶段。

只读 ROM SHA-256：`c9d4c9b4dd0f915b45a553e6b66d2cab7e51b80f4b2189fb6db4d91b1ccc94a5`。镜像覆盖已恢复的音乐采样目录，不是整机所有 Flash/扩展存储的备份。
