# Krose research

原始输入、逆向脚本、解码产物与研究证据全部保留在此目录。产品源码在上一级；网页源码在相邻 `krose-website/public/`。

- [原生共享库与首批接入](../docs/NATIVE_ARCHITECTURE.md)
- [当前逆向进度](docs/PROGRESS.md)
- [资源总索引](RESOURCES.md) · [全部音色状态表 CSV](derived/catalog/programs.csv)
- [ROM 采集与校验](docs/ROM_ACQUISITION.md)
- [采样解码与音色组织](docs/ROM_DECODING.md)
- [原机预制音色](docs/FACTORY_SOUNDS.md)
- [声音控制](docs/VOICE_CONTROL.md)、[控制时间](docs/VOICE_TIMING.md)、[滤波](docs/FILTER_CONTROL.md)
- [网页原始释放包络及动态 AMS](docs/WEB_RELEASE_AMS.md)
- [迁移前项目记录](HISTORY.md)
- [迁移清单](archive/migration-2026-11-01/manifest.json)

从 `krose` 根目录运行新的入口：

```sh
python3 research/tools/index_resources.py
python3 research/tools/verify_workspace.py
python3 research/tools/test_korg_pcm.py
python3 research/tools/test_kep_extraction.py
python3 research/tools/verify_wav_exports.py
```

研究环境可用 `python3 -m venv research/.venv`，再安装 `research/requirements-research.txt` 与 `research/requirements-rom-audio.txt`。当前仍保留已验证的 Capstone / Unicorn 本地依赖。原 ARM 执行对宿主 JIT 权限有要求；无需为了普通插件或网页开发运行探针。

`tools/layout.py` 支持旧报告中的 `research/...`、`output/...`、`tools/...` 等路径，原报告和来源哈希不重写。历史文档中的旧命令、`build/` 与 `output/` 路径是当时的记录：研究输出现在为 `research/output/`，研究脚本现在为 `research/tools/`。工具源码移动后，报告对旧工具 SHA 的检查可能要求重新生成证据；不要绕过检查或将旧报告标为当前通过。

网页资源导出入口仍为 `python3 research/tools/build_krose_web.py`，读取网站仓库的唯一网页源文件，在 `research/output/Krose_Web/` 生成待检查副本。日常网站修改、测试和部署只需在 `krose-website` 中运行 Bun scripts。已生成的网页目录、ZIP 和 Opus 中间输入可按需重建。

硬件采集脚本只作为研究资料保存；当前工作不执行硬件命令，也不安装 VST3。
