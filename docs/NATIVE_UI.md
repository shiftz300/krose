# 原生界面与素材维护

VST3 与独立程序使用 C++、iPlug2 IGraphics 和 NanoVG；macOS 渲染器为 Metal，Windows 配置为 OpenGL 2。逻辑尺寸为 1472×648，右键 FX 可按 60–150% 等比缩放。插件不链接 WebKit。

## 控件与显示

原生面板包含旋钮、两套包络推子、61 键键盘、弯音、延音、Panic、LCD 音色页与控制设置、SW1／SW2、FX 收放和完整音色目录。顶部 PRESET 先显示 Favorites 与原厂分类，再展开音色列表；BROWSE 支持搜索和筛选。分类与条目保持原厂顺序。

LCD 的菜单、边框、填充及箭头遵循屏幕像素网格，菜单宽度与输入框一致。列表超出屏幕时滚动；方向键、Home／End、回车与 Esc 支持键盘操作。旋钮和推子双击复位、滚轮调整，Shift 细调；普通按钮逐次处理连点。浏览器关闭入口只有叉号，搜索框使用深色底。

SAVE／BROWSE → LOAD FILE 使用系统文件对话框；Compare 基准在打开编辑器、选音色、载入或保存时建立。`.krose` 文件只应用声音参数，SW、输入通道和 MIDI 映射保留。

Limiter 表针读取 IFX 输出峰值，回落按实际时间计算；默认 AUTO 和其他算法图案仍用于识别类型，不宣称频谱／混响声场测量。Meter 数据通过固定大小原子值传递，音频线程不调用绘图。FX 页已独立到 `PanelEffects.cpp`。

旋钮、推子、数值框、菜单和键盘编辑共用 `editor/ParameterBinding.h`。值直接读取 iPlug2 delegate，步进以参数最小值为基准，跳过未变化的写入；连续拖动与离散编辑分别维护配对的宿主手势，关闭窗口或中断拖动时结束手势。重绘比较使用 `kNumParams`，不另存一份可与宿主漂移的参数状态。

Favorites 按稳定的 Program 编号保存，与工程参数分开：macOS 为 `~/Library/Application Support/Krose/favorites.json`，Windows 为 `%LOCALAPPDATA%/Krose/favorites.json`。写入前合并已有内容，通过临时文件原子替换；失败时显示 FAVORITES NOT SAVED。

FX 收放是独立的显示状态，不改变音频。动画使用基于单调时钟的临界阻尼曲线，快速反向时继承位置和速度；收起后移除模块命中区域。位置计算不依赖逐帧积分，绘制目标为 60 Hz，复用离屏纹理，结束后停止动画重绘。

## LCD 效果链

点 LCD 的 FX 标签或左侧模块，进入 IFX 1、IFX 2、MFX 1、MFX 2 四个参数页。上排选择槽位，当前页显示效果类型、独立开关、Wet/Dry 或 Send，以及当前算法的参数。OFF 类型和自动解析为空的槽显示淡红轨道与棕色菱形，点菱形直接选择效果。已有类型的槽在关闭、全局绕过或效果量为零时熄灯并灰显，类型和参数仍保留。切换算法时，图案随算法更新。

- IFX 串联处理主声。EQ 按 Band 选择四个频段，分别调整 Freq、Gain 和 Q。压缩显示阈值、比率、起音和释放，限幅显示 Ceiling 与释放。Drive 与 Exciter 分别显示 Drive 和 Blend。
- MFX 从 IFX 2 后并联取信号。Chorus 显示深度与 LFO 频率，延迟显示左右时间与反馈，Hall 和 Plate 显示衰减时间与高频阻尼。手动设定的两路 MFX 可使用相同效果并各自调整。
- AUTO 保留 Krose 的默认处理。编辑 AUTO 的算法参数会将该槽切到对应的手动类型。参数和开关随宿主工程保存。
- C107 Trumpet Overblown 的试听设置为 IFX 1 选 Drive，Drive 60、Wet/Dry 70%，MFX 2 保持 AUTO。

页面组织与字段参考项目保存的原厂参数记录及 [KROSS 2 参数手册](https://cdn.korg.com/us/support/download/files/96dbde75752a88b2daf897262d199b80.pdf)。原机 A000 记录的槽位为 IFX1、IFX2、IFX5 和 MFX2。Krose 的四槽编辑器采用双插入、双发送路由和本机 DSP。

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

应用图标为独立绘制的粗体罗马衬线 K，使用石墨灰底和暖色大理石纹理；字形以矢量轮廓保存，不依赖系统字体。面板中的 Maincore 标识保持原样。`src/plugin/resources/Krose.svg`／`Krose.png` 为预览，`Krose.icns` 用于 macOS，`Krose.ico` 用于 Windows 应用及 NSIS 安装器。显式更新命令为 `python3 tools/native-ui/generate_app_icon.py`（Pillow）；普通编译直接使用冻结图标，无需生成依赖。macOS 的图标通过 Info.plist 和 iPlug2 bundle 资源接入，Windows 同时设置 EXE 资源、独立窗口与卸载列表图标。

K 在初版基础上等比缩小至 82%，增加留白、柔和投影和石材边缘高光。层次参考 [Apple App Icons](https://developer.apple.com/design/human-interface-guidelines/app-icons)。`Krose.icon` 保存独立的无光照 K 图层及默认／深色／单色配置，由系统处理圆角、玻璃和光照；ICNS／ICO 保留兼容外观。

分层图标采用一次预编译：`python3 tools/native-ui/compile_app_icon.py` 在安装 Xcode 26+ 的 Mac 上生成 `resources/macos-icon/Assets.car` 和校验清单；也可手动运行 `Precompile macOS app icon` 工作流，取回同一产物。将这两个文件纳入源码后，日常构建只需 Command Line Tools，不调用 Xcode，也不上传图标。

CMake 校验图层及编译产物的 SHA-256，再将 `Assets.car` 复制到独立程序并添加 `CFBundleIconName=Krose`；原 `CFBundleIconFile` 保留供旧系统使用。图层改动却未更新产物时构建报错，避免打包过期图标。缺少预编译产物时明确回退到静态 ICNS，此状态不代表已支持系统外观切换。

六种外观已通过 Icon Composer 1.2 官方渲染器检查。首次预编译由 [图标 CI](https://github.com/shiftz300/krose/actions/runs/42082909494) 完成，`Assets.car` 为 1,799,544 字节。本地只用 Command Line Tools 构建，已核对 bundle 命名、资源哈希及签名；NSWorkspace 从实际应用读取到系统深色版本，独立程序正常启动。透明／染色的六宫格为官方渲染器预览，尚未逐项改变用户的系统外观设置。

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
