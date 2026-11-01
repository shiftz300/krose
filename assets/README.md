# 产品运行资源

`concert-se-grand/` 是已验证数据的冻结导出，供普通 CMake 构建使用。包含采样包、控制表、EQ 系数及来源清单；不含完整固件或研究执行环境。

修改研究结果后，显式运行 `python3 tools/export_runtime_assets.py` 更新。不要手工修改导出文件。大型 `SEGrand.samples` 仅保留本地，取得源码后需另备完整资源包。详见 [目录与导出流程](../docs/PROJECT_LAYOUT.md)。

`factory-starter/`：独立冻结的首批板载共享库（357 份单声道采样、6 个 Program、418 个区域），包含带版本的 PCM24/参数包与 manifest。显式导出：`python3 research/tools/export_factory_bank.py`，选择来源为 `research/config/native-starter.json`。产品构建只检查并复制已有资源，不执行导出器。
