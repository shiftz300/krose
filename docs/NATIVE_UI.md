# 原生界面与素材维护

VST3 与独立程序使用 C++、iPlug2 IGraphics 和 NanoVG；macOS 渲染器为 Metal，Windows 配置为 OpenGL 2。基准逻辑尺寸为 1472×648；LCD 的 `>CTRL → INPUT → UI SIZE` 可选自动适应屏幕，或 60／75／85／100／125／150% 等比缩放，菜单同时显示对应窗口尺寸。选择保存为全局界面偏好，下次打开沿用；默认自动适应。右键 FX 的快捷入口保留。宿主拒绝调整窗口时保持原尺寸和偏好，并显示原因。插件不链接 WebKit。

## 控件与显示

原生面板包含旋钮、两套包络推子、61 键键盘、弯音、延音、Panic、LCD 音色页与控制设置、SW1／SW2、FX 收放和完整音色目录。顶部 PRESET 先显示 Favorites 与原厂分类，再展开音色列表；BROWSE 支持搜索和筛选。分类与条目保持原厂顺序。

LCD 的菜单、边框、填充及箭头遵循屏幕像素网格，菜单宽度与输入框一致。列表超出屏幕时滚动；方向键、Home／End、回车与 Esc 支持键盘操作。旋钮和推子双击复位、滚轮调整，Shift 细调；普通按钮逐次处理连点。浏览器关闭入口只有叉号，搜索框使用深色底。

SAVE／BROWSE → LOAD FILE 使用系统文件对话框；Compare 基准在打开编辑器、选音色、载入或保存时建立。`.krose` 文件只应用声音参数，SW、输入通道和 MIDI 映射保留。

四个模块读取各槽的实际音频。EQ 显示频谱与响应曲线，AUTO Concert EQ 使用实测输入／输出比；压缩器和 Limiter 保留灰／黄 VU 表，显示输出电平及增益衰减；Drive／Exciter 显示输入输出频谱和传输点；Chorus 显示立体声相位轨迹，Delay 显示返回能量历史，Hall／Plate 用返回频谱和能量驱动深度切片。深度切片是声音数据的视觉表达，不代表实测房间几何。

音频线程向固定 SPSC 环写入，界面约 30 Hz 分析，读写全程不等待；环满时丢弃显示数据。关闭编辑器后停止写入，静音后停止重绘，回落按实际时间计算。布局、材质、关闭灰显与四个参数页沿用定稿。`FxMonitor.h` 负责音频传递，`FxAnalysis.h` 负责分析，`PanelFxVisual.cpp` 负责绘制。

最终输出增加立体声联动的软过载保护：峰值低于 0.95 时逐样本保持原值，超过后平滑约束在 0.999 内，不增加延迟。此保护会改变过载信号，不能代替合理增益设置；触发时音量旋钮下方短暂显示 SAFE 和衰减条。

旋钮、推子、数值框、菜单和键盘编辑共用 `editor/ParameterBinding.h`。值直接读取 iPlug2 delegate，步进以参数最小值为基准，跳过未变化的写入；连续拖动与离散编辑分别维护配对的宿主手势，关闭窗口或中断拖动时结束手势。重绘比较使用 `kNumParams`，不另存一份可与宿主漂移的参数状态。

Favorites 按稳定的 Program 编号保存，与工程参数分开：macOS 为 `~/Library/Application Support/Krose/favorites.json`，Windows 为 `%LOCALAPPDATA%/Krose/favorites.json`。写入前合并已有内容，通过临时文件原子替换；失败时显示 FAVORITES NOT SAVED。

FX 收放是独立的显示状态，不改变音频。动画使用基于单调时钟的临界阻尼曲线，快速反向时继承位置和速度；收起后移除模块命中区域。位置计算不依赖逐帧积分，绘制目标为 60 Hz，复用离屏纹理，结束后停止动画重绘。

旋钮与推子的离散跳转、AMP／FILTER 推子切换和弯音回中使用 120 ms 视觉过渡；直接拖动跟随指针，音频参数与 MIDI 即时发送。按钮背光 120 ms、悬停 100 ms、按压反馈 80–90 ms；琴键按下即时显示，松开用 90 ms 回落。LCD 页与菜单打开使用 100 ms 透明度过渡，不平移或缩放像素文字；菜单关闭即时完成。

这些过渡由 `UIMotion.h`／`PanelMotion.cpp` 管理，使用单调时钟，重复目标不会重启动画，快速修改从当前画面接续。空闲后停止重绘；菜单离屏层仅在过渡中存在，完成后释放。数值文本、命中区域与宿主参数始终保持当前值，视觉插值不进入音频线程。

2026-11-06 本机 arm64 Release 短测：`KROSE_BENCH_CASE=ui_animation benchmark-runtime <VST3> 5` 连续操作页面、推子、按钮与菜单，帧间隔中位 16.66 ms、p95 18.23 ms，绘制 CPU p95 3.02 ms。整个测试宿主平均 CPU 5.2%（单核 = 100%），结束后空闲约 2.0%；平均物理占用从操作中的 312 MiB 回落至 241 MiB。48 kHz／128 帧音频回调无超预算。此测量包含窗口与 Metal 资源，未连接音频设备。

## LCD 效果链

点 LCD 的 FX 标签，进入 IFX 1、IFX 2、MFX 1、MFX 2 四个参数页。上排选择槽位，当前页显示效果类型、Wet/Dry 或 Send，以及当前算法的参数。左侧效果模块单击切换启用／旁通，保留类型和参数；右键打开对应槽位的 LCD 编辑页；中键移除效果，恢复空槽菱形。类型菜单选择 Off 也可清空效果。LCD 内不再显示 ON／OFF 按钮。OFF 类型和自动解析为空的槽显示淡红轨道与棕色菱形，点菱形直接选择效果。已有类型的槽在关闭或全局绕过时熄灯并灰显，类型和参数仍保留。发送量／Wet-Dry 为零时保留开关状态，提示显示 DRY；全局绕过显示 BYPASS。切换算法时，图案随算法更新。

- IFX 串联处理主声。四段 EQ 可调整 Freq、Gain 和 Q；七段 Graphic EQ 保留原厂 12 组频点布局、七段增益与 Trim。压缩、限幅、Drive、Exciter、Phaser、Tremolo 和 Auto Pan 均在当前槽内编辑。新增类型菜单在 LCD 内滚动。
- MFX 从 IFX 2 后并联取信号，支持 Chorus、Stereo Delay、Hall、Plate，以及 EQ、七段 Graphic EQ、压缩、限幅、Drive、Exciter、Phaser、Tremolo、Auto Pan。参数仍由四个槽位标签管理。
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

## 本轮交互修复

- LCD 状态行的分类／编号和 Tempo 共用文字基线；切页取消整屏白色叠层，边框和背光保持稳定。
- 菜单打开／关闭、按钮灯和 FX 旁通有时间驱动的淡入淡出；关闭中的图层不占用点击区域。预设背景保持清晰，不使用模糊。
- 数值区域支持上下拖动、Shift 细调；短按仍可输入数值，滚轮操作保留。
- 编辑器从音频线程快照读取按键、弯音、Mod 和延音状态，MIDI 映射与宿主自动化更新旋钮／推子／按钮。拖动滚轮时忽略过期快照，下一条实际 MIDI 输入继续同步。
- ARP 的 EDIT 菜单和分类模式选择位于 LCD 内，不移动整机控件块。

选择工厂音色会同步载入其主通路效果与琶音，复位相对 Tone Adjust。四个效果槽保持不变：沿主输入总线跟随 IFX 串接，优先保留前两个有效插入和两路 MFX；不把未进入主通路的 IFX5 强行插入。原厂效果名、双槽分配、发送和返回从原 Program 读取。当前主机算法覆盖范围仍有限：未实现的效果在 LCD 标出原名，不继承上一音色的效果，也不冒充完整原厂 DSP；超过两级的插入和主效果串接仍有还原差异。

七段 EQ 的频点来自 v1.2.4 固件 `0x37cb30` 表，参数位域和 ±18 dB 增益按原数据读取；音频使用主机 biquad。Phaser 为六级 allpass，Tremolo／Auto Pan 使用主机调制器，保留能解释的原深度、速率和效果量。原 DSP 的反馈、波形整形、Dmod 和全部时间定律仍有差异。普通 Limiter 使用限幅器路径，不再映射为压缩器。

`.krose` 文件为格式 4，新增参数只追加 ID。格式 1–3 转换旧范围和算法枚举；旧 103／106 参数宿主状态也能恢复。已有宿主自动化若保存归一化 FX 类型曲线，需要按新枚举数量复核；宿主状态中的物理算法编号保持兼容。
