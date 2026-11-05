# 使用与构建

Krose 提供 VST3 和独立程序，使用固定尺寸的原生界面。目录包含 768 个出厂、265 个 GM、128 个扩展 Program，以及 Concert 兼容入口，共 1,162 项。分类与浏览顺序来自原厂目录，宿主 Program 编号固定。

## 演奏

- PRESET 按大类展开音色列表；BROWSE 支持名称／编号、音色库和类型筛选。爱心加入 Favorites。
- VOLUME、PAN、CUTOFF、RESONANCE、VELOCITY 调整当前演奏；AMP／FILTER 推子分别保存包络偏移，零位保留原值。
- POLY、MONO、LEGATO 和 GLIDE 的规则见 [演奏模式](PERFORMANCE.md)。ARP、Latch、时钟及 Pattern 见 [琶音器](ARPEGGIATOR.md)。
- 支持延音、音量、表情、柔音、弯音及 MIDI 控制器复位。屏幕键盘用于试音，PANIC 清理按键、声部和事件。
- 切换音色时后台加载所需采样；加载期间旧音色继续演奏，原有尾音保留。界面显示 LOADING 或 LOAD FAILED。
- FX 收放只改变编辑器显示，不修改音频、参数或旁通。SW1／SW2 的分配、MIDI 学习和输入设置均在 LCD 的 CTRL 入口；操作见 [MIDI 控制](MIDI.md)。屏幕 Mod、Save/Compare 和完整效果编辑目前禁用。

独立程序的 Audio and MIDI Settings 用于选择声卡、缓冲、采样率与 MIDI 输入；VST3 使用宿主设置。支持 32–192 kHz。宿主参数按音频块读取并平滑；MIDI 音符与映射参数在事件的采样位置应用。

独立程序将设备回调按不超过 128 帧分段，末段使用实际帧数，支持小缓冲及非整倍数长度。MIDI 以单调时钟对齐 RtMidi 源时间间隔，再映射到音频块内偏移；重开音频流时丢弃旧流事件并重新准备音源。输入队列溢出会释放踏板和全部声音，避免丢失 Note Off 后卡音。

设备断连或回调停滞后，由主线程定时重试打开；首选设备暂不可用时使用系统默认输出，设备回来后恢复首选项。临时回退不覆盖保存的设备或采样率偏好。关流等待有超时，避免驱动停止回调后挂住退出。物理设备拔插、睡眠唤醒及 Windows 驱动仍需目标环境验收。

MIDI 输入设备消失时清理排队事件并释放踏板／声音，保留所选设备名称，重连后自动重新打开；关闭输入或使用虚拟端口时不进行物理端口重连。

## 从源码构建

需要 CMake 3.25+、Ninja、平台编译工具链及本地冻结采样。依赖版本固定在 `cmake/dependencies.json`，大型 `.samples` 不纳入 Git。

```sh
python3 tools/bootstrap_plugin.py
cmake --preset plugin
cmake --build --preset plugin
ctest --preset plugin
```

生成的 app 和 VST3 位于 `build/plugin/out/`。纯核心构建使用 `engine` 预设；ASan／UBSan 使用 `sanitize`。原生交互检查：

```sh
build/plugin/test-vst3-host build/plugin/out/Krose.vst3 --editor-only
python3 tests/tools/test_runtime_assets.py
```

构建过程不运行研究代码。资源、采样加载及当前声音边界见 [架构](ARCHITECTURE.md)与[采样存储](SAMPLES.md)；发行流程见 [RELEASE.md](RELEASE.md)。
