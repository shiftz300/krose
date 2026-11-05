# 完成度复查 · 2026-11-06

复查范围为 Krose 0.3.0，涵盖四槽 FX、应用图标和平台打包资源。图标源与预编译流程见 `362977d`，生成的图标资源随 0.3.0 源码交付。

## 已接通

- 1,162 个可选入口，原厂分类顺序、搜索、收藏、后台按需加载与进程内共享采样。
- 原生界面、宿主工程保存、演奏模式、五种内置 ARP、SW 分配及通用 MIDI 学习。
- 四个 FX 参数页：两路串联 IFX、两路并联 MFX，独立类型、开关、效果量和算法细节；九种算法图案、关闭灰显、空槽菱形入口。
- 应用图标：粗体罗马衬线 K，填充暖色大理石纹理。macOS ICNS／plist、Windows EXE／窗口、NSIS 安装与卸载入口均已配置。
- 系统外观：六种外观通过 Apple 渲染器验证；专用 CI 首次预编译成功，1,799,544 字节的 `Assets.car` 已装入本地应用。NSWorkspace 从实际 bundle 读取到深色黑底 K，应用启动正常；其余外观目前以官方渲染器预览为证据。

## 还没做完

| 优先级 | 缺项 | 当前影响与证据 |
| --- | --- | --- |
| 优先补齐 | Save／Compare | 面板按钮禁用，尚无用户音色文件保存和编辑前后比较流程；宿主工程保存正常。见 `NativePanel.cpp`。 |
| 优先补齐 | 屏幕 Mod 滚轮 | 只画了标针，未注册拖动命中区域；外接 MIDI CC1 已接入。见 `NativePanel.cpp`。 |
| 优先补齐 | 新 FX 参数的内置 MIDI 学习 | 映射目标仍限于原有 39 参数和既有动作；新 FX 可用宿主自动化，尚不能直接右键学习。见 `Parameters.h`、`PanelInput.cpp`、`PanelControllers.cpp`。 |
| 还原范围 | 原厂 FX 配置与算法 | 当前九类主机 DSP、四槽简化路由可编辑；原机完整算法、各音色完整效果路由尚未复刻。AUTO 保留当前 Krose 默认声音。见 [效果链](NATIVE_UI.md#lcd-效果链)。 |
| 还原范围 | 用户琶音与原 Program ARP 设置 | 五种内置 Pattern 可用；1,280 条用户 Pattern、双 ARP A/B、原 Program 自动分配、独立键区／力度区等未接通。见 [琶音器](ARPEGGIATOR.md)。 |
| 还原范围 | 演奏与调制细节 | OSC 独立滑音、Fingered、Offset Legato、Unison、公共 LFO、部分 Tone Adjust／Part 屏蔽位仍有缺口；滤波 Hz/Q 和 TG 响应采用主机实现。见 [演奏模式](PERFORMANCE.md)、[调制链路](MODULATION.md)。 |
| 资源缺口 | Electric Beats Kit 部分层 | EXPCM004:043 的 MIDI 45 第二层、83 第一层、96 两层缺逻辑 bank 6；其他已有层继续播放。原厂鼓 start-offset 也仍有未接入部分。见 [架构](ARCHITECTURE.md)。 |

Pad／鼓轨界面已按设计范围移除，不列为待补功能。鼓组 Program 的采样完整度仍需单独跟进。

## 尚需目标环境验收

- 本轮 Windows 图标的 Explorer／任务栏显示及 NSIS 安装卸载，须用新代码在 Windows 构建运行；本地 macOS 通过不代替 Windows 验收。
- Windows 不同 DPI、实体控制键盘、真实 DAW 多实例长时间运行、设备热插拔和睡眠唤醒。
- 与实琴／原 CD 的听音对照不能由单元测试替代；目前不宣称完整硬件音频等效。
- macOS 使用 ad-hoc 签名，安装包未公证。Windows 安装包尚未使用 Authenticode 签名。发行流程见 [发行说明](RELEASE.md)。

## 本轮检查

Release／LTO／PGO 本地构建通过；18 项 CTest 全部通过。免安装打包、Universal 合并和资源归档的 13 项 Python 回归通过。macOS bundle 的图标引用、图标字节、ICNS／ICO 各尺寸及代码签名已核对。独立程序以 `--no-io --screenshot` 成功启动并截取完整界面；更新后的免安装 ZIP 包含同一图标。此启动检查不打开音频设备。

同时纠正文档中“完整效果编辑禁用”“当前只有 39 个工程参数”及旧 WebView 验收路径的过时表述。
