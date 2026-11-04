# 产品运行资源

本目录中的原厂采样、Program 参数、固件派生表及其生成表示不属于项目的 Apache-2.0 授权。来源清单用于追溯，不构成原权利人的再分发许可；具体路径及第三方边界见[授权范围说明](../docs/LICENSING.md)。

`concert-se-grand/` 保留独立 Concert 路径的采样包、控制表、EQ 系数与来源清单。显式更新命令为 `python3 research/tools/export_runtime_assets.py`。

`program-library/` 现为完整共享库：768 个出厂、265 个 GM、128 个扩展 Program；4,920 段采样和 42,980 个区域。`FactoryPrograms.json` 与 `FactoryPrograms.h` 统一提供音色数据和宿主目录；`FactoryBrowser.json` 记录原厂分类及显示顺序；manifest 记录来源、校验和及缺失层。更新命令为 `python3 research/tools/export_full_bank.py`。`legacy-program-order.json` 仅固定最早六个音色的兼容顺序。

CMake 校验冻结包后直接复制，不执行研究脚本。两个大型 `.samples` 文件只保留本地；纯源码副本需要另备资源包。导出数据不要手工编辑。范围与已知限制见 [原生引擎结构](../docs/ARCHITECTURE.md)。
