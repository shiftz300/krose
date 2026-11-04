# 插件内存对照与第二轮界面优化

2026-11-04。保留 Krose 的布局、材质、2× 纹理、动画曲线和 60 Hz 刷新。此次只处理图片解码临时内存、未使用字体资源和 LCD 绘制中的数据复制。

## 同一宿主测量其他插件

本机 macOS arm64；每个 VST3 在全新的 `benchmark-plugin-memory` 进程中加载。48 kHz／128 帧，先处理静音，再打开默认编辑器三秒，随后关闭。使用 `task_vm_info.phys_footprint`，单位为十进制 MB；下表包含约 11 MB 的空宿主开销。没有打开声卡、修改预设或保存用户工程。

| 插件及版本 | 初始化 | 开窗 | 关窗 | 逻辑界面尺寸 |
| --- | ---: | ---: | ---: | --- |
| Auburn Couture 1.10.0 | 11 | 96 | 88 | 626×487 |
| Auburn Lens 1.4.0 | 13 | 118 | 117 | 800×550 |
| Auburn Panagement 2.8.0 | 33 | 139 | 138 | 824×584 |
| Grand Piano 2.9.3 | 122 | 174 | 170 | 600×250 |
| Analog Lab V 5.12.4.6686 | 169 | 578 | 389 | 960×664 |
| Krose 修改前，Concert | 139 | 240 | 156 | 1472×648 |
| Krose 修改后，Concert | 139 | 221 | 160 | 1472×648 |

这是这些已安装版本的默认实例实测，不能视为整个产品的固定占用或行业平均值。效果器不需要同等规模的采样，窗口尺寸与渲染方式也不同。Analog Lab 会随载入的引擎和预设变化；大型采样音源还取决于预载、奏法和麦克风数量。

公开资料常给最低整机配置。例如 [Pianoteq 手册](https://www.modartt.com/user_manual?lang=en&product=pianoteq) 的 512 MB RAM 属于运行要求，不能当作其单实例实测。[Spitfire 的说明](https://support.spitfireaudio.com/en/articles/11815469-how-does-my-computer-hardware-affect-streaming-samples) 介绍了预载与流式采样；[Orchestral Tools](https://orchestraltools.helpscoutdocs.com/article/473-resource-usage-101) 则说明奏法、力度层和麦克风位置会影响内存。因此本次优先使用本机同宿主数据。

## Analog Lab 发声测试

另建默认实例，发送八个音符（48、55、60、64、67、72、76、79，力度 0.8），保持两秒、释放一秒。输出写入测试缓冲，不送往声卡。该次结果：

| 指标 | 实测 |
| --- | ---: |
| 初始化 | 176 MB |
| 开窗 | 600 MB |
| 演奏与尾音后 | 692 MB |
| 关窗后 | 376 MB |
| 128 帧处理耗时中位数 | 490 µs |
| P95 | 804 µs |
| 每块时间预算 | 2667 µs |

输出非零且全为有限值，峰值约 0.794。测试未识别具体预设名称，不外推到其他预设，也未做硬件输出、长时 DAW 演奏或听感验收。处理耗时只统计 `process()`，GUI 与等待时间在外；测试循环经事件泵节奏执行，不代表声卡回调调度的最坏情况。

## Krose 的实际改动

1. **图片解码缓冲**：通过 stb_image 官方提供的分配钩子，将 macOS 上至少 256 KiB 的解码缓冲放入独立匿名内存。上传纹理后直接归还系统，避免通用堆暂存大块 PNG 解码数据。解码算法、RGBA 像素和持久 GPU 纹理不变；固定版本的 iPlug2 源码没有改动。
2. **字体预载**：四张只在网页导出中使用的字体图集不再提前上传。当前原生页面、菜单和动画所需字体仍预载；其他字体保留按需加载入口。
3. **LCD 绘制**：状态行直接读取点阵数据，去掉逐字复制、删除首项等临时操作，使用同样的点阵坐标绘制。
4. **测量宿主**：补充 Cocoa 临时对象回收。Apple 的 [autorelease pool 文档](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/MemoryMgmt/Articles/mmAutoreleasePools.html) 说明正常事件循环会逐轮回收对象。旧测试循环会延长部分临时对象的存活期；这项测量修订不计作产品内存优化。

## 内存与动画回归

为衔接上一轮 278–341 MB 的结果，继续使用 Krose 专用状态恢复／GUI 回归宿主。新旧二进制均使用同一修正后的测试宿主，各运行三次取中位数。该宿主与上面的通用宿主有不同的初始化、状态恢复和窗口流程，不能交叉相减。

| 状态 | Concert 前 → 后 | A000 前 → 后 |
| --- | ---: | ---: |
| 打开完整界面 | 341.4 → **302.0 MB** | 278.5 → **238.2 MB** |
| 收放 FX 12 次后 | 368.5 → 347.7 MB | 287.3 → 283.8 MB |
| 关闭界面 | 178.6 → 159.7 MB | 97.2 → 95.9 MB |

开窗时减少约 39–40 MB。动画暖机后仍有图形缓冲和驱动缓存，内存降幅较小；没有声称这些缓存全部卸载。

| 动画指标 | Concert 前 → 后 | A000 前 → 后 |
| --- | ---: | ---: |
| 帧间隔中位数 | 16.663 → 16.663 ms | 16.648 → 16.640 ms |
| 帧间隔 P95 | 17.858 → 18.029 ms | 19.151 → 19.756 ms |
| Draw CPU 中位数 | 0.350 → 0.325 ms | 0.354 → 0.331 ms |

中位帧间隔保持约 60 Hz，P95 有亚毫秒波动。没有降低纹理分辨率、刷新率、抗锯齿或动画更新频率。十张原生帧缓冲图（主界面、ARP、FX、浏览器与下拉菜单等）与已接受版本逐 RGBA 像素一致。

图片分配器另有增长、缩小、跨堆／匿名内存转换、对齐和溢出失败保留旧缓冲的检查。构建与交付验证记录见 [evidence.json](verification/native-ui/current/evidence.json)，所有原始测量见 [memory-followup](verification/native-ui/memory-followup/)。

## 复测

```sh
cmake --build --preset plugin --target benchmark-plugin-memory
build/plugin/benchmark-plugin-memory '/Library/Audio/Plug-Ins/VST3/Analog Lab V.vst3'
KROSE_BENCH_PLAY=1 build/plugin/benchmark-plugin-memory '/Library/Audio/Plug-Ins/VST3/Analog Lab V.vst3'
KROSE_UI_BENCH=1 KROSE_UI_PROFILE=/tmp/krose-ui.json \
  build/plugin/test-vst3-host build/plugin/out/Krose.vst3 --editor-only
```

每条命令单独运行，避免并行编译或音频压力测试干扰结果。`benchmark-plugin-memory` 是 macOS 开发工具，不随插件加载。
