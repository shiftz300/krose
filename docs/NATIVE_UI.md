# 原生界面与素材维护

VST3 与独立程序使用 C++、iPlug2 IGraphics 和 NanoVG；macOS 渲染器为 Metal，Windows 配置为 OpenGL 2。逻辑尺寸固定为 1472×648。插件不链接 WebKit。

## 控件与显示

原生面板包含旋钮、两套包络推子、61 键键盘、弯音、延音、Panic、LCD 音色页与控制设置、SW1／SW2、FX 收放和完整音色目录。顶部 PRESET 先显示 Favorites 与原厂分类，再展开音色列表；BROWSE 支持搜索和筛选。分类与条目保持原厂顺序。

LCD 的菜单、边框、填充及箭头遵循屏幕像素网格，菜单宽度与输入框一致。列表超出屏幕时滚动；方向键、Home／End、回车与 Esc 支持键盘操作。旋钮和推子双击复位，普通按钮逐次处理连点。

旋钮、推子、数值框、菜单和键盘编辑共用 `editor/ParameterBinding.h`。值直接读取 iPlug2 delegate，步进以参数最小值为基准，跳过未变化的写入；连续拖动与离散编辑分别维护配对的宿主手势，关闭窗口或中断拖动时结束手势。重绘比较使用 `kNumParams`，不另存一份可与宿主漂移的参数状态。

Favorites 按稳定的 Program 编号保存，与工程参数分开：macOS 为 `~/Library/Application Support/Krose/favorites.json`，Windows 为 `%LOCALAPPDATA%/Krose/favorites.json`。写入前合并已有内容，通过临时文件原子替换；失败时显示 FAVORITES NOT SAVED。

FX 收放是独立的显示状态，不改变音频。动画使用基于单调时钟的临界阻尼曲线，快速反向时继承位置和速度；收起后移除模块命中区域。位置计算不依赖逐帧积分，绘制目标为 60 Hz，复用离屏纹理，结束后停止动画重绘。

## LCD 控制设置

点击 LCD 标题右侧 `>CTRL` 打开控制设置，`< PROG` 返回音色页面。CTRL 配置 SW1／SW2 的功能、Toggle／Momentary 和测试；MIDI 管理 64 个映射；INPUT 保存 4 个用户配置并选择输入通道、时钟；HELP 显示最后收到的 MIDI 消息及操作提示。右键旋钮、推子或参数字段直接学习对应目标；右键 SW 按钮打开功能分配。学习可点 CANCEL 或按 Esc 取消。

设置页复用现有字体图集，边框和连接标签落在 LCD 像素网格。设置仅改变 LCD 内容，整机布局和动画材质保持原样。范围、默认 CC 和宿主差异见 [MIDI 控制](MIDI.md)。

## 源码与资源

- `src/plugin/editor/NativeEditor.cpp`：控件装配与输入路由。
- `src/plugin/editor/native/NativePanel.cpp`：整机与 LCD 绘制。
- `PanelInput.cpp`、`PanelBrowser.cpp`、`PanelFavorites.cpp`、`PanelControllers.cpp`：参数输入、菜单、收藏与 LCD 控制设置。
- `src/plugin/editor/native/assets/`：实际运行的 PNG 材质、点阵字形和几何数据。
- `tools/native-ui/reference/`：定稿的可编辑 HTML／CSS 参考源，仅用于素材生成和设计核对。

图片按需加载，字体图集保留原像素。更改外观应同时维护参考源和冻结资源，保持画布、控件坐标与参数 ID 一致。

## 重建素材

普通产品构建不处理参考页面。开发期在 macOS 显式运行：

```sh
cmake -S tools/native-ui -B build/native-ui/preview
python3 tools/native-ui/prepare.py
clang++ -std=c++17 -fobjc-arc tools/native-ui/capture.mm -framework Cocoa -framework WebKit -o /tmp/krose-native-capture
/tmp/krose-native-capture build/native-ui/reference.html build/native-ui/jobs.json build/native-ui
python3 tools/native-ui/complete_assets.py
/tmp/krose-native-capture build/native-ui/reference.html build/native-ui/complete-jobs.json build/native-ui/complete
python3 tools/native-ui/field_assets.py
/tmp/krose-native-capture build/native-ui/reference.html build/native-ui/field-jobs.json build/native-ui/fields
python3 tools/native-ui/publish_complete.py
```

素材导出要求 2× 显示缩放；发布脚本校验尺寸并更新冻结清单。图片处理依赖 Pillow。收起状态的截图在动画结束后获取，显式隐藏被裁剪画布，避免离屏截图遗漏 clip-path。

原生 Cocoa 交互测试位于 `tests/plugin/test_editor_mac.mm`；测试通过 `KROSE_FAVORITES_FILE` 和 `KROSE_MIDI_MAP_FILE` 隔离用户设置。Windows GUI、不同 DPI 以及 DAW 长时间演奏需在目标环境验收。
