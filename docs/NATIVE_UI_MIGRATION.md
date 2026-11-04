# 原生界面移植

目标：按已定稿的 1472×648 面板移植到 iPlug2 IGraphics，支持 Windows 和 macOS。布局、材质、字体、控件状态和现有功能以当前安装版页面为基准。

## 实施状态

- 原生面板已成为 VST3 和独立程序的默认编辑器。运行时使用 C++ / iPlug2 / IGraphics / NanoVG；macOS 使用 Metal，Windows 配置为 OpenGL 2。产品不再链接 WebKit。
- 已接入旋钮、两套包络推子、61 键键盘、弯音、延音、Panic、LCD 四页、FX 收放、1162 项音色及原厂分类顺序。参数 ID 和声音核心保留。
- 顶部 PRESET、LCD 和浏览器下拉菜单统一按输入框左边与宽度展开，固定文字内边距与箭头位置，支持鼠标与方向键选择。用户追加要求已落实：LCD 内无圆角，所有下拉框使用直角像素边框及点阵箭头。此项作为原稿之后的明确样式修订记录。
- 本机原生窗口的 Cocoa 事件测试通过，包括参数编辑、音色搜索、下拉选择和关窗重开；7 项 CTest 通过。原生帧缓冲与冻结页面的对比保存在 `build/native-ui/comparison/`。像素差分仍非零，不能宣称逐像素完全一致。
- Windows 的模块资源路径、VST3/独立程序资源复制和原生窗口资源已补齐；Windows CI 使用独立的编译占位包，运行结果另记。占位包不包含 PCM，也不作可试听产物发布。

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

## 完成标准

- 全部音色、原厂分类顺序及现有参数连接通过原生编辑器测试。
- 逐项对比默认、按下、展开/收起、LCD 四页、音色切换和宿主自动化状态。
- 提供原生整机截图和差分结果；仅通过编译不视为视觉通过。
- Windows 和 macOS 分别构建、验证 VST3 并检查缩放及反复开关编辑器。
- 完成验收后切换默认编辑器，并移除产品对 WebKit/WebView 的运行时依赖。

## 本次保持的功能边界

SW1/2、Mod、Save/Compare 和 FX 参数在迁移前的实际插件中处于禁用状态，原生界面保留此行为。FX 材质显示已有四组路由预览；没有已确认路由的音色不生成虚构模块。LCD 中的 Release/Space 使用宿主实际值，修正了脱离宿主导出时这两项为空的问题。

开发期 WebKit 仅用于提取已批准的材质和字体。FX 收起参考需等待动画结束；导出收起底图时显式隐藏被裁剪的画布，避免 WKWebView 离屏截图遗漏 clip-path 后仍残留模块。
