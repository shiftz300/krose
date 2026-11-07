# 琶音器：原厂 Pattern、编辑与宿主时钟

ARP 已进入原生音频路径，关闭编辑器后继续运行。Concert 与完整 Program 引擎共用同一个事件发生器，面板布局保持不变，编辑项放在 LCD 的 ARP 页。

## 当前功能

| 控件 | 行为 |
| --- | --- |
| ARP | 开关琶音；切换时停止旧声音并清空按键，需要重新按键 |
| LATCH | 松键后继续；新按键先清理已松开的旧键，仍按住的键保留 |
| Pattern | 五种内置生成器，以及原厂 1,280 条 Pattern；按原编号保存，菜单按名称前缀分类 |
| Resolution | 1/32T、1/32、1/16T、1/16、1/8T、1/8、1/4T、1/4 |
| Gate | 1–100%，另有 STEP 档沿用每步 Gate；原厂步骤支持休止和连音 |
| Octave | 1–4 个八度，高于 MIDI 127 的音按八度折回 |
| Sort | 开启按音高排列，关闭按触键顺序排列 |
| Key Sync | 开启时首个按键立即起奏；关闭时等待当前时钟的下一个步进网格 |
| HOST / INT | 有效宿主音乐时钟优先；关闭 HOST 或无有效宿主时钟时使用内部速度 |
| Tempo | 内部速度 20–300 BPM；LCD 顶行显示当前实际速度 |
| Swing | 内置五种生成器忽略 Swing；用户 Pattern 按原 ×1／×2／×4 分组偏移 |

ALT 1 折返时不重复端点，ALT 2 重复端点。每个 MIDI 通道各自保存最多 128 个唯一按键及力度；重复触键更新力度，数量不增加。RANDOM 使用原 16 位反馈移位序列，通道按编号共享该状态，Panic／重新准备／开关 ARP 时从种子 1 重置。

CC64 在 ARP 开启时保持源按键，避免把每个生成音都积成持续音。松踏板时移除已松开的键；Latch 开启时仍保持。CC120、CC123 清理该通道的按键与生成音，CC121 释放踏板并复位原有 MIDI 控制器。关闭 Latch 会移除未被踏板保持的已松开键。

选择 Program 会载入其 Pattern、开关、Latch、Resolution、Gate、力度、八度、Sort、Key Sync、Swing 和 Keyboard 直通设置，保留全局时钟来源。LCD 的 EDIT 菜单可选择模式、恢复当前 Program 的琶音设置或切换 Keyboard 直通。保存的 `.krose`／宿主工程保留用户修改，不在恢复时重置。换音色时清理琶音和旧声部。切换 Pattern、Resolution、Octave、Sort、Key Sync 或时钟来源时关闭当前生成音并重新排程，保持按键集合。ARP 生成的音符进入插件音源，当前不向宿主导出 MIDI。

## 时钟与实时处理

VST3 使用 iPlug2 提供的有效音乐位置、Tempo 和播放状态。播放停止时关闭生成音；恢复播放、跳转或循环回跳时重新排程。Key Sync 关闭时与宿主 PPQ 的步进网格对齐，支持负拍位置。正常变速保留以拍表示的步长和 Gate，下一次回调采用新速度。无音乐位置信息时回退到内部时钟；独立程序可在 LCD 的 INPUT 页选择内部或外部 MIDI Clock，详见 [MIDI 控制](MIDI.md)。

事件在音频采样边界派发，先处理该时刻的输入，再处理生成的关音与起音。按键、通道和事件缓冲均为固定容量；大离线块在音源入口分段处理，防止生成事件填满音源队列。音频线程不执行 WebKit、文件访问或堆分配。实际速度通过原子值交给 UI 定时读取。

## 逆向来源与边界

五种生成器、排序、八度折回、触键力度、Resolution、Swing 忽略规则及 RANDOM 递推来自 [原琶音检查](https://github.com/shiftz300/krose-source/blob/main/research/docs/architecture/ARPEGGIATOR.md)。`tests/fixtures/arpeggiator/` 冻结了 200 组、9,600 个原音符及五条连续事件轨迹，来源指纹位于其 `manifest.json`。显式更新命令为 `python3 research/tools/export_arp_checks.py`，正常构建不加载固件。

内置生成器使用插件的采样时钟及 VST3 PPQ。首音、宿主网格、停播和跳转采用上面的插件规则；原 OS 调度及双琶音 A/B 同步未作为实机音频时序复现。已接入原 1,280 条 Pattern 的步骤、固定音高、Tone 映射、Flam、连音、力度及 Swing。十二组隔离原 ARM 输出共 318 个事件已与主机实现对照，覆盖五种采样率和三种块大小；全部 Pattern 另检查音符配平。扩展包可能引用 PRELOAD 中的空用户槽，缺少步骤时仅在自动载入阶段关闭琶音，保留音色可演奏性；手动选择初始化 Pattern 仍保持其空步骤。独立版的外部 MIDI Clock 已接入；Keyboard 直通已接入；独立键区、力度区、双琶音与全部动态调制仍留有差异。

## 状态与验证

ARP 宿主参数使用 ID 19–28，既有 0–18 保持。旧 6、17、19 参数工程迁移后 ARP 默认关闭；工程状态保存当前全部参数（含后续 FX 参数）及 MIDI 映射，旧 29／39／47 参数状态仍可读取。

原生测试覆盖原音符与事件、随机周期、八种 Resolution、三种采样率、非整数 BPM、Gate 边界、分块一致、Latch、踏板、通道隔离、128 键、开关及 Panic、宿主停播／恢复／跳转／变速和两套音源的零实时分配。编译后的 VST3 另验证实际 ProcessContext 下停播无起音、播放恢复发声。原生 Cocoa 测试检查 LCD 字段边界、参数回写和窗口重开。实际 DAW 长时演奏仍待手工验收。

Pattern 记录编译为共享只读数据，运行时不读取固件或逐实例解压。冻结数据与 SHA-256 位于 `assets/arpeggiator/`；原 ARM 事件位于 `tests/fixtures/arpeggiator/user-*.tsv`。
