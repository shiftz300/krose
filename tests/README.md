# 产品回归测试

这里存放引擎、控制模型、效果核心和 VST3 测试的 C/C++ 源码。`fixtures/concert-se-grand/` 保存原 ARM 生成的独立期望结果与哈希清单；正常测试不加载固件、不执行 Unicorn。

`tools/` 中同名旧路径是指向本目录的相对符号链接，保留历史脚本和报告兼容性。请编辑本目录中的真实文件。详见 [研究与产品边界](../docs/PROJECT_LAYOUT.md)。

`test_program_engine.cpp` 覆盖共享库、原参数选样、双 OSC、两套鼓组、块划分一致、原 Concert 输出一致及实时零分配；编译后 VST3 测试另覆盖所有新 Program 的发声和状态保存。

完整库测试读取 `fixtures/full-programs/` 中冻结的原 CPU 观察数据，覆盖 8,900 条声部记录和 8,944 个选样场景。`program-engine` 与编译后的 `vst3-host` 均逐项渲染 1,161 个原始音色；后者还检查每项的工程状态恢复。`--editor` 验证 1,162 项目录、按编号搜索末项、选择后向宿主回写及窗口重开。
