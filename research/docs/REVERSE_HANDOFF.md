# KROSS 2 逆向研究交接

2026-11-02，按用户要求结束本轮逆向，整理成果供插件开发使用。自动研究停止；以下未解项留档。本次交付包含已验证的控制逻辑与阶段报告，完整原机音频仍未还原。

## 交付入口

| 内容 | 位置 |
| --- | --- |
| 论文式图文报告，10 页、7 幅图 | [报告 PDF](../output/pdf/KROSS2-v1.2.4-plugin-report.pdf) |
| 可编辑正文与证据引用 | [报告正文](architecture/PLUGIN_REPORT.md) |
| 按主题排列的全部章节 | [文档索引](architecture/INDEX.md) |
| 研究脚本与底层模型 | [工具索引](../tools/README.md) |
| 原始输入、采样与音色资源 | [资源总索引](../RESOURCES.md) |
| 逐项核验与文件指纹 | [核验结果](../derived/firmware/KROSS2_V124/architecture/stage02/verification.json) · [证据清单](../derived/firmware/KROSS2_V124/architecture/stage02/manifest.json) |
| 剩余音频问题的核查 | [阻塞记录](../derived/firmware/KROSS2_V124/architecture/stage05/audio-evidence-blocker-audit.json) |
| 整理前的入口、报告与状态 | [快照清单](../archive/reverse-closeout-2026-11-02/snapshot-manifest.json) |

## 可供插件使用的成果

采样解码、Program/Drum Kit 数据、键区与力度选层、音高与电平、立体声配对、声部分配及释放、主要 EG/LFO/AMS、MIDI 控制和必要的音乐发生器已有可追溯结果。效果参数、路由、部分系数与初始化也有原 ARM 检查。

当前统一核验包含 86 份原 ARM 模块结果；54 份产品源码、资源和验证基线保持原哈希。各模块的受控输入与截获边界仍适用，检查数量不表示完整 TG 音频覆盖。

现有原生产品仍保持原接入范围，见[原生结构](../../docs/NATIVE_ARCHITECTURE.md)。研究目录里的新模型、更多音色和验证结果尚未自动接入产品。

## 保留的缺口

| 内容 | 尚未确定 |
| --- | --- |
| 采样播放 | TG 插值、循环末端和预测历史策略 |
| Filter A/B | 控制字到真实滤波传递函数、共振及非线性的映射 |
| 常用效果 | EQ B2 动态混合、限制器检测与增益递推、合唱插值、Hall 耦合与阻尼 |
| 资源 | 部分扩展上下文依赖的银行 6 |
| 产品验收 | 新研究成果的插件接入、宿主项目与原机声音对照 |

需要新的数值语义依据或匹配输入、参数、时序的原机对照数据，才能进一步验证核心音频。已有 16 组 Pad 音频缺少这样的配套信息。后续是否继续，由新的任务决定。

## 文件布局与维护

- `research/docs/architecture/`：报告正文、分模块章节和图。
- `research/tools/`：复现脚本、整数模型和绘图工具；路径保持原值。
- `research/derived/firmware/KROSS2_V124/architecture/`：阶段证据、CSV、指令片段与核验；保留历史失败和候选结果。
- `research/output/`：当前 PDF、WAV 与研究试听。
- `research/firmware/`、`libraries/`、`downloads/`：原始输入，沿用原校验值。
- `research/archive/`：历史快照与迁移记录；本次整理前的文件也保存在这里。
- `research/build/`、`research/tmp/`：工作目录；证据引用的渲染结果继续保留。

仓库发布文档、脚本、图表和最终 PDF。原始资料、派生证据和归档目录沿用 Git 忽略规则，相关链接供完整本地工作区使用。复现脚本、证据和原文之间存在路径与指纹依赖，因此本轮使用分组索引整理，保留文件位置。

## 复核命令

在仓库根目录运行：

```sh
python3 research/tools/firmware_runtime_verify.py
```

该命令检查现有结果、指纹、文档和当前 PDF，不会重跑全部 ARM 矩阵。单项重跑入口在对应章节中，Unicorn 执行需要宿主允许 JIT。
