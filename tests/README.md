# 产品回归测试

这里存放引擎、控制模型、效果核心和 VST3 测试的 C/C++ 源码。`fixtures/concert-se-grand/` 保存原 ARM 生成的独立期望结果与哈希清单；正常测试不加载固件、不执行 Unicorn。

`tools/` 中同名旧路径是指向本目录的相对符号链接，保留历史脚本和报告兼容性。请编辑本目录中的真实文件。详见 [研究与产品边界](../docs/PROJECT_LAYOUT.md)。

`test_program_engine.cpp` 覆盖共享库、原参数选样、双 OSC、两套鼓组、块划分一致、原 Concert 输出一致及实时零分配；编译后 VST3 测试另覆盖所有新 Program 的发声和状态保存。
