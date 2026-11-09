# Arturia KeyLab Essential mk3

适配目标为 **KeyLab Essential 49 mk3**。本机 Live 的已保存设备名为 `KL Essential 49 mk3 (MIDI)`。旧款 Essential、完整 KeyLab mkII／mk3 使用不同协议，本实现不向这些设备发送指令。

## 内置资源和用户扩展

源码固定放在 `controllers/`。默认构建把适配器、目录数据、独立版映射和模板一起放进 APP／VST3 的 `Resources/Controllers`；无需另下 ZIP，也无需运行时安装 Python。`-DKROSE_BUNDLE_CONTROLLERS=OFF` 可以关闭附带资源。

打开 **LCD > CTRL > INPUT > PROFILES > OPEN BUILT-IN KIT** 可查看随包资源。Ableton 的 `ableton/Remote Scripts` 和 `ableton/Defaults` 已包含所需音色索引，可直接复制到 User Library，随本体一并交付。

独立版通用映射模板是 `templates/standalone/generic-keyboard.json`。复制到 **PROFILES > OPEN USER PROFILES** 打开的用户目录，修改名称、CC／音符编号、通道、目标和编码器模式；重新打开 PROFILES 即会列出文件；无效内容标为 INVALID，不会替换现有映射。选择后确认替换，点 STORE 保存到 USER 槽。EXPORT CURRENT MAP 生成可编辑的新 JSON，不覆盖已有文件。用户目录位于每用户应用支持路径下的 `Krose/Controllers/Profiles`，升级不会覆盖。模板只定义输入映射，设备的 MIDI 端口仍通过正常音频／MIDI 设置选择。

`templates/ableton/Krose_Generic_Template` 是独立的输入型控制脚本模板，默认不发送 SysEx 或灯光回传，不自动注册端口。它只控制选中的 Krose；修改 `CHANNEL` 和 `CONTROLS` 后由使用者手动安装、选择。设备专用屏幕／灯协议需要单独实现并做实物验证，不能把 Arturia 协议直接套到别的键盘。

### 安全边界

- Krose 对用户扩展只读取 JSON；不加载 Python／动态库，不执行命令，不跟随配置中的路径，也不向任意 MIDI 设备发送配置指定的 SysEx。
- JSON 导入限 256 KiB、16 层和现有 64 个映射槽；目标按参数名称解析，拒绝未知字段、枚举、越界通道／编号和配置文件符号链接。完整验证后才替换当前映射。这里只在 UI 操作时读取，音频线程保持固定容量原子映射。
- Ableton Python 脚本具有 Live 进程的用户权限，Krose 无法为其提供沙箱。模板不会自动复制到 Live；第三方脚本需自行检查。Live 脚本目录由用户明确选择，不改写 Live 应用目录。
- 安装工具拒绝托管路径中的符号链接及 Windows junction 目录联接，限制参数配置大小和条目数，先准备新脚本再替换旧目录；已有脚本和参数布局保留备份。异常配置不会先删掉旧脚本。
- KeyLab 目录 JSON 采用有限长度读取并验证索引及字符串结构；错误时退回参数文字显示。短 SysEx 不会越界索引。独立版硬件识别、输出速率和多实例归属沿用现有约束。

## 独立版

1. 键盘通过 USB 连接，在键盘上选择 **DAW** 程序。
2. Krose 的 Audio and MIDI Settings 选择 `Automatic` 或键盘的 **MIDI** 输入。
3. LCD 的 `>CTRL → INPUT` 最下一行显示连接状态；点击可关闭或恢复 Arturia 反馈。偏好保存在 `midi-mappings.json`，不随音色改变。

屏幕采用插件 LCD 的页面层级：标题显示音色编号和原厂分类；编辑时显示 TONE、FX 槽位、ARP 或 CTRL，以及参数名和数值，1.2 秒后返回音色。使用键盘内置的钢琴、贝斯、弦乐等图标；音色名只占一行，超过 12 个 ASCII 字符时在固定宽度内横向滚动，每 0.35 秒移动一个字符，首尾各停顿约 1.2 秒，不续写到下一行。短名称静止；切音色、编辑参数或重新连接后从头显示。参数名最多 12 个字符，数值行最多 18 个，缩写保留完整 IFX／MFX 编号。先创建页面，再写标题，避免固件重建页面清掉标题。字体和图标由键盘固件绘制，未上传 KROSS 的位图。

只回传屏幕文字和 Pad 灯状态，不向旋钮回写位置，也不自动居中 Value，以免覆盖键盘正在显示的数值。Value 首次输入只记录位置，后续转动按原厂目录切换；它使用键盘发送的绝对值，到端点后需反向旋转。中央编码器可持续逐项切换。推子使用拾取接管，接管后每条输入立即应用；记录参数取整后的实际值，避免快速移动时被反复判定为外部修改。切换音色或外部修改参数后重新拾取。

独立版和 Live 脚本为 18 个旋钮／推子写入键盘固件的参数弹窗文字缓存，按真实控件的 CC 标识选择原生旋钮／推子图示，转动时显示对应名称和数值；连续操作期间暂停整页覆盖，停止约 1.2 秒后恢复音色页面。弹窗文字缓存不改变硬件旋钮位置。Value 快速旋转的大步进全部处理，避免旧的跳变过滤丢弃加速输入。

反馈通过单独的 MIDI 输出句柄发送，不替换用户选择的常规 MIDI 输出，也不重复打开 MIDI 输入。只在选中的输入和匹配输出均为 mk3 时启用映射。主线程每秒检查一次设备连接、最多每秒更新十次反馈，只发送改变的内容。没有设备或关闭反馈时保持原有 MIDI 学习行为。

这套 DAW 固定映射使用控制通道，不受演奏输入通道过滤。要自定义这些旋钮／Pad 的 MIDI 学习映射，先关闭此页的 Arturia 适配。

## Ableton Live

需要 Live **11.3.3 或更新版本**，并包含官方 `KeyLab_Essential_mk3` 脚本。本次使用本机 Live 12.4.3 核对接口。

源码安装：

```sh
python3 tools/install_ableton_controller.py
```

使用内置资源里的 `ableton` 文件夹：将 `Krose_KeyLab_Essential` 文件夹复制到 **User Library / Remote Scripts**，将 `Defaults` 合并到 **User Library / Defaults**。已有自定义参数配置时，推荐用安装脚本保留并补全配置。不需要修改 Live 的应用目录。安装后重启 Live。

在 Live 的 Tempo & MIDI 设置中：

- Control Surface 选择 **Krose_KeyLab_Essential**。
- Input 和 Output 都选择 **KL Essential 49 mk3 (MIDI)**。
- 同一对端口仅配置一个控制表面，移除原 `KeyLab_Essential_mk3` 的重复端口配置。
- 不为此适配启用 ALV、MCU/HUI 或 DINTHRU。

安装时同时写入 Krose 专用的 `Default.appc`，新建 VST3 实例会自动暴露所需的 **53 个参数**，包括 AMP／FILTER 的 `EG Target` 和四键入口 `FX Edit`，无需逐项 Configure。配置只记录参数 ID 和排列，不包含音色值，也不修改其他插件的全局设置。原有参数 ID 保持不变，新项追加为 ID 194、195。

厂商目录使用 `Defaults/Plug-In Configurations/VST3s/maincore/Krose`。安装脚本会沿用旧 `Local Instruments/Krose` 目录中的自定义配置；新目录已存在时优先保留新配置，旧文件不删除。插件 ID 保持不变，旧工程可继续加载。

安装脚本保留已有参数布局、名称和 MPE 设置，只补上缺失参数；修改前会备份至 **User Library / Krose Controller Backups**。旧工程可能保留自身的参数配置，若屏幕显示 `Krose / Configure in Live`，需为该旧实例补上 Program 及缺失参数。已配置参数的增删会自动重新绑定。

首次需在 Live 中选择一次控制脚本和 MIDI 端口；以后同名端口重新接入会自动恢复反馈。脚本不与官方 Arturia 控制表面重复自动注册。

选中 Krose 时控制当前实例。选中其他设备、删除实例或切换轨道后，恢复官方脚本的控制。播放、停止、录音、循环、节拍器、Undo／Redo 等继续由官方组件处理。Krose 接管期间，大滚轮上方四个按钮用于 FX 编辑入口，不再承担 Arm／轨道切换。

VST3 不直接打开键盘端口。Live 脚本统一发送屏幕和灯光反馈，多个 Krose 实例不会争用硬件。Krose 接管期间同时屏蔽官方脚本的旋钮位置回传。

## FL Studio

使用 MIDI 脚本 API 26 或更新版本。先在 FL Studio 的 File settings 查看 **User data folder**，把完整的 `Resources/Controllers/fl-studio/Krose_KeyLab_Essential` 复制到该目录的 `Settings/Hardware`。从源码取用时，先运行 `python3 tools/build_controller_resources.py build/controller-kit/Controllers`，复制生成目录里的同名文件夹。

1. 键盘按 **Prog** 进入 **DAW** 程序。
2. 打开 **Options → MIDI settings**，为 KeyLab Essential mk3 的 **MIDI** 输入选择 **Krose KeyLab Essential mk3 (user)** 并启用。给同名 **MIDI** 输出分配与输入相同的空闲端口号。
3. 在 Channel Rack 加载并选中 Krose VST3。脚本按参数名称绑定，无需逐项设置 MultiLink。音符、力度、弯音、调制轮和踏板沿用 FL Studio 的演奏路由。ALV、MCU/HUI 和 DIN THRU 无需用于这套配置。

旋钮、推子、Pads 和四个 FX 键复用下方的映射；屏幕显示音色、分类图标和参数数值。切换 Channel Rack 的选择即可控制另一实例。播放、停止、录音、Tap、循环录音和节拍器由脚本交给 FL Studio。要用 Arturia 原厂脚本的混音器和浏览器页面，可在 Controller type 切回原厂脚本。

目前已验证脚本的宿主接口调用、MIDI 处理和打包。FL Studio 实机和实体键盘组合待验证。端口配对与脚本目录参见 [Arturia 的 FL Studio 设置](https://support.arturia.com/hc/en-us/articles/8905862388508-KeyLab-Essential-mk3-DAW-Integration) 和 [Image-Line MIDI Scripting](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm)。

## 默认映射

| 硬件 | Krose |
|---|---|
| 旋钮 1–6 | Glide、Filter EG Int（滤波包络强度）、Pan、Cutoff、Resonance、Velocity；按左侧矩阵从左到右、从上到下 |
| 旋钮 7 | Volume（Output），对应软件右侧音量旋钮；显示 Volume 和 dB 数值 |
| 旋钮 8–9 | 未分配，显示 Unassigned／--；不改动 FX 参数 |
| 推子 1–4 | 跟随界面 AMP／FILTER 选择的 Attack、Decay、Sustain、Release |
| 推子 5–8 | 另一组包络的 Attack、Decay、Sustain、Release |
| 推子 9 | Output |
| 中央编码器 | 按原厂目录顺序切换音色 |
| 大滚轮上方四键，从左至右 | IFX1、IFX2、MFX1、MFX2；短按松开进入对应 LCD 编辑页，长按约 0.6 秒切换该槽开关 |
| Bank A Pad 1–2 | ARP、Latch |
| Bank A Pad 3–6 | 四个 FX 槽开关 |
| Bank A Pad 7–8 | SW1、SW2，遵循 Toggle／Momentary 设置 |

点击 AMP／FILTER 后，推子目标、键盘弹窗名称和数值同步切换；两组包络推子重新拾取，音量推子的接管状态保留。选择属于实例的控制状态，随宿主工程保存，不被音色切换、音色文件或 Compare 覆盖。独立版和 Live 使用相同的顺序；旧 Live 实例若没有暴露 `EG Target`，会保留 AMP 顺序，需将该参数补入旧实例的 Configure 列表。

四个 FX 入口键的 RGB 灯随实际算法变化：EQ 蓝、Graphic EQ 青蓝、Compressor 橙、Limiter 黄、Drive 红、Exciter 玫红、Phaser 紫、Tremolo 绿、Auto Pan 青绿、Chorus 靛蓝、Delay 青、Hall 淡紫、Plate 粉。AUTO 按实际解析出的算法显示；空槽、OFF、槽位关闭或全局 Bypass 熄灯，发送量为零仍保留开关状态。屏幕显示实际 IFX／MFX 槽名和效果名称，使用 SFX 图标。重复按同一键可以重新打开该页；从旧工程恢复时不执行旧的编辑请求。旧 Live 实例需要暴露 `FX Edit` 才能使用四键入口，新实例自动配置。失去实例控制权或断连时清理这四个灯，恢复官方脚本的上下文按钮行为。

长按达到阈值时只切换一次，继续按住或松开不会再触发短按；空槽和 OFF 算法不会被长按自动添加。切换 Program、实例、断连或音频流重启会取消尚未完成的按压。独立版在音频线程使用采样时钟和固定状态表处理长按，不依赖界面帧率；Live 使用控制脚本的单调时钟。

按本机实体编号，Pad 1–4 对应音高 40–43，Pad 5–8 对应 36–39；灯光地址使用相同的两排转换。灯反映软件状态；FX Off、Bypass 熄灯；发送量／Wet-Dry 为零时仍反映槽位开关，软件提示 DRY。独立版断连及 Live 实例失去控制权时释放本次适配按住的瞬时 SW。实体 ARP 按钮控制键盘内置琶音器，软件 ARP 使用 Pad 1；两者可独立开关。

## 实时演奏与八度

LCD `>CTRL → UI → UI SIZE` 控制界面大小，提供自动适应和 60–150% 的固定比例，并保存选择。它与音频缓冲独立，不随音色或 MIDI 配置切换。

独立版在 LCD `>CTRL → INPUT → BUFFER` 直接选择 32–8192 样本，显示驱动实际接受的大小和每块毫秒数，并保存到独立版设置；设备拒绝时恢复原值。128 可作为低延迟演奏的起点；较重的复音／效果或较慢的声卡可增加到 256。也可按 `⌘ ,` 使用系统音频设置。插件版显示 HOST／DAW 及宿主最大处理块，实际缓冲在宿主设置；它不属于音色或 MIDI 映射。驱动和输出设备还会增加延迟，缓冲块时长不等于端到端延迟。CoreMIDI 同包多个音符的重复间隔不会累加到未来，避免和弦被人为拆开排队。

本机实物 KeyLab Essential 49 mk3 按 OCT± 时，四个端口未收到八度状态通知，只收到移调后的普通音符。当前软件 OCT 表示屏幕键盘的显示范围，无法精确镜像硬件的八度档位；音符高亮按收到的实际音高处理，声音不再额外移调。

## 验证范围

- 用户已实物确认四键的不同灯色及进入对应编辑页；新增长按行为已通过软件时序测试，实物手感待复测。
- 2026-11-09：用户在新版独立版上确认连续旋转／快速推拉恢复正常，屏幕跳 DAW 与转动中断已消失。右侧控件映射仍在重新核对，这次反馈不代表全部分配已验收。
- 原生协议、ASCII 边界、错误型号／端口隔离、推子拾取、反馈节流、重复帧抑制、重连快照：自动测试。
- Live 桥接的音色顺序、多实例切换、参数变化、灯状态、拾取及安装备份：软件测试。
- macOS 独立版已通过 CoreMIDI 虚拟 mk3 验证音色、Cutoff 数值、ARP 状态灯的实际收发；原有回归 29 项通过。
- Live 12.4.3 + 本机 VST3 0.4.0 + CoreMIDI 虚拟 mk3：两个新实例均自动显示 51 个参数；音色切换遵循原厂目录；硬件消息修改参数、软件修改回传屏幕数值、ARP 与 Pad 灯同步均通过。后续已移除旋钮位置回传。
- Live 实例切换后只控制当前目标，推子拾取通过；瞬时 SW 在切走或拔线时释放。重新创建同名虚拟端口后，无需重选端口即可恢复屏幕和 Pad 状态。
- 切到普通音轨后恢复官方控制；播放／停止有效。普通 MIDI 和弦经已武装的 Krose 轨道输出到 Main，实测峰值 −28.4 dB。控制目标跟随设备焦点，音符路由遵循 Live 的轨道武装／监听设置。
- 保存验收工程、退出并重开 Live 后，两个实例的音色、参数和 SW 模式保留；当前自动化测试包含 24 项 Python 控制器测试及 VST3 参数配置核验。后续的图标布局、六旋钮顺序、两排 Pad 编号、音色名单行滚动、快速推子拾取及停用旋钮回传已通过软件测试；Volume 分配及未分配旋钮的字段仍需实物确认。
- 实物键盘已接入并核对端口及八度按键的原始消息；屏幕排版、亮度及固件差异尚未由用户验收。Windows 代码路径复用 RtMidi，当前未进行 Windows 设备实测。

## 协议依据

采用本机官方 Live `KeyLab_Essential_mk3` 的协议常量和公开的设备行为，代码独立编写，未复制或分发厂商脚本。

- [Arturia mk3 端口说明](https://support.arturia.com/hc/en-us/articles/8841900354076-KeyLab-Essential-mk3-General-Questions)
- [Arturia 官方 Ableton 设置](https://support.arturia.com/hc/en-us/articles/8905862388508-KeyLab-Essential-mk3-DAW-Integration)
- [Ableton 第三方脚本安装](https://help.ableton.com/hc/en-us/articles/209072009-Installing-third-party-remote-scripts)
- [Ableton 保存插件参数配置](https://help.ableton.com/hc/en-us/articles/209073089-Saving-plug-in-parameter-configurations)
- [mk3 SysEx 研究笔记](https://github.com/PrzemekBarski/arturia-keylab-essential-mk3-programming-guide)

第三方脚本的安装目录遵循 [Ableton 官方说明](https://help.ableton.com/hc/en-us/articles/209072009-Installing-third-party-remote-scripts)。

设置页按用途分开：INPUT 管理输入通道、时钟和映射配置；AUDIO 显示采样率并设置独立版缓冲（插件由宿主管理）；UI 管理窗口比例。左侧 EG INT 旋钮引出固件原有滤波包络强度，提供 −99 至 +99 的偏移；0 保留音色原值，Arturia 第二个编码器同步控制它。它控制包络作用的深度，右侧四推子控制时间和持续电平；音色仍通过预设列表及前后按钮切换。

### 独立版设备设置

Windows 保留系统标题栏，移除 File / Help 菜单栏。LCD `CTRL > AUDIO` 可选择音频驱动、输出设备、采样率、缓冲，并打开 ASIO 驱动面板；`CTRL > INPUT` 可选择 MIDI 输入和输出，`CTRL > UI` 管理窗口比例。Windows 系统音频使用 WASAPI，原有 ASIO 选择继续保留。显示的毫秒数是单个处理块的时长，不代表声卡的完整往返延迟。

MIDI 输入选 Automatic 时，断开设备会选择可用的演奏输入；没有输入时置空并清理挂音。显式选择的设备缺失时保留偏好，暂用可用输入，设备重连后再恢复。设备恢复和驱动重启在主线程处理，音频流未准备好期间输出静音。

LCD `CTRL > INFO` 显示插件版本和构建时间（UTC）。时间在构建时写入，独立版与 VST3 共用同一份构建信息。

INFO 页的 `CHECK UPDATES` 开关控制自动更新检测，默认开启并保存为本机偏好。检测到更新的正式版本时显示 GitHub 更新入口；关闭后停止自动检测。应用只提示更新，不自动下载安装。
