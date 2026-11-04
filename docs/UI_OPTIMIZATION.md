# 分类、收藏与界面性能

后续已加入按音色加载，完整编辑器占用降至默认 Concert 约 341 MB、A000 约 278 MB。当前机制和实测见 [采样与效果优化](SAMPLE_LOADING.md)。下文保留第一阶段的完整采样常驻基线。

2026-11-04。PRESET 改为「原厂大类 → 音色」二级菜单，点击爱心加入 Favorites；收藏在编辑器重开后保留。浏览器同步提供爱心和收藏筛选。整机布局、材质和 LCD 像素样式保持。

## 测量结果

同一台 Apple Silicon Mac、同一原生 VST3 测试宿主、1472×648 逻辑尺寸及 2× 帧缓冲。基线源码为 `3a97a9a`。先加载完整采样，再打开编辑器，连续收放 FX 12 次，最后关闭编辑器。内存使用 macOS `task_vm_info.phys_footprint`；它包含当前进程计入的压缩内存等，不能用 RSS 替代，也不能直接套用到截图中的独立程序或其他 DAW。

| 项目 | 修改前 | 修改后 |
| --- | ---: | ---: |
| 打开编辑器后内存 | 1064 MB | 750 MB |
| 收放 FX 12 次后内存 | 1112 MB | 780 MB |
| 关闭编辑器后内存 | 794 MB | 605 MB |
| 动画绘制间隔中位数 | 33.01 ms | 16.64 ms |
| 动画绘制间隔 P95 | 37.36 ms | 18.63 ms |
| 每次绘制 CPU 用时中位数 | 1.85 ms | 0.36 ms |
| 字体解码图像大小 | 90.2 MiB | 6.65 MiB |

内存表用十进制 MB。打开界面后减少约 30%。帧间隔测量的是进入 Draw 的时间，CPU 用时排除 GPU 提交后的执行；这些结果不代表 DAW 端到端帧率。原始数字见 [测量文件](verification/native-ui/performance/)。

## 修改内容

- **字体与图片**：字体只去掉透明留白，保留每个字形的原始像素和位置；图集坐标按逻辑整数对齐，防止取样偏移。面板图片按使用加载。
- **动画**：复用 FX 离屏纹理，避免逐帧分配；刷新率由 30 Hz 调整为 60 Hz，动画直接跟随绘制时钟，更新最后一帧。
- **采样**：原来把全部 PCM24 展开成 float32，现在常驻保存原始三字节数据，读取时精确转换。Factory 采样从 512,779,708 字节降到 384,589,701 字节，包含每段一个越界保护字节。播放期间不读盘、不分配内存、不加锁；全部音色仍可即时切换。

采样转换增加少量 CPU 工作。64 声部、三组效果、128 帧、48 kHz 的本地 Concert 引擎对照中，单块中位用时从 213.7 µs 到 223.7 µs，约增加 5%；单块预算为 2666.7 µs。两次运行 P99 分别为 340.9 和 245.4 µs，受系统调度影响，不能据此宣称音频核心提速。44.1/48/96 kHz 的原始测量一并保留。

## 验证

- 穷举全部 16,777,216 个 24 位编码，与原 float 转换逐值相等；ASan/UBSan 覆盖最后一个采样的读取边界。
- A000 钢琴、F042 鼓组和 Concert 的离线测试 WAV 与基线逐字节相同；仅保存哈希，不提交音频资源。
- 7 项 CTest、6 项 ASan/UBSan、原生 Cocoa 交互测试通过；覆盖全部 1162 个入口、状态恢复、零音频线程分配及收藏添加／移除／重开。
- 主界面、ARP、FX 静态帧与本次修改前截图逐像素一致。菜单和收藏截图见 [current](verification/native-ui/current/)。这项对比针对本次优化，不能用于推断此前 Page 到原生的全部差异。
- 产品边界检查通过：隐藏研究目录、输出目录和工具后，可独立构建并通过 6 项声音核心测试。

仍保留全部采样常驻，所以内存不会降到只有界面资源的水平。本次没有引入磁盘流式播放。Windows 编译和打包二进制的验证记录见 [evidence.json](verification/native-ui/current/evidence.json)；Windows GUI、不同 DPI 和实际 DAW 长时演奏继续等待实机验收。

## 复测

```sh
KROSE_UI_BENCH=1 KROSE_UI_PROFILE=/tmp/krose-ui.json \
  build/plugin/test-vst3-host build/plugin/out/Krose.vst3 --editor-only
build/plugin/benchmark-piano build/plugin/generated/SEGrand.samples
```

第一条在窗口退出时输出 JSON，标准输出记录各阶段内存。请单独运行，避免同时编译或执行音频压力测试。`KROSE_UI_REFERENCE` 可导出实际 Metal 帧缓冲；`tools/native-ui/compare.py` 转换为 PNG。
