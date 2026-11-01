# 工程边界

2026-11-01 从 `kross2` 拆分为相邻两个工程：`krose` 为插件，`krose-website` 为独立网站。原 `kross2` 不再作为开发目录。

```text
krose/
  src/                         产品 C/C++ 源码、DSP 与 iPlug2 界面
  assets/                      冻结产品输入
  tests/                       原生测试及 fixtures
  cmake/                       构建配置、依赖版本锁
  tools/                       bootstrap、打包、隔离检查与渲染/性能工具
  docs/                        产品文档
  licenses/                    框架与字体声明
  build/                       必要 SDK 与可重建产物
  research/
    EXPCM001/                  用户提供的未修改原件
    downloads/                 官方下载 ZIP / PDF 与曲目来源
    firmware/                  官方固件解包原件
    libraries/                 原始 USB 备份和采集原始消息
    external/                  参考项目资料
    derived/                   ROM 镜像、解析数据、原 ARM 比较证据
    output/                    完整 PCM24 WAV、参数目录和研究试听
    tools/                     解码、固件分析、探针与研究导出
    docs/                      逆向研究记录
    archive/                   历史源码快照、迁移清单、必要过程证据
    python-deps/               仍需使用的 Capstone / Unicorn
    build/                     研究可重建缓存，当前保留 Opus 编码以便重新导出
krose-website/
  public/                      唯一网页源码与静态资源
  tests/                       独立网页测试和固定输入
  scripts/                     Bun 检查、构建、本地服务器与依赖资源同步
  wrangler.jsonc               Cloudflare Workers 静态资源配置
  wrangler.pages.jsonc         可切换的 Pages 配置模板
```

普通 CMake 构建只读产品源码、冻结资源、测试数据和 SDK。`python3 tools/check_project_boundary.py` 会在没有 research/output/tools 的隔离目录中编译并运行引擎测试。研究资源更新是显式操作：`python3 research/tools/export_runtime_assets.py`，需要先按新源码重新生成并验证相关研究报告。

历史报告保留原始字节和原工具 SHA，不修改旧证据来迎合迁移后的代码。`research/tools/layout.py` 将旧相对路径解析到新目录，防止为了兼容路径而复制或散放研究文件。新工具可直接使用其中 `RESEARCH_ROOT` 与 `PRODUCT_ROOT`；新报告以产品根目录作为相对路径基准。

迁移前源码、工具和文档保存在 `research/archive/migration-2026-11-01/pre-split-sources.tar.gz`；迁移清单记录原件 SHA、删除范围和校验结果。旧版本构建聚合校验（例如 `verify_native_player.py`）是历史工具；已清理的构建结果需要重建，不能用旧日志声称当前编译成功。

保留原始备份、完整 ROM、完整 WAV 和研究报告；清理编译缓存、重复网页导出、旧插件二进制、转换中间 WAV、无用 Crypto 依赖及项目临时文件。没有安装插件、访问或改写琴。

当前资源索引由 `python3 research/tools/index_resources.py` 生成，位于 `research/RESOURCES.md` 与 `research/derived/catalog/`。音色状态表覆盖板载参数、GM 名称目录与扩展包；不改写旧来源文件的可用性标记。

原生共享库与 Program 首批接入见 [NATIVE_ARCHITECTURE.md](NATIVE_ARCHITECTURE.md)。新增 `assets/factory-starter` 和 `research/config/native-starter.json`，不改变原 Concert 冻结资源。
