# 原生界面移植

目标：按已定稿的 1472×648 面板移植到 iPlug2 IGraphics，支持 Windows 和 macOS。布局、材质、字体、控件状态和现有功能以当前安装版页面为基准。

## 实施状态

1. **已完成：参考冻结。** 从实际 WKWebView 提取 1472×648 逻辑坐标、2944×1296 Retina 图像、四个 LCD 页和五个代表音色。源文件 SHA-256 记录在 `verification/native-ui/source-manifest.json`。
2. **已完成：首批资源与控件。** 透明旋钮外壳、独立指针、16 个按钮的开关状态、FX 展开/收起底图。C++ IGraphics 旋钮与开关已加入编译；旋钮使用连续旋转，支持拖动、Shift 微调、双击复位和方向键。
3. **待完成：原生面板接入。** 推子、琴键、滚轮、数值编辑、LCD 字体与页面、音色浏览、FX 状态和启动状态尚未完成原生接入。当前产品入口仍使用 WebEditor。
4. **待完成：图像差分和交互验收。** 已生成的材质资产通过尺寸与透明度检查。尚未取得原生整机渲染的对比结果，不能据此宣称 1:1 移植完成。
5. **待完成：Windows 构建及宿主验证。** 绘图配置已按 macOS Metal / Windows GL2 分支。Windows 安装、资源路径和宿主验证仍待完成。

## 文件组织

- `src/plugin/editor/native/BitmapControls.h`：IGraphics 控件。
- `src/plugin/editor/native/assets/`：运行时 PNG 材质与坐标清单。
- `tools/native-ui/`：开发期 WebKit 导出工具；原生控件不依赖 WebKit。
- `docs/verification/native-ui/`：版本化参考图、源哈希和几何数据。

## 重建参考与资源

先配置现有 `plugin` preset，得到 `build/plugin/src/plugin/editor.html`。随后在 macOS 运行：

```sh
python3 tools/native-ui/prepare.py
clang++ -std=c++17 -fobjc-arc tools/native-ui/capture.mm -framework Cocoa -framework WebKit -o /tmp/krose-native-capture
/tmp/krose-native-capture build/native-ui/reference.html build/native-ui/jobs.json build/native-ui
python3 tools/native-ui/assets.py
/tmp/krose-native-capture build/native-ui/reference.html build/native-ui/asset-jobs.json build/native-ui/assets
python3 tools/native-ui/publish_assets.py
```

导出 PNG 需要 2× 显示缩放；发布脚本拒绝尺寸不符的资源。开发工具仅从已生成页面读取资源，使用临时 WebKit 数据存储。发布脚本需要 Pillow。

## 完成标准

- 全部音色、原厂分类顺序及现有参数连接通过原生编辑器测试。
- 逐项对比默认、按下、展开/收起、LCD 四页、音色切换和宿主自动化状态。
- 提供原生整机截图和差分结果；仅通过编译不视为视觉通过。
- Windows 和 macOS 分别构建、验证 VST3 并检查缩放及反复开关编辑器。
- 完成验收后切换默认编辑器，并移除产品对 WebKit/WebView 的运行时依赖。
