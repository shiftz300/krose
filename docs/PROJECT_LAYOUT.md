# 项目结构与开发入口

普通构建只依赖 `src/`、`assets/`、`cmake/`、`tests/` 和固定版本 SDK。界面源码和音色数据都有唯一的产品入口。`docs/` 保存说明与设计参考，`research/` 保存原件和逆向证据。

```text
krose/
  CMakeLists.txt                 选项和子项目编排
  CMakePresets.json              plugin / engine / sanitize
  .editorconfig                 文本格式约定
  .clang-format                 C/C++ 格式约定
  src/
    instrument/                 采样库、音符调度、包络和滤波控制
    dsp/                        可独立使用的 C 效果内核
    plugin/
      KrosePlugin.cpp/.h        插件生命周期与音频/MIDI 入口
      Parameters.cpp/.h        参数注册、固定 ID、旧状态迁移
      editor/
        WebEditor.cpp           WebKit 生命周期与消息边界
        web/
          panel.html            定稿面板结构
          panel.css             面板材质与固定布局
          font.css              内嵌点阵字体
          panel.js              面板渲染与交互
          host-bridge.js        宿主消息协议与参数手势
          control-bindings.js   原生参数/MIDI 到控件的绑定
          preset-browser.js     搜索、分类和音色选择
          editor.html.in        随包页面模板
      resources/               平台 plist、菜单、许可证资源引用
  assets/
    concert-se-grand/            Concert 兼容路径的冻结数据
    program-library/            全部出厂、GM、扩展音色及显示顺序
  tests/
    CMakeLists.txt               引擎测试目标
    test_*.cpp / .mm             原生、宿主及真实 WebKit 测试
    fixtures/                   从原固件观察结果冻结的独立输入
  cmake/
    Assets.cmake                校验与复制资源
    RuntimeAssets.cmake         manifest 验证函数
    EditorResources.cmake       合成内嵌界面及 Page 预览
    PluginDependencies.cmake    iPlug2 构建配置
    VST3Tests.cmake              固定版本 SDK 宿主和验证器
    dependencies.json           依赖版本锁
  tools/                        依赖准备、隔离检查、打包、音频工具
  docs/                         产品说明、设计参考、验证记录
  licenses/                     第三方声明
  research/                     原始资料、逆向工具和证据
  build/                        本机 SDK、缓存、生成页面和测试产物
  output/Krose/                 本地交付的 app、VST3 和清单
```

## 构建和预览

取得本地冻结采样包后，首次运行 `python3 tools/bootstrap_plugin.py` 准备固定版本 SDK。macOS 插件构建：

```sh
cmake --preset plugin
cmake --build --preset plugin
ctest --preset plugin
build/plugin/test-vst3-host build/plugin/out/Krose.vst3 --editor
```

无需 iPlug2 的引擎构建使用 `engine` preset；内存检查使用 `sanitize` preset。普通 CMake 不调用 Python 或固件提取器。目标名称及 `build/plugin/` 下原有工具入口保留。

构建配置阶段将 `editor/web/` 合成 `build/plugin/src/plugin/editor.html`，该文件直接装入 app 和 VST3。相同的面板源码还生成 `panel-preview.html`，可用于 Page／设计核对。不要修改生成文件；改动入口是对应 HTML、CSS 或 JS。`docs/design/` 只保存说明、布局索引和参考图。

## 数据和代码约定

- 新参数只追加到 `Parameters.h`，既有编号明确写出。插件 ID、bundle ID、原资源文件名及音色索引保留，以兼容现有工程。
- `instrument/` 和 `dsp/` 不依赖编辑器或宿主 SDK。音频线程禁止文件 I/O、锁和动态分配。
- 完整库路径统一为 `assets/program-library/`。旧 CMake 默认缓存自动迁移；用户指定的外部资源路径保持原值。历史研究路径通过 `research/tools/layout.py` 解析。
- 冻结资源由显式导出器生成；手工改 JSON／头文件会导致哈希校验失败。大型 `.samples`、原始固件和 WAV 不进入 Git。
- HTML 结构、CSS 和面板逻辑此次按原内容拆分；视觉调整仍以定稿为准。字体内嵌数据单列在 `font.css`，无需逐行格式化。
- `.editorconfig` 与 `.clang-format` 约束后续改动。保留未涉及的历史 DSP／研究文件格式，避免把格式差异混入声音修正。

导出入口：`research/tools/export_runtime_assets.py` 更新 Concert，`export_full_bank.py` 更新完整库，`export_program_checks.py` 更新独立选样 fixtures。`audit_resource_gaps.py` 核对剩余资源缺口和已有导入证据。

## 隔离和交付

`python3 tools/check_project_boundary.py` 在不复制 `research/`、`docs/`、`output/`、`tools/` 的临时目录里重建引擎并运行全部四项测试，同时检查产品代码和 CMake 的依赖边界。结果写入 `build/project-boundary-check.json`。

`python3 tools/package_plugin.py` 运行测试、验证签名并生成 `output/Krose/`。已有本轮成功日志时，可使用 `--skip-tests`，打包器仍检查日志并运行官方 validator。正式发布签名、公证和实际 DAW 验收分别记录。

## 研究资料

`research/libraries/`、`downloads/`、`firmware/`、`EXPCM001/` 保存原件；`derived/` 保存解包、解析和原 ARM 执行结果；`output/` 保存解码 PCM 与试听；`tools/`、`docs/` 分别保存研究代码和说明。原始文件、报告正文与既有来源哈希不随目录重构改写。

`research/RESOURCES.md` 中旧表保留其时间口径。当前产品覆盖以 [原生架构](NATIVE_ARCHITECTURE.md) 和 `assets/program-library/manifest.json` 为准；剩余缺口见 [资源复核](../research/docs/architecture/RESOURCE_GAPS.md)。独立试听网站仍位于相邻的 `krose-website` 工程。
