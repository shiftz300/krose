# CI 与安装包发行

普通 push 和 Pull Request 构建 Windows x64、macOS Universal（Apple Silicon + Intel），开启 Release 与 LTO。编译检查使用单独的占位采样目录，验证 NSIS 安装／卸载和 macOS PKG 结构，不上传占位成品。

真实安装包流程位于 `.github/workflows/release.yml`：资源包采用三字节差分 + XZ 压缩，只保存 Factory 波形一次和 Concert 引用索引；CI 无损重建并逐包 SHA-256 校验后构建，macOS 运行引擎及 VST3 回归，再生成 Windows NSIS EXE 和 macOS PKG。普通构建的真实安装包保留为 Actions artifact 14 天；推送 `v版本号` 标签时，两个平台均成功后自动创建 GitHub Release，附安装包和 SHA256SUMS.txt。标签须与 CMake、插件版本一致。

## 首次接入完整资源

完整采样未纳入 Git。`packaging/runtime-assets.json` 固定资源包名称、草稿 Release 标签及 SHA-256。资源上传需明确授权；没有完整资源时，仅编译／安装结构 CI 可运行，不能发行可用音源。

授权后，在有完整资源的工作区执行：

```sh
python3 tools/release/runtime_assets.py pack /tmp/krose-runtime-v1.tar.xz
gh release create runtime-assets-v1 --draft --prerelease --title 'Frozen runtime assets v1' --notes 'CI input banks'
gh release upload runtime-assets-v1 /tmp/krose-runtime-v1.tar.xz
gh variable set KROSE_RELEASE_ASSETS_READY --body true
```

资源包存于同仓库草稿 Release，CI 通过当前仓库的 GITHUB_TOKEN 读取；fork PR 不获取完整采样。更换资源时创建新的资源版本并更新锁文件，勿覆盖已经固定的旧包。

## 发布

先在普通分支确认完整安装包构建成功，再推送与代码版本一致的标签：

```sh
git tag -a v0.1.0 -m 'Krose 0.1.0'
git push origin v0.1.0
```

Windows NSIS 默认安装独立程序到 `Program Files\Krose`、VST3 到 `Common Files\VST3\Krose.vst3`，支持组件选择、开始菜单、系统卸载及 `/S` 静默安装；采样共用 `Common Files\Krose\Samples\版本号`，卸载保留用户收藏。macOS PKG 安装到 `/Applications/Krose.app` 和 `/Library/Audio/Plug-Ins/VST3/Krose.vst3`，关闭 bundle 重定位，采样共用 `/Library/Application Support/Krose/Samples/版本号`。便携 bundle 优先使用内置采样，安装版也可用 `KROSE_SAMPLE_DIRECTORY` 指定自定义位置。

当前没有发行证书：macOS bundle 使用 ad-hoc 签名，PKG 未签名／公证，Windows EXE 未做 Authenticode 签名。Release 说明明确标注此状态。

## 编译优化

CMake Release 默认采用 Clang `-O3`／MSVC `/O2`，新增 `KROSE_ENABLE_IPO=ON` 对 Release 开启跨文件优化；工具链不支持时明确报错，可设置 OFF 回退。保留通用 CPU 指令集和严格浮点行为。Sanitizer 构建关闭 LTO，以便诊断。

复测：`cmake --preset plugin && cmake --build --preset plugin && ctest --preset plugin`。本机构建 PKG：`bash tools/release/package_macos.sh build/plugin 0.1.0`。
