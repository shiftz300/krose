# 产品回归测试

这里存放引擎、控制模型、效果核心和 VST3 测试的 C/C++ 源码。`fixtures/concert-se-grand/` 保存原 ARM 生成的独立期望结果与哈希清单；正常测试不加载固件、不执行 Unicorn。

`core/` 验证音频核心；`ui/` 验证无宿主的图像内存和动画；`plugin/` 验证 VST3 与 Cocoa；`tools/` 验证资源归档、PGO 构建配置和 Universal 合并。夹具按原有来源分组。详见 [模块边界](../docs/PROJECT_LAYOUT.md)。

`core/test_midi_queue.cpp` 检查相同时间戳的稳定顺序、块边界、跨块偏移、数据规范化与容量溢出。归档工具测试单独运行：`python3 tests/tools/test_runtime_assets.py`，不要求安装插件或下载采样。

`python3 -B tests/tools/test_pgo_configuration.py` 检查 Release 默认训练、退出开关、Debug／Sanitizer、缺失工具及多架构保护，并实际构建多配置 Debug，确认不运行或构建训练程序。`python3 -B tests/tools/test_macos_merge.py` 检查原生切片、资源和版本一致性；两者均不读取完整采样。

`test_program_engine.cpp` 覆盖共享库、原参数选样、双 OSC、两套鼓组、块划分一致、原 Concert 输出一致及实时零分配；编译后 VST3 测试另覆盖所有新 Program 的发声和状态保存。

完整库测试读取 `fixtures/full-programs/` 中冻结的原 CPU 观察数据，覆盖 8,900 条声部记录和 8,944 个选样场景。`program-engine` 与编译后的 `vst3-host` 均逐项渲染 1,161 个原始音色；后者还检查每项的工程状态恢复。`--editor` 验证 1,162 项目录、按编号搜索末项、选择后向宿主回写及窗口重开。

`test_performance.cpp` 对照 `fixtures/performance/` 的原 ARM 按键／滑音记录，并验证两套引擎的单音重触发、连奏保留采样与包络、三种采样率、块划分一致、重复音、分通道踏板、换音色、Panic 和零音频线程分配。VST3 测试覆盖 6／17 参数状态迁移、19 参数往返；原生 Cocoa 检查模式按钮与 Glide 回写及重开回读。

`test_arpeggiator.cpp` 对照 9,600 个原生成音符和五条连续事件轨迹，覆盖采样级排程、宿主时钟、Latch/踏板、停止与两套音源。`--editor-only` 可快速复核状态、宿主 ARP 和原生 Cocoa 界面，明确跳过完整音色渲染；完整交付执行常规 CTest 与原生交互检查。`KROSE_UI_REFERENCE` 指定实际 Metal 帧缓冲的导出目录。

`test_sample_loading.cpp` 对比全库与按需加载的输出，覆盖旧声部持有采样、取消加载、暂停宿主反复选音色、文件读取失败、离线等待，以及实时线程零分配／释放。另验证大块匿名内存的解码边界与移动所有权；可单独启用 ThreadSanitizer。

`test_effects.cpp` 对比共享干声 EQ 与独立效果处理，在五种采样率、奇数块长和自动化下检查逐样本相等、尾音与缓冲区边界。采样格式和生命周期见 [采样存储](../docs/SAMPLES.md)。

`modulation` 对照冻结的原 ARM LFO、Pitch EG、AMS Mixer、双 LFO 交叉调制及音高／滤波目标结果，并检查动态控制值与四种滤波连接。夹具来源、原实验输入和未接通项见 [调制链路](../docs/MODULATION.md)。`program-engine` 另按实际音色选取各 LFO 类型，在六种采样率、多种分块和跨通道控制事件下检查输出一致及实时零分配。
## 独立程序与界面绑定回归

`standalone` 直接编译产品使用的回调／恢复适配实现，使用设备替身检查 1–1025 帧输出边界、无设备、重试、采样率回退、首选设备重连及有界关流。`midi-timing` 检查源时间间隔、跨分段／跨回调偏移、重启代际、溢出清音和生产者／消费者并发，可独立使用 ASan／UBSan／TSan。`parameter-binding` 检查值量化、无变化写入、手势配对及宿主状态回写。

原生 Cocoa 测试另通过 VST3 `IComponentHandler` 验证实际 UI 的 begin／perform／end 配对，并检查窗口打开时的宿主更新成为下一次拖动的起点。设备替身回归不等同于物理声卡拔插或睡眠唤醒验收。
