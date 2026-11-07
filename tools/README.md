# 开发工具

现有构建、CI 和打包保留 Python 实现，不需要安装 Node.js。依赖准备、校验与打包使用 Python 标准库；原生界面图片处理只额外需要 Pillow：

```sh
python3 -m pip install -r tools/native-ui/requirements.txt
```

- `bootstrap_plugin.py`：准备并核验固定版本 SDK。
- `check_project_boundary.py`：在独立临时目录构建引擎并运行全部已注册测试。
- `package_plugin.py`：验证测试记录、签名与 VST3 后打包本地交付物。
- `release/runtime_assets.py`、`release/package_macos.sh`：运行采样归档与安装包。
- `release/merge_macos.py`：校验原生 bundle 的资源、版本与架构后合成 Universal。
- `audio/train_pgo.cpp`：Release 构建自动执行的代表性训练负载，生成数据仅在构建目录保存。
- `../tests/tools/test_runtime_assets.py`：新旧归档往返、校验失败及路径拒绝测试。
- `resources/native_bank.py`：维护阶段从原厂波形重建紧凑资源，使用 C++ 校验器逐采样核对；不参与普通构建。
- `native-ui/ci_assets.py`：生成编译检查专用占位资源，不用于发行。
- `audio/`：离线音频渲染与性能基准；`benchmark-core` 同时记录回调耗时和确定性音频哈希。
- `audio/audit_program_audio.cpp`：全音色、全鼓键及密集和弦诊断，音频窗口与 TSV 写入指定位置。`audio/analyze_program_audio.py` 使用可选的 NumPy 做离线音高候选筛查，不参与插件运行。`audio/calibrate_program_levels.py` 结合原厂 FX 电平与压力峰值生成静态补偿。
- `resources/extract_effect_metadata.py`、`extract_drum_controls.py`：从锁定哈希的原件生成产品所需参数表，不参与普通构建。
- `native-ui/prepare.py`、`complete_assets.py`、`field_assets.py`、`publish_complete.py`：完整界面素材导出流程，见[原生界面移植](../docs/NATIVE_UI.md)。
- `native-ui/compact_fonts.py`、`compare.py`：字体图集与图片对比，仅使用 Pillow。

插件运行时不调用 Python，也不收集 PGO 计数。PGO 的开关、工具链和跨架构规则见 [发行配置](../docs/RELEASE.md)。

设计参考页通过 `cmake -S tools/native-ui -B build/native-ui/preview` 单独生成；普通插件构建不处理该页面。本地交付输出到 `dist/portable/`，安装包与资源归档同属 `dist/`。
