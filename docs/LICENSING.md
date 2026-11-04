# 许可证与授权范围 / Licensing scope

Krose 的原创代码和原创文档采用 **Apache License 2.0**，SPDX 标识为 `Apache-2.0`。完整且未经修改的许可证见源码根目录 `LICENSE`，项目归属及资源边界摘要见 `NOTICE`。本说明界定项目实际授予的权利范围，不增加或修改 Apache-2.0 的条件。

## 原创内容

在项目贡献者有权授权的范围内，Apache-2.0 适用于以下内容的原创部分：

- `src/core/` 的引擎、声部、采样加载与解码、MIDI 和效果处理实现；下表列出的固件数据除外。
- `src/plugin/` 的插件、参数和原生界面实现；第三方模板、原厂及第三方素材除外。
- `cmake/`、`tools/`、`packaging/`、`.github/` 中的原创构建、导出、校验和打包代码。
- `tests/` 中的原创测试代码，以及 README 和 `docs/` 中的原创说明、图示；测试夹具、引用内容和第三方素材除外。

允许商业使用、修改和再分发，具体条件以 `LICENSE` 为准。源文件不必逐一带有许可证头才能属于上述范围。路径只是定位依据：第三方或原厂内容即使嵌入源码、改名或移动，也不会因此被重新授权。原创导出工具的许可证不自动适用于其读取或输出的数据。

## 原厂资源与派生数据

以下原厂内容及其派生表示**不在项目 Apache-2.0 授权范围内**。Krose 不代原权利人授予复制、再授权或再分发权；使用及分发须有独立的适用授权或法律依据。

| 路径或内容 | 范围及来源证据 |
| --- | --- |
| `assets/program-library/` | `Factory.samples` 中的原厂、GM、扩展采样及编码数据；`FactoryPrograms.h`、`FactoryPrograms.json`、`FactoryBrowser.json` 中的原始 Program 参数、名称、分类、顺序和区域映射。`manifest.json` 记录 Editor、固件、扩展包的来源及哈希。GM 类别或标准编号不表示具体采样可自由分发。 |
| `assets/concert-se-grand/` | `SEGrand.samples` 的采样引用、`ConcertEqData.h`、`NativeVoiceData.h` 中的原参数、EQ／包络／增益等数据。来源见 `manifest.json`、`assets.json`、`voice-assets.json`。 |
| `src/core/midi/PerformanceData.h` | 从 v1.2.4 固件地址 `0x3FD380` 得到的 `kPortamentoCoefficients` 表；外围原创代码不因引用该表而被排除。 |
| `src/core/voice/ModulationData.h` | 从 v1.2.4 固件提取的 LFO 波形、速率、相位、淡入和 Mixer 平滑等表；文件注明原镜像偏移及哈希。外围独立实现仍按原创代码处理。 |
| `tests/fixtures/` | Concert、全 Program、琶音及演奏控制的原固件观察值、轨迹和导出表。各子目录 `manifest.json` 记录来源；作为测试证据不代表取得了数据再授权。 |
| `src/plugin/editor/native/assets/lcd-resources.json` | 明确注明来自 `KROSS2 v1.2.4 KROSSAPP.bin` 的 LCD 字形、分类图标等数据，以及来自实机参考的像素素材。 |
| `src/plugin/editor/native/assets/` 的 PNG、`native-data.json` 等冻结素材 | 包含 LCD 字形／图标、原厂目录及字体栅格等混合来源内容。当前不对整套素材作统一 Apache-2.0 授权；原创绘制代码仍按上文授权。`files.json` 提供文件校验信息，不能充当授权凭证。 |
| `tools/native-ui/reference/font.css`、`tools/native-ui/reference/panel.js` | 内嵌 LCD 字体、`lcdResources` 字形／图标及原厂音色数据不在授权内；原创 CSS／JavaScript 逻辑仍适用 Apache-2.0。 |
| 本地或外部研究资料及生成物 | 原固件、ROM、Editor／扩展包、解码音频、归档、`build/` 中生成的头文件和嵌入资源，以及 app／VST3 内复制的数据，沿用各自来源边界。关联的 `krose-source` 仓库须另查其声明，不因链接而获得本项目授权。 |

来源记录和哈希用于追溯，不是权利证明。上述排除也不主张事实、数值、通用算法或公有领域内容必然受排他权保护。独立编写的实现与直接提取、复制的内容应分别判断；仅转换格式、重新编码或压缩不会自动产生原厂内容的再授权权利。

KORG 的 Editor 下载页含其自身的许可协议：<https://www.korg.com/us/support/download/software/0/754/3834/>。不同固件、ROM、扩展音色及字体须分别核对适用来源和条款；这里不作统一可分发结论。KORG／KROSS 等第三方商标亦不在本项目授权内，项目不表示获得其背书。

## 第三方代码、字体与模板

这些内容继续使用上游许可证。版本固定信息见 `cmake/dependencies.json`，已收集的声明见 `licenses/THIRD_PARTY.txt`；单个上游文件中的条款和归属仍须保留。

| 组件 | 源码或使用位置 | 上游条款 |
| --- | --- | --- |
| iPlug2 | `build/deps/iPlug2/`；插件和 IGraphics 框架 | zlib 类许可证；固定版本 `d82b2e99b17c8f723d3f6e2a88ffd8b656f28e5d`。 |
| iPlug2 模板的本地改编 | `src/plugin/resources/` 中源自 IPlugEffect 的 `resource.h`、菜单及对话框资源 | 上游部分继续适用 iPlug2 条款；这些文件已经本地修改，不是未经修改的上游模板。 |
| iPlug2 独立程序后端的构建期改编 | `cmake/StandaloneHost.cmake` 在构建目录生成的 APP 源码副本 | 生成副本中上游代码继续适用 iPlug2 条款并保留原声明；本地修改已明确标记。项目原创适配工具及 `src/plugin/standalone/` 辅助代码按 Apache-2.0 授权。 |
| Cockos WDL／SWELL、NanoVG、NanoSVG、Fontstash | iPlug2 内附框架及图形组件 | zlib 类许可证；具体文件声明优先。 |
| MetalNanoVG、RtAudio、RtMidi、nlohmann/json | iPlug2 内附 Metal、音频／MIDI 与 JSON 组件；JSON 位于 `Dependencies/Extras/nlohmann/` | MIT；保留各自版权及许可文本。 |
| stb_image、stb_truetype | iPlug2 内附图像和字体组件 | 以固定版本文件内的公有领域声明／许可文本为准。 |
| Steinberg VST3 SDK 3.8.0 | `build/deps/vst3sdk/` 及 iPlug2 的 SDK 链接 | MIT；固定标签 `v3.8.0_build_66`，各子模块保留原声明。 |
| Roboto Regular | iPlug2 `Examples/IPlugEffect/resources/fonts/Roboto-Regular.ttf`，构建时复制到资源中 | Apache-2.0；版权归 Google，全文见 `licenses/Roboto-Apache-2.0.txt`，不改记为 Krose 原创字体。 |
| 系统字体及其栅格输出 | `tools/native-ui/complete_assets.py` 使用 Arial、Menlo、系统回退字体；对应 `font-*.png` 图集 | 不由 Krose 重新授权，按实际字体来源核对；不能用 Roboto 的许可证覆盖这些图集。 |

第三方清单针对当前固定构建，不能视为未来启用的可选组件已获审查。Python、Pillow、CMake、编译器等开发工具本身也不因此被重新授权；若另行打包这些工具，需要保留其各自条款。

## 交付时的说明

源码副本应保留 `LICENSE`、`NOTICE`、本说明及相关第三方声明。当前构建将这些文件放入 app／VST3 的资源目录，便携打包也会附带副本。安装包沿用 bundle 或 Windows `Resources` 中的声明。

原厂资源是否进入 Git、是否免费发布、是否仅供个人研究，与是否取得其再分发权是不同问题。随二进制交付声明、把资源移到独立归档或添加免责声明，都不替代资源授权。

## English summary

Original Krose code and documentation are licensed under Apache-2.0 only to
the extent the contributors have authority to license them. Third-party code,
adapted iPlug2 templates and fonts retain their upstream terms. Manufacturer
firmware/ROM content, samples, Program data, extracted tables, LCD glyphs/icons,
test fixture data and their embedded or generated representations are excluded
from the project's grant. The path tables above identify current locations,
including mixed-content source files and font atlases. Original implementation
code remains covered even when it reads excluded data. Neither provenance nor
format conversion establishes redistribution permission. No exclusive rights
are asserted over facts or public-domain data. Preserve LICENSE, NOTICE, this
scope document and applicable upstream notices when distributing covered work;
obtain an independent basis for distributing excluded resources. This document
does not alter Apache-2.0 or any upstream license.
