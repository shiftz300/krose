# MIDI 控制与 LCD 设置

点击 LCD 的 `>CTRL` 进入设置；`< PROG` 返回。原有音色／音色编辑／效果／琶音页面保留，整机控件位置保持原样。

## 最短操作路径

1. 右键旋钮或推子，直接打开 MIDI 页并开始学习该目标。
2. 移动键盘上的一个旋钮、推子或按钮。首条消息只建立绑定，随后操作才改变参数。
3. 绝对值控制默认启用 PICKUP：推子经过当前值后接管，避免参数跳变。相对编码器选择匹配硬件设置的 REL 模式。
4. 工程会保存映射。要在其他工程使用，进入 INPUT，点击 STORE 保存到当前 USER 配置。

学习期间可点 CANCEL 或按 Esc；再次按 Esc 返回音色页。通过 MIDI 页的目标框也能选择参数、NEXT PRESET、PREV PRESET 或 PANIC。学习同一物理消息会替换旧绑定；手动编辑可建立一对多绑定。64 个槽位足以覆盖 KeyLab Essential 的 9 旋钮、9 推子和 8 个 Pad，音符键、踏板、弯音仍走通常的 MIDI 输入。

## SW1／SW2

CTRL 页选择功能和 Toggle／Momentary，右侧 TEST 可直接试听；面板的 1／2 按钮执行相同操作。Momentary 在松开鼠标、按键或关闭编辑器时释放。MAP SW1／SW2 可把任意支持的 MIDI 控制器绑定到开关状态。

| 分配 | 行为 |
| --- | --- |
| Off | 保留按钮状态，不修改演奏 |
| Mod CC | SW1 发送 CC80，SW2 发送 CC81；声音变化取决于 Program 的 AMS 分配 |
| Portamento | CC65 控制滑音，时间使用 GLIDE；GLIDE 为零时使用中值 64 |
| Octave Down／Up | 后续 Note On 移调一个八度；已按下的音符仍按原音高关闭 |
| Pitch Lock | 冻结当前弯音，解锁时恢复最后收到的轮位置 |
| Arp／Latch／Sustain | 控制琶音开关、保持或延音 |
| Mono／Legato | 在 MONO 与 LEGATO 间切换 |
| FX Bypass | 平滑切换效果旁通，保留效果尾音状态供重新启用 |

SW 为全局控制；普通输入的踏板、弯音和 AMS CC 仍按各自 MIDI 通道处理。两只 SW 分配相同功能时以任一处于 ON 为激活条件。旁通继续计算效果，以避免重新打开时截断尾音。

## 映射选项

- 来源：CC、成对 CC 14 bit、NRPN、RPN、Note、Pitch Bend、通道压力、复音压力。选择来源后点 LEARN 可限定学习类型；右键进入学习时自动识别普通消息。
- 通道：OMNI 或 1–16；号码对应 CC、Note 或参数编号。CC 14 bit 使用 MSB 的 0–31，NRPN／RPN 使用 0–16383。
- 模式：ABSOLUTE、二补码相对值、64 为中心的相对值、符号位相对值、TOGGLE、MOMENTARY。没有可靠的跨品牌自动识别规则，模式需要与键盘的输出设置一致。
- PICKUP 只用于绝对值；THRU 决定消息是否继续进入音源；INVERT 反转数值或按钮电平。CC120／121／123 始终继续传递。
- 改掉或清除正在按下的瞬时绑定时，音频线程会释放原目标；映射吞掉 Note Off 时也会补发已进入音源的关音，防止卡音。

默认 CC：10 PAN、71 RESONANCE、74 CUTOFF、73 AMP ATTACK、75 DECAY、70 SUSTAIN、72 RELEASE、91 SPACE。默认映射启用 PICKUP 并消费消息。原有 CC1、7、11、64、65、67、80／81、弯音及压力仍可直接演奏；CC80／81 对声音的作用由音色 AMS 决定，控制面板 SW 状态需显式学习。

## 输入与宿主

INPUT CH 对演奏和映射共同生效，改通道时清理旧声部。VST3 向宿主开放全部 16 通道 CC／弯音／通道压力，同一音频块内的多次编码器步进和按钮边沿逐条保留；键盘连接和端口选择由 DAW 管理。时钟使用宿主或内部；VST3 的标准输入路径没有原始 F8 时钟和 Program Change，界面相应显示 `PGM: HOST / DAW`，不提供不可用的外部时钟选项。

独立版支持原始 Program Change 与 F8／Start／Continue／Stop／Song Position：

- Krose Index：`(MSB × 128 + LSB) × 128 + PC` 对应固定宿主索引，越界忽略。
- Catalog Banks：LSB 为 0；MSB 0–5 对应 A–F，6 对应 GM 主表，7／8／9 对应 EXPCM001／002／004；PC 从 0 开始。此为插件的目录选择约定，不代表原琴 MIDI Implementation 的银行协议；GM 变体仍可通过 Krose Index 选择。
- MIDI Clock：在 ARP 页顶部速度栏开关同步；24 PPQN，支持只发 Clock 的键盘；收到 Stop 后后续 Clock 不会自行重新启动。时钟超时暂停琶音器；内部速度值作为尚未测出速度时的回退。

键盘内部的和弦、音阶、琶音功能，只要输出普通 MIDI 音符就可以使用。MCU／HUI 和 DAW 运输控制由宿主管理。KeyLab Essential mk3 的屏幕、编码器和 Pad 反馈由独立版适配器或专用 Live 脚本提供，见 [控制器适配](CONTROLLERS.md)；实物键盘兼容性待验收。

## 保存与实现

工程状态保存当前全部参数（含 FX）及带版本的 64 槽映射；旧版 6／17／19／29／39／47 参数状态可读取，原有参数 ID 0–38 保持固定。工厂音色预设只包含声音参数，不覆盖输入配置或 MIDI 映射；瞬时 SW 不保存按下状态。

内置 MIDI 学习覆盖当前全部参数，包括新增 FX 类型、效果量、单槽开关和算法细节。右键旋钮、推子或 LCD 参数即可学习。旧目标 0–38、Next／Previous／Panic 的编码保持不变，新增参数目标追加在动作之后；宿主参数 ID 不变。

4 个 USER 配置位于应用支持目录 `Krose/midi-mappings.json`。STORE 显式写入，采用临时文件替换；写入失败显示提示。切换配置、恢复 STANDARD CC 或清空全部映射会保护未保存修改。工程保存与 USER 文件相互独立，载入工程不会覆盖 USER 文件。

`src/plugin/midi/ControllerMap.h` 使用固定容量和整条原子记录；音频线程不解析 JSON、不访问磁盘、不为映射分配内存。`ControllerInput.cpp` 在事件采样位置应用输入，宿主通知延后到主线程；`ControllerState.cpp` 负责工程兼容与 USER 文件。原生交互、状态往返、跨通道、映射并发及零分配均有自动测试；实物键盘、Windows GUI 和 DAW 长时间演奏仍需目标环境验收。

## 设备与显示同步

独立程序默认 Automatic 输入，优先演奏端口并避开同设备 DAW／MCU 控制端；连接、断开和重连由主线程轮询，设置下拉列表同步刷新。显式选择的设备暂时消失时保留偏好，临时使用可用输入，返回后恢复；Off 保持显式关闭。

宿主／独立版输入会更新面板按键、弯音、Mod、延音及映射参数。输入通道过滤和 SW 移调先执行，再发布实际送往音源的状态；按键按通道计数，避免一个通道的 Note Off 熄灭另一个通道的同音。CC120／123／121、踏板与 Panic 分别保留正确的清理规则。UI 只读取每块发布的无锁快照。

新增 ARP Swing／Velocity／Keyboard 参数追加在原 FX 参数之后，不移动旧宿主参数及 MIDI 动作目标。`.krose` 格式 3 可读取旧文件，并通过物理单位迁移旧 FX 范围、Pattern 与 Gate 归一化值；旧工程的直接参数值和已编辑 FX／ARP 不被工厂默认值覆盖。
