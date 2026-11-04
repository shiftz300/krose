# 原生界面移植

目标：按已定稿的 1472×648 面板移植到 iPlug2 IGraphics，支持 Windows 和 macOS。布局、材质、字体、控件状态和现有功能以当前安装版页面为基准。

## 实施状态

- 原生面板已成为 VST3 和独立程序的默认编辑器。运行时使用 C++ / iPlug2 / IGraphics / NanoVG；macOS 使用 Metal，Windows 配置为 OpenGL 2。产品不再链接 WebKit。
- 已接入旋钮、两套包络推子、61 键键盘、弯音、延音、Panic、LCD 四页、FX 收放、1162 项音色及原厂分类顺序。参数 ID 和声音核心保留。
- 顶部 PRESET、LCD 和浏览器下拉菜单统一按输入框左边与宽度展开，固定文字内边距与箭头位置，支持鼠标与方向键选择。用户追加要求已落实：LCD 内无圆角，所有下拉框使用直角像素边框及点阵箭头。此项作为原稿之后的明确样式修订记录。
- 本机原生窗口的 Cocoa 事件测试通过，包括参数编辑、音色搜索、下拉选择和关窗重开；7 项 CTest 通过。原生帧缓冲与冻结页面的对比保存在 `build/native-ui/comparison/`。像素差分仍非零，不能宣称逐像素完全一致。
- Windows x64 的 VST3 和独立程序已通过 MSVC 编译：[构建记录](https://github.com/shiftz300/krose/actions/runs/41788798938)。CI 使用独立的编译占位包，不包含 PCM，不作可试听产物发布。Windows 窗口与宿主运行尚未实机验收。
- LCD 菜单保持与输入框同宽，限制在屏幕内部，超出可见行数时滚动；Home/End、方向键与回车均可选择。数值微调按钮使用点阵箭头，清除了系统圆角底图。浏览器的搜索文字和行点击范围按可见区域裁剪，末尾音色可完整滚入视野。

## 文件组织

- `src/plugin/editor/native/NativePanel.cpp`：整机与 LCD 绘制；`PanelInput.cpp`：宿主参数及输入；`PanelBrowser.cpp`：音色与菜单。
- `src/plugin/editor/native/assets/`：运行时 PNG 材质与坐标清单。
- `tools/native-ui/`：开发期 WebKit 导出工具；原生控件不依赖 WebKit。
- `docs/verification/native-ui/`：版本化参考图、源哈希和几何数据。

## 重建参考与资源

先配置现有 `plugin` preset，得到 `build/plugin/src/plugin/editor.html`。随后在 macOS 运行：

```sh
python3 tools/native-ui/prepare.py
clang++ -std=c++17 -fobjc-arc tools/native-ui/capture.mm -framework Cocoa -framework WebKit -o /tmp/krose-native-capture
/tmp/krose-native-capture build/native-ui/reference.html build/native-ui/jobs.json build/native-ui
python3 tools/native-ui/complete_assets.py
/tmp/krose-native-capture build/native-ui/reference.html build/native-ui/complete-jobs.json build/native-ui/complete
python3 tools/native-ui/field_assets.py
/tmp/krose-native-capture build/native-ui/reference.html build/native-ui/field-jobs.json build/native-ui/fields
python3 tools/native-ui/publish_complete.py
```

导出 PNG 需要 2× 显示缩放；发布脚本拒绝尺寸不符的资源。开发工具仅从已生成页面读取资源，使用临时 WebKit 数据存储。发布脚本需要 Pillow。

## 验证与交付

- macOS arm64：官方 VST3 验证器 47/47，7/7 CTest，通过全部音色渲染、状态恢复与声音核心回归；原生 Cocoa 事件测试另行验证控件、搜索、菜单、FX 收放和编辑器重开。未修改的声音核心此前通过 6/6 ASan/UBSan 检查。
- 原生实际渲染图保存在 [current](verification/native-ui/current/)，包括整机、ARP、FX 与三处菜单。历史 `reference-*.png` 保留，不覆盖原稿。
- 当前图与原稿的差分包含已授权的像素边框修订，以及文字栅格化等差异。MAE 与超阈值像素占比见 `current/comparison.json`；这些数值不能换算成移植完成率，也不表示逐像素完全一致。
- 本机交付：`output/Krose/Krose.vst3`、`Krose.app`。打包时重新签名、校验并运行官方 VST3 验证器，精确二进制、资源和测试日志哈希写入 `manifest.json`。
- Windows 已完成编译验证；Windows GUI、不同 DPI 和 DAW 手工验收仍待实机执行。macOS DAW 的长期演奏、工程往返与跨机发行也尚未验收。

## 本次保持的功能边界

SW1/2、Mod、Save/Compare 和 FX 参数在迁移前的实际插件中处于禁用状态，原生界面保留此行为。FX 材质显示已有四组路由预览；没有已确认路由的音色不生成虚构模块。LCD 中的 Release/Space 使用宿主实际值，修正了脱离宿主导出时这两项为空的问题。

开发期 WebKit 仅用于提取已批准的材质和字体。FX 收起参考需等待动画结束；导出收起底图时显式隐藏被裁剪的画布，避免 WKWebView 离屏截图遗漏 clip-path 后仍残留模块。
