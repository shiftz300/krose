# 产品回归测试

这里存放引擎、控制模型、效果核心和 VST3 测试的 C/C++ 源码。`fixtures/concert-se-grand/` 保存原 ARM 生成的独立期望结果与哈希清单；正常测试不加载固件、不执行 Unicorn。

`tools/` 中同名旧路径是指向本目录的相对符号链接，保留历史脚本和报告兼容性。请编辑本目录中的真实文件。详见 [研究与产品边界](../docs/PROJECT_LAYOUT.md)。

`test_program_engine.cpp` 覆盖共享库、原参数选样、双 OSC、两套鼓组、块划分一致、原 Concert 输出一致及实时零分配；编译后 VST3 测试另覆盖所有新 Program 的发声和状态保存。

完整库测试读取 `fixtures/full-programs/` 中冻结的原 CPU 观察数据，覆盖 8,900 条声部记录和 8,944 个选样场景。`program-engine` 与编译后的 `vst3-host` 均逐项渲染 1,161 个原始音色；后者还检查每项的工程状态恢复。`--editor` 验证 1,162 项目录、按编号搜索末项、选择后向宿主回写及窗口重开。

`test_performance.cpp` 对照 `fixtures/performance/` 的原 ARM 按键／滑音记录，并验证两套引擎的单音重触发、连奏保留采样与包络、三种采样率、块划分一致、重复音、分通道踏板、换音色、Panic 和零音频线程分配。VST3 测试覆盖 6／17 参数状态迁移、19 参数往返；原生 Cocoa 检查模式按钮与 Glide 回写及重开回读。

`test_arpeggiator.cpp` 对照 9,600 个原生成音符和五条连续事件轨迹，覆盖采样级排程、宿主时钟、Latch/踏板、停止与两套音源。`--editor-only` 可快速复核状态、宿主 ARP 和原生 Cocoa 界面，明确跳过完整音色渲染；完整交付执行常规 CTest 与原生交互检查。`KROSE_UI_REFERENCE` 指定实际 Metal 帧缓冲的导出目录。

`test_sample_loading.cpp` 对比全库与按需加载的输出，覆盖旧声部持有采样、取消加载、暂停宿主反复选音色、文件读取失败、离线等待，以及实时线程零分配／释放。另验证大块匿名内存的解码边界与移动所有权；可单独启用 ThreadSanitizer。

`test_effects.cpp` 对比共享干声 EQ 与独立效果处理，在五种采样率、奇数块长和自动化下检查逐样本相等、尾音与缓冲区边界。新旧算法独立基准及音频哈希见 [采样与效果优化](../docs/SAMPLE_LOADING.md)。
