# CI 与安装包发行

## 0.4.1

- 插件公开厂商名统一为 `maincore`，Windows 安装器与 Ableton 参数配置目录同步更新；保留原有插件 ID 和安装包标识，旧工程继续使用同一插件。
- KeyLab Essential mk3 独立版与 Ableton 集成：音色／参数屏幕、RGB 灯、七个旋钮、包络推子及四键 FX 编辑入口；短按编辑，长按约 0.6 秒切换开关。
- AMP／FILTER 选择同步硬件目标和屏幕字段；新增可保存的 UI SIZE 控件及独立版 BUFFER 控件。
- 修复密集 MIDI 时间戳累积、推子重复拾取和 FX 鼠标交互；修正 B094 的 Chorus LFO／深度转换。
- Release 同时提供 Ableton 控制脚本 ZIP。安装器仍采用现有签名策略，升级与实物验证范围见 [控制器说明](CONTROLLERS.md)。

## 0.4.0

本版包含音色电平与播放边界修复、原厂 FX／ARP 配置随音色恢复、1,280 条用户琶音、扩展四槽效果、实时 ADSR 与 MIDI 显示，以及独立程序的 MIDI 自动选择与设备列表刷新。新增参数保留旧 ID，旧宿主状态与 `.krose` 文件可迁移。独立版自带资源，可以直接试音；剩余算法差异见 [完成度](STATUS.md)。

本地 Release、28 项产品回归、25 项打包工具检查通过；独立 ZIP 的解压启动、原生界面及 MIDI 映射／键盘／弯音／延音显示已验证。Windows 安装包与 macOS Universal 产物以本版本 CI 结果为准。

普通 push 和 Pull Request 进行 Windows x64、macOS Universal（Apple Silicon + Intel）编译检查，开启 Release 与 LTO。编译检查使用单独的占位采样目录并显式关闭 PGO；占位数据不用于训练。检查 Inno Setup 安装、旧 NSIS 记录迁移及卸载和 macOS PKG 结构，不上传占位成品。

真实安装包流程位于 `.github/workflows/release.yml`：v2 资源归档采用 XZ，直接保存原厂编码 Factory 库和 Concert 引用索引。CI 校验并提取后保留紧凑格式，后台按音色解码；安装时不展开整库 PCM。Windows 使用 clang-cl／lld-link，macOS arm64 与 x86_64 分别在对应原生 runner 上训练 PGO，并运行各自回归；macOS 两套 bundle 的资源及版本核对一致后合成 Universal。最终生成 Windows Inno Setup EXE、macOS Universal PKG，以及两平台的免安装独立版 ZIP。普通构建的真实安装包保留为 Actions artifact 14 天；推送 `v版本号` 标签时，两个平台均成功后自动创建 GitHub Release，附安装包和 SHA256SUMS.txt。标签须与 CMake、插件版本一致。


## 免安装独立版

macOS 分层应用图标为架构无关的预编译资源。只有修改图标时才手动运行 `.github/workflows/app-icon.yml`，将 artifact 中的 `Assets.car` 和 `manifest.json` 放回 `src/plugin/resources/macos-icon/` 并纳入版本控制。普通构建直接校验／复制，不调用图标编译器；Intel 与 Apple Silicon 使用同一份资源。首次预编译已生成并在本地 bundle 验证；没有预编译资源的检出会明确回退到静态 ICNS。

Actions 另提供 `Krose-windows-x64-standalone` 与 `Krose-macos-universal-standalone`，正式标签 Release 同时附上 ZIP。Windows 包包含 `Krose/Krose.exe` 和同目录的 `Resources`；macOS 包包含自带资源的 `Krose.app`。完整解压后即可运行，支持没有 DAW 的独立试音；保留 ZIP 内的资源布局。安装器仍同时提供 APP 与 VST3。

CI 在临时目录完整解压 ZIP，以 `--no-io --screenshot screenshot.png` 启动，检查原生界面截图，避免打开 CI 的音频／MIDI 设备；macOS 同时核对签名和 Universal 架构。便携版优先使用包内采样，不依赖已安装的共享资源。

本地打包：`python3 tools/release/package_standalone.py --input build/plugin/out --output dist --version 0.4.1 --platform macos-arm64 --smoke`。Windows 指定 `--platform windows-x64`；合并后的 macOS 产物指定 `macos-universal`。

## 首次接入完整资源

完整采样未纳入 Git。`packaging/runtime-assets.json` 固定资源包名称、草稿 Release 标签及 SHA-256。资源上传需明确授权；没有完整资源时，仅编译／安装结构 CI 可运行，不能发行可用音源。

授权后，在有完整资源的工作区执行（生成或更换归档后，需提交更新后的锁文件）：

```sh
python3 tools/release/runtime_assets.py pack /tmp/krose-runtime-v2.tar.xz
gh release create runtime-assets-v2 --draft --prerelease --title 'Frozen runtime assets v2' --notes 'Native encoded CI input banks'
gh release upload runtime-assets-v2 /tmp/krose-runtime-v2.tar.xz
gh variable set KROSE_RELEASE_ASSETS_READY --body true
```

资源包存于同仓库草稿 Release。读取草稿需要推送权限，因此真实安装包的 `build` job 单独授予 `GITHUB_TOKEN` 的 `contents: write`；工作流默认仍为只读，fork PR 不获取完整采样。更换资源时创建新的资源版本并更新锁文件，勿覆盖已经固定的旧包。

CI 从锁文件读取标签、文件名及 SHA-256。归档工具仍支持旧 PCM v1 包；新包不会添加三字节差分滤波。提取新包时，两份文件均通过冻结清单校验后才替换本地资源。

## 发布

标签触发编译、回归、打包与发布，无需单独上传安装包。重跑同一版本时，在全部构建成功后替换 Release 的同名文件并重新生成校验和。

先在普通分支确认完整安装包构建成功，再推送与代码版本一致的标签：

```sh
git tag -a v0.4.1 -m 'Krose 0.4.1'
git push origin v0.4.1
```

Windows Inno Setup 默认深色安装界面，默认安装独立程序到 `Program Files\Krose`、VST3 到 `Common Files\VST3\Krose.vst3`，支持组件选择、开始菜单、系统卸载及 `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART` 静默安装；采样共用 `Common Files\Krose\Samples\版本号`，卸载保留用户收藏。macOS PKG 安装到 `/Applications/Krose.app` 和 `/Library/Audio/Plug-Ins/VST3/Krose.vst3`，关闭 bundle 重定位，采样共用 `/Library/Application Support/Krose/Samples/版本号`。便携 bundle 优先使用内置采样，安装版也可用 `KROSE_SAMPLE_DIRECTORY` 指定自定义位置。

当前没有发行证书：macOS bundle 使用 ad-hoc 签名，PKG 未签名／公证，Windows EXE 未做 Authenticode 签名。Release 说明明确标注此状态。

## 编译优化

CMake Release 默认采用 Clang `-O3`／clang-cl `/O2`，并开启 `KROSE_ENABLE_IPO=ON` 和 `KROSE_ENABLE_PGO=ON`。编译器保持通用 CPU 指令集和严格浮点行为。

PGO 自动构建独立的带运行计数的核心与训练程序，使用当前冻结资源运行 36 组音色、采样率、块长、踏板、单音／连奏与 ARP 负载。`llvm-profdata` 合并计数后，生产核心使用该 profile 重新编译。训练程序、原始计数和 profile 均留在构建目录，不进入插件或安装包。源码、训练程序或运行采样变化后，构建依赖会重新训练；旧计数先清空，过期 profile 诊断按错误处理。

PGO 只用于 Release 核心。Debug 和 Sanitizer 不使用 PGO；Sanitizer 也关闭 LTO。可用 `-DKROSE_ENABLE_PGO=OFF` 回到普通优化构建。Windows 的 PGO 需要 clang-cl、lld-link、llvm-profdata 和 MSVC 开发环境；使用 MSVC cl 时应关闭 PGO。

macOS 各架构独立训练，直接配置 `arm64;x86_64` 时启用 PGO 会报错。CI 使用 `macos-15`（arm64）和 `macos-15-intel`（x86_64）生成原生 bundle，再调用 `tools/release/merge_macos.py` 合成 Universal，最后重新签名、校验。

复测：`cmake --preset plugin && cmake --build --preset plugin && ctest --preset plugin`。安装器保持系统原生布局和默认图案，不嵌入界面截图。Windows 编译器由 `packaging/inno-setup.json` 固定版本及 SHA256，`tools/release/package_windows.ps1` 构建；旧 NSIS 安装在同目录成功覆盖后才移除旧卸载记录，不运行会删除新文件的旧卸载器。macOS 使用标准 PKG 界面，外观跟随系统。

本机构建 PKG：`bash tools/release/package_macos.sh build/plugin 0.4.1`。

## 依赖警告与边界

依赖下载仍按原始哈希校验；CMake 在 `generated/dependencies` 生成修补后的编译副本，原始 iPlug2／SDK 不变。修补脚本按原始代码片段核对，版本变化不匹配时停止配置；补丁及冻结清单共同决定生成目录。

- CoreAudio 设备／采样率列表使用标准容器，核对字节长度，处理查询期间列表缩短。
- CoreMIDI 小消息使用 512 字节栈缓存；大 SysEx 按实际长度分配并明确分包，检查算术溢出及长度截断，保留原始时间戳。不额外限制正常长消息，不在音频渲染路径分配。
- SDK 的 GUID 格式参数匹配实际类型，浮点转整数排除正的 `2^63` 边界；变体显式清空字段。键名／字体复制限定目标长度，日志使用线程局部缓存与有界格式化。
- Windows 显式标注 COM override／默认分支；CI 官方 Actions 使用 Node 24 版本，VS 环境由本仓库 PowerShell 脚本导入。

SDK 的宿主验证工具仍使用 C++17 的 `codecvt` 转码实现；其标准库弃用提示保留，等待上游替换。没有关闭全局格式、数组、类型转换或边界警告。跨平台实际构建结果以当前提交的 CI 为准。

## 2026-11-09 CI 复核

检查仓库现有 76 次运行记录、全部 23 个失败任务的可读日志，以及安装包、原生编译、图标三套工作流最近一次成功日志。记录为 49 次成功、20 次失败、1 次取消、6 次跳过；历史失败记录保留。最新远端代码 `e7e70cd` 的 [安装包及发布](https://github.com/shiftz300/krose/actions/runs/42523922719) 和 [原生编译检查](https://github.com/shiftz300/krose/actions/runs/42523922629) 均成功。

| 历史失败 | 当前核对结果 |
| --- | --- |
| 编译占位资源的冻结哈希不一致 | 占位内容按字节写入并同步清单；最新编译检查通过 |
| MSVC 把 `/Wextra` 识别成非法参数 | 已按编译器选择 `/W4` 或 `-Wall -Wextra` |
| Xcode 产物位于 `out/Release`，PKG 脚本只查 `out` | 打包脚本兼容两种路径，最新 PKG 阶段通过 |
| 草稿采样资源不可见／未就绪 | 资源已就绪，构建 job 具有读取草稿所需权限；最新安装包构建通过 |
| Windows 引擎回归及 PGO 训练栈溢出 | 大引擎实例已转移到堆上；最新 Windows 训练及回归通过 |
| Windows 无设备截图启动崩溃 | 对未创建的 MIDI 端口判空，并仅在解压后的烟雾测试副本注入经校验的 Mesa DLL；正式 ZIP 不携带它们 |
| 独立版测试桩缺少 `mMidiOut`、Windows 宏与局部变量冲突 | 测试桩及变量命名已修，最新构建通过 |
| Windows 文件对话框的工作目录、Unicode 路径、覆盖确认及超时 | 对话框恢复工作目录，测试规范长路径并驱动自身确认框；最新 Windows 回归通过 |

一次早期 macOS 任务只有取消状态、没有步骤记录，日志接口返回 404，无法确认其原因；最新同平台任务已成功。六次跳过发生在完整资源尚未就绪阶段，一次后续推送替换了尚在运行的旧安装包任务。

本地补修尚未推送：原生 MSVC／Xcode 中另外发现的整数窄化、变量遮蔽及 Xcode `PRODUCT_BUNDLE_IDENTIFIER` 与 plist 不一致问题；旧插件 ID 保留。两个构建工作流改为单次 `unittest discover` 执行完整工具测试集，避免 PowerShell 只传播最后一条原生命令的退出码；安装与卸载也显式检查退出码。解包兼容 Python 3.9 的旧接口与新版 `data` 过滤接口，两条路径均先拒绝越界路径、链接及特殊文件。Actions 升级及这些更改仍需推送后的 Windows／Xcode CI 验证。

本机复测：Release + PGO／LTO 构建成功，31 项原生回归、56 项工具测试、47 项官方 VST3 验证通过；3 套工作流通过 actionlint。10 个相关编译单元按 Xcode 的 64 位到 32 位窄化诊断检查通过。编译日志仍保留两条宿主验证工具的上游 Unicode 转码弃用提示。
