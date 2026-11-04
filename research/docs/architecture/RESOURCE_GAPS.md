# 剩余资源复核

2026-11-04。此次检查限定在现有固件、三套扩展库及本地备份，未连接设备。

## 鼓组关联已确认

重新执行 `firmware_resource_import.py --verify-arm`，65 组分节用例、16 个鼓组放置起点和 64 组 Program 引用对照通过。原导入函数按文件顺序放置鼓组，随后按目标起点平移编号。Nu Pop 与 Nu DISCO 两份 Program 保存的 45 号引用始终保持共享，实际内容为第四套 Nu DISCO Kit。

此前插件把这一项列为“重映射待核对”，遗漏了已有的 [Program 引用重编号](PROGRAM_RELOCATION.md) 和 [原分节导入](RESOURCE_IMPORT.md) 后续结果。现已删除过时提示，保持原编号和共享关系。没有按名称重新分配鼓组。

## bank 6 继续缺失

现有三个扩展库的来源及解密数据指纹均已核对，分别提供逻辑银行 2、3、5。本地 KEP 原件中没有提供逻辑银行 6 的库。缺少采样载荷时，仅凭银行号和采样号无法恢复波形，因此本轮在此停止追查。

当前实际引用的 Electric Beats Kit 有四条缺失层：

| MIDI 键号 | 层（从 1 起） | 采样号 | 力度 |
| --- | --- | --- | --- |
| 45 | 2 | 7 | 1–127 |
| 83 | 1 | 34 | 1–127 |
| 96 | 1 | 17 | 85–127 |
| 96 | 2 | 16 | 1–84 |

这些引用继续保留为空，其他可用层正常播放。全扩展文件中十条启用层的旧统计包含未被当前 Program 引用的套件，详见 [扩展采样依赖](EXPANSION_PCM.md)。

## 复现

```sh
python3 research/tools/firmware_resource_import.py --verify-arm
python3 research/tools/audit_resource_gaps.py
```

第一步需要允许 Unicorn 使用本机 JIT，原指令在私有内存中执行。第二步核对工具、输入文件、三库指纹、四个鼓组关联和缺失层，输出 `research/derived/catalog/resource-gap-audit.json`。音频算法及完整调制链的实现进度继续由产品计划管理。
